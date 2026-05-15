"""
Image Generation Step

Generates an image from the user's prompt when the adapter is of type
'image_generation'. Replaces LLMInferenceStep for such adapters.
"""

import base64
import logging
from typing import Optional, Dict, Any

from ..base import PipelineStep, ProcessingContext

logger = logging.getLogger(__name__)


def _get_adapter_type(container, adapter_name: str) -> Optional[str]:
    """Return the adapter's 'type' field, or None if unavailable."""
    if not adapter_name or not container.has('adapter_manager'):
        return None
    try:
        adapter_manager = container.get('adapter_manager')
        adapter_config = adapter_manager.get_adapter_config(adapter_name)
        if adapter_config:
            return adapter_config.get('type')
    except Exception:
        pass
    return None


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
        return _get_adapter_type(self.container, context.adapter_name) == 'image_generation'

    def supports_streaming(self) -> bool:
        return False

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        image_service = await self._get_image_service(context)
        if image_service is None:
            context.set_error("No image generation service is available for this adapter.")
            return context

        # Refine prompt using conversation history or retrieved context if available
        prompt = context.message
        logger.info(
            "Image generation context: context_messages=%d, formatted_context_len=%d",
            len(context.context_messages),
            len(context.formatted_context),
        )
        if context.context_messages or context.formatted_context:
            if context.context_messages and not context.formatted_context:
                logger.debug(
                    "Image generation has conversation history but no structured retrieval "
                    "context (not in a thread). Prompt rewrite will use conversation text only."
                )
            prompt = await self._rewrite_prompt(context)
            logger.info("Image generation prompt after rewrite: %r", prompt[:200])

        try:
            result = await image_service.generate_image(prompt)
            context.image = base64.b64encode(result["image_bytes"]).decode("utf-8")
            context.image_format = result.get("format", "png")
            # Use provider-revised prompt if available (DALL-E 3), else the prompt we sent.
            # Always populate image_revised_prompt so the UI can display it.
            context.image_revised_prompt = result.get("revised_prompt") or prompt
            context.response = context.image_revised_prompt
        except Exception as e:
            logger.error(f"Image generation failed: {e}", exc_info=True)
            context.set_error(f"Image generation failed: {e}")

        return context

    async def _resolve_rewrite_provider(self, context: ProcessingContext):
        """Resolve the LLM provider for prompt rewriting.

        Priority:
        1. Explicit `rewrite_provider` field on the skill adapter config.
        2. Original (retrieval) adapter's inference provider (e.g. openai on customer-orders).
        3. Skill adapter's inference_provider.
        4. Global llm_provider fallback.
        """
        if self.container.has('adapter_manager'):
            adapter_manager = self.container.get('adapter_manager')

            # 1. Explicit rewrite_provider wins — avoids picking a provider that
            #    returns empty for text completions (e.g. ollama_cloud/image models).
            if context.adapter_name:
                skill_config = adapter_manager.get_adapter_config(context.adapter_name)
                if skill_config:
                    rewrite_provider_name = skill_config.get('rewrite_provider')
                    if rewrite_provider_name:
                        try:
                            provider = await adapter_manager.get_overridden_provider(
                                rewrite_provider_name, context.adapter_name
                            )
                            if provider:
                                logger.debug(
                                    "Using rewrite_provider '%s' for prompt rewrite",
                                    rewrite_provider_name,
                                )
                                return provider
                        except Exception as e:
                            logger.debug(
                                "Could not resolve rewrite_provider '%s': %s",
                                rewrite_provider_name, e,
                            )

            # 2 & 3. Try original adapter's provider, then skill adapter's provider.
            for adapter_name in (context.original_adapter_name, context.adapter_name):
                if not adapter_name:
                    continue
                adapter_config = adapter_manager.get_adapter_config(adapter_name)
                if not adapter_config:
                    continue
                inference_provider = adapter_config.get('inference_provider')
                if inference_provider:
                    try:
                        provider = await adapter_manager.get_overridden_provider(
                            inference_provider, adapter_name
                        )
                        if provider:
                            logger.debug(
                                "Using inference provider '%s' (adapter '%s') for prompt rewrite",
                                inference_provider, adapter_name,
                            )
                            return provider
                    except Exception as e:
                        logger.debug("Could not resolve provider for '%s': %s", adapter_name, e)

        return self.container.get_or_none('llm_provider')

    async def _rewrite_prompt(self, context: ProcessingContext) -> str:
        """Rewrite the user's message into a descriptive image prompt using history and context."""
        if not context.context_messages and not context.formatted_context:
            return context.message

        llm_provider = await self._resolve_rewrite_provider(context)
        if not llm_provider:
            logger.warning("No llm_provider available — skipping prompt rewrite for image generation")
            return context.message

        # Cap history to last 6 turns to avoid blowing the context window.
        # Exclude the current message if it happens to be the last entry.
        recent_msgs = context.context_messages[-6:] if context.context_messages else []
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

        rewrite_prompt = (
            "You are an expert at writing prompts for AI image generators.\n"
            "Your task: rewrite the user's request into a single, standalone, richly descriptive image generation prompt.\n\n"
            "Rules:\n"
            "1. Always enrich the prompt with visual detail: subjects, actions, setting, art style, lighting, mood, and composition.\n"
            "2. If the user's message is vague or uses references like 'Draw it' or 'Visualize this', resolve those references "
            "using the conversation history or retrieved data below.\n"
            "3. If the message references data, numbers, or a chart, describe a visually compelling infographic or data visualization.\n"
            "4. Even if the user already wrote a descriptive prompt, enrich it further — always improve quality.\n"
            "5. Output ONLY the final prompt. No preamble, no explanation, no quotes.\n\n"
            f"Conversation History:\n{history_text}\n"
            f"{context_text}"
            f"User request: {context.message}\n"
            "Image prompt:"
        )

        try:
            rewritten = await llm_provider.generate(rewrite_prompt, max_tokens=300, temperature=0.3)
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
        except Exception as e:
            logger.warning(f"Failed to rewrite skill prompt: {e}")

        return context.message

    async def _get_image_service(self, context: ProcessingContext):
        """Resolve the image generation service from config and adapter settings."""
        from ai_services.factory import AIServiceFactory
        from ai_services.base import ServiceType

        config = self.container.get_or_none('config') or {}

        # Determine provider: adapter override > global default
        provider = self._resolve_provider(context, config)
        if not provider:
            logger.warning("No image generation provider configured.")
            return None

        service = await AIServiceFactory.create_and_initialize_service(
            ServiceType.IMAGE_GENERATION,
            provider,
            config,
            use_cache=True,
        )
        return service

    def _resolve_provider(self, context: ProcessingContext, config: Dict[str, Any]) -> Optional[str]:
        """Return the provider name for this request."""
        # Allow adapter config to override the global default
        if context.adapter_name and self.container.has('adapter_manager'):
            try:
                adapter_manager = self.container.get('adapter_manager')
                adapter_config = adapter_manager.get_adapter_config(context.adapter_name)
                if adapter_config:
                    provider = adapter_config.get('image_provider')
                    if provider:
                        return provider
            except Exception:
                pass

        return config.get('image', {}).get('provider')
