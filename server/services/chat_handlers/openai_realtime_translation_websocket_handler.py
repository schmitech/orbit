"""
OpenAI Realtime Translation WebSocket bridge.

Proxies ORBIT voice clients (same JSON protocol as real-time-voice-chat) to
OpenAI's Realtime Translation WebSocket API (speech-to-speech translation). See:
https://developers.openai.com/api/docs/guides/realtime-translation

Unlike the speech-to-speech chat bridge, the translation endpoint is a stateless
interpreter: no instructions, no VAD/turn detection, no response lifecycle. Audio
is streamed continuously and translated speech/text streams back until the client
disconnects (at which point we send `session.close`).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect
from services.chat_handlers.openai_realtime_websocket_handler import _resolve_openai_api_key
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)

try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore


REALTIME_TRANSLATION_WS_URL = "wss://api.openai.com/v1/realtime/translations"

DEFAULT_TARGET_LANGUAGE = "es"


class OpenAIRealtimeTranslationWebSocketHandler:
    """
    Bridges ORBIT /ws/voice clients to OpenAI Realtime Translation.

    Client protocol (unchanged):
    - {"type": "audio_chunk", "data": "<base64>", "format": "pcm"|"wav"} — PCM16 LE mono 24kHz
    - {"type": "interrupt"}  (no-op for translation)
    - {"type": "ping"}

    Server → client:
    - {"type": "connected", ...}
    - {"type": "audio_chunk", "data": "<base64>", "format": "pcm", "sample_rate": 24000, ...}
    - {"type": "transcription", "text": "..."} — source speech (input transcript delta)
    - {"type": "assistant_transcript_delta", "delta": "..."} — translated text delta
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
        target_language: Optional[str] = None,
    ):
        self.websocket = websocket
        self.adapter_name = adapter_name
        self.adapter_config = adapter_config
        self.config = config
        self.orbit_session_id = session_id or str(uuid.uuid4())
        self.user_id = user_id

        cfg = adapter_config.get("config") or {}
        self._realtime_model = cfg.get("realtime_model", "gpt-realtime-translate")
        self._connection_timeout = float(cfg.get("openai_connection_timeout_seconds", 60))
        # Effective target language: query param > adapter config > default.
        self._target_language = (
            (target_language or "").strip()
            or (cfg.get("target_language") or "").strip()
            or DEFAULT_TARGET_LANGUAGE
        )

        self.is_connected = False
        self._http_session: Optional["aiohttp.ClientSession"] = None
        self._openai_ws: Optional["aiohttp.ClientWebSocketResponse"] = None
        self._client_task: Optional[asyncio.Task] = None
        self._openai_task: Optional[asyncio.Task] = None
        self._chunk_index = 0

    def _build_session_update(self) -> Dict[str, Any]:
        return {
            "type": "session.update",
            "session": {
                "audio": {
                    "output": {
                        "language": self._target_language,
                    },
                },
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

        url = f"{REALTIME_TRANSLATION_WS_URL}?model={self._realtime_model}"
        headers = {"Authorization": f"Bearer {api_key}"}

        timeout = aiohttp.ClientTimeout(total=self._connection_timeout)
        self._http_session = aiohttp.ClientSession(timeout=timeout)

        try:
            self._openai_ws = await self._http_session.ws_connect(url, headers=headers)
        except Exception as e:
            logger.error("OpenAI Realtime Translation connect failed: %s", e, exc_info=True)
            await self._send_client(
                {"type": "error", "message": f"OpenAI Realtime Translation connection failed: {e}"}
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
            elif mtype == "set_target_language":
                # Switch the target language live, without reconnecting.
                lang = (message.get("language") or "").strip()
                if lang and lang != self._target_language:
                    self._target_language = lang
                    await self._openai_ws.send_str(json.dumps(self._build_session_update()))
                    await self._send_client(
                        {"type": "target_language_updated", "target_language": lang}
                    )
            elif mtype == "interrupt":
                # Translation has no response lifecycle to cancel; acknowledge only.
                await self._send_client({"type": "interrupted", "reason": "user_request"})
            elif mtype == "audio_chunk":
                b64 = message.get("data")
                if not b64:
                    continue
                await self._openai_ws.send_str(
                    json.dumps({"type": "session.input_audio_buffer.append", "audio": b64})
                )
            else:
                logger.debug("Unknown client message type: %s", mtype)

    async def _map_openai_event(self, event: Dict[str, Any]) -> None:
        etype = event.get("type")
        if etype == "session.output_audio.delta":
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
        elif etype == "session.output_transcript.delta":
            d = event.get("delta")
            if d:
                await self._send_client({"type": "assistant_transcript_delta", "delta": d})
        elif etype == "session.input_transcript.delta":
            d = event.get("delta")
            if d:
                await self._send_client({"type": "transcription", "text": d})
        elif etype == "session.closed":
            logger.debug("OpenAI Realtime Translation: session.closed")
            await self._send_client({"type": "done", "session_id": self.orbit_session_id})
            self._chunk_index = 0
        elif etype == "error":
            err = event.get("error") or {}
            msg = err.get("message") if isinstance(err, dict) else str(err)
            await self._send_client({"type": "error", "message": msg or "OpenAI Realtime error"})
        elif etype in ("session.created", "session.updated"):
            logger.debug("OpenAI Realtime Translation: %s", etype)

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
                "mode": "openai_realtime_translation",
                "realtime_model": self._realtime_model,
                "target_language": self._target_language,
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
            # Best-effort graceful close so OpenAI flushes any remaining translation.
            try:
                await self._openai_ws.send_str(json.dumps({"type": "session.close"}))
            except Exception as e:
                logger.debug("Error sending session.close: %s", e)
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

        logger.debug(
            "OpenAI Realtime Translation handler cleanup complete (adapter=%s)", self.adapter_name
        )
