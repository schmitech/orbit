"""
Gemini Live API WebSocket bridge.

Proxies ORBIT voice clients (same JSON protocol as openai_realtime) to
Google's Gemini Live API (speech-to-speech) via the google-genai SDK. See:
https://ai.google.dev/gemini-api/docs/live-api
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import uuid
from typing import Any, Dict, Optional, Tuple

import numpy as np
from fastapi import WebSocket, WebSocketDisconnect
from inference.pipeline.base import ProcessingContext
from inference.pipeline.prompt_builder import PromptInstructionBuilder
from services.chat_handlers.realtime_grounding import (
    build_tool_schema,
    execute_grounding_lookup,
    resolve_grounding_config,
)
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover
    genai = None  # type: ignore
    genai_types = None  # type: ignore

# ORBIT client sends 24kHz PCM16 input; Gemini Live requires 16kHz PCM16 input.
# Gemini's 24kHz PCM16 output already matches the client's expected output rate.
CLIENT_INPUT_SAMPLE_RATE = 24000
GEMINI_INPUT_SAMPLE_RATE = 16000
GEMINI_OUTPUT_SAMPLE_RATE = 24000


def _resolve_gemini_api_key(config: Dict[str, Any]) -> Optional[str]:
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    inf = config.get("inference") or {}
    gm = inf.get("gemini") or {}
    raw = gm.get("api_key")
    if isinstance(raw, str) and raw.startswith("${") and raw.endswith("}"):
        return os.environ.get(raw[2:-1])
    if raw:
        return str(raw)
    return None


def _resample_pcm16(data: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Linear-interpolation resample of little-endian PCM16 mono audio."""
    if src_rate == dst_rate or not data:
        return data
    samples = np.frombuffer(data, dtype="<i2")
    if samples.size == 0:
        return data
    duration = samples.size / float(src_rate)
    dst_count = max(1, int(round(duration * dst_rate)))
    src_index = np.linspace(0, samples.size - 1, num=dst_count)
    resampled = np.interp(src_index, np.arange(samples.size), samples.astype(np.float64))
    return resampled.astype("<i2").tobytes()


