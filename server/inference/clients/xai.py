import json
import time
import logging
import os
import aiohttp
from typing import Dict, List, Any, Optional, AsyncGenerator

from ..base_llm_client import BaseLLMClient
from ..llm_client_common import LLMClientCommon

class XAIClient(BaseLLMClient, LLMClientCommon):
    """LLM client implementation for x.ai Grok inference."""

    def __init__(self, config: Dict[str, Any], retriever: Any = None,
                 reranker_service: Any = None, prompt_service: Any = None, no_results_message: str = ""):
        # Initialize base classes properly
        BaseLLMClient.__init__(self, config, retriever, reranker_service, prompt_service, no_results_message)
        LLMClientCommon.__init__(self)  # Initialize the common client

        xai_cfg = config.get('inference', {}).get('xai', {})
        self.api_key = os.getenv("XAI_API_KEY", xai_cfg.get('api_key', ''))
        if not self.api_key:
            raise ValueError("XAI_API_KEY environment variable or api_key in config is required")
            
        self.api_base = xai_cfg.get('api_base', 'https://api.x.ai/v1')
        self.model = xai_cfg.get('model', 'grok-3-mini-beta')
        self.temperature = xai_cfg.get('temperature', 0.1)
        self.top_p = xai_cfg.get('top_p', 0.8)
        self.max_tokens = xai_cfg.get('max_tokens', 1024)
        self.stream = xai_cfg.get('stream', True)
        self.show_thinking = xai_cfg.get('show_thinking', False)
        self.verbose = config.get('general', {}).get('verbose', False)

        self.session: aiohttp.ClientSession | None = None
        self.logger = logging.getLogger(self.__class__.__name__)

    def _clean_response(self, text: str) -> str:
        """Remove thinking process from response if show_thinking is False."""
        if not self.show_thinking:
            # Remove content between <think> tags
            import re
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
            # Clean up any extra whitespace
            text = re.sub(r'\n\s*\n', '\n\n', text)
            text = text.strip()
            # Remove any remaining thinking tags
            text = text.replace('<think>', '').replace('</think>', '')
        return text

    async def initialize(self) -> None:
        """Initialize HTTP session for x.ai calls."""
        try:
            if not self.session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                self.session = aiohttp.ClientSession(headers=headers)
                if self.verbose:
                    self.logger.info("XAIClient session initialized")
        except Exception as e:
            self.logger.error(f"Error initializing XAI client: {str(e)}")
            raise

    async def close(self) -> None:
        """Clean up HTTP session."""
        try:
            if self.session:
                await self.session.close()
                self.session = None
                self.logger.info("XAIClient session closed")
        except Exception as e:
            self.logger.error(f"Error closing XAI client: {str(e)}")

    async def verify_connection(self) -> bool:
        """Quick ping to check x.ai API is reachable."""
        try:
            await self.initialize()
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Ping"}
                ],
                "max_tokens": 1,
                "stream": False,
                "temperature": 0
            }
            async with self.session.post(f"{self.api_base}/chat/completions", json=payload) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    self.logger.error(f"XAI API error: {error_text}")
                    return False
                return True
        except Exception as e:
            self.logger.error(f"XAI verify_connection failed: {str(e)}")
            return False

    async def generate_response(
        self,
        message: str,
        collection_name: str,
        system_prompt_id: Optional[str] = None,
        context_messages: Optional[List[Dict[str, str]]] = None
    ) -> dict:
        try:
            # Retrieve context and prompts
            docs = await self._retrieve_and_rerank_docs(message, collection_name)
            system_prompt = await self._get_system_prompt(system_prompt_id)
            context = self._format_context(docs)

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

            # Initialize session if not already initialized
            if not self.session:
                await self.initialize()
            start = time.time()

            # Prepare messages array
            messages = [{"role": "system", "content": system_prompt}]
            
            # Add context messages if provided
            if context_messages:
                messages.extend(context_messages)
            
            # Add the current message with context
            messages.append({"role": "user", "content": f"Context:\n{context}\n\nUser: {message}"})

            payload = {
                "model": self.model,
                "messages": messages,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "stream": False
            }

            async with self.session.post(f"{self.api_base}/chat/completions", json=payload) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"XAI API error: {error_text}")
                data = await resp.json()

            elapsed = time.time() - start
            text = self._clean_response(data["choices"][0]["message"]["content"])
            sources = self._format_sources(docs)

            usage = data.get("usage", {})
            tokens = {
                "prompt": usage.get("prompt_tokens", 0),
                "completion": usage.get("completion_tokens", 0),
                "total": usage.get("total_tokens", 0)
            }

            # Wrap response with security checking
            response_dict = {
                "response": text,
                "sources": sources,
                "tokens": tokens["total"],
                "token_usage": tokens,
                "processing_time": elapsed
            }
            
            return await self._secure_response(response_dict)
        except Exception as e:
            self.logger.error(f"Error generating response from XAI: {str(e)}")
            raise

    async def generate_response_stream(
        self,
        message: str,
        collection_name: str,
        system_prompt_id: Optional[str] = None,
        context_messages: Optional[List[Dict[str, str]]] = None
    ) -> AsyncGenerator[str, None]:
        # Wrap the entire streaming response with security checking
        async for chunk in self._secure_response_stream(
            self._generate_response_stream_internal(message, collection_name, system_prompt_id, context_messages)
        ):
            yield chunk
    
    async def _generate_response_stream_internal(
        self,
        message: str,
        collection_name: str,
        system_prompt_id: Optional[str] = None,
        context_messages: Optional[List[Dict[str, str]]] = None
    ) -> AsyncGenerator[str, None]:
        """Streaming chat completion via Server-Sent Events."""
        try:
            docs = await self._retrieve_and_rerank_docs(message, collection_name)
            system_prompt = await self._get_system_prompt(system_prompt_id)
            context = self._format_context(docs)

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

            # Initialize session if not already initialized
            if not self.session:
                await self.initialize()

            # Prepare messages array
            messages = [{"role": "system", "content": system_prompt}]
            
            # Add context messages if provided
            if context_messages:
                messages.extend(context_messages)
            
            # Add the current message with context
            messages.append({"role": "user", "content": f"Context:\n{context}\n\nUser: {message}"})

            payload = {
                "model": self.model,
                "messages": messages,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "stream": True
            }

            sources = self._format_sources(docs)
            current_chunk = ""
            in_thinking_block = False

            async with self.session.post(f"{self.api_base}/chat/completions", json=payload) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"XAI API error: {error_text}")

                async for line in resp.content:
                    chunk = line.decode().strip()
                    if not chunk or not chunk.startswith("data:"):
                        continue
                    data = chunk[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    
                    try:
                        payload = json.loads(data)
                        delta = payload["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        
                        if content:
                            current_chunk += content
                            
                            # Check if we're entering or exiting a thinking block
                            if '<think>' in content:
                                in_thinking_block = True
                            if '</think>' in content:
                                in_thinking_block = False
                                continue
                                
                            # Only yield content if we're not in a thinking block or show_thinking is True
                            if self.show_thinking or not in_thinking_block:
                                response_data = {
                                    "response": content,
                                    "sources": [] if current_chunk else sources,
                                    "done": False
                                }
                                yield json.dumps(response_data)
                    except json.JSONDecodeError as e:
                        self.logger.error(f"Error decoding XAI stream chunk: {str(e)}")
                        continue

            # Clean up any remaining thinking content
            if not self.show_thinking:
                current_chunk = self._clean_response(current_chunk)

            # Send final message with sources
            final_response = {
                "response": "",
                "sources": sources,
                "done": True
            }
            yield json.dumps(final_response)

        except Exception as e:
            self.logger.error(f"Error generating streaming response from XAI: {str(e)}")
            error_response = {
                "error": str(e),
                "done": True
            }
            yield json.dumps(error_response)
