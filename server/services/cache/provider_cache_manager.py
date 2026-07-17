"""
Provider Cache Manager for managing inference provider instances.

Provides thread-safe caching and lifecycle management for inference providers.
"""

import copy
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from .service_cache_manager import ServiceCacheManager

logger = logging.getLogger(__name__)


class ProviderCacheManager(ServiceCacheManager):
    """
    Manages inference provider cache with thread-safe access.

    Responsibilities:
    - Cache provider instances with model-specific keys
    - Handle provider creation with model overrides
    - Provide thread-safe provider access
    - Manage provider lifecycle
    """

    service_label = "inference provider"

    def __init__(self, config: Dict[str, Any], thread_pool: Optional[ThreadPoolExecutor] = None):
        """
        Initialize the provider cache manager.

        Args:
            config: Application configuration
            thread_pool: Optional thread pool for async operations
        """
        super().__init__(config, thread_pool)

    def build_cache_key(
        self,
        provider_name: str,
        model_override: Optional[str] = None,
        param_overrides: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Build cache key for a provider with optional model/parameter overrides.

        Args:
            provider_name: Name of the provider
            model_override: Optional model name override
            param_overrides: Optional dict of generation parameter overrides
                (e.g. temperature, max_tokens, context_window)

        Returns:
            Cache key string
        """
        key = provider_name
        if model_override:
            key += f":{model_override}"
        if param_overrides:
            suffix = ",".join(f"{k}={param_overrides[k]}" for k in sorted(param_overrides))
            key += f":{suffix}"
        return key

    async def remove_by_prefix(self, prefix: str) -> list[str]:
        """
        Remove all providers with keys matching the given prefix.

        Args:
            prefix: Prefix to match (e.g., provider name)

        Returns:
            List of removed cache keys
        """
        return await self._remove_matching(
            lambda key: key == prefix or key.startswith(f"{prefix}:")
        )

    async def create_provider(
        self,
        provider_name: str,
        model_override: Optional[str] = None,
        adapter_name: Optional[str] = None,
        param_overrides: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Create and cache a new provider instance.

        Args:
            provider_name: Name of the provider to create
            model_override: Optional model name override
            adapter_name: Optional adapter name for context
            param_overrides: Optional dict of generation parameter overrides
                (e.g. temperature, max_tokens, context_window) sourced from the
                adapter config, applied on top of inference.yaml defaults

        Returns:
            The created provider instance
        """
        cache_key = self.build_cache_key(provider_name, model_override, param_overrides)
        return await self._create_cached_service(
            cache_key,
            provider_name,
            adapter_name,
            model_override=model_override,
            param_overrides=param_overrides,
        )

    async def _create_instance(
        self,
        provider_name: str,
        adapter_name: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        model_override = kwargs.get('model_override')
        param_overrides = kwargs.get('param_overrides')
        config_for_provider = copy.deepcopy(self.config)

        if model_override:
            self._apply_model_override(config_for_provider, provider_name, model_override)
        else:
            logger.debug(f"Loading inference provider '{provider_name}' with default model")

        if param_overrides:
            self._apply_param_overrides(config_for_provider, provider_name, param_overrides)

        try:
            from server.inference.pipeline.providers import UnifiedProviderFactory as ProviderFactory
        except ImportError:
            from inference.pipeline.providers import UnifiedProviderFactory as ProviderFactory

        return ProviderFactory.create_provider_by_name(provider_name, config_for_provider)

    def _apply_model_override(
        self,
        config_for_provider: Dict[str, Any],
        provider_name: str,
        model_override: str,
    ) -> None:
        if 'inference' not in config_for_provider:
            config_for_provider['inference'] = {}
        if provider_name not in config_for_provider['inference']:
            config_for_provider['inference'][provider_name] = {}

        if provider_name == 'ollama':
            ollama_presets = config_for_provider.get('ollama_presets', {})
            if model_override in ollama_presets:
                preset = ollama_presets[model_override]
                inference_section = config_for_provider['inference'][provider_name]
                enabled = inference_section.get('enabled', True)

                for key, value in preset.items():
                    inference_section[key] = value
                inference_section['enabled'] = enabled

                logger.debug(
                    f"Loading Ollama with preset '{model_override}' (model: {preset.get('model', 'unknown')})"
                )
                return

            config_for_provider['inference'][provider_name]['model'] = model_override
            logger.debug(f"Loading Ollama with model override: {model_override}")
            return

        config_for_provider['inference'][provider_name]['model'] = model_override
        logger.debug(f"Loading inference provider '{provider_name}' with model override: {model_override}")

    # Most providers read the generic 'context_window'/'max_tokens' keys directly
    # (see ProviderAIService._get_model/_get_temperature-style helpers), but local
    # inference backends use their own native option names instead. Writing the
    # override under both the generic key and the provider's native alias ensures
    # the override actually reaches the request options for these providers too —
    # otherwise it's silently shadowed by whatever inference.yaml already set
    # (e.g. ollama_cloud hardcodes num_predict/num_ctx).
    _CONTEXT_WINDOW_ALIASES = {
        'ollama': 'num_ctx',
        'ollama_cloud': 'num_ctx',
        'ollama_remote': 'num_ctx',
        'llama_cpp': 'n_ctx',
        'bitnet': 'n_ctx',
        'vllm': 'max_model_len',
        'tensorrt': 'max_model_len',
        'huggingface': 'max_length',
    }
    _MAX_TOKENS_ALIASES = {
        'ollama': 'num_predict',
        'ollama_cloud': 'num_predict',
        'ollama_remote': 'num_predict',
    }

    def _apply_param_overrides(
        self,
        config_for_provider: Dict[str, Any],
        provider_name: str,
        param_overrides: Dict[str, Any],
    ) -> None:
        """
        Apply adapter-level generation parameter overrides (temperature, max_tokens,
        context_window) on top of the provider's inference.yaml defaults.

        Providers read these via ProviderAIService._extract_provider_config(), so writing
        them into config['inference'][provider_name] is sufficient for most providers —
        no per-provider plumbing needed. Providers with a native option name (see the
        alias maps above) also get that key set directly.
        """
        if 'inference' not in config_for_provider:
            config_for_provider['inference'] = {}
        if provider_name not in config_for_provider['inference']:
            config_for_provider['inference'][provider_name] = {}

        inference_section = config_for_provider['inference'][provider_name]
        for key, value in param_overrides.items():
            if value is None:
                continue
            inference_section[key] = value

            alias = None
            if key == 'context_window':
                alias = self._CONTEXT_WINDOW_ALIASES.get(provider_name)
            elif key == 'max_tokens':
                alias = self._MAX_TOKENS_ALIASES.get(provider_name)
            if alias:
                inference_section[alias] = value

        logger.debug(
            f"Applied adapter parameter overrides for provider '{provider_name}': {param_overrides}"
        )
