"""
Ollama LLM client for generating responses
"""

import os
import json
import asyncio
import logging
import aiohttp
from typing import Dict, Any, Tuple, Optional

from config.config_manager import _is_true_value

# Configure logging
logger = logging.getLogger(__name__)


class OllamaClient:
    """Handles communication with Ollama API"""

    def __init__(self, config: Dict[str, Any], retriever, guardrail_service=None, reranker_service=None, no_results_message: Optional[str] = None):
        self.config = config
        self.base_url = config['ollama']['base_url']
        self.model = config['ollama']['model']
        self.retriever = retriever
        self.guardrail_service = guardrail_service
        self.reranker_service = reranker_service
        self.verbose = _is_true_value(config.get('general', {}).get('verbose', False))
        
        # Summarization settings
        self.summarization_enabled = config.get('ollama', {}).get('summarization', {}).get('enabled', False)
        self.summarization_model = config.get('ollama', {}).get('summarization', {}).get('model', self.model)
        self.max_length = config.get('ollama', {}).get('summarization', {}).get('max_length', 100)
        self.min_text_length = config.get('ollama', {}).get('summarization', {}).get('min_text_length', 200)
        
        # Set no results message
        self.no_results_message = no_results_message or "Could not load no results message."
        
        # Initialize session as None (lazy initialization)
        self.session = None

    async def initialize(self):
        """Initialize the aiohttp session with a timeout and TCP connector to reduce latency"""
        if self.session is None:
            # Use a higher timeout for API calls
            timeout = aiohttp.ClientTimeout(total=self.config['ollama'].get('timeout', 10))
            connector = aiohttp.TCPConnector(limit=self.config['ollama'].get('connector_limit', 20))
            self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)

    async def close(self):
        """Close the aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None

    async def verify_connection(self) -> bool:
        """Verify connection to Ollama service"""
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
        Returns a tuple of (is_safe, refusal_message)
        """
        # Use the guardrail service if available, otherwise return safe
        if self.guardrail_service:
            return await self.guardrail_service.check_safety(query)
        else:
            logger.warning("No GuardrailService provided - skipping safety check")
            return True, None

    async def _format_prompt(self, message: str, context):
        """Format the prompt with context using efficient string concatenation"""
        context_lines = []
        if context:
            context_lines.append("Here is some relevant information:\n\n")
            for item in context:
                if "question" in item and "answer" in item:
                    context_lines.append(f"Question: {item['question']}\nAnswer: {item['answer']}\n\n")
                elif "content" in item:
                    context_lines.append(f"{item['content']}\n\n")
        context_text = "".join(context_lines)
        full_prompt = f"You are a helpful assistant that answers questions based on the provided context.\n\n"
        if context_text:
            full_prompt += f"{context_text}\n\n"
        full_prompt += f"User: {message}\n\nAssistant:"
        return full_prompt

    async def generate_response(self, message: str, stream: bool = True, collection_name: Optional[str] = None):
        """Generate a response using Chroma content and Ollama for formatting - optimized for streaming"""
        try:
            await self.initialize()

            # Set collection if provided
            if collection_name:
                await self.set_collection(collection_name)

            # First perform safety check
            is_safe, refusal_message = await self.check_safety(message)

            if self.verbose:
                logger.info(f"Safety check result: {is_safe}")

            if not is_safe:
                yield refusal_message
                return

            # Retrieve context from Chroma
            context = await self.retriever.get_relevant_context(message)
            
            # If no context is found, return the no results message
            if not context:
                yield self.no_results_message
                return
            
            # Apply reranking if the reranker service is available
            if self.reranker_service and context:
                try:
                    if self.verbose:
                        logger.info(f"Applying reranking to {len(context)} documents")
                        original_scores = [item.get("confidence", 0) for item in context]
                        logger.info(f"Original confidence scores: {original_scores}")
                    
                    reranked_context = await self.reranker_service.rerank(message, context)
                    
                    # Validate reranked results
                    if not isinstance(reranked_context, list):
                        logger.warning("Reranker returned invalid format, using original context")
                        reranked_context = context
                    elif len(reranked_context) == 0:
                        logger.warning("Reranker returned empty results, using original context")
                        reranked_context = context
                    else:
                        # Ensure all items have required fields
                        valid_items = []
                        for item in reranked_context:
                            if isinstance(item, dict) and "content" in item:
                                valid_items.append(item)
                            else:
                                logger.warning(f"Invalid item in reranked context: {item}")
                        
                        if valid_items:
                            reranked_context = valid_items
                        else:
                            logger.warning("No valid items in reranked context, using original context")
                            reranked_context = context
                    
                    if self.verbose:
                        logger.info(f"Reranking complete, got {len(reranked_context)} documents")
                        new_scores = [item.get("confidence", 0) for item in reranked_context]
                        logger.info(f"New confidence scores: {new_scores}")
                        if len(original_scores) == len(new_scores):
                            improvements = [new - orig for new, orig in zip(new_scores, original_scores)]
                            logger.info(f"Confidence score improvements: {improvements}")
                    
                    context = reranked_context
                    
                except Exception as e:
                    logger.error(f"Error in reranking: {str(e)}")
                    logger.info("Using original context due to reranking error")

            # Get the most relevant content from Chroma
            chroma_response = self.retriever.get_direct_answer(context)
            if not chroma_response:
                # If no direct answer, use the most relevant context
                chroma_response = context[0].get("content", "") if context else ""

            if self.verbose:
                logger.info("=== Chroma Response ===")
                logger.info(chroma_response)
                logger.info("=====================")

            # Format prompt with Chroma content and summarization instructions if needed
            full_prompt = "Here is the relevant information from our knowledge base:\n\n"
            
            # Log text length and threshold comparison only if summarization is enabled
            if self.verbose and self.summarization_enabled:
                logger.info("=== Text Length Analysis ===")
                logger.info(f"Text length: {len(chroma_response)} chars")
                logger.info(f"Summarization threshold: {self.min_text_length} chars")
                logger.info(f"Meets threshold: {len(chroma_response) >= self.min_text_length}")
                logger.info("=========================")
            
            # Add summarization instructions if enabled and text length exceeds threshold
            if (self.summarization_enabled and 
                len(chroma_response) >= self.min_text_length):
                if self.verbose:
                    logger.info("=== Summarization Triggered ===")
                    logger.info(f"Max summary length: {self.max_length} tokens")
                    logger.info(f"Using model: {self.summarization_model}")
                    logger.info("=============================")
                    
                full_prompt += f"""Please summarize the following text in {self.max_length} tokens or less, 
focusing on the key points and main ideas. Then use this summary to answer the user's question:

{chroma_response}

User Question: {message}

Assistant:"""
            else:
                if self.verbose and self.summarization_enabled:
                    logger.info("=== Summarization Not Triggered ===")
                    logger.info("================================")
                    
                full_prompt += f"{chroma_response}\n\nUser Question: {message}\n\nAssistant:"

            if self.verbose:
                logger.info("=== Full Prompt to Ollama ===")
                logger.info(full_prompt)
                logger.info("===========================")

            payload = {
                "model": self.model,
                "prompt": full_prompt,
                "temperature": self.config['ollama'].get('temperature', 0.1),
                "top_p": self.config['ollama'].get('top_p', 0.8),
                "top_k": self.config['ollama'].get('top_k', 20),
                "repeat_penalty": self.config['ollama'].get('repeat_penalty', 1.1),
                "num_predict": self.config['ollama'].get('num_predict', 1024),
                "num_ctx": self.config['ollama'].get('num_ctx', 8192),
                "num_threads": self.config['ollama'].get('num_threads', 8),
                "stream": stream
            }

            if self.verbose:
                logger.info("=== Ollama Payload Parameters ===")
                logger.info(f"  model: {payload['model']}")
                logger.info(f"  temperature: {payload['temperature']}")
                logger.info(f"  top_p: {payload['top_p']}")
                logger.info(f"  top_k: {payload['top_k']}")
                logger.info(f"  repeat_penalty: {payload['repeat_penalty']}")
                logger.info(f"  num_predict: {payload['num_predict']}")
                logger.info(f"  num_ctx: {payload['num_ctx']}")
                logger.info(f"  num_threads: {payload['num_threads']}")
                logger.info(f"  stream: {payload['stream']}")
                logger.info("===============================")

            async with self.session.post(f"{self.base_url}/api/generate", json=payload) as response:
                if stream:
                    last_chunk = ""
                    full_response = ""
                    if self.verbose:
                        logger.info("=== Ollama Response ===")
                    async for line in response.content:
                        line_text = line.decode('utf-8').strip()
                        if not line_text or not line_text.startswith('{'):
                            continue
                        try:
                            response_data = json.loads(line_text)
                        except json.JSONDecodeError:
                            continue
                        if response_data.get("response"):
                            chunk = response_data["response"]
                            # Add smart spacing if needed
                            if last_chunk and last_chunk[-1] in ".!?,:;" and chunk and chunk[0].isalnum():
                                chunk = " " + chunk
                            elif last_chunk and last_chunk[-1].islower() and chunk and chunk[0].isupper():
                                chunk = " " + chunk
                            last_chunk = chunk
                            full_response += chunk
                            if self.verbose:
                                logger.info(chunk)
                            yield chunk
                    if self.verbose:
                        logger.info("=====================")
                else:
                    response_data = await response.json()
                    response_text = response_data.get("response", "I'm sorry, I couldn't generate a response.")
                    if self.verbose:
                        logger.info("=== Ollama Response ===")
                        logger.info(response_text)
                        logger.info("=====================")
                    yield response_text

        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            yield "I'm sorry, an error occurred while generating a response."

    def _simple_fix_text(self, text: str) -> str:
        """Apply minimal text fixes to a chunk (focused on beginning of chunk only)"""
        if text and text[0].isalnum() and not text[0].isupper():
            return text
        elif text and text[0].isupper() and len(text) > 1:
            return " " + text if text[0].isupper() else text
        return text
    
    async def set_collection(self, collection_name: str) -> None:
        """
        Set the collection name for retrieval
        
        Args:
            collection_name: The name of the collection to use
        """
        try:
            # Update retriever to use this collection
            if self.retriever and hasattr(self.retriever, 'set_collection'):
                await self.retriever.set_collection(collection_name)
                
            if self.verbose:
                logger.info(f"Set collection to: {collection_name}")
                
        except Exception as e:
            logger.error(f"Error setting collection: {str(e)}")
            raise