"""
Video Generation Step

Generates a video from the user's prompt when the adapter is of type
'video_generation'. Replaces LLMInferenceStep for such adapters.
"""

import base64
import logging
from typing import Optional, Dict, Any

from ..base import PipelineStep, ProcessingContext
from ._utils import get_rewrite_prompt_config

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


class VideoGenerationStep(PipelineStep):
    """
    Generate a video from the user's text prompt.

    Executes only for adapters whose 'type' is 'video_generation'.
    Stores the result in context.video (base64), context.video_format,
    and context.video_revised_prompt.
    """

    def should_execute(self, context: ProcessingContext) -> bool:
        if context.is_blocked:
            return False
        return _get_adapter_type(self.container, context.adapter_name) == 'video_generation'

    def supports_streaming(self) -> bool:
        return False

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        video_service = await self._get_video_service(context)
        if video_service is None:
            context.set_error("No video generation service is available for this adapter.")
            return context

        prompt = context.message
        logger.debug(
            "Video generation context: context_messages=%d, formatted_context_len=%d",
            len(context.context_messages),
            len(context.formatted_context),
        )
        if context.context_messages or context.formatted_context:
            if context.context_messages and not context.formatted_context:
                logger.debug(
                    "Video generation has conversation history but no structured retrieval "
                    "context. Prompt rewrite will use conversation text only."
                )
            prompt = await self._rewrite_prompt(context)
            logger.debug("Video generation prompt after rewrite: %r", prompt[:200])

        try:
            result = await video_service.generate_video(prompt)
            context.video = base64.b64encode(result["video_bytes"]).decode("utf-8")
            context.video_format = result.get("format", "mp4")
            context.video_revised_prompt = result.get("revised_prompt") or prompt
            context.response = context.video_revised_prompt
        except Exception as e:
            logger.error(f"Video generation failed: {e}", exc_info=True)
            context.set_error(f"Video generation failed: {e}")

        return context

    async def _resolve_rewrite_provider(self, context: ProcessingContext):
        """Resolve the LLM provider for prompt rewriting.

        Priority:
        1. Explicit `rewrite_provider` field on the skill adapter config.
        2. Original (retrieval) adapter's inference provider.
        3. Skill adapter's inference_provider.
        4. Global llm_provider fallback.
        """
        if self.container.has('adapter_manager'):
            adapter_manager = self.container.get('adapter_manager')

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
        """Rewrite the user's message into a descriptive video prompt using history and context."""
        if not context.context_messages and not context.formatted_context:
            return context.message

        llm_provider = await self._resolve_rewrite_provider(context)
        if not llm_provider:
            logger.warning("No llm_provider available — skipping prompt rewrite for video generation")
            return context.message

        prompt_cfg = get_rewrite_prompt_config(self.container, 'video')
        template = prompt_cfg.get('template')
        if not template:
            logger.warning("No 'video' rewrite template in config/rewriters-prompts.yaml — skipping prompt rewrite")
            return context.message
        max_tokens = prompt_cfg.get('max_tokens', 300)
        temperature = prompt_cfg.get('temperature', 0.3)
        history_limit = prompt_cfg.get('history_limit', 6)

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

        try:
            rewrite_prompt = template.format(
                history_text=history_text,
                context_text=context_text,
                message=context.message,
            )
        except (KeyError, IndexError) as e:
            logger.warning(f"Malformed 'video' rewrite template in config/rewriters-prompts.yaml: {e}")
            return context.message

        try:
            rewritten = await llm_provider.generate(rewrite_prompt, max_tokens=max_tokens, temperature=temperature)
            rewritten = rewritten.strip()
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

    async def _get_video_service(self, context: ProcessingContext):
        """Resolve the video generation service from config and adapter settings."""
        config = self.container.get_or_none('config') or {}
        provider = self._resolve_provider(context, config)
        if not provider:
            logger.warning("No video generation provider configured.")
            return None

        if self.container.has('adapter_manager'):
            adapter_manager = self.container.get('adapter_manager')
            if hasattr(adapter_manager, 'get_video_service'):
                return await adapter_manager.get_video_service(provider, context.adapter_name)

        # Fallback for containers without a full adapter_manager (e.g. tests)
        from ai_services.factory import AIServiceFactory
        from ai_services.base import ServiceType
        return await AIServiceFactory.create_and_initialize_service(
            ServiceType.VIDEO_GENERATION, provider, config, use_cache=True,
        )

    def _resolve_provider(self, context: ProcessingContext, config: Dict[str, Any]) -> Optional[str]:
        """Return the provider name for this request."""
        if context.adapter_name and self.container.has('adapter_manager'):
            try:
                adapter_manager = self.container.get('adapter_manager')
                adapter_config = adapter_manager.get_adapter_config(context.adapter_name)
                if adapter_config:
                    provider = adapter_config.get('video_provider')
                    if provider:
                        return provider
            except Exception:
                pass

        return config.get('video', {}).get('provider')
