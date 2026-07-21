"""
Shared base for realtime speech-to-speech WebSocket bridges.

Each provider (OpenAI Realtime, Gemini Live, ...) bridges ORBIT's /ws/voice
clients to that provider's own realtime API. The wire protocol translation is
necessarily provider-specific, but the surrounding scaffolding — constructor
fields, sending JSON to the ORBIT client, persona/system-prompt resolution,
and persisting a completed turn to chat history — is identical across
providers. This base class owns that shared scaffolding so a new provider
only has to implement the actual protocol bridge.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, Optional, Tuple

from fastapi import WebSocket, WebSocketDisconnect
from inference.pipeline.base import ProcessingContext
from inference.pipeline.prompt_builder import PromptInstructionBuilder
from services.chat_handlers.realtime_grounding import resolve_grounding_config
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)


class BaseRealtimeWebSocketHandler:
    """Common scaffolding for a realtime STS provider bridge.

    Subclasses must set `self.provider_label` (used in log messages) before
    calling `_resolve_realtime_instructions()`, and are expected to implement
    their own `run()`/`cleanup()` using the shared helpers below.
    """

    provider_label: str = "Realtime"

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

        self.is_connected = False
        self._client_task: Optional[asyncio.Task] = None

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
                    "%s prompt fallback in use for adapter '%s' "
                    "(system_prompt_id=%s, prompt_service_available=%s)",
                    self.provider_label,
                    self.adapter_name,
                    self.system_prompt_id,
                    bool(self.prompt_service),
                )
            else:
                logger.info(
                    "%s loaded system prompt for adapter '%s' "
                    "(system_prompt_id=%s, preview=%r)",
                    self.provider_label,
                    self.adapter_name,
                    self.system_prompt_id,
                    prompt_preview,
                )
        else:
            logger.info(
                "%s has no system_prompt_id for adapter '%s'; using default prompt "
                "(preview=%r)",
                self.provider_label,
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

    def _discard_pending_turn(self) -> None:
        """Drop buffered transcript for the current turn (e.g. on interruption).

        Subclasses with additional per-turn buffers should override this,
        call super(), and clear their own state too.
        """
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
            return await self.chat_history_service.add_conversation_turn(
                session_id=self.orbit_session_id,
                user_message=self._pending_user_message,
                assistant_response=self._pending_assistant_text,
                user_id=self.user_id,
                api_key=self.api_key,
                adapter_name=self.adapter_name,
            )
        except Exception as e:
            logger.error("Failed to persist realtime voice turn to chat history: %s", e, exc_info=True)
            return None, None
        finally:
            self._discard_pending_turn()

    @staticmethod
    async def _run_until_either(task_a: asyncio.Task, task_b: asyncio.Task) -> None:
        """Run two tasks concurrently, cancel whichever is still pending once
        either finishes, and log (without raising) any exception from the one
        that completed. Shared by every provider's run() — the client-read
        loop and the provider-read loop are symmetric: either side ending the
        connection should tear down the other.
        """
        done, pending = await asyncio.wait(
            [task_a, task_b],
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
