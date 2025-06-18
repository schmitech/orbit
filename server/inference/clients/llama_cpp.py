"""
llama.cpp client implementation for LLM inference.

This module provides a llama.cpp-specific implementation of the BaseLLMClient interface.
"""

import json
import time
import asyncio
import os
from typing import Dict, List, Any, Optional, AsyncGenerator
import logging

# Suppress Metal/OpenCL initialization messages
os.environ["LLAMA_CPP_VERBOSE"] = "0"
os.environ["METAL_DEBUG_ERROR_MODE"] = "0"  
os.environ["METAL_DEVICE_WRAPPER_TYPE"] = "0"
os.environ["METAL_DEBUG_OPTIONS"] = "silent"  # Additional Metal setting
os.environ["GGML_METAL_SILENCE_INIT_LOGS"] = "1"  # Special for ggml_metal_init logs
os.environ["GGML_METAL_VERBOSE"] = "0"  # Another GGML Metal setting
os.environ["OPENCL_LOG_LEVEL"] = "0"
os.environ["GGML_SILENT"] = "1"  # Suppress all GGML messages
os.environ["GGML_VERBOSE"] = "0"  # Additional GGML verbosity control
os.environ["GGML_DEBUG"] = "0"  # Disable GGML debug messages
os.environ["GGML_METAL_DEBUG"] = "0"  # Disable Metal-specific debug messages

from ..base_llm_client import BaseLLMClient
from ..llm_client_common import LLMClientCommon

