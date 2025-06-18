import json
import time
import logging
import os
from typing import Any, Dict, Optional, AsyncGenerator, List

from azure.ai.inference import ChatCompletionsClient
from azure.core.credentials import AzureKeyCredential

from ..base_llm_client import BaseLLMClient
from ..llm_client_common import LLMClientCommon

class AzureOpenAIClient(BaseLLMClient, LLMClientCommon):
    """LLM client implementation for Azure AI Inference."""

    def __init__(self, config: Dict[str, Any], retriever: Any = None,
                 reranker_service: Any = None, prompt_service: Any = None, no_results_message: str = ""):
        super().__init__(config, retriever, reranker_service, prompt_service, no_results_message)

        azure_cfg = config.get('inference', {}).get('azure', {})
        self.endpoint = azure_cfg.get('endpoint', os.getenv("AZURE_OPENAI_ENDPOINT", ""))
        self.api_key = os.getenv("AZURE_OPENAI_KEY", azure_cfg.get('api_key', ''))
        self.deployment = azure_cfg.get('deployment_name', azure_cfg.get('deployment', 'gpt-35-turbo'))
        self.temperature = azure_cfg.get('temperature', 0.1)
        self.top_p = azure_cfg.get('top_p', 0.8)
        self.max_tokens = azure_cfg.get('max_tokens', 1024)
        self.stream = azure_cfg.get('stream', True)
        self.verbose = azure_cfg.get('verbose', config.get('general', {}).get('verbose', False))
        self.api_version = azure_cfg.get('api_version', '2024-06-01')

        self.client: Optional[ChatCompletionsClient] = None
        self.logger = logging.getLogger(__name__)

    async def initialize(self) -> None:
        """Initialize the Azure AI Inference client."""
        if not self.client:
            if not self.endpoint or not self.api_key:
                raise ValueError("AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY must be set")
            self.client = ChatCompletionsClient(
                endpoint=self.endpoint,
                credential=AzureKeyCredential(self.api_key),
                api_version=self.api_version
            )
            self.logger.info(f"Initialized Azure AI Inference client (deployment={self.deployment})")

    async def close(self) -> None:
        """No-op for Azure client cleanup."""
        self.logger.info("Azure AI Inference client cleanup complete")

    async def verify_connection(self) -> bool:
        """Quick test to verify Azure AI Inference is reachable."""
        try:
            await self.initialize()
            # simple ping via a tiny completion
            resp = await self.client.complete(
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Ping"}
                ],
                max_tokens=1,
                temperature=0.0
            )
            return bool(resp.choices)
        except Exception as e:
            self.logger.error(f"Azure AI Inference connection failed: {e}")
            return False

    async def generate_response(
        self,
        message: str,
        collection_name: str,
        system_prompt_id: Optional[str] = None,
        context_messages: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Generate a response for a chat message using Azure OpenAI.
        
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
            
            # Initialize Azure client if not already initialized
            if not self.client:
                await self.initialize()
            
            if self.verbose:
                self.logger.info(f"Calling Azure OpenAI API with model: {self.deployment}")
                
            # Call the Azure OpenAI API
            start_time = time.time()
            
            # For Azure OpenAI, we use a structured user message with the context and query
            user_message = f"Context information:\n{context}\n\nUser Query: {message}"
            
            # Prepare messages for the API call
            messages = []
            
            # Add context messages if provided
            if context_messages:
                messages.extend(context_messages)
            
            # Add the current message
            messages.append({"role": "user", "content": user_message})
            
            try:
                response = await self.client.complete(
                    messages=messages,
                    system=system_prompt,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    max_tokens=self.max_tokens,
                    stream=False
                )
            except Exception as api_error:
                self.logger.error(f"Azure OpenAI API error: {str(api_error)}")
                if self.verbose:
                    self.logger.debug(f"Request: model={self.deployment}, system={system_prompt[:50]}..., messages={messages}")
                raise
            
            processing_time = time.time() - start_time
            
            # Extract the response text
            if not response.choices or not response.choices[0].message:
                self.logger.error("Unexpected response format from Azure OpenAI API: missing content")
                if self.verbose:
                    self.logger.debug(f"Response: {response}")
                return {"error": "Failed to get valid response from Azure OpenAI API"}
                
            response_text = response.choices[0].message.content
            
            if self.verbose:
                self.logger.debug(f"Response length: {len(response_text)} characters")
                
            # Format the sources for citation
            sources = self._format_sources(retrieved_docs)
            
            # Get token usage from the response
            tokens = {
                "prompt": response.usage.prompt_tokens,
                "completion": response.usage.completion_tokens,
                "total": response.usage.total_tokens
            }
            
            if self.verbose:
                self.logger.info(f"Token usage: {tokens}")
            
            return {
                "response": response_text,
                "sources": sources,
                "tokens": tokens["total"],
                "token_usage": tokens,
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
        Generate a streaming response for a chat message using Azure OpenAI.
        
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
            
            # Initialize Azure client if not already initialized
            if not self.client:
                await self.initialize()
            
            if self.verbose:
                self.logger.info(f"Calling Azure OpenAI API with streaming enabled")
                
            # For Azure OpenAI, we use a structured user message with the context and query
            user_message = f"Context information:\n{context}\n\nUser Query: {message}"
            
            # Prepare messages for the API call
            messages = []
            
            # Add context messages if provided
            if context_messages:
                messages.extend(context_messages)
            
            # Add the current message
            messages.append({"role": "user", "content": user_message})
            
            chunk_count = 0
            # Generate streaming response
            try:
                response = await self.client.complete(
                    messages=messages,
                    system=system_prompt,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    max_tokens=self.max_tokens,
                    stream=True
                )
                
                async for chunk in response:
                    chunk_count += 1
                    
                    if self.verbose and chunk_count % 10 == 0:
                        self.logger.debug(f"Received chunk {chunk_count}")
                        
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield json.dumps({
                            "response": chunk.choices[0].delta.content,
                            "done": False
                        })
            except Exception as stream_error:
                self.logger.error(f"Azure OpenAI streaming error: {str(stream_error)}")
                if self.verbose:
                    self.logger.debug(f"Stream request: model={self.deployment}, system={system_prompt[:50]}..., messages={messages}")
                yield json.dumps({
                    "error": f"Error in streaming response: {str(stream_error)}",
                    "done": True
                })
                return
            
            if self.verbose:
                self.logger.info(f"Streaming complete. Received {chunk_count} chunks")
                
            # Send final message with sources
            yield json.dumps({
                "sources": self._format_sources(retrieved_docs),
                "done": True
            })
            
        except Exception as e:
            self.logger.error(f"Error generating streaming response: {str(e)}")
            yield json.dumps({
                "error": f"Failed to generate response: {str(e)}",
                "done": True
            })
