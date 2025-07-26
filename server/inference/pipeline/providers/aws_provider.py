"""
AWS Bedrock Provider for Pipeline Architecture

This module provides a clean AWS Bedrock implementation for the pipeline architecture.
"""

import json
import logging
from typing import Dict, Any, AsyncGenerator
import boto3
from botocore.exceptions import ClientError
from .llm_provider import LLMProvider

class AWSBedrockProvider(LLMProvider):
    """
    Clean AWS Bedrock implementation for the pipeline architecture.
    
    This provider communicates directly with AWS Bedrock API without
    any legacy wrapper layers.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the AWS Bedrock provider.
        
        Args:
            config: Configuration dictionary containing AWS settings
        """
        self.config = config
        aws_config = config.get("inference", {}).get("aws", {})
        
        # AWS credentials and region
        self.access_key = aws_config.get("access_key")
        self.secret_access_key = aws_config.get("secret_access_key")
        self.region = aws_config.get("region", "us-east-1")
        
        # Model configuration
        self.model = aws_config.get("model", "anthropic.claude-3-sonnet-20240229-v1:0")
        self.max_tokens = aws_config.get("max_tokens", 1024)
        self.temperature = aws_config.get("temperature", 0.1)
        self.top_p = aws_config.get("top_p", 0.8)
        
        # Response format
        self.content_type = aws_config.get("content_type", "application/json")
        self.accept = aws_config.get("accept", "application/json")
        
        self.client = None
        self.logger = logging.getLogger(__name__)
        self.verbose = config.get('general', {}).get('verbose', False)
    
    async def initialize(self) -> None:
        """Initialize the AWS Bedrock client."""
        try:
            # Create boto3 client with explicit credentials if provided
            if self.access_key and self.secret_access_key:
                self.client = boto3.client(
                    "bedrock-runtime",
                    region_name=self.region,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_access_key
                )
            else:
                # Use default AWS credentials (IAM role, environment, etc.)
                self.client = boto3.client(
                    "bedrock-runtime",
                    region_name=self.region
                )
            
            self.logger.info(f"Initialized AWS Bedrock provider with model: {self.model} in region: {self.region}")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize AWS Bedrock client: {str(e)}")
            raise
    
    def _prepare_messages(self, prompt: str) -> list:
        """
        Prepare messages in the format expected by AWS Bedrock.
        
        Args:
            prompt: The input prompt
            
        Returns:
            List of message dictionaries
        """
        # For now, we treat the entire prompt as a user message
        # The system prompt is already included in the prompt from the pipeline
        return [{"role": "user", "content": prompt}]
    
    def _extract_system_prompt(self, prompt: str) -> tuple[str, str]:
        """
        Extract system prompt and user message from the combined prompt.
        
        AWS Bedrock models like Claude expect system and user messages separately.
        
        Args:
            prompt: The combined prompt
            
        Returns:
            Tuple of (system_prompt, user_message)
        """
        # Look for common patterns that separate system prompt from user message
        if "\nUser:" in prompt and "Assistant:" in prompt:
            # Split on User: to separate system context from user message
            parts = prompt.split("\nUser:", 1)
            if len(parts) == 2:
                system_part = parts[0].strip()
                user_part = parts[1].replace("Assistant:", "").strip()
                return system_part, user_part
        
        # If no clear separation, treat entire prompt as user message
        return "", prompt
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using AWS Bedrock.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Returns:
            The generated response text
        """
        if not self.client:
            await self.initialize()
        
        try:
            # Extract system prompt and user message
            system_prompt, user_message = self._extract_system_prompt(prompt)
            
            # Prepare the request body based on the model
            if "claude" in self.model.lower():
                # Claude models use this format
                body = {
                    "messages": [{"role": "user", "content": user_message}],
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                    "top_p": self.top_p,
                    "anthropic_version": "bedrock-2023-05-31"
                }
                if system_prompt:
                    body["system"] = system_prompt
            else:
                # Generic format for other models
                body = {
                    "prompt": prompt,
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                    "top_p": self.top_p
                }
            
            if self.verbose:
                self.logger.debug(f"Sending request to AWS Bedrock: model={self.model}")
            
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
            if "claude" in self.model.lower():
                # Claude response format
                if 'content' in response_body and response_body['content']:
                    return response_body['content'][0]['text']
                else:
                    self.logger.error(f"Unexpected Claude response format: {response_body}")
                    raise ValueError("Invalid response format from Claude model")
            else:
                # Try common response formats
                if 'completion' in response_body:
                    return response_body['completion']
                elif 'completions' in response_body:
                    return response_body['completions'][0]['data']['text']
                elif 'text' in response_body:
                    return response_body['text']
                else:
                    self.logger.error(f"Unknown response format: {response_body}")
                    raise ValueError("Unknown response format from model")
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            self.logger.error(f"AWS Bedrock API error [{error_code}]: {error_message}")
            raise
        except Exception as e:
            self.logger.error(f"Error generating response with AWS Bedrock: {str(e)}")
            raise
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using AWS Bedrock.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Yields:
            Response chunks as they are generated
        """
        if not self.client:
            await self.initialize()
        
        try:
            # Extract system prompt and user message
            system_prompt, user_message = self._extract_system_prompt(prompt)
            
            # Prepare the request body
            if "claude" in self.model.lower():
                body = {
                    "messages": [{"role": "user", "content": user_message}],
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                    "top_p": self.top_p,
                    "anthropic_version": "bedrock-2023-05-31"
                }
                if system_prompt:
                    body["system"] = system_prompt
            else:
                body = {
                    "prompt": prompt,
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                    "top_p": self.top_p
                }
            
            if self.verbose:
                self.logger.debug(f"Starting streaming request to AWS Bedrock: model={self.model}")
            
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
                    if "claude" in self.model.lower():
                        # Claude streaming format
                        if chunk_data.get('type') == 'content_block_delta':
                            if 'delta' in chunk_data and 'text' in chunk_data['delta']:
                                yield chunk_data['delta']['text']
                    else:
                        # Try common streaming formats
                        if 'completion' in chunk_data:
                            yield chunk_data['completion']
                        elif 'text' in chunk_data:
                            yield chunk_data['text']
                        elif 'delta' in chunk_data:
                            yield chunk_data['delta'].get('text', '')
                
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            self.logger.error(f"AWS Bedrock streaming error [{error_code}]: {error_message}")
            yield f"Error: {error_message}"
        except Exception as e:
            self.logger.error(f"Error generating streaming response with AWS Bedrock: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def close(self) -> None:
        """Clean up the AWS Bedrock client."""
        # boto3 clients don't need explicit cleanup
        self.client = None
        self.logger.info("AWS Bedrock provider closed")
    
    async def validate_config(self) -> bool:
        """
        Validate the AWS Bedrock configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            if not self.region:
                self.logger.error("AWS region is missing")
                return False
            
            if not self.model:
                self.logger.error("AWS Bedrock model is missing")
                return False
            
            # Initialize client if needed
            if not self.client:
                await self.initialize()
            
            # Try to list available models to test connection
            try:
                # This is a lightweight operation to test connectivity
                response = self.client.list_foundation_models()
                if self.verbose:
                    self.logger.info(f"AWS Bedrock connection validated. Found {len(response.get('modelSummaries', []))} models")
                return True
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'UnrecognizedClientException':
                    self.logger.error("Invalid AWS credentials")
                else:
                    self.logger.error(f"AWS Bedrock validation error: {e.response['Error']['Message']}")
                return False
                
        except Exception as e:
            self.logger.error(f"AWS Bedrock configuration validation failed: {str(e)}")
            return False