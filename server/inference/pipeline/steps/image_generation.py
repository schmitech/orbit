"""
Image Generation Step

Generates an image from the user's prompt when the adapter is of type
'image_generation'. Replaces LLMInferenceStep for such adapters.
"""

import base64
import logging
from typing import Optional, Any

from ..base import PipelineStep, ProcessingContext
from ._utils import (
    get_adapter_type, get_generation_memory, get_rewrite_prompt_config, is_prompt_rewrite_enabled,
    record_media_generation_usage, resolve_media_provider, resolve_rewrite_provider, store_generation_memory,
)

logger = logging.getLogger(__name__)


class ImageGenerationStep(PipelineStep):
    """
    Generate an image from the user's text prompt.

    Executes only for adapters whose 'type' is 'image_generation'.
    Stores the result in context.image (base64), context.image_format,
    and context.image_revised_prompt.
    """

    def should_execute(self, context: ProcessingContext) -> bool:
        if context.is_blocked:
            return False
        return get_adapter_type(self.container, context.adapter_name) == 'image_generation'

    def supports_streaming(self) -> bool:
        return False

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        image_service = await self._get_image_service(context)
        if image_service is None:
            context.set_error("No image generation service is available for this adapter.")
            return context

        # Refine prompt using conversation history, retrieved context, and/or the
        # previous turn's generation prompt (for follow-up refinements) if available.
        prompt = context.message
        rewrite_sink: dict = {}
        memory = await get_generation_memory(self.container, context.adapter_name, context.session_id)
        logger.debug(
            "Image generation context: context_messages=%d, formatted_context_len=%d, has_memory=%s",
            len(context.context_messages),
            len(context.formatted_context),
            memory is not None,
        )
        if (
            is_prompt_rewrite_enabled(self.container, context.adapter_name)
            and (context.context_messages or context.formatted_context or memory)
        ):
            if context.context_messages and not context.formatted_context:
                logger.debug(
                    "Image generation has conversation history but no structured retrieval "
                    "context (not in a thread). Prompt rewrite will use conversation text only."
                )
            prompt = await self._rewrite_prompt(context, memory, rewrite_sink)
            logger.debug("Image generation prompt after rewrite: %r", prompt[:200])

        try:
            generate_kwargs = dict(context.runtime_image_param_overrides or {})
            if context.runtime_model_name:
                generate_kwargs["model"] = context.runtime_model_name
            result = await image_service.generate_image(prompt, **generate_kwargs)
            context.image = base64.b64encode(result["image_bytes"]).decode("utf-8")
            context.image_format = result.get("format", "png")
            # Use provider-revised prompt if available (DALL-E 3), else the prompt we sent.
            # Always populate image_revised_prompt so the UI can display it.
            context.image_revised_prompt = result.get("revised_prompt") or prompt
            context.response = context.image_revised_prompt
            # Report the image model as the model that produced the response —
            # not the rewrite LLM used to refine the prompt above. Reflects a runtime
            # override (allowed_image_models) when one was resolved for this request.
            context.runtime_provider = (
                context.runtime_provider
                or self._resolve_provider(context, self.container.get_or_none('config') or {})
            )
            context.runtime_model_name = context.runtime_model_name or getattr(image_service, "model", None)
            record_media_generation_usage(
                self.container, context, context.runtime_provider, context.runtime_model_name,
                call_type="image",
                token_usage=result.get("usage"), media_usage=result.get("media_usage"),
                rewrite_sink=rewrite_sink,
            )
            await store_generation_memory(
                self.container, context.adapter_name, context.session_id,
                {"prompt": context.image_revised_prompt},
            )
        except Exception as e:
            logger.error(f"Image generation failed: {e}", exc_info=True)
            context.set_error(f"Image generation failed: {e}")

        return context

    async def _rewrite_prompt(
        self, context: ProcessingContext, memory: Optional[dict[str, Any]] = None,
        rewrite_sink: Optional[dict[str, Any]] = None,
    ) -> str:
        """Rewrite the user's message into a descriptive image prompt using history, context,
        and (if this is a follow-up) the previous turn's generation prompt."""
        if not context.context_messages and not context.formatted_context and not memory:
            return context.message

        llm_provider = await resolve_rewrite_provider(self.container, context)
        if not llm_provider:
            logger.warning("No llm_provider available — skipping prompt rewrite for image generation")
            return context.message

        prompt_cfg = get_rewrite_prompt_config(self.container, 'image')
        template = prompt_cfg.get('template')
        if not template:
            logger.warning("No 'image' rewrite template in config/rewriters-prompts.yaml — skipping prompt rewrite")
            return context.message
        max_tokens = prompt_cfg.get('max_tokens', 300)
        temperature = prompt_cfg.get('temperature', 0.3)
        history_limit = prompt_cfg.get('history_limit', 6)

        # Cap history to avoid blowing the context window.
        # Exclude the current message if it happens to be the last entry.
        recent_msgs = context.context_messages[-history_limit:] if context.context_messages else []
        if recent_msgs and recent_msgs[-1].get('role') == 'user' and recent_msgs[-1].get('content', '').strip() == context.message.strip():
            recent_msgs = recent_msgs[:-1]

        history = []
        for msg in recent_msgs:
            role = msg.get('role', 'user').title()
            content = msg.get('content', '')
            if role and content:
                history.append(f"{role}: {content}")

        history_text = "\n".join(history) if history else "No prior conversation."
        context_text = f"\nRetrieved Data/Context:\n{context.formatted_context}\n" if context.formatted_context else ""
        previous_generation_text = (
            f"\nPrevious image prompt (this request may be a refinement — incorporate it):\n{memory['prompt']}\n"
            if memory and memory.get('prompt') else ""
        )

        try:
            rewrite_prompt = template.format(
                history_text=history_text,
                context_text=context_text,
                previous_generation_text=previous_generation_text,
                message=context.message,
            )
        except (KeyError, IndexError) as e:
            logger.warning(f"Malformed 'image' rewrite template in config/rewriters-prompts.yaml: {e}")
            return context.message

        try:
            rewritten = await llm_provider.generate_tracked(
                rewrite_prompt, usage_sink=rewrite_sink, max_tokens=max_tokens, temperature=temperature,
            )
            rewritten = rewritten.strip()
            # Strip surrounding quotes the LLM sometimes adds
            for quote in ('"', "'"):
                if rewritten.startswith(quote) and rewritten.endswith(quote) and len(rewritten) > 2:
                    rewritten = rewritten[1:-1].strip()
                    break
            if rewritten and len(rewritten) >= 10:
                logger.debug(f"Rewrote skill prompt: '{context.message}' -> '{rewritten}'")
                return rewritten
            logger.warning(
                "Prompt rewrite returned too-short response (%d chars) — using raw message",
                len(rewritten) if rewritten else 0,
            )
        except Exception as e:  # noqa: BLE001 - prompt rewrite is best-effort; falls back to raw message
            logger.warning(f"Failed to rewrite skill prompt: {e}")

        return context.message

    async def _get_image_service(self, context: ProcessingContext):
        """Resolve the image generation service from config and adapter settings."""
        config = self.container.get_or_none('config') or {}
        provider = self._resolve_provider(context, config)
        if not provider:
            logger.warning("No image generation provider configured.")
            return None

        if self.container.has('adapter_manager'):
            adapter_manager = self.container.get('adapter_manager')
            if hasattr(adapter_manager, 'get_image_service'):
                return await adapter_manager.get_image_service(provider, context.adapter_name)

        # Fallback for containers without a full adapter_manager (e.g. tests)
        from ai_services.factory import AIServiceFactory
        from ai_services.base import ServiceType
        return await AIServiceFactory.create_and_initialize_service(
            ServiceType.IMAGE_GENERATION, provider, config, use_cache=True,
        )

    def _resolve_provider(self, context: ProcessingContext, config: dict[str, Any]) -> Optional[str]:
        """Return the provider name for this request."""
        return resolve_media_provider(self.container, context, config, 'image_provider', 'image')
