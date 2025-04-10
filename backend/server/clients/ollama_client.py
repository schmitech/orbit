"""
Ollama LLM client for generating responses
"""

import os
import json
import asyncio
import logging
import aiohttp
from typing import Dict, Any, Tuple, Optional, List
from utils.text_utils import detect_language

from config.config_manager import _is_true_value

logger = logging.getLogger(__name__)


class OllamaClient:
    """Handles communication with Ollama API"""

    def __init__(
        self,
        config: Dict[str, Any],
        retriever,
        guardrail_service=None,
        reranker_service=None,
        no_results_message: Optional[str] = None,
    ):
        self.config = config
        self.base_url = config["ollama"]["base_url"]
        self.model = config["ollama"]["model"]
        self.retriever = retriever
        self.guardrail_service = guardrail_service
        self.reranker_service = reranker_service
        self.verbose = _is_true_value(config.get("general", {}).get("verbose", False))

        # Summarization settings
        ollama_config = config.get("ollama", {})
        summarization_config = ollama_config.get("summarization", {})
        self.summarization_enabled = summarization_config.get("enabled", False)
        self.summarization_model = summarization_config.get("model", self.model)
        self.max_length = summarization_config.get("max_length", 100)
        self.min_text_length = summarization_config.get("min_text_length", 200)

        self.no_results_message = no_results_message or "Could not load no results message."
        self.session: Optional[aiohttp.ClientSession] = None

    async def initialize(self):
        """Initialize the aiohttp session with a timeout and TCP connector to reduce latency."""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=self.config["ollama"].get("timeout", 10))
            connector = aiohttp.TCPConnector(limit=self.config["ollama"].get("connector_limit", 20))
            self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)

    async def close(self):
        """Close the aiohttp session."""
        if self.session:
            await self.session.close()
            self.session = None

    async def verify_connection(self) -> bool:
        """Verify connection to the Ollama service."""
        try:
            await self.initialize()
            async with self.session.get(f"{self.base_url}/api/tags") as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Failed to connect to Ollama: {str(e)}")
            return False

    async def check_safety(self, query: str) -> Tuple[bool, Optional[str]]:
        """
        Perform a safety pre-clearance check on the user query using the GuardrailService.
        Returns a tuple (is_safe, refusal_message).
        """
        if self.guardrail_service:
            return await self.guardrail_service.check_safety(query)
        logger.warning("No GuardrailService provided - skipping safety check")
        return True, None

    async def _format_prompt(self, message: str, context: List[Dict[str, Any]]) -> str:
        """Format the prompt by concatenating any available context with the user message."""
        context_text = ""
        if context:
            lines = ["Here is some relevant information:"]
            for item in context:
                if "question" in item and "answer" in item:
                    lines.append(f"Question: {item['question']}\n{item['answer']}")
                elif "content" in item:
                    lines.append(item["content"])
            context_text = "\n\n".join(lines)
        prompt = "I am going to ask you a question, which I would like you to answer based only on the provided context, and not any other information.\n\n"
        if context_text:
            prompt += f"{context_text}\n\n"
        prompt += f"User: {message}\n\nAssistant:"
        return prompt

    async def _apply_reranking(self, message: str, context: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Apply reranking to the retrieved context if a reranker service is provided.
        Returns the reranked context; if reranking fails or returns an invalid format, returns the original context.
        """
        if self.reranker_service and context:
            try:
                if self.verbose:
                    original_scores = [item.get("confidence", 0) for item in context]
                    logger.info(f"Applying reranking to {len(context)} documents, original scores: {original_scores}")
                reranked_context = await self.reranker_service.rerank(message, context)
                if not isinstance(reranked_context, list) or not reranked_context:
                    logger.warning("Reranker returned invalid or empty result; using original context")
                    return context
                valid_items = [item for item in reranked_context if isinstance(item, dict) and "content" in item]
                if not valid_items:
                    logger.warning("No valid items found in reranked context; using original context")
                    return context
                if self.verbose:
                    new_scores = [item.get("confidence", 0) for item in valid_items]
                    logger.info(f"Reranking complete, new confidence scores: {new_scores}")
                return valid_items
            except Exception as e:
                logger.error(f"Error in reranking: {str(e)}; using original context")
                return context
        return context

    async def generate_response(self, message: str, stream: bool = True, collection_name: Optional[str] = None):
        """
        Generate a response using Chroma content and Ollama.
        Optimized for streaming if needed.
        """
        try:
            await self.initialize()

            # Set collection if provided
            if collection_name:
                await self.set_collection(collection_name)

            # Perform safety check
            is_safe, refusal_message = await self.check_safety(message)
            if self.verbose:
                logger.info(f"Safety check result: {is_safe}")
            if not is_safe:
                yield refusal_message
                return

            # Retrieve context from Chroma
            context = await self.retriever.get_relevant_context(message)
            if not context:
                yield self.no_results_message
                return

            # Optionally apply reranking
            context = await self._apply_reranking(message, context)

            # Get a direct answer if available, otherwise fallback to most relevant context content
            chroma_response = self.retriever.get_direct_answer(context)
            if not chroma_response and context:
                # If no direct answer, try to find an answer field or use content
                if "answer" in context[0]:
                    chroma_response = f"Question: {context[0].get('question', '')}\nAnswer: {context[0].get('answer', '')}"
                else:
                    chroma_response = context[0].get("content", "")

            if self.verbose:
                logger.info("=== Chroma Response ===")
                logger.info(chroma_response)
                logger.info("=====================")

            # Detect if the user message is not in English
            query_language = detect_language(message)
            is_non_english = query_language != "en"

            # Create language instruction if needed
            language_instruction = ""
            if is_non_english:
                language_instruction = f"IMPORTANT: The user's query is in {query_language}. You MUST respond in {query_language}. "

            # Start building prompt with improved base instruction
            base_prompt = f"You are a helpful assistant. {language_instruction}"

            # Keep the existing summarization logic but improve the prompt structure
            if self.summarization_enabled and len(chroma_response) >= self.min_text_length:
                if self.verbose:
                    logger.info("Summarization triggered")
                full_prompt = (
                    f"{base_prompt}Please provide a concise, direct answer to the user's question using only the information provided. "
                    f"Do not use headings like 'Summary' or 'Answer' in your response. "
                    f"Read and understand the context carefully, but respond with a brief and to-the-point answer.\n\n"
                    f"Context:\n{chroma_response}\n\n"
                    f"User Question: {message}\n\n"
                    f"Assistant:"
                )
            else:
                if self.verbose and self.summarization_enabled:
                    logger.info("Summarization not triggered")
                full_prompt = (
                    f"{base_prompt}Please provide a concise, direct answer to the user's question using only the information provided. "
                    f"Keep your response brief and to the point.\n\n"
                    f"Context:\n{chroma_response}\n\n"
                    f"User Question: {message}\n\n"
                    f"Assistant:"
                )

            if self.verbose:
                logger.info("=== Full Prompt to Ollama ===")
                logger.info(full_prompt)
                logger.info("===========================")

            payload = {
                "model": self.model,
                "prompt": full_prompt,
                "temperature": self.config["ollama"].get("temperature", 0.1),
                "top_p": self.config["ollama"].get("top_p", 0.8),
                "top_k": self.config["ollama"].get("top_k", 20),
                "repeat_penalty": self.config["ollama"].get("repeat_penalty", 1.1),
                "num_predict": self.config["ollama"].get("num_predict", 1024),
                "num_ctx": self.config["ollama"].get("num_ctx", 8192),
                "num_threads": self.config["ollama"].get("num_threads", 8),
                "stream": stream,
            }

            if self.verbose:
                logger.info("=== Ollama Payload Parameters ===")
                for key in payload:
                    logger.info(f"  {key}: {payload[key]}")
                logger.info("===============================")

            async with self.session.post(f"{self.base_url}/api/generate", json=payload) as response:
                if stream:
                    last_chunk = ""
                    async for line in response.content:
                        line_text = line.decode("utf-8").strip()
                        if not line_text or not line_text.startswith("{"):
                            continue
                        try:
                            response_data = json.loads(line_text)
                        except json.JSONDecodeError:
                            continue
                        if response_data.get("response"):
                            chunk = response_data["response"]
                            # Smart spacing logic between chunks
                            if last_chunk and last_chunk[-1] in ".!?,:;" and chunk and chunk[0].isalnum():
                                chunk = " " + chunk
                            elif last_chunk and last_chunk[-1].islower() and chunk and chunk[0].isupper():
                                chunk = " " + chunk
                            last_chunk = chunk
                            yield chunk
                else:
                    response_data = await response.json()
                    response_text = response_data.get(
                        "response", "I'm sorry, I couldn't generate a response."
                    )
                    yield response_text

        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            yield "I'm sorry, an error occurred while generating a response."

    def _simple_fix_text(self, text: str) -> str:
        """Apply minimal text fixes to a chunk (focused on the beginning only)."""
        if text and text[0].isalnum() and not text[0].isupper():
            return text
        elif text and text[0].isupper() and len(text) > 1:
            return " " + text if text[0].isupper() else text
        return text

    async def set_collection(self, collection_name: str) -> None:
        """
        Set the collection name for retrieval.
        
        Args:
            collection_name: The name of the collection to use.
        """
        try:
            if self.retriever and hasattr(self.retriever, "set_collection"):
                await self.retriever.set_collection(collection_name)
            if self.verbose:
                logger.info(f"Set collection to: {collection_name}")
        except Exception as e:
            logger.error(f"Error setting collection: {str(e)}")
            raise