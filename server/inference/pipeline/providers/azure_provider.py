"""
Azure AI Provider for Pipeline Architecture

This module provides a clean Azure AI implementation for the pipeline architecture.
"""

import logging
from typing import Dict, Any, AsyncGenerator
from .llm_provider import LLMProvider

class AzureProvider(LLMProvider):
    """
    Clean Azure AI implementation for the pipeline architecture.
    
    This provider communicates directly with Azure AI using the official SDK
    without any legacy wrapper layers.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Azure AI provider.
        
        Args:
            config: Configuration dictionary containing Azure AI settings
        """
        self.config = config
        azure_config = config.get("inference", {}).get("azure", {})
        
        self.endpoint = azure_config.get("endpoint")
        self.api_key = azure_config.get("api_key")
        self.deployment = azure_config.get("deployment_name", azure_config.get("deployment", "gpt-35-turbo"))
        self.temperature = azure_config.get("temperature", 0.1)
        self.top_p = azure_config.get("top_p", 0.8)
        self.max_tokens = azure_config.get("max_tokens", 1024)
        self.api_version = azure_config.get("api_version", "2024-06-01")
        
        self.client = None
        self.logger = logging.getLogger(__name__)
        self.verbose = config.get('general', {}).get('verbose', False)
    
    async def initialize(self) -> None:
        """Initialize the Azure AI provider."""
        try:
            from azure.ai.inference import ChatCompletionsClient
            from azure.core.credentials import AzureKeyCredential
            
            if not self.endpoint:
                raise ValueError("Azure AI endpoint is required")
            
            if not self.api_key:
                raise ValueError("Azure AI API key is required")
            
            self.client = ChatCompletionsClient(
                endpoint=self.endpoint,
                credential=AzureKeyCredential(self.api_key),
                api_version=self.api_version
            )
            
            self.logger.info(f"Initialized Azure AI provider with deployment: {self.deployment}")
            
        except ImportError:
            self.logger.error("azure-ai-inference package not installed. Please install with: pip install azure-ai-inference")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize Azure AI client: {str(e)}")
            raise
    
    def _build_messages(self, prompt: str, messages: list = None) -> tuple[list, str | None]:
        """
        Build messages and system prompt in the format expected by Azure AI.
        
        Args:
            prompt: The input prompt (used if messages is None).
            messages: Optional list of message dictionaries.
            
        Returns:
            Tuple of (messages_list, system_prompt_string).
        """
        system_prompt = None
        conversation_messages = []

        if messages:
            # Process a list of messages
            for message in messages:
                if message.get("role") == "system":
                    system_prompt = message.get("content")
                else:
                    conversation_messages.append(message)
        else:
            # Parse the raw prompt string
            if "\nUser:" in prompt and "Assistant:" in prompt:
                parts = prompt.split("\nUser:", 1)
                if len(parts) == 2:
                    system_prompt = parts[0].strip()
                    user_part = parts[1].replace("Assistant:", "").strip()
                    conversation_messages = [{"role": "user", "content": user_part}]
            else:
                # If no clear separation, treat entire prompt as user message
                conversation_messages = [{"role": "user", "content": prompt}]

        if not conversation_messages:
             conversation_messages = [{"role": "user", "content": ""}]

        return conversation_messages, system_prompt
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using Azure AI.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Returns:
            The generated response text
        """
        if not self.client:
            await self.initialize()
        
        try:
            # Build messages and system prompt
            messages_from_kwarg = kwargs.pop('messages', None)
            messages, system_prompt = self._build_messages(prompt, messages_from_kwarg)
            
            if self.verbose:
                self.logger.debug(f"Generating with Azure AI: deployment={self.deployment}, temperature={self.temperature}")
            
            response = await self.client.complete(
                messages=messages,
                system=system_prompt,
                temperature=kwargs.get("temperature", self.temperature),
                top_p=kwargs.get("top_p", self.top_p),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
                stream=False,
                **{k: v for k, v in kwargs.items() if k not in ["temperature", "top_p", "max_tokens"]}
            )
            
            if not response.choices or not response.choices[0].message:
                raise Exception("No valid response from Azure AI API")
            
            return response.choices[0].message.content
            
        except Exception as e:
            self.logger.error(f"Error generating response with Azure AI: {str(e)}")
            raise
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using Azure AI.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Yields:
            Response chunks as they are generated
        """
        if not self.client:
            await self.initialize()
        
        try:
            # Build messages and system prompt
            messages_from_kwarg = kwargs.pop('messages', None)
            messages, system_prompt = self._build_messages(prompt, messages_from_kwarg)
            
            if self.verbose:
                self.logger.debug(f"Starting streaming generation with Azure AI")
            
            response = await self.client.complete(
                messages=messages,
                system=system_prompt,
                temperature=kwargs.get("temperature", self.temperature),
                top_p=kwargs.get("top_p", self.top_p),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
                stream=True,
                **{k: v for k, v in kwargs.items() if k not in ["temperature", "top_p", "max_tokens", "stream"]}
            )
            
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            self.logger.error(f"Error generating streaming response with Azure AI: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def close(self) -> None:
        """Clean up the Azure AI provider."""
        # Azure AI client doesn't require explicit cleanup
        self.client = None
        self.logger.info("Azure AI provider closed")
    
    async def validate_config(self) -> bool:
        """
        Validate the Azure AI configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            if not self.endpoint:
                self.logger.error("Azure AI endpoint is missing")
                return False
            
            if not self.api_key:
                self.logger.error("Azure AI API key is missing")
                return False
            
            if not self.deployment:
                self.logger.error("Azure AI deployment is missing")
                return False
            
            # Test connection with a simple request
            if not self.client:
                await self.initialize()
            
            # Validate with a minimal test
            response = await self.client.complete(
                messages=[{"role": "user", "content": "test"}],
                max_tokens=1,
                temperature=0
            )
            
            if not response.choices:
                self.logger.error("No response from Azure AI")
                return False
            
            if self.verbose:
                self.logger.info("Azure AI configuration validated successfully")
            
            return True
            
        except ImportError:
            self.logger.error("azure-ai-inference package not installed")
            return False
        except Exception as e:
            self.logger.error(f"Azure AI configuration validation failed: {str(e)}")
            return False