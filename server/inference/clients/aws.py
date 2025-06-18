import json
import time
import logging
import os
import boto3
import asyncio
from typing import Any, Optional, AsyncGenerator, List, Dict

from ..base_llm_client import BaseLLMClient
from ..llm_client_common import LLMClientCommon

class AWSBedrockClient(BaseLLMClient, LLMClientCommon):
    """LLM client implementation for AWS Bedrock via boto3."""

    def __init__(self, config: Dict[str, Any], retriever: Any = None,
                 reranker_service: Any = None, prompt_service: Any = None, no_results_message: str = ""):
        super().__init__(config, retriever, reranker_service, prompt_service, no_results_message)

        bedrock_cfg = config.get("inference", {}).get("bedrock", {})
        self.region = bedrock_cfg.get("region", os.getenv("AWS_REGION", "us-east-1"))
        self.model = bedrock_cfg.get("model", "anthropic.claude-3-sonnet-20240229-v1:0")
        self.content_type = bedrock_cfg.get("content_type", "application/json")
        self.accept = bedrock_cfg.get("accept", "application/json")
        self.max_tokens = bedrock_cfg.get("max_tokens", 1024)
        self.temperature = bedrock_cfg.get("temperature", 0.1)
        self.top_p = bedrock_cfg.get("top_p", 0.8)
        self.stream = bedrock_cfg.get("stream", True)

        self.client = None
        self.logger = logging.getLogger(__name__)

    async def initialize(self) -> None:
        """Initialize the boto3 Bedrock client."""
        if self.client is None:
            try:
                self.client = boto3.client("bedrock-runtime", region_name=self.region)
                self.logger.info(f"AWS Bedrock client initialized (region={self.region}, model={self.model})")
            except Exception as e:
                self.logger.error(f"Failed to initialize AWS Bedrock client: {e}")
                raise

    async def close(self) -> None:
        """No-op for boto3; included for interface compliance."""
        self.logger.info("AWS Bedrock client cleanup complete")

    async def verify_connection(self) -> bool:
        """Quick check: list available models."""
        try:
            await self.initialize()
            _ = self.client.list_models()
            return True
        except Exception as e:
            self.logger.error(f"AWS Bedrock connection test failed: {e}")
            return False

    async def generate_response(
        self,
        message: str,
        collection_name: str,
        system_prompt_id: Optional[str] = None,
        context_messages: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Generate a response for a chat message using AWS Bedrock.
        
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
            
            # Initialize AWS client if not already initialized
            if not self.client:
                await self.initialize()
            
            if self.verbose:
                self.logger.info(f"Calling AWS Bedrock API with model: {self.model}")
                
            # Call the AWS Bedrock API
            start_time = time.time()
            
            # For AWS Bedrock, we use a structured user message with the context and query
            user_message = f"Context information:\n{context}\n\nUser Query: {message}"
            
            # Prepare messages for the API call
            messages = []
            
            # Add context messages if provided
            if context_messages:
                messages.extend(context_messages)
            
            # Add the current message
            messages.append({"role": "user", "content": user_message})
            
            try:
                response = await self.client.invoke_model(
                    modelId=self.model,
                    body=json.dumps({
                        "messages": messages,
                        "system": system_prompt,
                        "temperature": self.temperature,
                        "top_p": self.top_p,
                        "max_tokens": self.max_tokens
                    })
                )
            except Exception as api_error:
                self.logger.error(f"AWS Bedrock API error: {str(api_error)}")
                if self.verbose:
                    self.logger.debug(f"Request: model={self.model}, system={system_prompt[:50]}..., messages={messages}")
                raise
            
            processing_time = self._measure_execution_time(start_time)
            
            # Parse the response
            response_body = json.loads(response['body'].read())
            
            # Extract the response text
            if not response_body.get('content'):
                self.logger.error("Unexpected response format from AWS Bedrock API: missing content")
                if self.verbose:
                    self.logger.debug(f"Response: {response_body}")
                return {"error": "Failed to get valid response from AWS Bedrock API"}
                
            response_text = response_body['content'][0]['text']
            
            if self.verbose:
                self.logger.debug(f"Response length: {len(response_text)} characters")
                
            # Format the sources for citation
            sources = self._format_sources(retrieved_docs)
            
            # Get token usage from the response
            tokens = {
                "prompt": response_body.get('usage', {}).get('prompt_tokens', 0),
                "completion": response_body.get('usage', {}).get('completion_tokens', 0),
                "total": response_body.get('usage', {}).get('total_tokens', 0)
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
        Generate a streaming response for a chat message using AWS Bedrock.
        
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
            
            # Initialize AWS client if not already initialized
            if not self.client:
                await self.initialize()
            
            if self.verbose:
                self.logger.info(f"Calling AWS Bedrock API with streaming enabled")
                
            # For AWS Bedrock, we use a structured user message with the context and query
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
                response = await self.client.invoke_model_with_response_stream(
                    modelId=self.model,
                    body=json.dumps({
                        "messages": messages,
                        "system": system_prompt,
                        "temperature": self.temperature,
                        "top_p": self.top_p,
                        "max_tokens": self.max_tokens
                    })
                )
                
                async for event in response['body']:
                    chunk = json.loads(event['chunk']['bytes'].decode())
                    chunk_count += 1
                    
                    if self.verbose and chunk_count % 10 == 0:
                        self.logger.debug(f"Received chunk {chunk_count}")
                        
                    if chunk.get('content'):
                        yield json.dumps({
                            "response": chunk['content'][0]['text'],
                            "done": False
                        })
            except Exception as stream_error:
                self.logger.error(f"AWS Bedrock streaming error: {str(stream_error)}")
                if self.verbose:
                    self.logger.debug(f"Stream request: model={self.model}, system={system_prompt[:50]}..., messages={messages}")
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