class QALlamaCppClient(BaseLLMClient, LLMClientCommon):
    """LLM client implementation for llama.cpp."""
    
    def __init__(self, config: Dict[str, Any], retriever: Any = None,
                 reranker_service: Any = None, prompt_service: Any = None, no_results_message: str = ""):
        super().__init__(config, retriever, reranker_service, prompt_service, no_results_message)
        
        # Get LlamaCpp specific configuration
        llama_cpp_config = config.get('inference', {}).get('llama_cpp', {})
        
        self.model_path = llama_cpp_config.get('model_path', '')
        self.chat_format = llama_cpp_config.get('chat_format', None)
        self.temperature = llama_cpp_config.get('temperature', 0.1)
        self.top_p = llama_cpp_config.get('top_p', 0.8)
        self.top_k = llama_cpp_config.get('top_k', 20)
        self.max_tokens = llama_cpp_config.get('max_tokens', 512)  # Reduced from 1024
        self.n_ctx = llama_cpp_config.get('n_ctx', 4096)
        self.n_threads = llama_cpp_config.get('n_threads', 4)
        self.stream = llama_cpp_config.get('stream', True)
        self.verbose = llama_cpp_config.get('verbose', config.get('general', {}).get('verbose', False))
        self.default_system_prompt = llama_cpp_config.get('system_prompt', "You are a helpful, accurate, precise, and expert assistant.")
        
        # Add GPU-related parameters
        self.n_gpu_layers = llama_cpp_config.get('n_gpu_layers', -1)  # -1 means use all layers on GPU
        self.main_gpu = llama_cpp_config.get('main_gpu', 0)
        self.tensor_split = llama_cpp_config.get('tensor_split', None)
        
        # Add stop tokens and repetition penalty
        self.stop_tokens = llama_cpp_config.get('stop_tokens', [
            "<|im_start|>", "<|file_ref_name|>", "<|file_ref>", "<|file_name|>",
            "<|im_end|>", "</im_end|>", "<im_end>", "</im_end>",
            "</s>", "<|endoftext|>", "<|system_prompt|>",
            "<|file_ref|>system_prompt", "<|im_start|>"  # Added im_start to default list
        ])
        self.repeat_penalty = llama_cpp_config.get('repeat_penalty', 1.1)
        
        self.llama_model = None
        self.logger = logging.getLogger(__name__)
        
    async def initialize(self) -> None:
        """Initialize the LlamaCpp client."""
        try:
            from llama_cpp import Llama
            
            # Check if model path exists
            if not os.path.exists(self.model_path):
                self.logger.error(f"Model file not found at: {self.model_path}")
                self.logger.error("Please download a model using the download_hugging_face_gguf_model.py script")
                raise FileNotFoundError(f"Model file not found at: {self.model_path}")
            
            # Load model from local path
            self.logger.info(f"Loading model from: {self.model_path}")
            self.llama_model = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                chat_format=self.chat_format,
                verbose=self.verbose,
                n_gpu_layers=self.n_gpu_layers,
                main_gpu=self.main_gpu,
                tensor_split=self.tensor_split,
                stop=self.stop_tokens,
                repeat_penalty=self.repeat_penalty
            )
            
            self.logger.info(f"Initialized llama.cpp client successfully")
        except ImportError:
            self.logger.error("llama_cpp package not installed. Please install with: pip install llama-cpp-python==0.3.8")
            raise
        except Exception as e:
            self.logger.error(f"Error initializing llama.cpp client: {str(e)}")
            raise
    
    async def close(self) -> None:
        """Clean up resources."""
        # llama.cpp model doesn't need explicit cleanup
        if self.verbose:
            self.logger.info("llama.cpp client resources released")
    
    async def verify_connection(self) -> bool:
        """
        Verify that the llama.cpp model is loaded properly.
        
        Returns:
            True if model is loaded, False otherwise
        """
        if self.llama_model is not None:
            if self.verbose:
                self.logger.info("llama.cpp model is loaded and ready")
            return True
        return False
    
    async def _get_system_prompt(self, system_prompt_id: Optional[str] = None) -> str:
        """
        Get the system prompt, falling back to the default from config if none provided.
        
        Args:
            system_prompt_id: Optional ID of the system prompt to use
            
        Returns:
            The system prompt to use
        """
        if system_prompt_id:
            prompt = await super()._get_system_prompt(system_prompt_id)
            if prompt:
                return prompt
        return self.default_system_prompt
    
    async def generate_response(
        self, 
        message: str, 
        collection_name: str,
        system_prompt_id: Optional[str] = None,
        context_messages: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Generate a response for a chat message using llama.cpp.
        
        Args:
            message: The user's message
            collection_name: Name of the collection to query for context
            system_prompt_id: Optional ID of a system prompt to use
            context_messages: Optional list of previous conversation messages
            
        Returns:
            Dictionary containing response and metadata
        """
        try:
            if self.verbose:
                self.logger.info(f"Generating response for message: {message[:100]}...")
                
            # Retrieve and rerank documents
            retrieved_docs = await self._retrieve_and_rerank_docs(message, collection_name)
            
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
            
            # Create messages for chat completion
            messages = []
            
            # Add context messages if provided
            if context_messages:
                messages.extend(context_messages)
            
            # Add system message if provided
            if system_prompt:
                system_content = system_prompt
                if context:
                    system_content += f"\n\nContext information:\n{context}"
                messages.append({"role": "system", "content": system_content})
            elif context:
                # If no system prompt but we have context
                messages.append({"role": "system", "content": f"Context information:\n{context}"})
            
            # Add user message
            messages.append({"role": "user", "content": message})
            
            if self.verbose:
                self.logger.info(f"Calling llama.cpp model for chat completion")
                
            # Call the llama.cpp model
            start_time = time.time()
            
            # We need to convert the async call to sync using ThreadPoolExecutor
            loop = asyncio.get_event_loop()
            
            def generate_chat():
                return self.llama_model.create_chat_completion(
                    messages=messages,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    top_k=self.top_k,
                    max_tokens=self.max_tokens,
                    stop=self.stop_tokens,
                    repeat_penalty=self.repeat_penalty
                )
            
            response = await loop.run_in_executor(None, generate_chat)
            
            processing_time = self._measure_execution_time(start_time)
            
            # Extract the response and metadata
            response_text = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # Clean up any remaining file reference tags and system tags
            response_text = response_text.strip()
            
            # Define patterns to clean up
            cleanup_patterns = [
                "<|file_ref_name|>", "<|file_ref>", "<|file_name|>",
                "<|im_end|>", "</im_end|>", "<im_end>", "</im_end>",
                "<|system_prompt|>", "<|file_ref|>system_prompt",
                "<|im_start|>", "</im_start|>", "<im_start>", "</im_start>"  # Added im_start patterns
            ]
            
            # Clean up any pattern that appears anywhere in the response
            for pattern in cleanup_patterns:
                response_text = response_text.replace(pattern, "")
            
            # Remove any trailing special tokens or incomplete tags
            response_text = response_text.split("<|")[0].strip()
            
            # Remove any remaining whitespace artifacts
            response_text = " ".join(response_text.split())
            
            if self.verbose:
                self.logger.debug(f"Response length: {len(response_text)} characters")
                
            # Format the sources for citation
            sources = self._format_sources(retrieved_docs)
            
            token_usage = response.get("usage", {})
            if self.verbose and token_usage:
                self.logger.info(f"Token usage: {token_usage}")
            
            return {
                "response": response_text,
                "sources": sources,
                "tokens": token_usage.get("completion_tokens", 0),
                "processing_time": processing_time
            }
        except Exception as e:
            self.logger.error(f"Error generating response: {str(e)}")
            return {"error": f"Failed to generate response: {str(e)}"}
    
    async def generate_response_stream(
        self, 
        message: str, 
        collection_name: str,
        system_prompt_id: Optional[str] = None,
        context_messages: Optional[List[Dict[str, str]]] = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming response for a chat message using llama.cpp.
        
        Args:
            message: The user's message
            collection_name: Name of the collection to query for context
            system_prompt_id: Optional ID of a system prompt to use
            context_messages: Optional list of previous conversation messages
            
        Yields:
            Chunks of the response as they are generated
        """
        try:
            if self.verbose:
                self.logger.info(f"Starting streaming response for message: {message[:100]}...")
                            
            # Retrieve and rerank documents
            retrieved_docs = await self._retrieve_and_rerank_docs(message, collection_name)
            
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
            
            # Create messages for chat completion
            messages = []
            
            # Add context messages if provided
            if context_messages:
                messages.extend(context_messages)
            
            # Add system message if provided
            if system_prompt:
                system_content = system_prompt
                if context:
                    system_content += f"\n\nContext information:\n{context}"
                messages.append({"role": "system", "content": system_content})
            elif context:
                # If no system prompt but we have context
                messages.append({"role": "system", "content": f"Context information:\n{context}"})
                
            # Add user message
            messages.append({"role": "user", "content": message})
            
            if self.verbose:
                self.logger.info(f"Calling llama.cpp model with streaming enabled")
                
            # Use a thread to run the CPU-bound llama.cpp inference
            loop = asyncio.get_event_loop()
            
            def stream_generate():
                return self.llama_model.create_chat_completion(
                    messages=messages,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    top_k=self.top_k,
                    max_tokens=self.max_tokens,
                    stream=True,
                    stop=self.stop_tokens,
                    repeat_penalty=self.repeat_penalty
                )
            
            # Start streaming in a separate thread
            stream = await loop.run_in_executor(None, stream_generate)
            
            # Stream response chunks
            chunk_count = 0
            for chunk in stream:
                if chunk and "choices" in chunk and len(chunk["choices"]) > 0:
                    choice = chunk["choices"][0]
                    if "delta" in choice and "content" in choice["delta"]:
                        text = choice["delta"]["content"]
                        if text:
                            # Skip chunks that match stop tokens
                            if any(token in text for token in self.stop_tokens):
                                continue
                                
                            # Strip out any stray stop-token emissions entirely
                            if text.strip() in self.stop_tokens:
                                continue

                            # Remove stop-token substrings but leave llama.cpp's leading space
                            for pattern in self.stop_tokens:
                                text = text.replace(pattern, "")

                            # Truncate at any control-token boundary
                            text = text.split("<|")[0]

                            if text:
                                chunk_count += 1
                                
                                if self.verbose and chunk_count % 10 == 0:
                                    self.logger.debug(f"Received chunk {chunk_count}")
                                    
                                yield json.dumps({
                                    "response": text,
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
            self.logger.error(f"Error generating streaming response: {str(e)}")
            yield json.dumps({"error": f"Failed to generate response: {str(e)}", "done": True}) 