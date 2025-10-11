"""
Configuration utilities for AI services.

This module provides utilities for parsing, validating, and managing
configuration for all AI services.
"""

import os
import logging
from typing import Dict, Any, Optional, List
import re

logger = logging.getLogger(__name__)


class ConfigResolver:
    """
    Resolves configuration values with support for environment variables
    and template substitution.
    """

    @staticmethod
    def resolve_value(value: Any) -> Any:
        """
        Resolve a configuration value, substituting environment variables
        if present.

        Supports formats like:
        - ${ENV_VAR} - substitutes the entire value
        - "prefix_${ENV_VAR}_suffix" - substitutes within a string

        Args:
            value: The value to resolve

        Returns:
            Resolved value
        """
        if not isinstance(value, str):
            return value

        # Pattern for ${VAR_NAME}
        pattern = r'\$\{([^}]+)\}'

        # Check if the entire value is a single environment variable reference
        if value.startswith('${') and value.endswith('}'):
            env_var = value[2:-1]
            resolved = os.environ.get(env_var)
            if resolved is None:
                logger.warning(f"Environment variable {env_var} not found")
            return resolved

        # Replace all ${VAR} occurrences in the string
        def replace_env_var(match):
            env_var = match.group(1)
            env_value = os.environ.get(env_var)
            if env_value is None:
                logger.warning(f"Environment variable {env_var} not found")
                return match.group(0)  # Keep original if not found
            return env_value

        return re.sub(pattern, replace_env_var, value)

    @staticmethod
    def resolve_dict(config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively resolve all values in a configuration dictionary.

        Args:
            config: Configuration dictionary

        Returns:
            Resolved configuration dictionary
        """
        resolved = {}

        for key, value in config.items():
            if isinstance(value, dict):
                resolved[key] = ConfigResolver.resolve_dict(value)
            elif isinstance(value, list):
                resolved[key] = [
                    ConfigResolver.resolve_dict(item) if isinstance(item, dict)
                    else ConfigResolver.resolve_value(item)
                    for item in value
                ]
            else:
                resolved[key] = ConfigResolver.resolve_value(value)

        return resolved


class ConfigValidator:
    """
    Validates configuration for AI services.
    """

    @staticmethod
    def validate_required_fields(
        config: Dict[str, Any],
        required_fields: List[str],
        config_name: str = "configuration"
    ) -> bool:
        """
        Validate that required fields are present in configuration.

        Args:
            config: Configuration dictionary
            required_fields: List of required field names
            config_name: Name of the configuration (for error messages)

        Returns:
            True if all required fields are present, False otherwise
        """
        missing_fields = []

        for field in required_fields:
            # Support nested field checking with dot notation
            if '.' in field:
                parts = field.split('.')
                current = config
                for part in parts:
                    if not isinstance(current, dict) or part not in current:
                        missing_fields.append(field)
                        break
                    current = current[part]
            else:
                if field not in config:
                    missing_fields.append(field)

        if missing_fields:
            logger.error(
                f"Missing required fields in {config_name}: {', '.join(missing_fields)}"
            )
            return False

        return True

    @staticmethod
    def validate_url(url: str) -> bool:
        """
        Validate that a string is a valid URL.

        Args:
            url: URL to validate

        Returns:
            True if valid, False otherwise
        """
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
            r'localhost|'  # localhost
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # or IP
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE
        )

        return bool(url_pattern.match(url))

    @staticmethod
    def validate_positive_number(value: Any, field_name: str) -> bool:
        """
        Validate that a value is a positive number.

        Args:
            value: Value to validate
            field_name: Name of the field (for error messages)

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(value, (int, float)):
            logger.error(f"{field_name} must be a number, got {type(value).__name__}")
            return False

        if value <= 0:
            logger.error(f"{field_name} must be positive, got {value}")
            return False

        return True


class EndpointManager:
    """
    Manages endpoint resolution and fallback logic for AI services.

    This class handles configurable endpoints to support easy API version
    updates without code changes.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        provider: str,
        service_type: str
    ):
        """
        Initialize the endpoint manager.

        Args:
            config: Full configuration dictionary
            provider: Provider name (e.g., 'openai', 'anthropic')
            service_type: Service type (e.g., 'embeddings', 'inference')
        """
        self.config = config
        self.provider = provider
        self.service_type = service_type
        self.logger = logging.getLogger(f"{__name__}.EndpointManager")

    def get_endpoint(self, endpoint_name: str = None) -> str:
        """
        Get endpoint for the service with fallback logic.

        Resolution order:
        1. Service-specific endpoint configuration
        2. Provider-specific endpoint configuration
        3. Default endpoint based on service type

        Args:
            endpoint_name: Optional specific endpoint name (for multiple endpoints)

        Returns:
            Endpoint path
        """
        # Try service-specific endpoint
        service_endpoint = self._get_service_endpoint(endpoint_name)
        if service_endpoint:
            return service_endpoint

        # Try provider-specific endpoint
        provider_endpoint = self._get_provider_endpoint(endpoint_name)
        if provider_endpoint:
            return provider_endpoint

        # Use default endpoint
        return self._get_default_endpoint(endpoint_name)

    def _get_service_endpoint(self, endpoint_name: Optional[str] = None) -> Optional[str]:
        """
        Get endpoint from service-specific configuration.

        Args:
            endpoint_name: Optional specific endpoint name

        Returns:
            Endpoint path or None if not found
        """
        service_config = self.config.get(self.service_type, {}).get(self.provider, {})

        # Check for single endpoint
        if 'endpoint' in service_config:
            return service_config['endpoint']

        # Check for endpoints dictionary
        endpoints = service_config.get('endpoints', {})
        if endpoint_name and endpoint_name in endpoints:
            return endpoints[endpoint_name]

        return None

    def _get_provider_endpoint(self, endpoint_name: Optional[str] = None) -> Optional[str]:
        """
        Get endpoint from provider-specific configuration.

        Args:
            endpoint_name: Optional specific endpoint name

        Returns:
            Endpoint path or None if not found
        """
        provider_config = self.config.get(self.provider, {})

        # Check for single endpoint
        if 'endpoint' in provider_config:
            return provider_config['endpoint']

        # Check for endpoints dictionary
        endpoints = provider_config.get('endpoints', {})
        if endpoint_name and endpoint_name in endpoints:
            return endpoints[endpoint_name]

        return None

    def _get_default_endpoint(self, endpoint_name: Optional[str] = None) -> str:
        """
        Get default endpoint based on service type and endpoint name.

        Args:
            endpoint_name: Optional specific endpoint name

        Returns:
            Default endpoint path
        """
        # Default endpoints by service type
        defaults = {
            'embeddings': '/v1/embeddings',
            'inference': '/v1/chat/completions',
            'moderation': '/v1/moderations',
            'reranking': '/v1/rerank',
            'vision': '/v1/chat/completions',
            'audio': '/v1/audio/transcriptions'
        }

        # Specific endpoint defaults
        specific_defaults = {
            'embeddings': {
                'embeddings': '/v1/embeddings',
                'models': '/v1/models',
            },
            'inference': {
                'chat': '/v1/chat/completions',
                'completions': '/v1/completions',
                'models': '/v1/models',
            },
            'audio': {
                'transcribe': '/v1/audio/transcriptions',
                'translate': '/v1/audio/translations',
                'speech': '/v1/audio/speech',
            }
        }

        # Try to get specific endpoint default
        if endpoint_name and self.service_type in specific_defaults:
            specific = specific_defaults[self.service_type].get(endpoint_name)
            if specific:
                return specific

        # Return service type default
        return defaults.get(self.service_type, '/v1/endpoint')

    def get_all_endpoints(self) -> Dict[str, str]:
        """
        Get all configured endpoints for this service.

        Returns:
            Dictionary mapping endpoint names to paths
        """
        service_config = self.config.get(self.service_type, {}).get(self.provider, {})
        endpoints = service_config.get('endpoints', {})

        if not endpoints and 'endpoint' in service_config:
            # Single endpoint configuration
            return {'default': service_config['endpoint']}

        return endpoints


class ConfigMerger:
    """
    Merges multiple configuration sources with proper precedence.
    """

    @staticmethod
    def merge_configs(*configs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge multiple configuration dictionaries.

        Later configs take precedence over earlier ones.

        Args:
            *configs: Configuration dictionaries to merge

        Returns:
            Merged configuration dictionary
        """
        merged = {}

        for config in configs:
            merged = ConfigMerger._deep_merge(merged, config)

        return merged

    @staticmethod
    def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deep merge two dictionaries.

        Args:
            base: Base dictionary
            override: Override dictionary (takes precedence)

        Returns:
            Merged dictionary
        """
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = ConfigMerger._deep_merge(result[key], value)
            else:
                result[key] = value

        return result
