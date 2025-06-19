"""
Ollama moderator implementation using Gemma 3:12b with JSON-based moderation.
"""

import logging
import asyncio
import aiohttp
import json
import os
from typing import Dict, Any, List, Optional

from .base import ModeratorService, ModerationResult

# Configure logging
logger = logging.getLogger(__name__)

class OllamaModerator(ModeratorService):
    """
    Implementation of the content moderation service using Ollama with Gemma 3:12b.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Ollama moderation service.
        
        Args:
            config: Configuration dictionary for Ollama
        """
        super().__init__(config)
        
        # Get configuration from the moderators.ollama section
        ollama_config = config.get('moderators', {}).get('ollama', {})
        
        self.base_url = ollama_config.get('base_url', 'http://localhost:11434')
        self.model = ollama_config.get('model', 'gemma3:12b')  # Using Gemma 3 12b by default
        self.batch_size = ollama_config.get('batch_size', 1)
        self.verbose = config.get('general', {}).get('verbose', False)  # Get verbose from general config
        
        # Initialize session
        self.session = None
        self._session_lock = asyncio.Lock()
        self.initialized = False
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """
        Get or create an aiohttp client session.
        Uses a lock to prevent multiple session creations.
        
        Returns:
            An aiohttp ClientSession
        """
        async with self._session_lock:
            if self.session is None or self.session.closed:
                connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
                timeout = aiohttp.ClientTimeout(total=60, connect=30)
                self.session = aiohttp.ClientSession(connector=connector, timeout=timeout)
            return self.session
    
    async def initialize(self) -> bool:
        """
        Initialize the Ollama moderation service.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # Check if the connection works
            if await self.verify_connection():
                if self.verbose:
                    logger.info(f"✅ Initialized Ollama moderation service with model {self.model}")
                self.initialized = True
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Failed to initialize Ollama moderation service: {str(e)}")
            return False
    
    async def moderate_content(self, content: str) -> ModerationResult:
        """
        Moderate content using Gemma 3 via Ollama with JSON-based moderation.
        
        Args:
            content: The text content to moderate
            
        Returns:
            ModerationResult object with moderation details
        """
        try:
            if not self.initialized:
                await self.initialize()
            
            if self.verbose:
                logger.info(f"🔍 Moderating content with {self.model}: {content[:50]}...")
            
            # Get a session
            session = await self._get_session()
            
            # System prompt for JSON-based moderation (similar to Anthropic approach)
            system_prompt = """
            You are a content moderation system. Analyze the content and determine if it violates any safety policies.
            You must respond with ONLY a valid, complete JSON object in this exact format:
            {"is_flagged": false, "categories": {"hate": 0.01, "harassment": 0.01, "sexual": 0.01, "violence": 0.01}}
            
            Set "is_flagged" to true if the content violates policies, false otherwise.
            Set category scores between 0.0 and 1.0 indicating confidence.
            
            IMPORTANT: You must respond with ONLY the JSON object. No other text, no explanations, no markdown formatting.
            """
            
            # User message asking for content moderation
            user_message = f"""
            Analyze this content for safety violations: "{content}"
            
            Respond with ONLY a valid JSON object in this format:
            {{"is_flagged": false, "categories": {{"hate": 0.01, "harassment": 0.01, "sexual": 0.01, "violence": 0.01}}}}
            
            No other text or explanations.
            """
            
            # Send the request to Ollama
            async with session.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    "stream": False,
                    "temperature": 0.0,  # Using 0 temperature for consistency
                    "max_tokens": 100  # Limit response length to ensure we get complete JSON
                }
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"❌ Ollama API error: {error_text}")
                    return ModerationResult(
                        is_flagged=True,
                        categories={},
                        provider="ollama",
                        model=self.model,
                        error=f"API error: {error_text}"
                    )
                
                data = await response.json()
            
            # Extract the response
            response_text = data.get("message", {}).get("content", "").strip()
            
            # Try to fix common JSON parsing issues
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "", 1)
            if response_text.endswith("```"):
                response_text = response_text.replace("```", "", 1)
            response_text = response_text.strip()
            
            # Clean up the response text - remove newlines and extra whitespace
            response_text = ' '.join(response_text.split())
            
            # Handle incomplete JSON responses more intelligently
            if not response_text.endswith("}"):
                logger.warning(f"⚠️ Received incomplete JSON from Ollama: {response_text}")
                
                # Try to interpret partial responses
                response_lower = response_text.lower()
                
                # If the model says "unsafe" or similar, treat as unsafe (check this first)
                if any(word in response_lower for word in ["unsafe", "bad", "harmful", "dangerous", "inappropriate", "block"]):
                    logger.info(f"🔍 Interpreting partial response '{response_text}' as unsafe")
                    return ModerationResult(
                        is_flagged=True,
                        categories={"interpreted": 0.8},
                        provider="ollama",
                        model=self.model,
                        error=f"Partial response interpreted: {response_text}"
                    )
                
                # If the model just says "safe" or similar, treat as safe
                if any(word in response_lower for word in ["safe", "ok", "good", "fine", "acceptable", "pass"]):
                    logger.info(f"🔍 Interpreting partial response '{response_text}' as safe")
                    return ModerationResult(
                        is_flagged=False,
                        categories={"interpreted": 0.5},
                        provider="ollama",
                        model=self.model,
                        error=f"Partial response interpreted: {response_text}"
                    )
                
                # Default to flagging the content when we get invalid JSON
                return ModerationResult(
                    is_flagged=True,
                    categories={"error": 1.0},
                    provider="ollama",
                    model=self.model,
                    error=f"Invalid JSON response: {response_text}"
                )
            
            # Parse the JSON response
            try:
                result = json.loads(response_text)
                
                # Check for required fields
                if "is_flagged" not in result:
                    logger.warning(f"⚠️ Ollama response missing 'is_flagged' field: {response_text}")
                    result["is_flagged"] = True  # Default to flagged if missing
                
                if "categories" not in result:
                    logger.warning(f"⚠️ Ollama response missing 'categories' field: {response_text}")
                    result["categories"] = {}
                
                is_flagged = result["is_flagged"]
                categories = result["categories"]
                
                # Only log high confidence categories in verbose mode
                if self.verbose:
                    # Log high confidence categories
                    high_confidence_categories = {k: v for k, v in categories.items() if v > 0.5}
                    if high_confidence_categories:
                        logger.info(f"⚠️ Content flagged for: {high_confidence_categories}")
                    
                    if is_flagged:
                        logger.info(f"🛑 Ollama flagged content as unsafe")
                    else:
                        logger.info(f"✅ Ollama determined content is safe")
                
                return ModerationResult(
                    is_flagged=is_flagged,
                    categories=categories,
                    provider="ollama",
                    model=self.model
                )
            except json.JSONDecodeError as json_error:
                logger.error(f"❌ Failed to parse Ollama response as JSON: {response_text}")
                logger.error(f"JSON error: {str(json_error)}")
                # If we can't parse the response, default to flagging the content
                return ModerationResult(
                    is_flagged=True,
                    categories={"parse_error": 1.0},
                    provider="ollama",
                    model=self.model,
                    error=f"Failed to parse response: {response_text}"
                )
                
        except Exception as e:
            logger.error(f"❌ Error in Ollama moderation: {str(e)}")
            return ModerationResult(
                is_flagged=True,  # Default to blocking on error
                provider="ollama",
                model=self.model,
                error=f"Request error: {str(e)}"
            )
    
    async def moderate_batch(self, contents: List[str]) -> List[ModerationResult]:
        """
        Moderate multiple content items in a batch.
        
        Args:
            contents: List of text content to moderate
            
        Returns:
            List of ModerationResult objects
        """
        results = []
        
        # Process in batches
        for i in range(0, len(contents), self.batch_size):
            batch = contents[i:i+self.batch_size]
            batch_tasks = [self.moderate_content(content) for content in batch]
            batch_results = await asyncio.gather(*batch_tasks)
            results.extend(batch_results)
        
        return results
    
    async def verify_connection(self) -> bool:
        """
        Verify the connection to the Ollama API.
        
        Returns:
            True if the connection is working, False otherwise
        """
        try:
            session = await self._get_session()
            
            # First check if the API is up
            async with session.get(f"{self.base_url}/api/tags") as response:
                if response.status != 200:
                    logger.error(f"❌ Failed to connect to Ollama API: {response.status}")
                    return False
                
                # Check if model is available
                data = await response.json()
                models = [model.get('name') for model in data.get('models', [])]
                
                if not any(m == self.model or m.split(':')[0] == self.model for m in models):
                    logger.warning(f"⚠️ Model {self.model} not found in Ollama. Available models: {models}")
                    logger.warning(f"⚠️ Please pull the model with: ollama pull {self.model}")
                    return False
            
            # Test with a simple moderation request
            system_prompt = """
            You are a content moderation system. Analyze the content and determine if it violates any safety policies.
            You must respond with ONLY a valid, complete JSON object in this exact format:
            {"is_flagged": false, "categories": {"hate": 0.01, "harassment": 0.01, "sexual": 0.01, "violence": 0.01}}
            
            IMPORTANT: You must respond with ONLY the JSON object. No other text, no explanations, no markdown formatting.
            """
            
            test_message = """
            Analyze this content for safety violations: "What is the capital of France?"
            
            Respond with ONLY a valid JSON object in this format:
            {"is_flagged": false, "categories": {"hate": 0.01, "harassment": 0.01, "sexual": 0.01, "violence": 0.01}}
            
            No other text or explanations.
            """
            
            async with session.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": test_message}
                    ],
                    "stream": False,
                    "temperature": 0.0,
                    "max_tokens": 50
                }
            ) as response:
                if response.status != 200:
                    logger.error(f"❌ Failed to test moderation: {response.status}")
                    return False
                
                # Successfully connected
                if self.verbose:
                    logger.info(f"✅ Connection to Ollama verified with model {self.model}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error verifying connection to Ollama: {str(e)}")
            return False
    
    async def close(self) -> None:
        """
        Close the moderation service and release any resources.
        """
        try:
            if self.session and not self.session.closed:
                await self.session.close()
                if self.verbose:
                    logger.info("Closed Ollama session")
        except Exception as e:
            logger.error(f"❌ Error closing Ollama session: {str(e)}")
        finally:
            self.session = None
            self.initialized = False
