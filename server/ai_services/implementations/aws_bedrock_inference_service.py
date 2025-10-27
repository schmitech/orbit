"""
AWS Bedrock inference service implementation using unified architecture.

This is a migrated version of the AWS Bedrock inference provider that uses
the new unified AI services architecture.

Compare with: server/inference/pipeline/providers/aws_provider.py (old implementation)
"""

import json
from typing import Dict, Any, AsyncGenerator
from botocore.exceptions import ClientError

from ..base import ServiceType
from ..providers import AWSBaseService
from ..services import InferenceService


class AWSBedrockInferenceService(InferenceService, AWSBaseService):
    """
    AWS Bedrock inference service using unified architecture.

    This implementation is simpler because:
    1. AWS credentials management handled by AWSBaseService
    2. boto3 client initialization handled by base class
    3. Configuration parsing handled by base classes
    4. Connection verification handled by base classes
    5. Error handling via _handle_aws_error()

    Old implementation: ~335 lines (aws_provider.py)
    New implementation: ~180 lines focused only on inference logic
    Reduction: ~46%

    Supports multiple models via AWS Bedrock:
    - Anthropic Claude models (claude-3-sonnet, claude-3-haiku, etc.)
    - Amazon Titan models
    - AI21 Jurassic models
    - Cohere Command models
    - Meta Llama models
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the AWS Bedrock inference service.

        Args:
            config: Configuration dictionary

        Note: All AWS setup (credentials, client, etc.) handled by AWSBaseService!
        """
        # Initialize base classes
        AWSBaseService.__init__(self, config, ServiceType.INFERENCE)
        InferenceService.__init__(self, config, "aws")

        # Get inference-specific configuration
        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=1024)
        self.top_p = self._get_top_p(default=0.8)

    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using AWS Bedrock.

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
            messages = kwargs.pop('messages', None)
            system_prompt, conversation_messages = self._build_messages(prompt, messages)

            # Prepare the request body based on the model type
            if self.model and "claude" in self.model.lower():
                # Claude models use the messages API format
                body = {
                    "messages": conversation_messages,
                    "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
                    "temperature": kwargs.pop('temperature', self.temperature),
                    "top_p": kwargs.pop('top_p', self.top_p),
                    "anthropic_version": "bedrock-2023-05-31"
                }
                if system_prompt:
                    body["system"] = system_prompt
            else:
                # For other models (Titan, Jurassic, etc.), use prompt format
                full_prompt = "\n".join([msg.get("content", "") for msg in conversation_messages])
                if system_prompt:
                    full_prompt = f"{system_prompt}\n\n{full_prompt}"

                body = {
                    "prompt": full_prompt,
                    "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
                    "temperature": kwargs.pop('temperature', self.temperature),
                    "top_p": kwargs.pop('top_p', self.top_p),
                    **kwargs  # Any other model-specific parameters
                }

            # Invoke the model
            response = self.client.invoke_model(
                modelId=self.model,
                contentType=self.content_type,
                accept=self.accept,
                body=json.dumps(body)
            )

            # Parse the response
            response_body = json.loads(response['body'].read().decode('utf-8'))

            # Extract text based on model type
            if self.model and "claude" in self.model.lower():
                # Claude response format
                if 'content' in response_body and response_body['content']:
                    return response_body['content'][0]['text']
                else:
                    raise ValueError("Invalid response format from Claude model")
            else:
                # Try common response formats for other models
                if 'completion' in response_body:
                    return response_body['completion']
                elif 'completions' in response_body:
                    return response_body['completions'][0]['data']['text']
                elif 'text' in response_body:
                    return response_body['text']
                else:
                    raise ValueError(f"Unknown response format from model: {list(response_body.keys())}")

        except Exception as e:
            self._handle_aws_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using AWS Bedrock.

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
            messages = kwargs.pop('messages', None)
            system_prompt, conversation_messages = self._build_messages(prompt, messages)

            # Prepare the request body based on the model type
            if self.model and "claude" in self.model.lower():
                # Claude models use the messages API format
                body = {
                    "messages": conversation_messages,
                    "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
                    "temperature": kwargs.pop('temperature', self.temperature),
                    "top_p": kwargs.pop('top_p', self.top_p),
                    "anthropic_version": "bedrock-2023-05-31"
                }
                if system_prompt:
                    body["system"] = system_prompt
            else:
                # For other models, use prompt format
                full_prompt = "\n".join([msg.get("content", "") for msg in conversation_messages])
                if system_prompt:
                    full_prompt = f"{system_prompt}\n\n{full_prompt}"

                body = {
                    "prompt": full_prompt,
                    "max_tokens": kwargs.pop('max_tokens', self.max_tokens),
                    "temperature": kwargs.pop('temperature', self.temperature),
                    "top_p": kwargs.pop('top_p', self.top_p),
                    **kwargs
                }

            # Invoke the model with streaming
            response = self.client.invoke_model_with_response_stream(
                modelId=self.model,
                contentType=self.content_type,
                accept=self.accept,
                body=json.dumps(body)
            )

            # Process the streaming response
            for event in response['body']:
                if 'chunk' in event:
                    chunk_data = json.loads(event['chunk']['bytes'].decode('utf-8'))

                    # Extract text based on model type
                    if self.model and "claude" in self.model.lower():
                        # Claude streaming format
                        if chunk_data.get('type') == 'content_block_delta':
                            if 'delta' in chunk_data and 'text' in chunk_data['delta']:
                                yield chunk_data['delta']['text']
                    else:
                        # Try common streaming formats for other models
                        if 'completion' in chunk_data:
                            yield chunk_data['completion']
                        elif 'text' in chunk_data:
                            yield chunk_data['text']
                        elif 'delta' in chunk_data:
                            yield chunk_data['delta'].get('text', '')

        except Exception as e:
            self._handle_aws_error(e, "streaming generation")
            yield f"Error: {str(e)}"
