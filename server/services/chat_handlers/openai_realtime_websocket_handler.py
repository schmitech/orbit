"""
OpenAI Realtime API WebSocket bridge.

Proxies ORBIT voice clients (same JSON protocol as real-time-voice-chat) to
OpenAI's Realtime WebSocket API (speech-to-speech). See:
https://developers.openai.com/api/docs/guides/realtime
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import uuid
from typing import Any, Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)

try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore


REALTIME_WS_URL = "wss://api.openai.com/v1/realtime"


def _resolve_openai_api_key(config: Dict[str, Any]) -> Optional[str]:
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    inf = config.get("inference") or {}
    oa = inf.get("openai") or {}
    raw = oa.get("api_key")
    if isinstance(raw, str) and raw.startswith("${") and raw.endswith("}"):
        return os.environ.get(raw[2:-1])
    if raw:
        return str(raw)
    return None


class OpenAIRealtimeWebSocketHandler:
    """
    Bridges ORBIT /ws/voice clients to OpenAI Realtime (GA WebSocket).

    Client protocol (unchanged):
    - {"type": "audio_chunk", "data": "<base64>", "format": "pcm"|"wav"} — PCM16 LE mono 24kHz
    - {"type": "interrupt"}
    - {"type": "ping"}

    Server → client:
    - {"type": "connected", ...}
    - {"type": "audio_chunk", "data": "<base64>", "format": "pcm", "sample_rate": 24000, ...}
    - {"type": "transcription", "text": "..."} — user input (ASR), when enabled
    - {"type": "assistant_transcript_delta", "delta": "..."} — model speech transcript
    - {"type": "done", "session_id": "..."}
    - {"type": "error", "message": "..."}
    """

    def __init__(
        self,
        websocket: WebSocket,
        adapter_name: str,
        adapter_config: Dict[str, Any],
        config: Dict[str, Any],
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        self.websocket = websocket
        self.adapter_name = adapter_name
        self.adapter_config = adapter_config
        self.config = config
        self.orbit_session_id = session_id or str(uuid.uuid4())
        self.user_id = user_id

        cfg = adapter_config.get("config") or {}
        self._realtime_model = cfg.get("realtime_model", "gpt-realtime")
        self._voice = cfg.get("realtime_voice", "marin")
        self._instructions = cfg.get(
            "realtime_instructions",
            "You are a helpful voice assistant. Keep replies concise for voice.",
        )
        self._enable_input_transcription = cfg.get("enable_input_transcription", True)
        self._transcription_model = cfg.get("input_transcription_model", "whisper-1")
        self._vad_silence_ms = int(cfg.get("vad_silence_duration_ms", 500))
        self._vad_prefix_ms = int(cfg.get("vad_prefix_padding_ms", 300))
        self._vad_threshold = float(cfg.get("vad_threshold", 0.5))
        self._connection_timeout = float(cfg.get("openai_connection_timeout_seconds", 60))
        self._use_beta_header = bool(cfg.get("use_realtime_beta_header", False))
        # False avoids cancelling the model mid-reply when the mic picks up room noise / overlap.
        self._interrupt_response = bool(cfg.get("realtime_interrupt_response", False))

        self.is_connected = False
        self._http_session: Optional["aiohttp.ClientSession"] = None
        self._openai_ws: Optional["aiohttp.ClientWebSocketResponse"] = None
        self._client_task: Optional[asyncio.Task] = None
        self._openai_task: Optional[asyncio.Task] = None
        self._chunk_index = 0

    def _build_session_update(self) -> Dict[str, Any]:
        pcm_format = {"type": "audio/pcm", "rate": 24000}
        audio: Dict[str, Any] = {
            "input": {
                "format": pcm_format,
                "turn_detection": {
                    "type": "server_vad",
                    "create_response": True,
                    "interrupt_response": self._interrupt_response,
                    "prefix_padding_ms": self._vad_prefix_ms,
                    "silence_duration_ms": self._vad_silence_ms,
                    "threshold": self._vad_threshold,
                },
            },
            "output": {
                "format": pcm_format,
                "voice": self._voice,
            },
        }
        if self._enable_input_transcription:
            audio["input"]["transcription"] = {"model": self._transcription_model}

        return {
            "type": "session.update",
            "session": {
                "type": "realtime",
                "model": self._realtime_model,
                "instructions": self._instructions,
                "audio": audio,
            },
        }

    async def _send_client(self, message: Dict[str, Any]) -> None:
        if self.websocket.client_state != WebSocketState.CONNECTED:
            self.is_connected = False
            return
        try:
            await self.websocket.send_text(json.dumps(message))
        except WebSocketDisconnect:
            self.is_connected = False
        except RuntimeError as e:
            if "WebSocket is not connected" in str(e):
                self.is_connected = False
            else:
                logger.error("WebSocket send failed: %s", e)
                self.is_connected = False
        except Exception as e:  # pragma: no cover
            logger.error("WebSocket send failed: %s", e)
            self.is_connected = False

    async def _connect_openai(self) -> bool:
        if aiohttp is None:
            await self._send_client(
                {"type": "error", "message": "aiohttp is required for OpenAI Realtime bridge"}
            )
            return False

        api_key = _resolve_openai_api_key(self.config)
        if not api_key:
            await self._send_client(
                {
                    "type": "error",
                    "message": "OPENAI_API_KEY is not set (or inference.openai.api_key)",
                }
            )
            return False

        url = f"{REALTIME_WS_URL}?model={self._realtime_model}"
        headers = {"Authorization": f"Bearer {api_key}"}
        if self._use_beta_header:
            headers["OpenAI-Beta"] = "realtime=v1"

        timeout = aiohttp.ClientTimeout(total=self._connection_timeout)
        self._http_session = aiohttp.ClientSession(timeout=timeout)

        try:
            self._openai_ws = await self._http_session.ws_connect(url, headers=headers)
        except Exception as e:
            logger.error("OpenAI Realtime connect failed: %s", e, exc_info=True)
            await self._send_client(
                {"type": "error", "message": f"OpenAI Realtime connection failed: {e}"}
            )
            await self._http_session.close()
            self._http_session = None
            return False

        await self._openai_ws.send_str(json.dumps(self._build_session_update()))
        return True

    async def _client_loop(self) -> None:
        assert self._openai_ws is not None
        while self.is_connected:
            try:
                data = await self.websocket.receive_text()
            except WebSocketDisconnect:
                self.is_connected = False
                break
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await self._send_client({"type": "error", "message": "Invalid JSON"})
                continue

            mtype = message.get("type")
            if mtype == "ping":
                await self._send_client({"type": "pong"})
            elif mtype == "interrupt":
                await self._openai_ws.send_str(json.dumps({"type": "response.cancel"}))
                await self._send_client({"type": "interrupted", "reason": "user_request"})
            elif mtype == "audio_chunk":
                b64 = message.get("data")
                if not b64:
                    continue
                await self._openai_ws.send_str(
                    json.dumps({"type": "input_audio_buffer.append", "audio": b64})
                )
            else:
                logger.debug("Unknown client message type: %s", mtype)

    async def _map_openai_event(self, event: Dict[str, Any]) -> None:
        etype = event.get("type")
        if etype == "response.output_audio.delta":
            delta = event.get("delta")
            if delta:
                await self._send_client(
                    {
                        "type": "audio_chunk",
                        "data": delta,
                        "format": "pcm",
                        "sample_rate": 24000,
                        "chunk_index": self._chunk_index,
                    }
                )
                self._chunk_index += 1
        elif etype == "response.output_audio.done":
            pass
        elif etype == "response.output_audio_transcript.delta":
            d = event.get("delta")
            if d:
                await self._send_client({"type": "assistant_transcript_delta", "delta": d})
        elif etype == "conversation.item.input_audio_transcription.completed":
            text = event.get("transcript")
            if text:
                await self._send_client({"type": "transcription", "text": text})
        elif etype == "response.done":
            await self._send_client(
                {"type": "done", "session_id": self.orbit_session_id}
            )
            self._chunk_index = 0
        elif etype == "error":
            err = event.get("error") or {}
            msg = err.get("message") if isinstance(err, dict) else str(err)
            await self._send_client({"type": "error", "message": msg or "OpenAI Realtime error"})
        elif etype in ("session.created", "session.updated", "input_audio_buffer.speech_started"):
            logger.debug("OpenAI Realtime: %s", etype)
        elif etype == "input_audio_buffer.speech_stopped":
            logger.debug("OpenAI Realtime: speech_stopped")

    async def _openai_loop(self) -> None:
        assert self._openai_ws is not None
        ws = self._openai_ws
        try:
            while True:
                msg = await ws.receive()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        event = json.loads(msg.data)
                    except json.JSONDecodeError:
                        logger.warning("Invalid JSON from OpenAI: %s", str(msg.data)[:200])
                        continue
                    await self._map_openai_event(event)
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    logger.debug("Ignoring binary frame from OpenAI")
                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                    break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error("OpenAI WS error: %s", ws.exception())
                    break
        except Exception as e:
            logger.error("OpenAI receive loop error: %s", e, exc_info=True)
            await self._send_client({"type": "error", "message": str(e)})
        finally:
            self.is_connected = False

    async def run(self) -> None:
        if aiohttp is None:
            await self.websocket.accept()
            await self._send_client(
                {"type": "error", "message": "aiohttp is required for OpenAI Realtime bridge"}
            )
            return

        await self.websocket.accept()
        self.is_connected = True

        if not await self._connect_openai():
            self.is_connected = False
            return

        await self._send_client(
            {
                "type": "connected",
                "adapter": self.adapter_name,
                "session_id": self.orbit_session_id,
                "audio_format": "pcm",
                "sample_rate": 24000,
                "mode": "openai_realtime",
                "realtime_model": self._realtime_model,
            }
        )

        self._client_task = asyncio.create_task(self._client_loop())
        self._openai_task = asyncio.create_task(self._openai_loop())

        done, pending = await asyncio.wait(
            [self._client_task, self._openai_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        for t in done:
            if t.cancelled():
                continue
            exc = t.exception()
            if exc:
                logger.error("Task ended with error: %s", exc)

    async def cleanup(self) -> None:
        self.is_connected = False

        if self._openai_ws and not self._openai_ws.closed:
            try:
                await self._openai_ws.close()
            except Exception as e:
                logger.debug("Error closing OpenAI ws: %s", e)
        self._openai_ws = None

        if self._http_session and not self._http_session.closed:
            try:
                await self._http_session.close()
            except Exception as e:
                logger.debug("Error closing aiohttp session: %s", e)
        self._http_session = None

        logger.info("OpenAI Realtime handler cleanup complete (adapter=%s)", self.adapter_name)
