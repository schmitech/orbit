import json
import time
import logging
import os
from typing import Any, Dict, Optional, AsyncGenerator

from ..base_llm_client import BaseLLMClient
from ..llm_client_common import LLMClientCommon

class OpenRouterClient(BaseLLMClient, LLMClientCommon):
    """LLM client implementation for OpenRouter.ai using the OpenAI library."""

    def __init__(
        self,
        config: Dict[str, Any],
        retriever: Any,
        guardrail_service: Any = None,
        reranker_service: Any = None,
        prompt_service: Any = None,
        no_results_message: str = ""
    ):
        super().__init__(config, retriever, guardrail_service, reranker_service, prompt_service, no_results_message)

        or_cfg = config.get('inference', {}).get('openrouter', {})
        self.base_url = or_cfg.get('base_url', os.getenv('OPENROUTER_API_BASE', 'https://openrouter.ai/api/v1'))
        self.api_key = os.getenv('OPENROUTER_API_KEY', or_cfg.get('api_key', ''))
        self.model = or_cfg.get('model', 'openai/gpt-4o')
        self.temperature = or_cfg.get('temperature', 0.1)
        self.top_p = or_cfg.get('top_p', 0.8)
        self.max_tokens = or_cfg.get('max_tokens', 1024)
        self.stream = or_cfg.get('stream', True)
        self.verbose = or_cfg.get('verbose', config.get('general', {}).get('verbose', False))

        self.openai_client = None
        self.logger = logging.getLogger(__name__)

    async def initialize(self) -> None:
        """Initialize the OpenAI Async client with OpenRouter settings."""
        try:
            from openai import AsyncOpenAI
            self.openai_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            self.logger.info(f"Initialized OpenRouter client for model {self.model} at {self.base_url}")
        except ImportError:
            self.logger.error("openai package not installed. Please install with: pip install -U openai>=1.0.0")
            raise
        except Exception as e:
            self.logger.error(f"Error initializing OpenRouter client: {e}")
            raise

    async def close(self) -> None:
        """Clean up resources."""
        try:
            if self.openai_client and hasattr(self.openai_client, 'close'):
                await self.openai_client.close()
                self.logger.info("Closed OpenRouter client session")
        except Exception as e:
            self.logger.error(f"Error closing OpenRouter client: {e}")
        finally:
            self.logger.info("OpenRouter client resources released")

    async def verify_connection(self) -> bool:
        """Ping OpenRouter endpoint via a minimal completion."""
        try:
            if not self.openai_client:
                await self.initialize()
            # simple ping
            resp = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Ping"}
                ],
                max_completion_tokens=1,
                stream=False
            )
            return True
        except Exception as e:
            self.logger.error(f"OpenRouter verification failed: {e}")
            return False

    async def generate_response(
        self,
        message: str,
        collection_name: str,
        system_prompt_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Non-streaming chat completion using OpenRouter.ai."""
        is_safe, refusal_message = await self._check_message_safety(message)
        if not is_safe:
            return await self._handle_unsafe_message(refusal_message)

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

        if not self.openai_client:
            await self.initialize()

        start = time.time()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context information:\n{context}\n\nUser Query: {message}"}
        ]
        params = {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "stream": False
        }
        response = await self.openai_client.chat.completions.create(**params)
        elapsed = time.time() - start

        text = response.choices[0].message.content
        sources = self._format_sources(docs)
        usage = response.usage if hasattr(response, 'usage') else None
        tokens = getattr(usage, 'total_tokens', None)

        return {
            "response": text,
            "sources": sources,
            "tokens": tokens,
            "token_usage": {
                "prompt": getattr(usage, 'prompt_tokens', None),
                "completion": getattr(usage, 'completion_tokens', None),
                "total": tokens
            },
            "processing_time": elapsed
        }

    async def generate_response_stream(
        self,
        message: str,
        collection_name: str,
        system_prompt_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Streaming chat completion using OpenRouter.ai."""
        is_safe, refusal_message = await self._check_message_safety(message)
        if not is_safe:
            yield await self._handle_unsafe_message_stream(refusal_message)
            return

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

        if not self.openai_client:
            await self.initialize()

        start = time.time()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context information:\n{context}\n\nUser Query: {message}"}
        ]
        params = {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "stream": True
        }
        resp_stream = await self.openai_client.chat.completions.create(**params)
        chunk_count = 0
        async for chunk in resp_stream:
            if chunk.choices and chunk.choices[0].delta.content:
                chunk_count += 1
                if self.verbose and chunk_count % 10 == 0:
                    self.logger.debug(f"Received chunk {chunk_count}")
                yield json.dumps({"response": chunk.choices[0].delta.content, "done": False})

        # final sources
        yield json.dumps({"sources": self._format_sources(docs), "done": True})
