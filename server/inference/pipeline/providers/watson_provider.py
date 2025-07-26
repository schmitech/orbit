"""
IBM Watson AI Provider for Pipeline Architecture

This module provides a clean IBM Watson AI implementation for the pipeline architecture.
"""

import logging
import asyncio
from typing import Dict, Any, AsyncGenerator
from .llm_provider import LLMProvider

class WatsonProvider(LLMProvider):
    """
    Clean IBM Watson AI implementation for the pipeline architecture.
    
    This provider communicates directly with IBM Watson AI using the official SDK
    without any legacy wrapper layers.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Watson AI provider.
        
        Args:
            config: Configuration dictionary containing Watson AI settings
        """
        self.config = config
        watson_config = config.get("inference", {}).get("watson", {})
        
        self.api_key = watson_config.get("api_key")
        self.url = watson_config.get("api_base", watson_config.get("url"))
        self.project_id = watson_config.get("project_id")
        self.space_id = watson_config.get("space_id")
        self.instance_id = watson_config.get("instance_id")
        self.region = watson_config.get("region")
        self.auth_type = watson_config.get("auth_type", "iam")
        
        self.model_id = watson_config.get("model", "meta-llama/llama-3-8b-instruct")
        self.temperature = watson_config.get("temperature", 0.1)
        self.top_p = watson_config.get("top_p", 0.8)
        self.top_k = watson_config.get("top_k", 20)
        self.max_tokens = watson_config.get("max_tokens", 1024)
        self.time_limit = watson_config.get("time_limit", 10000)
        self.verify = watson_config.get("verify", False)
        
        self.watson_client = None
        self.model = None
        self.logger = logging.getLogger(__name__)
        self.verbose = config.get('general', {}).get('verbose', False)
    
    async def initialize(self) -> None:
        """Initialize the Watson AI provider."""
        try:
            from ibm_watsonx_ai import APIClient
            from ibm_watsonx_ai import Credentials
            from ibm_watsonx_ai.foundation_models import ModelInference
            
            if not self.api_key:
                raise ValueError("Watson AI API key is required")
            
            if not self.url:
                raise ValueError("Watson AI URL is required")
            
            if not self.project_id and not self.space_id:
                raise ValueError("Watson AI project_id or space_id is required")
            
            # Initialize Watson credentials with proper authentication
            credential_params = {
                'url': self.url,
                'api_key': self.api_key
            }
            
            # Add additional authentication parameters if provided
            if self.instance_id:
                credential_params['instance_id'] = self.instance_id
            if self.region:
                credential_params['region'] = self.region
                
            # For IBM Cloud (watsonx.ai) authentication
            if 'cloud.ibm.com' in self.url.lower() or 'watsonx' in self.url.lower():
                # This is IBM Cloud watsonx.ai - use IAM authentication
                credentials = Credentials(
                    url=self.url,
                    api_key=self.api_key
                )
            else:
                # This might be Cloud Pak for Data - use all parameters
                credentials = Credentials(**credential_params)
            
            # Initialize Watson client
            self.watson_client = APIClient(credentials)
            
            # Set up model parameters
            params = {
                "time_limit": self.time_limit,
                "max_new_tokens": self.max_tokens,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "top_k": self.top_k
            }
            
            # Initialize model inference
            self.model = ModelInference(
                model_id=self.model_id,
                api_client=self.watson_client,
                params=params,
                project_id=self.project_id,
                space_id=self.space_id,
                verify=self.verify,
            )
            
            self.logger.info(f"Initialized Watson AI provider with model: {self.model_id}")
            
        except ImportError:
            self.logger.error("ibm-watsonx-ai package not installed. Please install with: pip install ibm-watsonx-ai")
            raise
        except Exception as e:
            self.logger.error(f"Failed to initialize Watson AI client: {str(e)}")
            raise
    
    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.
        
        Args:
            text: Text to estimate tokens for
            
        Returns:
            Estimated token count
        """
        # Rough estimation: ~4 characters per token
        return len(text) // 4
    
    def _extract_response_text(self, response) -> str:
        """
        Extract response text from Watson AI response object.
        
        Args:
            response: Watson AI response object
            
        Returns:
            Extracted response text
        """
        try:
            if isinstance(response, dict):
                # If response is a dict, extract from choices
                if 'choices' in response and response['choices']:
                    message = response['choices'][0].get('message', {})
                    return message.get('content', '')
            elif hasattr(response, 'choices') and response.choices:
                # If response is an object with choices
                if hasattr(response.choices[0], 'message'):
                    return response.choices[0].message.content or ''
                elif hasattr(response.choices[0], 'text'):
                    return response.choices[0].text or ''
            elif hasattr(response, 'content'):
                return response.content
            elif hasattr(response, 'text'):
                return response.text
            else:
                return str(response)
        except Exception as e:
            if self.verbose:
                self.logger.debug(f"Error parsing response: {e}")
            return str(response)
    
    def _build_messages(self, prompt: str) -> list:
        """
        Build messages in the format expected by Watson AI.
        
        Args:
            prompt: The input prompt
            
        Returns:
            List of message dictionaries
        """
        # Extract system prompt and user message if present
        if "\nUser:" in prompt and "Assistant:" in prompt:
            parts = prompt.split("\nUser:", 1)
            if len(parts) == 2:
                system_part = parts[0].strip()
                user_part = parts[1].replace("Assistant:", "").strip()
                
                messages = []
                if system_part:
                    messages.append({"role": "system", "content": system_part})
                messages.append({
                    "role": "user", 
                    "content": [{"type": "text", "text": user_part}]
                })
                return messages
        
        # If no clear separation, treat entire prompt as user message
        return [{
            "role": "user", 
            "content": [{"type": "text", "text": prompt}]
        }]
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using Watson AI.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Returns:
            The generated response text
        """
        if not self.model:
            await self.initialize()
        
        try:
            # Build messages from prompt
            messages = self._build_messages(prompt)
            
            if self.verbose:
                self.logger.debug(f"Generating with Watson AI: model={self.model_id}, temperature={self.temperature}")
            
            # Generate response in a thread to avoid blocking
            def _generate():
                return self.model.chat(messages=messages)
            
            response = await asyncio.to_thread(_generate)
            
            # Extract response text
            response_text = self._extract_response_text(response)
            
            return response_text
            
        except Exception as e:
            self.logger.error(f"Error generating response with Watson AI: {str(e)}")
            raise
    
    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using Watson AI.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters
            
        Yields:
            Response chunks as they are generated
        """
        if not self.model:
            await self.initialize()
        
        try:
            # Build messages from prompt
            messages = self._build_messages(prompt)
            
            if self.verbose:
                self.logger.debug(f"Starting streaming generation with Watson AI")
            
            # Generate streaming response in a thread
            def _stream_generate():
                return self.model.chat_stream(messages=messages)
            
            stream_response = await asyncio.to_thread(_stream_generate)
            
            for chunk in stream_response:
                if chunk:
                    # Parse the Watson AI response properly
                    chunk_text = ""
                    try:
                        if isinstance(chunk, dict):
                            # If chunk is already a dict, extract content directly
                            if 'choices' in chunk and chunk['choices']:
                                delta = chunk['choices'][0].get('delta', {})
                                chunk_text = delta.get('content', '')
                        elif hasattr(chunk, 'choices') and chunk.choices:
                            # If chunk is an object with choices attribute
                            delta = chunk.choices[0].delta
                            chunk_text = getattr(delta, 'content', '') or ''
                        else:
                            # Fallback to string conversion
                            chunk_text = str(chunk)
                    except Exception as e:
                        if self.verbose:
                            self.logger.debug(f"Error parsing chunk: {e}")
                        chunk_text = str(chunk)
                    
                    # Only yield if there's actual content
                    if chunk_text:
                        yield chunk_text
                    
        except Exception as e:
            self.logger.error(f"Error generating streaming response with Watson AI: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def close(self) -> None:
        """Clean up the Watson AI provider."""
        # Watson AI client doesn't require explicit cleanup
        self.watson_client = None
        self.model = None
        self.logger.info("Watson AI provider closed")
    
    async def validate_config(self) -> bool:
        """
        Validate the Watson AI configuration.
        
        Returns:
            True if configuration is valid, False otherwise
        """
        try:
            if not self.api_key:
                self.logger.error("Watson AI API key is missing")
                return False
            
            if not self.url:
                self.logger.error("Watson AI URL is missing")
                return False
            
            if not self.project_id and not self.space_id:
                self.logger.error("Watson AI project_id or space_id is required")
                return False
            
            if not self.model_id:
                self.logger.error("Watson AI model is missing")
                return False
            
            # Test connection with a simple request
            if not self.model:
                await self.initialize()
            
            # Validate with a minimal test
            test_messages = [{
                "role": "user",
                "content": [{"type": "text", "text": "test"}]
            }]
            
            def _test():
                return self.model.chat(messages=test_messages)
            
            response = await asyncio.to_thread(_test)
            
            if self.verbose:
                self.logger.info("Watson AI configuration validated successfully")
            
            return True
            
        except ImportError:
            self.logger.error("ibm-watsonx-ai package not installed")
            return False
        except Exception as e:
            self.logger.error(f"Watson AI configuration validation failed: {str(e)}")
            return False