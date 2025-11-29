"""
Azure OpenAI inference service implementation using unified architecture.

This is a migrated version of the Azure OpenAI inference provider that uses
the new unified AI services architecture.

Compare with: server/inference/pipeline/providers/azure_provider.py (old implementation)
"""

from typing import Dict, Any, AsyncGenerator

from ...base import ServiceType
from ...providers import AzureBaseService
from ...services import InferenceService


class AzureOpenAIInferenceService(InferenceService, AzureBaseService):
    """
    Azure OpenAI inference service using unified architecture.

    This implementation is simpler because:
    1. Azure credentials and endpoint handling managed by AzureBaseService
    2. ChatCompletionsClient initialization handled by base class
    3. Configuration parsing handled by base classes
    4. Connection verification handled by base classes
    5. Error handling via _handle_azure_error()

    Old implementation: ~238 lines (azure_provider.py)
    New implementation: ~110 lines focused only on inference logic
    Reduction: ~54%

    Azure OpenAI provides enterprise-grade OpenAI models with:
    - Private endpoints
    - Azure Active Directory authentication
    - Compliance certifications (SOC, ISO, etc.)
    - Data residency options
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Azure OpenAI inference service.

        Args:
            config: Configuration dictionary

        Note: All Azure setup (endpoint, credentials, client, etc.) handled by AzureBaseService!
        """
        # Initialize base classes
        AzureBaseService.__init__(self, config, ServiceType.INFERENCE)
        InferenceService.__init__(self, config, "azure")

        # Get inference-specific configuration
        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=1024)
        self.top_p = self._get_top_p(default=0.8)

    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using Azure OpenAI.

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters (including 'messages' for native format)

        Returns:
            The generated response text
        """
        if not self.initialized:
            await self.initialize()

        try:
            # Check if we have messages format in kwargs
            messages_from_kwargs = kwargs.pop('messages', None)
            conversation_messages, system_prompt = self._build_messages(prompt, messages_from_kwargs)

            # Call Azure AI with messages and optional system prompt
            response = await self.client.complete(
                messages=conversation_messages,
                system=system_prompt,
                temperature=kwargs.pop('temperature', self.temperature),
                top_p=kwargs.pop('top_p', self.top_p),
                max_tokens=kwargs.pop('max_tokens', self.max_tokens),
                stream=False,
                **kwargs  # Any other Azure-specific parameters
            )

            if not response.choices or not response.choices[0].message:
                raise ValueError("No valid response from Azure AI API")

            return response.choices[0].message.content

        except Exception as e:
            self._handle_azure_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using Azure OpenAI.

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters (including 'messages' for native format)

        Yields:
            Response chunks as they are generated
        """
        if not self.initialized:
            await self.initialize()

        try:
            # Check if we have messages format in kwargs
            messages_from_kwargs = kwargs.pop('messages', None)
            conversation_messages, system_prompt = self._build_messages(prompt, messages_from_kwargs)

            # Call Azure AI with streaming enabled
            response = await self.client.complete(
                messages=conversation_messages,
                system=system_prompt,
                temperature=kwargs.pop('temperature', self.temperature),
                top_p=kwargs.pop('top_p', self.top_p),
                max_tokens=kwargs.pop('max_tokens', self.max_tokens),
                stream=True,
                **kwargs  # Any other Azure-specific parameters
            )

            # Stream the response chunks
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            self._handle_azure_error(e, "streaming generation")
            yield f"Error: {str(e)}"
