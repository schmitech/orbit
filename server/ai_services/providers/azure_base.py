"""
Azure-specific base class for all Azure AI services.

This module provides a unified base class for all Azure AI-based services,
consolidating common functionality like credential management, client initialization,
and error handling for Azure services.
"""

from typing import Dict, Any, Optional
import logging

from ..base import ProviderAIService, ServiceType
from ..connection import RetryHandler


class AzureBaseService(ProviderAIService):
    """
    Base class for all Azure AI services.

    This class consolidates:
    - Azure endpoint and API key resolution
    - ChatCompletionsClient initialization
    - Deployment name configuration
    - API version management
    - Connection verification
    - Common Azure error handling patterns
    """

    DEFAULT_API_VERSION = "2024-06-01"

    def __init__(self, config: Dict[str, Any], service_type: ServiceType = None, provider_name: str = "azure"):
        """
        Initialize the azure base service.

        Args:
            config: Configuration dictionary
            service_type: Type of AI service
            provider_name: Provider name (defaults to "azure")
        """
        # For cooperative multiple inheritance
        if service_type:
            super().__init__(config, service_type, provider_name)
        else:
            super().__init__(config, ServiceType.INFERENCE, provider_name)
        self._setup_azure_config()

    def _setup_azure_config(self) -> None:
        """
        Set up Azure-specific configuration.

        This method:
        1. Resolves the Azure endpoint
        2. Resolves the API key
        3. Gets the deployment name
        4. Sets the API version
        5. Initializes the Azure AI client
        """
        azure_config = self._extract_provider_config()

        # Get Azure endpoint (required)
        self.endpoint = azure_config.get("endpoint")
        if not self.endpoint:
            raise ValueError(
                "Azure endpoint is required. Set it in configuration under azure.endpoint"
            )

        # Get API key (required)
        self.api_key = azure_config.get("api_key") or self._resolve_api_key("AZURE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Azure API key is required. Set AZURE_API_KEY environment "
                "variable or provide in configuration."
            )

        # Get deployment name (model name in Azure)
        self.deployment = azure_config.get("deployment_name") or azure_config.get("deployment", "gpt-35-turbo")

        # Get API version
        self.api_version = azure_config.get("api_version", self.DEFAULT_API_VERSION)

        # Initialize Azure AI client
        try:
            from azure.ai.inference import ChatCompletionsClient
            from azure.core.credentials import AzureKeyCredential

            self.client = ChatCompletionsClient(
                endpoint=self.endpoint,
                credential=AzureKeyCredential(self.api_key),
                api_version=self.api_version
            )
        except ImportError:
            raise ImportError(
                "azure-ai-inference package not installed. "
                "Please install with: pip install azure-ai-inference"
            )

        # Setup retry handler
        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(
            max_retries=retry_config['max_retries'],
            initial_wait_ms=retry_config['initial_wait_ms'],
            max_wait_ms=retry_config['max_wait_ms'],
            exponential_base=retry_config['exponential_base'],
            enabled=retry_config['enabled']
        )

        self.logger.info(
            f"Configured Azure AI service with deployment: {self.deployment}"
        )

    async def initialize(self) -> bool:
        """
        Initialize the Azure AI service.

        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # Verify connection
            if await self.verify_connection():
                self.initialized = True
                self.logger.info(
                    f"Initialized Azure AI {self.service_type.value} service "
                    f"with deployment {self.deployment}"
                )
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to initialize Azure AI service: {str(e)}")
            return False

    async def verify_connection(self) -> bool:
        """
        Verify Azure AI connection with a test request.

        Returns:
            True if the connection is working, False otherwise
        """
        try:
            # Test with a minimal request
            response = await self.client.complete(
                messages=[{"role": "user", "content": "test"}],
                max_tokens=1,
                temperature=0
            )

            if not response.choices:
                self.logger.error("Azure AI connection test returned no responses")
                return False

            self.logger.debug("Azure AI connection verified successfully")
            return True
        except Exception as e:
            self.logger.error(f"Azure AI connection verification failed: {str(e)}")
            return False

    async def close(self) -> None:
        """
        Close the Azure AI service and release resources.

        Note: Azure AI client doesn't require explicit cleanup
        """
        self.client = None
        self.initialized = False
        self.logger.debug("Closed Azure AI service")

    def _get_max_tokens(self, default: int = 1024) -> int:
        """
        Get max_tokens configuration.

        Args:
            default: Default value if not configured

        Returns:
            Maximum number of tokens
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('max_tokens', default)

    def _get_temperature(self, default: float = 0.7) -> float:
        """
        Get temperature configuration.

        Args:
            default: Default value if not configured

        Returns:
            Temperature value
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('temperature', default)

    def _get_top_p(self, default: float = 1.0) -> float:
        """
        Get top_p configuration.

        Args:
            default: Default value if not configured

        Returns:
            Top P value
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('top_p', default)

    def _build_messages(self, prompt: str, messages: list = None) -> tuple[list, str | None]:
        """
        Build messages and system prompt in the format expected by Azure AI.

        Azure AI (like OpenAI) separates system prompts from conversation messages.

        Args:
            prompt: The input prompt string (used as a fallback)
            messages: An optional list of message dictionaries

        Returns:
            A tuple containing (conversation_messages, system_prompt)
        """
        system_prompt = None
        conversation_messages = []

        if messages:
            # Case 1: Process a list of messages
            for message in messages:
                if message.get("role") == "system":
                    system_prompt = message.get("content")
                else:
                    conversation_messages.append(message)
        else:
            # Case 2: Parse the raw prompt string
            if "\nUser:" in prompt and "Assistant:" in prompt:
                parts = prompt.split("\nUser:", 1)
                if len(parts) == 2:
                    system_prompt = parts[0].strip()
                    user_part = parts[1].replace("Assistant:", "").strip()
                    conversation_messages = [{"role": "user", "content": user_part}]
            else:
                # If no clear separation, treat entire prompt as user message
                conversation_messages = [{"role": "user", "content": prompt}]

        # Ensure there's at least one message
        if not conversation_messages:
            conversation_messages = [{"role": "user", "content": ""}]

        return conversation_messages, system_prompt

    def _handle_azure_error(self, error: Exception, operation: str = "operation") -> None:
        """
        Handle Azure-specific errors with appropriate logging.

        Args:
            error: The exception that occurred
            operation: Description of the operation that failed
        """
        error_str = str(error)

        if "authentication" in error_str.lower() or "unauthorized" in error_str.lower():
            self.logger.error(
                f"Azure authentication failed during {operation}: Invalid credentials"
            )
        elif "rate limit" in error_str.lower() or "throttl" in error_str.lower():
            self.logger.warning(
                f"Azure rate limit exceeded during {operation}"
            )
        elif "quota" in error_str.lower():
            self.logger.error(
                f"Azure quota exceeded during {operation}: {error_str}"
            )
        elif "deployment" in error_str.lower():
            self.logger.error(
                f"Azure deployment error during {operation}: {error_str}"
            )
        else:
            self.logger.error(
                f"Azure error during {operation}: {error_str}"
            )
