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
    
    def __init__(self, config: Dict[str, Any], retriever):
        self.config = config
        self.base_url = config['ollama']['base_url']
        self.model = config['ollama']['model']
        self.retriever = retriever
        self.system_prompt = self._load_system_prompt()
        self.safety_prompt = self._load_safety_prompt()
        self.verbose = _is_true_value(config.get('general', {}).get('verbose', False))
        # Create aiohttp ClientSession for async requests
        self.session = None
    
    def _load_system_prompt(self):
        """Load system prompt from file if available"""
        try:
            prompt_file = self.config.get('general', {}).get('system_prompt_file', '../prompts/system_prompt.txt')
            with open(prompt_file, 'r') as file:
                return file.read().strip()
        except Exception as e:
            logger.warning(f"Could not load system prompt: {str(e)}")
            return """You are a helpful assistant that answers questions based on the provided context."""
    
    def _load_safety_prompt(self):
        """Load safety prompt from file if available"""
        try:
            prompt_file = self.config.get('general', {}).get('safety_prompt_file', '../prompts/safety_prompt.txt')
            with open(prompt_file, 'r') as file:
                return file.read().strip()
        except Exception as e:
            logger.error(f"Could not load safety prompt from file {prompt_file}: {str(e)}")
            raise RuntimeError(f"Safety prompt file '{prompt_file}' is required but could not be loaded: {str(e)}")
    
    async def initialize(self):
        """Initialize the aiohttp session"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
    
    async def close(self):
        """Close the aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def verify_connection(self) -> bool:
        """Verify connection to Ollama service"""
        try:
            # Use aiohttp for non-blocking requests
            await self.initialize()
            async with self.session.get(f"{self.base_url}/api/tags") as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Failed to connect to Ollama: {str(e)}")
            return False
    
    async def check_safety(self, query: str) -> Tuple[bool, Optional[str]]:
        """
        Perform a safety pre-clearance check on the user query.
        Returns a tuple of (is_safe, refusal_message)
        """
        try:
            await self.initialize()  # Ensure session is initialized
            
            # Use the loaded safety prompt + the query
            prompt = self.safety_prompt + " Query: " + query
            
            # Create payload for Ollama API
            payload = {
                "model": self.model,
                "prompt": prompt,
                "temperature": 0.0,  # Use 0 for deterministic response
                "top_p": 1.0,
                "top_k": 1,
                "repeat_penalty": self.config['ollama'].get('repeat_penalty', 1.1),
                "num_predict": 20,  # Limit response length
                "stream": False
            }
            
            start_time = asyncio.get_event_loop().time()
            # Make direct API call to Ollama
            async with self.session.post(f"{self.base_url}/api/generate", json=payload) as response:
                if response.status != 200:
                    logger.error(f"Safety check failed with status {response.status}")
                    return False, "I cannot assist with that type of request."
                
                data = await response.json()
                model_response = data.get("response", "").strip()
                
                if self.verbose:
                    end_time = asyncio.get_event_loop().time()
                    logger.info(f"Safety check completed in {end_time - start_time:.3f}s")
                    logger.info(f"Safety check response: {model_response}")
                
                # Check if response indicates the query is safe
                is_safe = model_response == "SAFE: true"
                refusal_message = None if is_safe else "I cannot assist with that type of request."
                
                return is_safe, refusal_message
                
        except Exception as e:
            logger.error(f"Error in safety check: {str(e)}")
            # On error, err on the side of caution
            return False, "I cannot assist with that type of request."
    
    async def _format_prompt(self, message: str, context):
        """Format the prompt with context"""
        # Format context for prompt
        context_text = ""
        if context:
            context_text = "Here is some relevant information:\n\n"
            for item in context:
                if "question" in item and "answer" in item:
                    context_text += f"Question: {item['question']}\nAnswer: {item['answer']}\n\n"
                elif "content" in item:
                    context_text += f"{item['content']}\n\n"
        
        # Create full prompt with system message, context, and user query
        full_prompt = f"{self.system_prompt}\n\n"
        if context_text:
            full_prompt += f"{context_text}\n\n"
        full_prompt += f"User: {message}\n\nAssistant:"
        
        return full_prompt
    
    async def generate_response(self, message: str, stream: bool = True):
        """Generate a response using Ollama and retrieved context with safety check - optimized for streaming"""
        try:
            # Ensure session is initialized
            await self.initialize()
            
            # Perform safety check first
            start_time = asyncio.get_event_loop().time()
            is_safe, refusal_message = await self.check_safety(message)
            
            if self.verbose:
                safety_time = asyncio.get_event_loop().time() - start_time
                logger.info(f"Safety check took {safety_time:.3f}s, result: {is_safe}")
            
            # If not safe, return the refusal message
            if not is_safe:
                if stream:
                    yield refusal_message
                else:
                    yield refusal_message
                return
            
            # Get relevant context
            context = await self.retriever.get_relevant_context(message)
            
            # Check for direct answer with high confidence
            direct_answer = self.retriever.get_direct_answer(context)
            if direct_answer:
                if self.verbose:
                    logger.info(f"Using direct answer: {direct_answer}")
                if stream:
                    yield direct_answer
                else:
                    yield direct_answer
                return
            
            # Format prompt
            full_prompt = await self._format_prompt(message, context)
            
            # Create request payload
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
            
            # Make async request to Ollama
            async with self.session.post(f"{self.base_url}/api/generate", json=payload) as response:
                if stream:
                    # Process streaming response more efficiently
                    last_chunk = ""
                    async for line in response.content:
                        try:
                            line_text = line.decode('utf-8').strip()
                            if not line_text:
                                continue
                                
                            response_data = json.loads(line_text)
                            if response_data.get("response"):
                                chunk = response_data["response"]
                                
                                # Smart space addition only when needed
                                if last_chunk and last_chunk[-1] in ".!?,:;" and chunk and chunk[0].isalnum():
                                    chunk = " " + chunk
                                # Add space between lowercase and uppercase only when needed
                                elif last_chunk and last_chunk[-1].islower() and chunk and chunk[0].isupper():
                                    chunk = " " + chunk
                                    
                                last_chunk = chunk
                                yield chunk
                        except json.JSONDecodeError:
                            continue
                else:
                    # For non-streaming, yield the complete response once
                    response_data = await response.json()
                    yield response_data.get("response", "I'm sorry, I couldn't generate a response.")
                
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            yield "I'm sorry, an error occurred while generating a response."

    def _simple_fix_text(self, text: str) -> str:
        """Apply minimal text fixes to a chunk (focused on beginning of chunk only)"""
        # Only fix beginning of chunk if needed - for connecting to previous chunk
        if text and text[0].isalnum() and not text[0].isupper():
            # This might be continuing a sentence, so no changes needed
            return text
        elif text and text[0].isupper() and len(text) > 1:
            # This could be a new sentence, might need a space
            return " " + text if text[0].isupper() else text
        return text