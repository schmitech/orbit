"""
Hugging Face client implementation for LLM inference.

This module provides a Hugging Face-specific implementation of the BaseLLMClient interface.
"""

import json
import time
import asyncio
from typing import Dict, List, Any, Optional, AsyncGenerator
import logging
import os

# Fix import statement for hugging-py-face 0.5.3
from hugging_py_face import NLP
# Import the correct exception class
from hugging_py_face.exceptions import APICallException

from ..base_llm_client import BaseLLMClient

# Rename our class to avoid conflict with the imported HuggingFace
class HuggingFaceClient(BaseLLMClient):
    """LLM client implementation for Hugging Face."""
    
    def __init__(self, config: Dict[str, Any], retriever: Any, guardrail_service: Any = None, 
                 reranker_service: Any = None, prompt_service: Any = None, no_results_message: str = ""):
        super().__init__(config, retriever, guardrail_service, reranker_service, prompt_service, no_results_message)
        
        # Get Hugging Face specific configuration
        hf_config = config.get('inference', {}).get('huggingface', {})
        
        self.api_key = os.getenv("HUGGINGFACE_API_KEY", hf_config.get('api_key', ''))
        self.model = hf_config.get('model', 'mistralai/Mistral-7B-Instruct-v0.2')
        self.temperature = hf_config.get('temperature', 0.1)
        self.top_p = hf_config.get('top_p', 0.8)
        self.top_k = hf_config.get('top_k', 20)
        self.max_tokens = hf_config.get('max_tokens', 1024)
        self.stream = hf_config.get('stream', True)
        self.verbose = config.get('general', {}).get('verbose', False)
        self.skip_connection_check = hf_config.get('skip_connection_check', False)
        
        # Flag to use direct API instead of the library
        self._use_direct_api = hf_config.get('use_direct_api', False)
        
        self.hf_client = None
        self.logger = logging.getLogger(__name__)
        
        # Import requests for direct API calls if needed
        if self._use_direct_api:
            import requests
            self.requests = requests
        
    async def initialize(self) -> None:
        """Initialize the Hugging Face client."""
        try:
            # Log masked version of the API key for debugging
            self._log_masked_api_key()
            
            # Clean the API key - remove leading/trailing whitespace
            clean_api_key = self.api_key.strip()
            
            # Initialize Hugging Face client with correct API for v0.5.3
            # If we're using the library incorrectly, log detailed message
            try:
                self.hf_client = NLP(api_token=clean_api_key)
            except TypeError as e:
                self.logger.error(f"Error initializing NLP client: {str(e)}")
                self.logger.error("This might be due to changes in the hugging_py_face library API.")
                self.logger.error("Manual workaround: Will use direct API calls instead of the library if needed.")
                self._use_direct_api = True
                raise
            
            if self.verbose:
                self.logger.info(f"Initialized Hugging Face client with model {self.model}")
                self.logger.debug(f"Hugging Face configuration: temperature={self.temperature}, top_p={self.top_p}, top_k={self.top_k}, max_tokens={self.max_tokens}")
        except Exception as e:
            self.logger.error(f"Error initializing Hugging Face client: {str(e)}")
            raise
    
    def _log_masked_api_key(self) -> None:
        """Log a masked version of the API key for debugging purposes."""
        if not self.api_key:
            self.logger.warning("No API key provided for Hugging Face")
            return
            
        # Get the last 4 characters of the API key
        masked_key = f"****{self.api_key[-4:]}" if len(self.api_key) >= 4 else "****"
        self.logger.info(f"Using Hugging Face API key ending with: {self.api_key[-4:]}")
        self.logger.info(f"API key length: {len(self.api_key)} characters")
        
        # Check if the API key has the correct format
        if not self.api_key.startswith("hf_"):
            self.logger.warning("API key does not have the expected 'hf_' prefix. This might cause authentication issues.")
        
        # Check for common issues with API keys
        if self.api_key.startswith(" ") or self.api_key.endswith(" "):
            self.logger.warning("API key contains leading or trailing spaces, which may cause authentication issues.")
        if "\n" in self.api_key or "\r" in self.api_key:
            self.logger.warning("API key contains newline characters, which will cause authentication issues.")
    
    async def close(self) -> None:
        """Clean up resources."""
        if self.verbose:
            self.logger.info("Closing Hugging Face client")
        # No specific cleanup needed for hugging-py-face
        self.logger.info("Hugging Face client resources released")
    
    async def verify_connection(self) -> bool:
        """
        Verify that the connection to Hugging Face is working.
        
        Returns:
            True if connection is working, False otherwise
        """
        # Skip connection check if configured to do so
        if self.skip_connection_check:
            self.logger.warning("Skipping Hugging Face connection verification as configured.")
            self.logger.warning("Note: This may lead to errors if the API is unreachable or unauthorized.")
            return True
            
        try:
            if not self.hf_client and not self._use_direct_api:
                await self.initialize()
            
            if self.verbose:
                self.logger.info("Testing connection to Hugging Face API")
            
            # Check if API token is provided
            if not self.api_key:
                self.logger.error("No Hugging Face API token provided. Please set HUGGINGFACE_API_KEY environment variable or configure it in the config file.")
                return False
            
            # Always log the API key info for debugging connection issues
            self._log_masked_api_key()
            
            # Use the appropriate method to test the connection
            if self._use_direct_api:
                try:
                    generated_text = await self._direct_api_text_generation(
                        text="Hello, can you hear me?",
                        parameters={"max_new_tokens": 5, "return_full_text": False}
                    )
                    if self.verbose:
                        self.logger.info("Successfully connected to Hugging Face API using direct API")
                        self.logger.debug(f"Test response: {generated_text}")
                    return True
                except Exception as e:
                    self.logger.error(f"Error connecting to Hugging Face API using direct API: {str(e)}")
                    return False
            else:
                # Use the library as before
                response = self.hf_client.text_generation(
                    text="Hello, can you hear me?",
                    parameters={
                        "max_new_tokens": 5,
                        "temperature": self.temperature,
                        "top_p": self.top_p,
                        "top_k": self.top_k,
                        "return_full_text": False
                    },
                    model=self.model
                )
                
                if self.verbose:
                    self.logger.info("Successfully connected to Hugging Face API")
                    self.logger.debug(f"Test response: {response}")
                
                return True
        except APICallException as e:
            error_msg = str(e)
            if "403" in error_msg:
                self.logger.error(f"Authentication error with Hugging Face API: {error_msg}")
                self.logger.error("Please check your Hugging Face API token. It may be invalid or expired.")
                self.logger.error("You can get a new token at https://huggingface.co/settings/tokens")
                
                # Try with a publicly accessible model as a test
                return await self._try_fallback_connection()
            else:
                self.logger.error(f"Error connecting to Hugging Face API: {error_msg}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error connecting to Hugging Face API: {str(e)}")
            return False
    
    async def _try_fallback_connection(self) -> bool:
        """
        Try connecting with a free model that might not require authentication.
        This is a fallback method if the primary connection fails due to authentication issues.
        
        Returns:
            True if fallback connection works, False otherwise
        """
        try:
            # Try with a free model that might be accessible without a token
            self.logger.info("Trying fallback connection with a freely accessible model...")
            
            fallback_model = "gpt2"  # A model that might be accessible without authentication
            
            response = self.hf_client.text_generation(
                text="Test",
                parameters={
                    "max_new_tokens": 5,
                    "temperature": 0.7,
                    "return_full_text": False
                },
                model=fallback_model
            )
            
            self.logger.info("Fallback connection successful. However, your configured model may still require proper authentication.")
            self.logger.warning(f"Using the fallback model '{fallback_model}' instead of your configured model '{self.model}'.")
            self.logger.warning("This is a temporary solution. Please update your Hugging Face API token.")
            
            # Update the model to use the fallback model
            self.model = fallback_model
            
            return True
        except Exception as e:
            self.logger.error(f"Fallback connection also failed: {str(e)}")
            self.logger.error("Please ensure you have a valid Hugging Face API token and internet connectivity.")
            return False
    
    async def generate_response(
        self, 
        message: str, 
        collection_name: str,
        system_prompt_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a response for a chat message using Hugging Face.
        
        Args:
            message: The user's message
            collection_name: Name of the collection to query for context
            system_prompt_id: Optional ID of a system prompt to use
            
        Returns:
            Dictionary containing response and metadata
        """
        try:
            if self.verbose:
                self.logger.info(f"Generating response for message: {message[:100]}...")
            
            # Check if the message is safe
            if self.guardrail_service and not await self.guardrail_service.is_safe(message):
                if self.verbose:
                    self.logger.warning("Message failed safety check")
                return {
                    "response": "I'm sorry, but I cannot respond to that message as it may violate content safety guidelines.",
                    "sources": [],
                    "tokens": 0,
                    "processing_time": 0
                }
            
            # Query for relevant documents
            if self.verbose:
                self.logger.info(f"Retrieving context from collection: {collection_name}")
            retrieved_docs = await self.retriever.get_relevant_context(
                query=message,
                collection_name=collection_name
            )
            
            if self.verbose:
                self.logger.info(f"Retrieved {len(retrieved_docs)} relevant documents")
            
            # Rerank if reranker is available
            if self.reranker_service and retrieved_docs:
                if self.verbose:
                    self.logger.info("Reranking retrieved documents")
                retrieved_docs = await self.reranker_service.rerank(message, retrieved_docs)
            
            # Get the system prompt
            system_prompt = "You are a helpful assistant that provides accurate information."
            if system_prompt_id and self.prompt_service:
                if self.verbose:
                    self.logger.info(f"Fetching system prompt with ID: {system_prompt_id}")
                prompt_doc = await self.prompt_service.get_prompt_by_id(system_prompt_id)
                if prompt_doc and 'prompt' in prompt_doc:
                    system_prompt = prompt_doc['prompt']
                    if self.verbose:
                        self.logger.debug(f"Using custom system prompt: {system_prompt[:100]}...")
            
            # Format the context from retrieved documents
            context = self._format_context(retrieved_docs)
            
            # Prepare the prompt with context
            prompt = f"{system_prompt}\n\nContext information:\n{context}\n\nUser: {message}\nAssistant:"
            
            if self.verbose:
                self.logger.debug(f"Prepared prompt length: {len(prompt)} characters")
            
            # Call the Hugging Face API with updated method for v0.5.3
            start_time = time.time()
            
            if self.verbose:
                self.logger.info(f"Calling Hugging Face API with model: {self.model}")
            
            # Initialize client if not already initialized
            if not self.hf_client and not self._use_direct_api:
                await self.initialize()
                
            # Generate text using the appropriate method
            if self._use_direct_api:
                try:
                    generated_text = await self._direct_api_text_generation(
                        text=prompt,
                        parameters={
                            "max_new_tokens": self.max_tokens,
                            "temperature": self.temperature,
                            "top_p": self.top_p,
                            "top_k": self.top_k,
                            "return_full_text": False
                        }
                    )
                except Exception as e:
                    self.logger.error(f"Error calling Hugging Face API directly: {str(e)}")
                    return {"error": f"Failed to generate response: {str(e)}"}
            else:
                # Use the correct method for text generation in v0.5.3
                response = self.hf_client.text_generation(
                    text=prompt,
                    parameters={
                        "max_new_tokens": self.max_tokens,
                        "temperature": self.temperature,
                        "top_p": self.top_p,
                        "top_k": self.top_k,
                        "return_full_text": False
                    },
                    model=self.model
                )
                
                # In hugging-py-face 0.5.3, the text_generation method returns 
                # a dictionary with the generated text
                if isinstance(response, dict) and "generated_text" in response:
                    generated_text = response["generated_text"]
                elif isinstance(response, list) and len(response) > 0 and "generated_text" in response[0]:
                    generated_text = response[0]["generated_text"]
                else:
                    # Fallback if response format is different
                    generated_text = str(response)
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            if self.verbose:
                self.logger.info(f"Received response in {processing_time:.2f} seconds")
                self.logger.debug(f"Response length: {len(generated_text)} characters")
            
            # Format the sources for citation
            sources = self._format_sources(retrieved_docs)
            
            # Estimate token count (HF doesn't always provide this directly)
            # Rough estimate: 4 chars per token
            estimated_tokens = len(prompt) // 4 + len(generated_text) // 4
            
            if self.verbose:
                self.logger.info(f"Estimated token usage: {estimated_tokens}")
            
            return {
                "response": generated_text,
                "sources": sources,
                "tokens": estimated_tokens,
                "processing_time": processing_time
            }
        except APICallException as e:
            self.logger.error(f"Hugging Face API error: {str(e)}")
            return {"error": f"Failed to generate response: {str(e)}"}
        except Exception as e:
            self.logger.error(f"Unexpected error generating response: {str(e)}")
            return {"error": f"Failed to generate response: {str(e)}"}
    
    async def generate_response_stream(
        self, 
        message: str, 
        collection_name: str,
        system_prompt_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming response for a chat message using Hugging Face.
        
        Note: Hugging Face API doesn't natively support streaming,
        so this implementation simulates streaming by returning the entire response
        but in chunks after receiving it.
        
        Args:
            message: The user's message
            collection_name: Name of the collection to query for context
            system_prompt_id: Optional ID of a system prompt to use
            
        Yields:
            Chunks of the response as they are generated
        """
        try:
            if self.verbose:
                self.logger.info(f"Starting streaming response for message: {message[:100]}...")
            
            # Check if the message is safe
            if self.guardrail_service and not await self.guardrail_service.is_safe(message):
                if self.verbose:
                    self.logger.warning("Message failed safety check")
                yield json.dumps({
                    "response": "I'm sorry, but I cannot respond to that message as it may violate content safety guidelines.",
                    "sources": [],
                    "done": True
                })
                return
            
            # Query for relevant documents
            if self.verbose:
                self.logger.info(f"Retrieving context from collection: {collection_name}")
            retrieved_docs = await self.retriever.get_relevant_context(
                query=message,
                collection_name=collection_name
            )
            
            if self.verbose:
                self.logger.info(f"Retrieved {len(retrieved_docs)} relevant documents")
            
            # Rerank if reranker is available
            if self.reranker_service and retrieved_docs:
                if self.verbose:
                    self.logger.info("Reranking retrieved documents")
                retrieved_docs = await self.reranker_service.rerank(message, retrieved_docs)
            
            # Get the system prompt
            system_prompt = "You are a helpful assistant that provides accurate information."
            if system_prompt_id and self.prompt_service:
                if self.verbose:
                    self.logger.info(f"Fetching system prompt with ID: {system_prompt_id}")
                prompt_doc = await self.prompt_service.get_prompt_by_id(system_prompt_id)
                if prompt_doc and 'prompt' in prompt_doc:
                    system_prompt = prompt_doc['prompt']
                    if self.verbose:
                        self.logger.debug(f"Using custom system prompt: {system_prompt[:100]}...")
            
            # Format the context from retrieved documents
            context = self._format_context(retrieved_docs)
            
            # Prepare the prompt with context
            prompt = f"{system_prompt}\n\nContext information:\n{context}\n\nUser: {message}\nAssistant:"
            
            if self.verbose:
                self.logger.debug(f"Prepared prompt length: {len(prompt)} characters")
            
            # Initialize Hugging Face client if not already initialized
            if not self.hf_client and not self._use_direct_api:
                await self.initialize()
            
            if self.verbose:
                self.logger.info(f"Calling Hugging Face API with model: {self.model}")
            
            # Get the full response using the appropriate method
            try:
                if self._use_direct_api:
                    full_response_text = await self._direct_api_text_generation(
                        text=prompt,
                        parameters={
                            "max_new_tokens": self.max_tokens,
                            "temperature": self.temperature,
                            "top_p": self.top_p,
                            "top_k": self.top_k,
                            "return_full_text": False
                        }
                    )
                else:
                    # Get the full response with the correct method for v0.5.3
                    full_response = self.hf_client.text_generation(
                        text=prompt,
                        parameters={
                            "max_new_tokens": self.max_tokens,
                            "temperature": self.temperature,
                            "top_p": self.top_p,
                            "top_k": self.top_k,
                            "return_full_text": False
                        },
                        model=self.model
                    )
                    
                    # Extract the generated text from the response
                    if isinstance(full_response, dict) and "generated_text" in full_response:
                        full_response_text = full_response["generated_text"]
                    elif isinstance(full_response, list) and len(full_response) > 0 and "generated_text" in full_response[0]:
                        full_response_text = full_response[0]["generated_text"]
                    else:
                        # Fallback if response format is different
                        full_response_text = str(full_response)
            except Exception as e:
                self.logger.error(f"Error getting response from Hugging Face API: {str(e)}")
                yield json.dumps({"error": f"Failed to generate response: {str(e)}", "done": True})
                return
            
            if self.verbose:
                self.logger.debug(f"Full response length: {len(full_response_text)} characters")
            
            # Simulate streaming by chunking the response
            # Split into sentences or reasonable chunks
            import re
            chunks = re.split(r'(?<=[.!?])\s+', full_response_text)
            
            if self.verbose:
                self.logger.info(f"Split response into {len(chunks)} chunks for streaming")
            
            # Stream each chunk
            chunk_count = 0
            for chunk in chunks:
                if chunk.strip():
                    chunk_count += 1
                    if self.verbose:
                        self.logger.debug(f"Streaming chunk {chunk_count}: {chunk[:50]}...")
                    yield json.dumps({
                        "response": chunk + " ",
                        "sources": [],
                        "done": False
                    })
                    # Small delay to simulate streaming
                    await asyncio.sleep(0.1)
            
            if self.verbose:
                self.logger.info(f"Streaming complete. Sent {chunk_count} chunks")
            
            # When stream is complete, send the sources
            sources = self._format_sources(retrieved_docs)
            yield json.dumps({
                "response": "",
                "sources": sources,
                "done": True
            })
                
        except APICallException as e:
            self.logger.error(f"Hugging Face API error: {str(e)}")
            yield json.dumps({"error": f"Failed to generate response: {str(e)}", "done": True})
        except Exception as e:
            self.logger.error(f"Unexpected error generating streaming response: {str(e)}")
            yield json.dumps({"error": f"Failed to generate response: {str(e)}", "done": True})

    async def _direct_api_text_generation(self, text, model=None, parameters=None):
        """
        Call the Hugging Face API directly using HTTP requests.
        This is a fallback for when the hugging_py_face library doesn't work properly.
        
        Args:
            text: The input text for text generation
            model: The model to use (defaults to self.model)
            parameters: Parameters for text generation
            
        Returns:
            The generated text
        """
        import requests
        
        if not hasattr(self, 'requests'):
            self.requests = requests
            
        model_name = model or self.model
        api_url = f"https://api-inference.huggingface.co/models/{model_name}"
        
        # Prepare the headers with proper Bearer token
        headers = {
            "Authorization": f"Bearer {self.api_key.strip()}",
            "Content-Type": "application/json"
        }
        
        # Prepare the request payload
        payload = {
            "inputs": text,
            "parameters": parameters or {
                "max_new_tokens": self.max_tokens,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "top_k": self.top_k,
                "return_full_text": False
            }
        }
        
        if self.verbose:
            self.logger.info(f"Making direct API call to Hugging Face for model: {model_name}")
            
        # Make the API request
        response = self.requests.post(api_url, headers=headers, json=payload)
        
        if response.status_code != 200:
            error_msg = f"API call failed with status code {response.status_code}: {response.text}"
            self.logger.error(error_msg)
            raise APICallException(error_msg)
            
        # Parse the response
        result = response.json()
        
        if isinstance(result, list) and len(result) > 0:
            if "generated_text" in result[0]:
                return result[0]["generated_text"]
            else:
                return str(result[0])
        elif isinstance(result, dict) and "generated_text" in result:
            return result["generated_text"]
        else:
            # If we can't extract the text in the expected way, return the raw response
            return str(result)