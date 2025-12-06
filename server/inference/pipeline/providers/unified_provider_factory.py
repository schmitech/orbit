"""
Unified Provider Factory

This factory creates LLM providers using the new unified AI services architecture,
while maintaining backward compatibility with the existing pipeline interface.
"""

import logging
from typing import Dict, Any, List
from .llm_provider import LLMProvider
from .unified_provider_adapter import create_unified_provider


class UnifiedProviderFactory:
    """
    Factory for creating LLM providers using the new unified architecture.

    This factory uses the AI services under the hood while maintaining
    compatibility with the existing pipeline LLMProvider interface.
    """

    @classmethod
    def _get_configured_providers(cls, config: Dict[str, Any]) -> List[str]:
        """
        Get list of providers configured in inference.yaml.

        Args:
            config: Application configuration dictionary

        Returns:
            List of provider names from the inference config
        """
        inference_config = config.get('inference', {})
        return list(inference_config.keys())

    @classmethod
    def _get_enabled_providers(cls, config: Dict[str, Any]) -> List[str]:
        """
        Get list of enabled providers from inference.yaml.

        Args:
            config: Application configuration dictionary

        Returns:
            List of enabled provider names
        """
        inference_config = config.get('inference', {})
        enabled = []
        for provider_name, provider_config in inference_config.items():
            if isinstance(provider_config, dict) and provider_config.get('enabled', False):
                enabled.append(provider_name)
        return enabled

    @classmethod
    def create_provider(cls, config: Dict[str, Any]) -> LLMProvider:
        """
        Create an LLM provider using the unified architecture.

        Args:
            config: Application configuration dictionary

        Returns:
            LLMProvider instance using the new unified architecture

        Raises:
            ValueError: If the provider is not configured

        Example:
            >>> factory = UnifiedProviderFactory()
            >>> provider = factory.create_provider(config)
            >>> await provider.initialize()
            >>> response = await provider.generate("Hello!")
        """
        provider_name = config['general'].get('inference_provider', 'openai')
        configured_providers = cls._get_configured_providers(config)

        if provider_name not in configured_providers:
            supported = ', '.join(configured_providers)
            raise ValueError(
                f"Unsupported provider '{provider_name}'. "
                f"Configured providers: {supported}"
            )

        logger = logging.getLogger(__name__)
        logger.debug(f"Creating provider '{provider_name}' using unified architecture")

        return create_unified_provider(provider_name, config)

    @classmethod
    def create_provider_by_name(
        cls,
        provider_name: str,
        config: Dict[str, Any]
    ) -> LLMProvider:
        """
        Create a provider by name using the unified architecture.

        Args:
            provider_name: Name of the provider
            config: Application configuration

        Returns:
            LLMProvider instance

        Raises:
            ValueError: If the provider is not configured
        """
        configured_providers = cls._get_configured_providers(config)

        if provider_name not in configured_providers:
            supported = ', '.join(configured_providers)
            raise ValueError(
                f"Unsupported provider '{provider_name}'. "
                f"Configured providers: {supported}"
            )

        logger = logging.getLogger(__name__)
        logger.info(f"Creating provider '{provider_name}' by name using unified architecture")

        return create_unified_provider(provider_name, config)

    @classmethod
    def list_providers(cls, config: Dict[str, Any]) -> List[str]:
        """
        List all configured providers from inference.yaml.

        Args:
            config: Application configuration dictionary

        Returns:
            List of configured provider names
        """
        return cls._get_configured_providers(config)

    @classmethod
    def list_available_providers(cls, config: Dict[str, Any]) -> List[str]:
        """
        List providers that are enabled in inference.yaml.

        Args:
            config: Application configuration dictionary

        Returns:
            List of enabled provider names
        """
        return cls._get_enabled_providers(config)
