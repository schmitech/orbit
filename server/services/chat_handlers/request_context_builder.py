"""
Request Context Builder

Builds ProcessingContext objects from request parameters,
eliminating duplication between streaming and non-streaming paths.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List

from bson import ObjectId

from inference.pipeline import ProcessingContext

logger = logging.getLogger(__name__)


class RequestContextBuilder:
    """Builds ProcessingContext objects from request parameters."""

    def __init__(
        self,
        config: Dict[str, Any],
        adapter_manager=None
    ):
        """
        Initialize the request context builder.

        Args:
            config: Application configuration
            adapter_manager: Optional adapter manager for getting adapter settings
        """
        self.config = config
        self.adapter_manager = adapter_manager

    def get_adapter_config(self, adapter_name: str) -> Dict[str, Any]:
        """
        Get configuration for a specific adapter.

        Args:
            adapter_name: The adapter name

        Returns:
            Adapter configuration dictionary
        """
        if adapter_name and self.adapter_manager:
            adapter_config = self.adapter_manager.get_adapter_config(adapter_name)
            if adapter_config:
                return adapter_config
        return {}

    def get_inference_provider(self, adapter_name: str) -> Optional[str]:
        """
        Get the inference provider override for an adapter.

        Args:
            adapter_name: The adapter name

        Returns:
            Inference provider name or None
        """
        adapter_config = self.get_adapter_config(adapter_name)
        provider = adapter_config.get('inference_provider')

        if provider:
            logger.debug(
                f"Using adapter-specific inference provider: {provider} for adapter: {adapter_name}"
            )

        return provider

    def get_timezone(self, adapter_name: str) -> Optional[str]:
        """
        Get the timezone setting for an adapter.

        Args:
            adapter_name: The adapter name

        Returns:
            Timezone string or None
        """
        adapter_config = self.get_adapter_config(adapter_name)
        custom_config = adapter_config.get('config') or {}
        return custom_config.get('timezone')

    def resolve_runtime_model_override(
        self,
        adapter_name: str,
        requested_model: Optional[str],
    ) -> tuple[Optional[str], Optional[str], Optional[Dict[str, Any]]]:
        """
        Resolve a client-requested model name against the adapter's allowed_models list.

        Callable ahead of build_context() (e.g. so the conversation-history token
        budget can reflect the runtime model choice before context messages are
        fetched), and reused by build_context() itself so both call sites agree.

        Args:
            adapter_name: The adapter name
            requested_model: Optional model name from the request body

        Returns:
            Tuple of (runtime_provider, runtime_model_name, runtime_param_overrides).
            All None when requested_model is falsy or the adapter has no allowed_models.

        Raises:
            ValueError: If requested_model doesn't match any allowed_models entry
                (except the adapter-name echo from OpenAI-compatible clients, which
                is silently treated as "no override").
        """
        if not requested_model:
            return None, None, None

        adapter_config = self.get_adapter_config(adapter_name)
        allowed = adapter_config.get('allowed_models') or []
        if not allowed:
            # No allowed_models list — silently ignore the override
            return None, None, None

        match = next((m for m in allowed if m.get('name') == requested_model), None)
        if match is None:
            # OpenAI-compatible clients (e.g. LiteLLM) echo the adapter name back as
            # the model field. Treat that specific case as "no override" so they work
            # out of the box. Any other unrecognized value is a real validation error.
            if requested_model == adapter_name:
                logger.debug(
                    f"Ignoring model echo '{requested_model}' from OpenAI-compatible client "
                    f"for adapter '{adapter_name}' — using adapter default"
                )
                return None, None, None
            allowed_names = [m['name'] for m in allowed if m.get('name')]
            raise ValueError(
                f"Model '{requested_model}' is not allowed for adapter '{adapter_name}'. "
                f"Allowed models: {allowed_names}"
            )

        runtime_provider = match.get('provider')
        runtime_model_name = match.get('model')
        if not runtime_provider or not runtime_model_name:
            raise ValueError(
                f"Adapter '{adapter_name}' has an invalid allowed_models entry for "
                f"'{requested_model}'. Each entry must include 'name', 'provider', and 'model'."
            )

        runtime_param_overrides = {
            key: match[key]
            for key in ('temperature', 'max_tokens', 'context_window')
            if key in match and match[key] is not None
        } or None

        logger.debug(
            f"Runtime model override: '{requested_model}' → "
            f"{runtime_provider}/{runtime_model_name} for adapter '{adapter_name}'"
            + (f" (params: {runtime_param_overrides})" if runtime_param_overrides else "")
        )
        return runtime_provider, runtime_model_name, runtime_param_overrides

    def get_time_format(self, adapter_name: str) -> Optional[str]:
        """
        Get the time format setting for an adapter.

        This allows per-adapter customization of the time format
        used in the clock service timestamp injection.

        Args:
            adapter_name: The adapter name

        Returns:
            Time format string (strftime format) or None to use global default
        """
        adapter_config = self.get_adapter_config(adapter_name)
        custom_config = adapter_config.get('config') or {}
        return custom_config.get('time_format')

    def build_context(
        self,
        message: str,
        adapter_name: str,
        context_messages: List[Dict[str, str]],
        system_prompt_id: Optional[ObjectId] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        api_key: Optional[str] = None,
        file_ids: Optional[List[str]] = None,
        thread_id: Optional[str] = None,
        audio_input: Optional[str] = None,
        audio_format: Optional[str] = None,
        language: Optional[str] = None,
        return_audio: Optional[bool] = None,
        tts_voice: Optional[str] = None,
        source_language: Optional[str] = None,
        target_language: Optional[str] = None,
        cancel_event: Optional[asyncio.Event] = None,
        requested_model: Optional[str] = None,
        skill: Optional[str] = None,
        skill_auto_detected: bool = False,
    ) -> ProcessingContext:
        """
        Build a ProcessingContext from request parameters.

        Args:
            message: The chat message
            adapter_name: Adapter name to use
            context_messages: Previous conversation messages
            system_prompt_id: Optional system prompt ID
            user_id: Optional user identifier
            session_id: Optional session identifier
            api_key: Optional API key
            file_ids: Optional list of file IDs
            audio_input: Optional base64 audio input
            audio_format: Optional audio format
            language: Optional language code
            return_audio: Whether to return audio
            tts_voice: Optional TTS voice
            source_language: Optional source language for translation
            target_language: Optional target language for translation
            cancel_event: Optional asyncio.Event for stream cancellation
            requested_model: Optional model name from the request body (must match
                             a allowed_models entry in the adapter config)

        Returns:
            ProcessingContext instance
        """
        # Get adapter-specific settings
        inference_provider = self.get_inference_provider(adapter_name)
        timezone = self.get_timezone(adapter_name)
        time_format = self.get_time_format(adapter_name)

        # Get tts_voice from adapter config if not provided in request
        if tts_voice is None:
            adapter_config = self.get_adapter_config(adapter_name)
            custom_config = adapter_config.get('config') or {}
            tts_voice = custom_config.get('tts_voice')
            if tts_voice:
                logger.debug(f"Using adapter config tts_voice: {tts_voice} for adapter: {adapter_name}")

        # Resolve runtime model override from adapter's allowed_models
        runtime_provider, runtime_model_name, runtime_param_overrides = (
            self.resolve_runtime_model_override(adapter_name, requested_model)
        )

        # Resolve skill invocation: validate allowlist and swap adapter
        original_adapter_name = None
        requested_skill = None
        if skill:
            adapter_config = self.get_adapter_config(adapter_name)
            capabilities_cfg = adapter_config.get('capabilities', {})
            available_skills = capabilities_cfg.get('available_skills', [])
            # An auto-detected skill is validated against auto_routable_skills
            # (falling back to available_skills) — this lets ORBIT auto-route to
            # skills users may not invoke explicitly. An explicit skill from the
            # request is always restricted to available_skills.
            if skill_auto_detected:
                permitted_skills = capabilities_cfg.get('auto_routable_skills') or available_skills
            else:
                permitted_skills = available_skills
            if skill not in permitted_skills:
                raise ValueError(
                    f"Skill '{skill}' is not available for adapter '{adapter_name}'. "
                    f"Available skills: {permitted_skills}"
                )
            skill_adapter_name = (
                self.adapter_manager.get_skill_adapter(skill)
                if self.adapter_manager and hasattr(self.adapter_manager, 'get_skill_adapter')
                else None
            )
            if not skill_adapter_name:
                raise ValueError(f"No adapter is registered for skill '{skill}'")
            original_adapter_name = adapter_name
            requested_skill = skill
            adapter_name = skill_adapter_name
            skill_inference_provider = self.get_inference_provider(adapter_name)
            if skill_inference_provider:
                # Skill has its own LLM (e.g. image/video generation) — use it.
                inference_provider = skill_inference_provider
                runtime_provider = None
                runtime_model_name = None
                runtime_param_overrides = None
            else:
                # Skill has no configured LLM (e.g. fetch) — keep the invoking
                # adapter's provider/model so the caller's LLM processes the result.
                pass  # inference_provider, runtime_provider, runtime_model_name, runtime_param_overrides unchanged
            logger.debug(
                f"Skill routing: '{requested_skill}' → adapter '{adapter_name}' "
                f"(original: '{original_adapter_name}')"
            )

        # Resolve web search capability from the (possibly skill-swapped) adapter
        final_cfg = self.get_adapter_config(adapter_name)
        web_search = bool(final_cfg.get('capabilities', {}).get('web_search', False))

        # Resolve opportunistic MCP tool-calling capability the same way.
        mcp_tools = bool(final_cfg.get('capabilities', {}).get('mcp_tools', False))
        mcp_servers_allowlist = final_cfg.get('capabilities', {}).get('mcp_servers')

        # Create and return processing context
        return ProcessingContext(
            message=message,
            adapter_name=adapter_name,
            system_prompt_id=str(system_prompt_id) if system_prompt_id else None,
            inference_provider=inference_provider,
            context_messages=context_messages,
            user_id=user_id,
            session_id=session_id,
            api_key=api_key,
            timezone=timezone,
            time_format=time_format,
            file_ids=file_ids or [],
            thread_id=thread_id,
            audio_input=audio_input,
            audio_format=audio_format,
            language=language,
            return_audio=return_audio,
            tts_voice=tts_voice,
            source_language=source_language,
            target_language=target_language,
            cancel_event=cancel_event,
            runtime_provider=runtime_provider,
            runtime_model_name=runtime_model_name,
            runtime_param_overrides=runtime_param_overrides,
            requested_skill=requested_skill,
            original_adapter_name=original_adapter_name,
            web_search=web_search,
            mcp_tools=mcp_tools,
            mcp_servers_allowlist=mcp_servers_allowlist,
        )
