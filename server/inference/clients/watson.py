"""
IBM Watson AI client implementation for LLM inference.

This module provides an IBM Watson AI-specific implementation of the BaseLLMClient interface.
"""

import json
import time
from typing import Dict, List, Any, Optional, AsyncGenerator
import aiohttp
import logging
import os

from ..base_llm_client import BaseLLMClient
from ..llm_client_common import LLMClientCommon

class WatsonClient(BaseLLMClient, LLMClientCommon):
    """LLM client implementation for IBM Watson AI."""
    
    def __init__(self, config: Dict[str, Any], retriever: Any = None,
                 reranker_service: Any = None, prompt_service: Any = None, no_results_message: str = ""):
        # Initialize base classes properly
        BaseLLMClient.__init__(self, config, retriever, reranker_service, prompt_service, no_results_message)
        LLMClientCommon.__init__(self)  # Initialize the common client
        
        # Get Watson specific configuration
        watson_config = config.get('inference', {}).get('watson', {})
        
        self.api_key = os.getenv("WATSON_API_KEY", watson_config.get('api_key', ''))
        self.url = os.getenv("WATSON_API_BASE", watson_config.get('api_base', ''))
        
        # Handle project_id - prefer config value if it doesn't look like an env var placeholder
        config_project_id = watson_config.get('project_id', '')
        env_project_id = os.getenv("WATSON_PROJECT_ID", '')
        
        if config_project_id and not config_project_id.startswith('${'):
            # Use direct config value if it's not an env var placeholder
            self.project_id = config_project_id
        elif env_project_id and not env_project_id.startswith('${'):
            # Use env var if it's not a placeholder
            self.project_id = env_project_id
        else:
            # Fallback to config value even if it might be a placeholder
            self.project_id = config_project_id
        
        self.space_id = watson_config.get('space_id', None)
        
        # Additional authentication parameters
        self.instance_id = watson_config.get('instance_id', None)
        self.region = watson_config.get('region', None)
        self.auth_type = watson_config.get('auth_type', 'iam')  # Default to IAM authentication
        self.model_id = watson_config.get('model', 'meta-llama/llama-3-8b-instruct')
        self.temperature = watson_config.get('temperature', 0.1)
        self.top_p = watson_config.get('top_p', 0.8)
        self.top_k = watson_config.get('top_k', 20)
        self.max_tokens = watson_config.get('max_tokens', 1024)
        self.time_limit = watson_config.get('time_limit', 10000)
        self.stream = watson_config.get('stream', True)
        self.verify = watson_config.get('verify', False)
        self.verbose = watson_config.get('verbose', config.get('general', {}).get('verbose', False))
        
        self.watson_client = None
        self.model = None
        
    async def initialize(self) -> None:
        """Initialize the Watson AI client."""
        try:
            from ibm_watsonx_ai import APIClient
            from ibm_watsonx_ai import Credentials
            from ibm_watsonx_ai.foundation_models import ModelInference
            
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
            
            if self.verbose:
                self.logger.info(f"Watson AI configuration:")
                self.logger.info(f"  - API Base: {self.url}")
                self.logger.info(f"  - Project ID: {self.project_id}")
                self.logger.info(f"  - Model: {self.model_id}")
            
            self.logger.info(f"Initialized Watson AI client with model {self.model_id}")
        except ImportError:
            self.logger.error("ibm-watsonx-ai package not installed. Please install with: pip install ibm-watsonx-ai")
            raise
        except Exception as e:
            self.logger.error(f"Error initializing Watson AI client: {str(e)}")
            raise
    
    async def close(self) -> None:
        """Clean up resources."""
        try:
            # Watson AI client doesn't require explicit cleanup
            self.logger.info("Watson AI client resources released")
        except Exception as e:
            self.logger.error(f"Error closing Watson AI client: {str(e)}")
    
    async def verify_connection(self) -> bool:
        """
        Verify that the connection to Watson AI is working.
        
        Returns:
            True if connection is working, False otherwise
        """
        try:
            if not self.watson_client or not self.model:
                await self.initialize()
            
            if self.verbose:
                self.logger.info("Testing Watson AI API connection")
                
            # Simple test request to verify connection
            test_messages = [
                {
                    "role": "system",
                    "content": "You are a helpful assistant."
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Ping"
                        }
                    ]
                }
            ]
            
            response = self.model.chat(messages=test_messages)
            
            if self.verbose:
                self.logger.info("Successfully connected to Watson AI API")
                
            # If we get here, the connection is working
            return True
        except Exception as e:
            self.logger.error(f"Error connecting to Watson AI API: {str(e)}")
            return False
    
    async def generate_response(
        self, 
        message: str, 
        adapter_name: str,
        system_prompt_id: Optional[str] = None,
        context_messages: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Generate a response for a chat message using Watson AI.
        
        Args:
            message: The user's message
            adapter_name: Name of the adapter to use for context retrieval
            system_prompt_id: Optional ID of a system prompt to use
            context_messages: Optional list of previous conversation messages
            
        Returns:
            Dictionary containing response and metadata
        """
        try:
            if self.verbose:
                self.logger.info(f"Generating response for message: {message[:100]}...")
                            
            # Retrieve and rerank documents
            retrieved_docs = await self._retrieve_and_rerank_docs(message, adapter_name)
            
            # Get the system prompt
            system_prompt = await self._get_system_prompt(system_prompt_id)
            
            # Format the context from retrieved documents
            context = self._format_context(retrieved_docs)
            
            # If no context was found, return the default no-results message
            if context is None:
                no_results_message = self.config.get('messages', {}).get('no_results_response', 
                    "I'm sorry, but I don't have any specific information about that topic in my knowledge base.")
                return {
                    "response": no_results_message,
                    "sources": [],
                    "tokens": 0,
                    "processing_time": 0
                }
            
            # Initialize Watson client if not already initialized
            if not self.watson_client or not self.model:
                await self.initialize()
            
            if self.verbose:
                self.logger.info(f"Calling Watson AI API with model: {self.model_id}")
                
            # Call the Watson AI API
            start_time = time.time()
            
            # Prepare messages for the API call
            messages = [{"role": "system", "content": system_prompt}]
            
            # Add context messages if provided
            if context_messages:
                for msg in context_messages:
                    watson_msg = {
                        "role": msg.get("role", "user"),
                        "content": msg["content"] if isinstance(msg["content"], str) else [
                            {"type": "text", "text": msg["content"]}
                        ]
                    }
                    messages.append(watson_msg)
            
            # Add the current message with context
            messages.append({
                "role": "user", 
                "content": [
                    {
                        "type": "text",
                        "text": f"Context information:\n{context}\n\nUser Query: {message}"
                    }
                ]
            })
            
            response = self.model.chat(messages=messages)
            
            if self.verbose:
                self.logger.debug(f"Watson AI response type: {type(response)}")
                if hasattr(response, '__dict__'):
                    self.logger.debug(f"Watson AI response attributes: {list(response.__dict__.keys())}")
            
            processing_time = self._measure_execution_time(start_time)
            
            # Extract the response text from Watson AI response
            response_text = ""
            try:
                if isinstance(response, dict):
                    # If response is a dict, extract from choices
                    if 'choices' in response and response['choices']:
                        message = response['choices'][0].get('message', {})
                        response_text = message.get('content', '')
                elif hasattr(response, 'choices') and response.choices:
                    # If response is an object with choices
                    if hasattr(response.choices[0], 'message'):
                        response_text = response.choices[0].message.content or ''
                    elif hasattr(response.choices[0], 'text'):
                        response_text = response.choices[0].text or ''
                elif hasattr(response, 'content'):
                    response_text = response.content
                elif hasattr(response, 'text'):
                    response_text = response.text
                else:
                    response_text = str(response)
            except Exception as e:
                if self.verbose:
                    self.logger.debug(f"Error parsing response: {e}")
                response_text = str(response)
            
            if self.verbose:
                self.logger.debug(f"Response length: {len(response_text)} characters")
                
            # Format the sources for citation
            sources = self._format_sources(retrieved_docs)
            
            # Estimate token usage (Watson AI might not always provide exact counts)
            estimated_tokens = self._estimate_tokens(str(messages), response_text)
            
            # Get actual token usage if available
            tokens = estimated_tokens
            if hasattr(response, 'usage'):
                tokens = {
                    "prompt": getattr(response.usage, 'prompt_tokens', 0),
                    "completion": getattr(response.usage, 'completion_tokens', 0),
                    "total": getattr(response.usage, 'total_tokens', estimated_tokens)
                }
            
            if self.verbose:
                self.logger.info(f"Token usage: {tokens}")
            
            # Prepare the response data
            response_data = {
                "response": response_text,
                "sources": sources,
                "tokens": tokens["total"] if isinstance(tokens, dict) else tokens,
                "token_usage": tokens if isinstance(tokens, dict) else {"total": tokens},
                "processing_time": processing_time
            }
            
            if self.verbose:
                self.logger.info("🔒 [WATSON CLIENT] Calling security wrapper for non-streaming response")
            
            # Apply security checking before returning
            return await self._secure_response(response_data)
        except Exception as e:
            self.logger.error(f"Error generating response: {str(e)}")
            return {"error": f"Failed to generate response: {str(e)}"}
    
    async def generate_response_stream(
        self, 
        message: str, 
        adapter_name: str,
        system_prompt_id: Optional[str] = None,
        context_messages: Optional[List[Dict[str, str]]] = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming response for a chat message using Watson AI.
        
        Args:
            message: The user's message
            adapter_name: Name of the adapter to use for context retrieval
            system_prompt_id: Optional ID of a system prompt to use
            context_messages: Optional list of previous conversation messages
            
        Yields:
            Chunks of the response as they are generated
        """
        try:
            if self.verbose:
                self.logger.info(f"Starting streaming response for message: {message[:100]}...")
                
            # Retrieve and rerank documents
            retrieved_docs = await self._retrieve_and_rerank_docs(message, adapter_name)
            
            # Get the system prompt
            system_prompt = await self._get_system_prompt(system_prompt_id)
            
            # Format the context from retrieved documents
            context = self._format_context(retrieved_docs)
            
            # If no context was found, return the default no-results message
            if context is None:
                no_results_message = self.config.get('messages', {}).get('no_results_response', 
                    "I'm sorry, but I don't have any specific information about that topic in my knowledge base.")
                yield json.dumps({
                    "response": no_results_message,
                    "sources": [],
                    "done": True
                })
                return
            
            # Initialize Watson client if not already initialized
            if not self.watson_client or not self.model:
                await self.initialize()
            
            if self.verbose:
                self.logger.info(f"Calling Watson AI API with streaming enabled")
                
            # Prepare messages for the API call
            messages = [{"role": "system", "content": system_prompt}]
            
            # Add context messages if provided
            if context_messages:
                for msg in context_messages:
                    watson_msg = {
                        "role": msg.get("role", "user"),
                        "content": msg["content"] if isinstance(msg["content"], str) else [
                            {"type": "text", "text": msg["content"]}
                        ]
                    }
                    messages.append(watson_msg)
            
            # Add the current message with context
            messages.append({
                "role": "user", 
                "content": [
                    {
                        "type": "text",
                        "text": f"Context information:\n{context}\n\nUser Query: {message}"
                    }
                ]
            })
            
            # Create the original stream generator
            async def original_stream():
                try:
                    # Generate streaming response
                    stream_response = self.model.chat_stream(messages=messages)
                    
                    chunk_count = 0
                    for chunk in stream_response:
                        if chunk:
                            chunk_count += 1
                            
                            if self.verbose and chunk_count % 10 == 0:
                                self.logger.debug(f"Received chunk {chunk_count}")
                            
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
                                yield json.dumps({
                                    "response": chunk_text,
                                    "sources": [],
                                    "done": False
                                })
                    
                    if self.verbose:
                        self.logger.info(f"Streaming complete. Received {chunk_count} chunks")
                    
                    # When stream is complete, send the sources
                    sources = self._format_sources(retrieved_docs)
                    yield json.dumps({
                        "response": "",
                        "sources": sources,
                        "done": True
                    })
                except Exception as e:
                    self.logger.error(f"Error in streaming response: {str(e)}")
                    yield json.dumps({"error": f"Error in streaming response: {str(e)}", "done": True})
            
            # Apply security checking to the stream
            if self.verbose:
                self.logger.info("🔒 [WATSON CLIENT] Calling security wrapper for streaming response")
            
            async for secure_chunk in self._secure_response_stream(original_stream()):
                yield secure_chunk
                
        except Exception as e:
            self.logger.error(f"Error generating streaming response: {str(e)}")
            yield json.dumps({"error": f"Failed to generate response: {str(e)}", "done": True})
