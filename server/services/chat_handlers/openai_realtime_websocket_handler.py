"""
OpenAI Realtime API WebSocket bridge.

Proxies ORBIT voice clients (same JSON protocol as real-time-voice-chat) to
OpenAI's Realtime WebSocket API (speech-to-speech). See:
https://developers.openai.com/api/docs/guides/realtime
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional

from fastapi import WebSocket, WebSocketDisconnect
from services.chat_handlers.base_realtime_websocket_handler import BaseRealtimeWebSocketHandler
from services.chat_handlers.realtime_grounding import (
    build_tool_schema,
    execute_grounding_lookup,
)

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


class OpenAIRealtimeWebSocketHandler(BaseRealtimeWebSocketHandler):
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

    provider_label = "OpenAI Realtime"

    def __init__(
        self,
        websocket: WebSocket,
        adapter_name: str,
        adapter_config: Dict[str, Any],
        config: Dict[str, Any],
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        prompt_service: Optional[Any] = None,
        system_prompt_id: Optional[str] = None,
        clock_service: Optional[Any] = None,
        adapter_manager: Optional[Any] = None,
        api_key: Optional[str] = None,
        chat_history_service: Optional[Any] = None,
    ):
        super().__init__(
            websocket=websocket,
            adapter_name=adapter_name,
            adapter_config=adapter_config,
            config=config,
            session_id=session_id,
            user_id=user_id,
            prompt_service=prompt_service,
            system_prompt_id=system_prompt_id,
            clock_service=clock_service,
            adapter_manager=adapter_manager,
            api_key=api_key,
            chat_history_service=chat_history_service,
        )
        self._assistant_transcript_prefixes: Dict[str, str] = {}

        cfg = adapter_config.get("config") or {}
        self._realtime_model = cfg.get("realtime_model", "gpt-realtime")
        self._voice = cfg.get("realtime_voice", "marin")
        self._enable_input_transcription = cfg.get("enable_input_transcription", True)
        self._transcription_model = cfg.get("input_transcription_model", "whisper-1")
        self._vad_silence_ms = int(cfg.get("vad_silence_duration_ms", 500))
        self._vad_prefix_ms = int(cfg.get("vad_prefix_padding_ms", 300))
        self._vad_threshold = float(cfg.get("vad_threshold", 0.5))
        self._connection_timeout = float(cfg.get("openai_connection_timeout_seconds", 60))
        self._use_beta_header = bool(cfg.get("use_realtime_beta_header", False))
        # False avoids cancelling the model mid-reply when the mic picks up room noise / overlap.
        self._interrupt_response = bool(cfg.get("realtime_interrupt_response", False))

        self._http_session: Optional["aiohttp.ClientSession"] = None
        self._openai_ws: Optional["aiohttp.ClientWebSocketResponse"] = None
        self._openai_task: Optional[asyncio.Task] = None
        self._chunk_index = 0
        self._grounding_response_pending = False

    async def _build_session_update(self) -> Dict[str, Any]:
        pcm_format = {"type": "audio/pcm", "rate": 24000}
        instructions = await self._resolve_realtime_instructions()
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

        session: Dict[str, Any] = {
            "type": "realtime",
            "model": self._realtime_model,
            "instructions": instructions,
            "audio": audio,
        }
        if self._grounding:
            session["tools"] = [build_tool_schema(self._grounding)]
            session["tool_choice"] = "auto"

        return {
            "type": "session.update",
            "session": session,
        }

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

        await self._openai_ws.send_str(json.dumps(await self._build_session_update()))
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
                self._discard_pending_turn()
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
        elif etype in (
            "response.output_audio_transcript.delta",
            "response.audio_transcript.delta",
        ):
            d = event.get("delta")
            if isinstance(d, str) and d:
                self._pending_assistant_text += d
                key = self._transcript_key(event)
                self._assistant_transcript_prefixes[key] = self._assistant_transcript_prefixes.get(key, "") + d
                await self._send_client({"type": "assistant_transcript_delta", "delta": d})
        elif etype in (
            "response.output_audio_transcript.done",
            "response.audio_transcript.done",
        ):
            await self._send_missing_transcript_suffix(event)
        elif etype == "conversation.item.input_audio_transcription.completed":
            text = event.get("transcript")
            if text:
                self._pending_user_message = text
                await self._send_client({"type": "transcription", "text": text})
        elif etype == "response.done":
            response_obj = event.get("response") or {}
            outputs = response_obj.get("output") or []
            # A response containing only a function_call (no message/audio) is the
            # tool-call turn itself — the real spoken answer arrives in the *next*
            # response we trigger via response.create, so don't signal "done" yet.
            is_tool_call_only = bool(outputs) and all(
                item.get("type") == "function_call" for item in outputs
            )
            if is_tool_call_only:
                logger.debug("OpenAI Realtime: response.done (tool-call turn, suppressing client done)")
                if self._grounding_response_pending:
                    self._grounding_response_pending = False
                    assert self._openai_ws is not None
                    # OpenAI does not allow response.create while the
                    # function-call response is still active. The function
                    # output is already in the conversation; now that this
                    # response is done, request the spoken follow-up.
                    await self._openai_ws.send_str(json.dumps({"type": "response.create"}))
            else:
                logger.debug("OpenAI Realtime: response.done")
                user_message_id, assistant_message_id = await self._persist_turn()
                await self._send_client(
                    {
                        "type": "done",
                        "session_id": self.orbit_session_id,
                        "user_message_id": user_message_id,
                        "assistant_message_id": assistant_message_id,
                    }
                )
                self._chunk_index = 0
                self._assistant_transcript_prefixes.clear()
        elif etype == "error":
            err = event.get("error") or {}
            msg = err.get("message") if isinstance(err, dict) else str(err)
            await self._send_client({"type": "error", "message": msg or "OpenAI Realtime error"})
        elif etype in ("session.created", "session.updated", "input_audio_buffer.speech_started"):
            logger.debug("OpenAI Realtime: %s", etype)
        elif etype == "input_audio_buffer.speech_stopped":
            logger.debug("OpenAI Realtime: input_audio_buffer.speech_stopped")
        elif etype == "response.function_call_arguments.done":
            await self._handle_function_call(event)

    @staticmethod
    def _transcript_key(event: Dict[str, Any]) -> str:
        return ":".join(str(event.get(key, "")) for key in ("response_id", "item_id", "output_index", "content_index"))

    async def _send_missing_transcript_suffix(self, event: Dict[str, Any]) -> None:
        """Forward any final transcript portion that did not arrive as a delta."""
        transcript = event.get("transcript")
        key = self._transcript_key(event)
        prefix = self._assistant_transcript_prefixes.pop(key, "")
        if not isinstance(transcript, str) or not transcript:
            return
        if transcript.startswith(prefix):
            suffix = transcript[len(prefix):]
        else:
            logger.warning("OpenAI Realtime final transcript did not extend streamed prefix")
            suffix = transcript
        if suffix:
            self._pending_assistant_text += suffix
            await self._send_client({"type": "assistant_transcript_delta", "delta": suffix})

    def _discard_pending_turn(self) -> None:
        super()._discard_pending_turn()
        self._assistant_transcript_prefixes.clear()

    async def _handle_function_call(self, event: Dict[str, Any]) -> None:
        if not self._grounding:
            return
        call_id = event.get("call_id")
        name = event.get("name")
        if name and name != self._grounding.tool_name:
            logger.debug("Ignoring unknown realtime tool call: %s", name)
            return
        try:
            arguments = json.loads(event.get("arguments") or "{}")
        except json.JSONDecodeError:
            arguments = {}
        query = arguments.get("query", "")
        logger.debug(
            "OpenAI Realtime: _handle_function_call invoking grounding_adapter='%s' query=%r",
            self._grounding.adapter_name, query,
        )

        result_text = await execute_grounding_lookup(
            self.adapter_manager, self._grounding, query, api_key=self.api_key
        )
        logger.debug(
            "OpenAI Realtime: grounding lookup result (%d chars): %r",
            len(result_text), result_text,
        )

        assert self._openai_ws is not None
        await self._openai_ws.send_str(
            json.dumps(
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": result_text,
                    },
                }
            )
        )
        # response.function_call_arguments.done precedes response.done. Wait
        # for the tool-only response to close before requesting the spoken
        # follow-up, otherwise OpenAI rejects response.create as concurrent.
        self._grounding_response_pending = True

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

        await self._run_until_either(self._client_task, self._openai_task)

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
