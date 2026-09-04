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
from typing import Any, Optional

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
        adapter_config: dict[str, Any],
        config: dict[str, Any],
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        prompt_service: Optional[Any] = None,
        system_prompt_id: Optional[str] = None,
        clock_service: Optional[Any] = None,
        adapter_manager: Optional[Any] = None,
        api_key: Optional[str] = None,
        chat_history_service: Optional[Any] = None,
        audit_service: Optional[Any] = None,
        pricing_service: Optional[Any] = None,
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
        self.audit_service = audit_service
        self.pricing_service = pricing_service
        self._grounding = resolve_grounding_config(adapter_config)
        self._pending_user_message = ""
        self._pending_assistant_text = ""
        # Usage summed across every response.done/usageMetadata event this
        # session receives — flushed as ONE audit record on disconnect, not
        # per-turn (a session can produce hundreds of turns).
        self._usage_accumulator: dict[str, Any] = {}
        self._embedding_usage_accumulator: dict[str, Any] = {}

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

    async def _send_client(self, message: dict[str, Any]) -> None:
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

    async def _persist_turn(self) -> tuple[Optional[Any], Optional[Any]]:
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

    def _accumulate_realtime_usage(
        self,
        provider: str,
        model: Optional[str],
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        audio_prompt_tokens: Optional[int] = None,
        audio_completion_tokens: Optional[int] = None,
    ) -> None:
        """
        Sum usage from one turn's response.done/usageMetadata event into the
        session-lifetime accumulator. Called from each provider's receive loop
        as soon as a turn's usage event arrives — before any discard/cancel
        early-return, since a cancelled or tool-call-only turn still bills
        tokens on the provider side.
        """
        acc = self._usage_accumulator
        acc["reported"] = True
        acc.setdefault("provider", provider)
        acc.setdefault("model", model)
        for key, value in (
            ("prompt_tokens", prompt_tokens),
            ("completion_tokens", completion_tokens),
            ("audio_prompt_tokens", audio_prompt_tokens),
            ("audio_completion_tokens", audio_completion_tokens),
        ):
            if value is not None:
                acc[key] = (acc.get(key) or 0) + value
        acc["total_tokens"] = (acc.get("prompt_tokens") or 0) + (acc.get("completion_tokens") or 0)

    def _accumulate_embedding_usage(self, usage_sink: dict[str, Any]) -> None:
        """Add one grounding lookup's embedding usage to the session total."""
        if not usage_sink or not usage_sink.get("reported"):
            return
        from ai_services.providers.usage_reporting import accumulate_usage_sink
        accumulate_usage_sink(self._embedding_usage_accumulator, usage_sink)

    async def _flush_realtime_usage(self) -> None:
        """
        Write ONE audit record for the whole session's accumulated usage.
        Call at the very top of cleanup(), before any upstream teardown —
        this is the only guaranteed once-per-session hook; the receive loops
        may be cancelled or end abnormally, so nothing should depend on them
        completing normally.  Best-effort: never raises, never blocks
        session teardown.
        """
        acc = self._usage_accumulator
        embedding_acc = self._embedding_usage_accumulator
        if not (acc.get("reported") or embedding_acc.get("reported")) or not self.audit_service:
            return
        try:
            if not getattr(self.audit_service, "chat_events_enabled", False):
                return
        except Exception:
            return

        from inference.pipeline.steps._utils import summarize_embedding_usage

        embedding_usage = summarize_embedding_usage(embedding_acc, self.pricing_service)
        provider = acc.get("provider") or (embedding_usage or {}).get("provider")
        model = acc.get("model") or (embedding_usage or {}).get("model")
        prompt_tokens = acc.get("prompt_tokens")
        completion_tokens = acc.get("completion_tokens")
        usage: dict[str, Any] = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": acc.get("total_tokens"),
            "cost_usd": None,
            "input_rate_per_1m": None,
            "output_rate_per_1m": None,
            "pricing_source": "unreported",
        }
        audio_prompt_tokens = acc.get("audio_prompt_tokens")
        audio_completion_tokens = acc.get("audio_completion_tokens")
        if audio_prompt_tokens or audio_completion_tokens:
            usage["usage_unit"] = "audio_tokens"
            usage["usage_quantity"] = (audio_prompt_tokens or 0) + (audio_completion_tokens or 0)
            usage["call_type"] = "audio"

        if self.pricing_service and acc.get("reported"):
            try:
                estimate = self.pricing_service.estimate(
                    provider, model, prompt_tokens, completion_tokens,
                    audio_prompt_tokens=audio_prompt_tokens, audio_completion_tokens=audio_completion_tokens,
                )
                usage["input_rate_per_1m"] = estimate.input_rate_per_1m
                usage["output_rate_per_1m"] = estimate.output_rate_per_1m
                usage["pricing_source"] = estimate.pricing_source
                usage["cost_usd"] = estimate.cost_usd
            except Exception:
                logger.debug("Pricing estimate failed for realtime voice session", exc_info=True)

        if embedding_usage:
            usage["embedding_prompt_tokens"] = embedding_usage["embedding_prompt_tokens"]
            if embedding_usage.get("embedding_cost_usd") is not None:
                usage["embedding_cost_usd"] = embedding_usage["embedding_cost_usd"]
            embedding_cost = embedding_usage.get("cost_usd")
            if embedding_cost is not None:
                usage["cost_usd"] = round((usage.get("cost_usd") or 0.0) + embedding_cost, 6)
            if acc.get("reported"):
                usage["pricing_source"] = "mixed"
            else:
                usage["pricing_source"] = embedding_usage["pricing_source"]

        try:
            await self.audit_service.log_conversation(
                query=f"[realtime voice session] adapter={self.adapter_name}",
                response="",
                provider=provider,
                blocked=False,
                api_key=self.api_key,
                session_id=self.orbit_session_id,
                user_id=self.user_id,
                adapter_name=self.adapter_name,
                model=model,
                usage=usage,
            )
        except Exception:
            logger.debug("Failed to write audit record for realtime voice session", exc_info=True)

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
