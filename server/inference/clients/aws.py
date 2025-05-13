import json
import time
import logging
import os
import boto3
import asyncio
from typing import Any, Optional, AsyncGenerator

from ..base_llm_client import BaseLLMClient
from ..llm_client_mixin import LLMClientMixin

class AWSBedrockClient(BaseLLMClient, LLMClientMixin):
    """LLM client implementation for AWS Bedrock via boto3."""

    def __init__(
        self,
        config: dict,
        retriever: Any,
        guardrail_service: Any = None,
        reranker_service: Any = None,
        prompt_service: Any = None,
        no_results_message: str = ""
    ):
        super().__init__(
            config,
            retriever,
            guardrail_service,
            reranker_service,
            prompt_service,
            no_results_message
        )

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
        system_prompt_id: Optional[str] = None
    ) -> dict:
        """Non-streaming chat completion using AWS Bedrock."""
        # Safety & context retrieval
        is_safe, refusal_message = await self._check_message_safety(message)
        if not is_safe:
            return await self._handle_unsafe_message(refusal_message)

        docs = await self._retrieve_and_rerank_docs(message, collection_name)
        system_prompt = await self._get_system_prompt(system_prompt_id)
        context = self._format_context(docs)

        # Prepare and send request
        await self.initialize()
        start = time.time()

        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{context}\n\n{message}"}
            ],
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens
        }

        resp = self.client.invoke_model(
            modelId=self.model,
            body=json.dumps(payload).encode("utf-8"),
            contentType=self.content_type,
            accept=self.accept
        )

        # Parse response
        raw = resp["body"].read().decode("utf-8")
        data = json.loads(raw)
        text = data["choices"][0]["message"]["content"]

        elapsed = time.time() - start
        sources = self._format_sources(docs)

        return {
            "response": text,
            "sources": sources,
            "tokens": None,  # AWS Bedrock doesn't provide token counts
            "token_usage": {},
            "processing_time": elapsed
        }

    async def generate_response_stream(
        self,
        message: str,
        collection_name: str,
        system_prompt_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Stream a response from AWS Bedrock."""
        is_safe, refusal_message = await self._check_message_safety(message)
        if not is_safe:
            yield await self._handle_unsafe_message_stream(refusal_message)
            return

        try:
            docs = await self._retrieve_and_rerank_docs(message, collection_name)
            system_prompt = await self._get_system_prompt(system_prompt_id)
            context = self._format_context(docs)
            sources = self._format_sources(docs)

            await self.initialize()

            payload = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"{context}\n\n{message}"}
                ],
                "temperature": self.temperature,
                "top_p": self.top_p,
                "max_tokens": self.max_tokens,
                "stream": True
            }

            # First chunk includes sources
            first_chunk = True
            current_chunk = ""

            resp = self.client.invoke_model_with_response_stream(
                modelId=self.model,
                body=json.dumps(payload).encode("utf-8"),
                contentType=self.content_type,
                accept=self.accept
            )

            for event in resp["body"]:
                chunk = event.get("chunk", {})
                if chunk:
                    chunk_data = json.loads(chunk.get("bytes", b"{}").decode())
                    if "choices" in chunk_data and chunk_data["choices"]:
                        delta = chunk_data["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        
                        if content:
                            current_chunk += content
                            response_data = {
                                "response": content,
                                "sources": sources if first_chunk else [],
                                "done": False
                            }
                            first_chunk = False
                            yield json.dumps(response_data)

            # Send final message
            final_response = {
                "response": "",
                "sources": sources,
                "done": True
            }
            yield json.dumps(final_response)

        except Exception as e:
            self.logger.error(f"Error generating streaming response: {str(e)}")
            error_response = {
                "error": str(e),
                "done": True
            }
            yield json.dumps(error_response)
