import json
import time
import logging
import os
from typing import Any, Dict, Optional, AsyncGenerator

from azure.ai.inference import ChatCompletionsClient
from azure.core.credentials import AzureKeyCredential

from ..base_llm_client import BaseLLMClient
from ..llm_client_mixin import LLMClientMixin

class AzureOpenAIClient(BaseLLMClient, LLMClientMixin):
    """LLM client implementation for Azure AI Inference."""

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
        system_prompt_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Non-streaming chat completion using Azure AI Inference."""
        if not await self._check_message_safety(message):
            return await self._handle_unsafe_message()

        docs = await self._retrieve_and_rerank_docs(message, collection_name)
        system_prompt = await self._get_system_prompt(system_prompt_id)
        context = self._format_context(docs)

        await self.initialize()
        start = time.time()

        resp = await self.client.complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Context:\n{context}\n\nUser: {message}"}
            ],
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            top_p=self.top_p,
            stream=False
        )

        elapsed = time.time() - start
        text = resp.choices[0].message.content
        sources = self._format_sources(docs)

        return {
            "response": text,
            "sources": sources,
            "tokens": None,  # Azure AI Inference doesn't provide token counts
            "token_usage": {},
            "processing_time": elapsed
        }

    async def generate_response_stream(
        self,
        message: str,
        collection_name: str,
        system_prompt_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Streaming chat completion via Azure AI Inference."""
        if not await self._check_message_safety(message):
            yield await self._handle_unsafe_message_stream()
            return

        docs = await self._retrieve_and_rerank_docs(message, collection_name)
        system_prompt = await self._get_system_prompt(system_prompt_id)
        context = self._format_context(docs)

        await self.initialize()

        stream = await self.client.complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Context:\n{context}\n\nUser: {message}"}
            ],
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            top_p=self.top_p,
            stream=True
        )

        chunk_count = 0
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                chunk_count += 1
                if self.verbose and chunk_count % 10 == 0:
                    self.logger.debug(f"Received chunk {chunk_count}")
                yield json.dumps({"response": chunk.choices[0].delta.content, "done": False})

        # final yield with sources
        yield json.dumps({"sources": self._format_sources(docs), "done": True})