class GeminiLiveWebSocketHandler:
    """
    Bridges ORBIT /ws/voice clients to Gemini Live (google-genai SDK).

    Client protocol (unchanged, identical to OpenAIRealtimeWebSocketHandler):
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
        prompt_service: Optional[Any] = None,
        system_prompt_id: Optional[str] = None,
        clock_service: Optional[Any] = None,
        adapter_manager: Optional[Any] = None,
        api_key: Optional[str] = None,
        chat_history_service: Optional[Any] = None,
    ):
        self.websocket = websocket
        self.adapter_name = adapter_name
        self.adapter_config = adapter_config
        self.config = config
        self.orbit_session_id = session_id or str(uuid.uuid4())
        self.user_id = user_id
        self.prompt_service = prompt_service
        self.system_prompt_id = system_prompt_id
        self.clock_service = clock_service
        self.adapter_manager = adapter_manager
        self.api_key = api_key
        self.chat_history_service = chat_history_service
        self._grounding = resolve_grounding_config(adapter_config)
        self._pending_user_message = ""
        self._pending_assistant_text = ""

        cfg = adapter_config.get("config") or {}
        self._realtime_model = cfg.get("realtime_model", "gemini-3.1-flash-live-preview")
        self._voice = cfg.get("realtime_voice", "Puck")
        self._enable_input_transcription = cfg.get("enable_input_transcription", True)
        self._enable_output_transcription = cfg.get("enable_output_transcription", True)
        self._vad_silence_ms = int(cfg.get("vad_silence_duration_ms", 500))
        self._vad_prefix_ms = int(cfg.get("vad_prefix_padding_ms", 300))

        self.is_connected = False
        self._session: Optional[Any] = None
        self._client_task: Optional[asyncio.Task] = None
        self._gemini_task: Optional[asyncio.Task] = None
        self._chunk_index = 0

    async def _resolve_realtime_instructions(self) -> str:
        cfg = self.adapter_config.get("config") or {}
        context = ProcessingContext(
            adapter_name=self.adapter_name,
            system_prompt_id=self.system_prompt_id,
            timezone=cfg.get("timezone"),
            time_format=cfg.get("time_format"),
        )
        builder = PromptInstructionBuilder(
            config=self.config,
            prompt_service=self.prompt_service,
            clock_service=self.clock_service,
            builder_logger=logger,
        )
        base_system_prompt = await builder.get_system_prompt(context)
        prompt_preview = " ".join(base_system_prompt.split())[:160]

        if self.system_prompt_id:
            if base_system_prompt == builder.DEFAULT_SYSTEM_PROMPT:
                logger.warning(
                    "Gemini Live prompt fallback in use for adapter '%s' "
                    "(system_prompt_id=%s, prompt_service_available=%s)",
                    self.adapter_name,
                    self.system_prompt_id,
                    bool(self.prompt_service),
                )
            else:
                logger.info(
                    "Gemini Live loaded system prompt for adapter '%s' "
                    "(system_prompt_id=%s, preview=%r)",
                    self.adapter_name,
                    self.system_prompt_id,
                    prompt_preview,
                )
        else:
            logger.info(
                "Gemini Live has no system_prompt_id for adapter '%s'; using default prompt "
                "(preview=%r)",
                self.adapter_name,
                prompt_preview,
            )

        instructions = await builder.build_system_message_content(context)
        if self._grounding:
            instructions += (
                f"\n\nWhen the user asks a factual question, call the {self._grounding.tool_name} "
                "tool to look up the answer, then respond naturally and conversationally in your "
                "own words in a friendly tone — do not read the looked-up text verbatim."
            )
        return instructions

    async def _build_live_config(self) -> Any:
        instructions = await self._resolve_realtime_instructions()

        kwargs: Dict[str, Any] = dict(
            response_modalities=[genai_types.Modality.AUDIO],
            speech_config=genai_types.SpeechConfig(
                voice_config=genai_types.VoiceConfig(
                    prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(voice_name=self._voice)
                )
            ),
            system_instruction=genai_types.Content(parts=[genai_types.Part(text=instructions)]),
            realtime_input_config=genai_types.RealtimeInputConfig(
                automatic_activity_detection=genai_types.AutomaticActivityDetection(
                    prefix_padding_ms=self._vad_prefix_ms,
                    silence_duration_ms=self._vad_silence_ms,
                ),
                turn_coverage="TURN_INCLUDES_ONLY_ACTIVITY",
            ),
        )
        if self._enable_input_transcription:
            kwargs["input_audio_transcription"] = genai_types.AudioTranscriptionConfig()
        if self._enable_output_transcription:
            kwargs["output_audio_transcription"] = genai_types.AudioTranscriptionConfig()
        if self._grounding:
            schema = build_tool_schema(self._grounding)
            kwargs["tools"] = [
                genai_types.Tool(
                    function_declarations=[
                        genai_types.FunctionDeclaration(
                            name=schema["name"],
                            description=schema["description"],
                            parameters_json_schema=schema["parameters"],
                        )
                    ]
                )
            ]

        return genai_types.LiveConnectConfig(**kwargs)

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

    async def _client_loop(self) -> None:
        assert self._session is not None
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
                # Gemini Live's automatic VAD handles barge-in server-side; just
                # acknowledge to the client for UX parity with the OpenAI bridge.
                await self._send_client({"type": "interrupted", "reason": "user_request"})
            elif mtype == "audio_chunk":
                b64 = message.get("data")
                if not b64:
                    continue
                pcm24k = base64.b64decode(b64)
                pcm16k = _resample_pcm16(pcm24k, CLIENT_INPUT_SAMPLE_RATE, GEMINI_INPUT_SAMPLE_RATE)
                await self._session.send_realtime_input(
                    audio=genai_types.Blob(
                        data=pcm16k,
                        mime_type=f"audio/pcm;rate={GEMINI_INPUT_SAMPLE_RATE}",
                    )
                )
            else:
                logger.debug("Unknown client message type: %s", mtype)

    def _discard_pending_turn(self) -> None:
        self._pending_user_message = ""
        self._pending_assistant_text = ""

    async def _persist_turn(self) -> Tuple[Optional[Any], Optional[Any]]:
        """Persist the completed turn to chat_history, the same way normal
        passthrough/retriever chat does via ConversationHistoryHandler — so a
        voice conversation shows up in history and can be cleared through the
        same DELETE /admin/conversations/{session_id} endpoint as any other
        conversation. Best-effort: a failure here never disrupts the live
        audio session.
        """
        if not self.chat_history_service:
            return None, None
        if not self._pending_user_message.strip() and not self._pending_assistant_text.strip():
            return None, None
        try:
            result = await self.chat_history_service.add_conversation_turn(
                session_id=self.orbit_session_id,
                user_message=self._pending_user_message,
                assistant_response=self._pending_assistant_text,
                user_id=self.user_id,
                api_key=self.api_key,
                adapter_name=self.adapter_name,
            )
            if isinstance(result, tuple) and len(result) == 2:
                return result
            return None, None
        except Exception as e:
            logger.error("Failed to persist realtime voice turn to chat history: %s", e, exc_info=True)
            return None, None
        finally:
            self._discard_pending_turn()

    async def _handle_tool_call(self, tool_call: Any) -> None:
        if not self._grounding:
            return
        function_responses = []
        for fc in tool_call.function_calls or []:
            if fc.name != self._grounding.tool_name:
                logger.debug("Ignoring unknown realtime tool call: %s", fc.name)
                continue
            args = fc.args or {}
            query = args.get("query", "")
            logger.debug(
                "Gemini Live: _handle_tool_call invoking grounding_adapter='%s' query=%r",
                self._grounding.adapter_name, query,
            )
            result_text = await execute_grounding_lookup(
                self.adapter_manager, self._grounding, query, api_key=self.api_key
            )
            logger.debug(
                "Gemini Live: grounding lookup result (%d chars): %r",
                len(result_text), result_text,
            )
            function_responses.append(
                genai_types.FunctionResponse(
                    id=fc.id,
                    name=fc.name,
                    response={"result": result_text},
                )
            )
        if function_responses:
            await self._session.send_tool_response(function_responses=function_responses)

    async def _gemini_loop(self) -> None:
        assert self._session is not None
        try:
            while self.is_connected:
                async for response in self._session.receive():
                    if response.go_away:
                        logger.info("Gemini Live: go_away received, ending session")
                        self.is_connected = False
                        break

                    tool_call = response.tool_call
                    if tool_call:
                        await self._handle_tool_call(tool_call)

                    server_content = response.server_content
                    if not server_content:
                        continue

                    if server_content.interrupted:
                        self._discard_pending_turn()
                        await self._send_client({"type": "interrupted", "reason": "model_interrupted"})

                    if server_content.input_transcription and server_content.input_transcription.text:
                        self._pending_user_message = server_content.input_transcription.text
                        await self._send_client(
                            {"type": "transcription", "text": server_content.input_transcription.text}
                        )

                    if server_content.output_transcription and server_content.output_transcription.text:
                        self._pending_assistant_text += server_content.output_transcription.text
                        await self._send_client(
                            {
                                "type": "assistant_transcript_delta",
                                "delta": server_content.output_transcription.text,
                            }
                        )

                    if server_content.model_turn:
                        for part in server_content.model_turn.parts or []:
                            if part.inline_data and part.inline_data.data:
                                await self._send_client(
                                    {
                                        "type": "audio_chunk",
                                        "data": base64.b64encode(part.inline_data.data).decode("ascii"),
                                        "format": "pcm",
                                        "sample_rate": GEMINI_OUTPUT_SAMPLE_RATE,
                                        "chunk_index": self._chunk_index,
                                    }
                                )
                                self._chunk_index += 1

                    if server_content.turn_complete:
                        logger.debug("Gemini Live: turn_complete")
                        user_message_id, assistant_message_id = await self._persist_turn()
                        await self._send_client({
                            "type": "done",
                            "session_id": self.orbit_session_id,
                            "user_message_id": user_message_id,
                            "assistant_message_id": assistant_message_id,
                        })
                        self._chunk_index = 0
                if not self.is_connected:
                    break
        except Exception as e:
            logger.error("Gemini receive loop error: %s", e, exc_info=True)
            await self._send_client({"type": "error", "message": str(e)})
        finally:
            self.is_connected = False

    async def run(self) -> None:
        if genai is None:
            await self.websocket.accept()
            await self._send_client(
                {"type": "error", "message": "google-genai is required for Gemini Live bridge"}
            )
            return

        await self.websocket.accept()

        api_key = _resolve_gemini_api_key(self.config)
        if not api_key:
            self.is_connected = True
            await self._send_client(
                {
                    "type": "error",
                    "message": "GOOGLE_API_KEY is not set (or inference.gemini.api_key)",
                }
            )
            self.is_connected = False
            return

        self.is_connected = True
        client = genai.Client(api_key=api_key)

        try:
            live_config = await self._build_live_config()
            async with client.aio.live.connect(model=self._realtime_model, config=live_config) as session:
                self._session = session

                await self._send_client(
                    {
                        "type": "connected",
                        "adapter": self.adapter_name,
                        "session_id": self.orbit_session_id,
                        "audio_format": "pcm",
                        "sample_rate": GEMINI_OUTPUT_SAMPLE_RATE,
                        "mode": "gemini_live",
                        "realtime_model": self._realtime_model,
                    }
                )

                self._client_task = asyncio.create_task(self._client_loop())
                self._gemini_task = asyncio.create_task(self._gemini_loop())

                done, pending = await asyncio.wait(
                    [self._client_task, self._gemini_task],
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
        except Exception as e:
            logger.error("Gemini Live connect failed: %s", e, exc_info=True)
            await self._send_client({"type": "error", "message": f"Gemini Live connection failed: {e}"})
        finally:
            self.is_connected = False
            self._session = None

    async def cleanup(self) -> None:
        self.is_connected = False
        self._session = None
        logger.info("Gemini Live handler cleanup complete (adapter=%s)", self.adapter_name)
