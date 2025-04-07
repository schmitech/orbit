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

    def __init__(self, config: Dict[str, Any], retriever, guardrail_service=None):
        self.config = config
        self.base_url = config['ollama']['base_url']
        self.model = config['ollama']['model']
        self.retriever = retriever
        self.guardrail_service = guardrail_service
        self.system_prompt = self._load_system_prompt()
        self.verbose = _is_true_value(config.get('general', {}).get('verbose', False))
        # Initialize session as None (lazy initialization)
        self.session = None

    def _load_system_prompt(self):
        """Load system prompt from file if available"""
        try:
            prompt_file = self.config.get('general', {}).get('system_prompt_file', '../prompts/system_prompt.txt')
            with open(prompt_file, 'r') as file:
                return file.read().strip()
        except Exception as e:
            logger.warning(f"Could not load system prompt: {str(e)}")
            return "You are a helpful assistant that answers questions based on the provided context."

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
        full_prompt = f"{self.system_prompt}\n\n"
        if context_text:
            full_prompt += f"{context_text}\n\n"
        full_prompt += f"User: {message}\n\nAssistant:"
        return full_prompt

    async def generate_response(self, message: str, stream: bool = True):
        """Generate a response using Ollama and retrieved context with safety check - optimized for streaming"""
        try:
            await self.initialize()

            # Start safety check and context retrieval concurrently
            safety_task = asyncio.create_task(self.check_safety(message))
            context_task = asyncio.create_task(self.retriever.get_relevant_context(message))

            is_safe, refusal_message = await safety_task

            if self.verbose:
                logger.info(f"Safety check result: {is_safe}")

            if not is_safe:
                context_task.cancel()  # Cancel context retrieval if unsafe
                yield refusal_message
                return

            context = await context_task

            # Check for direct answer with high confidence
            direct_answer = self.retriever.get_direct_answer(context)
            if direct_answer:
                if self.verbose:
                    logger.info(f"Using direct answer: {direct_answer}")
                yield direct_answer
                return

            # Format prompt
            full_prompt = await self._format_prompt(message, context)

            payload = {
                "model": self.model,
                "prompt": full_prompt,
                "temperature": self.config['ollama'].get('temperature', 0.7),
                "top_p": self.config['ollama'].get('top_p', 0.9),
                "top_k": self.config['ollama'].get('top_k', 40),
                "repeat_penalty": self.config['ollama'].get('repeat_penalty', 1.1),
                "num_predict": self.config['ollama'].get('num_predict', 1024),
                "stream": stream
            }

            if self.verbose:
                logger.info(f"Sending prompt to Ollama (length: {len(full_prompt)})")
                logger.info("Payload parameters:")
                logger.info(f"  model: {payload['model']}")
                logger.info(f"  temperature: {payload['temperature']}")
                logger.info(f"  top_p: {payload['top_p']}")
                logger.info(f"  top_k: {payload['top_k']}")
                logger.info(f"  repeat_penalty: {payload['repeat_penalty']}")
                logger.info(f"  num_predict: {payload['num_predict']}")
                logger.info(f"  stream: {payload['stream']}")

            async with self.session.post(f"{self.base_url}/api/generate", json=payload) as response:
                if stream:
                    last_chunk = ""
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
                            yield chunk
                else:
                    response_data = await response.json()
                    yield response_data.get("response", "I'm sorry, I couldn't generate a response.")

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