"""
Ollama moderator implementation using Gemma 3:12b with safety prompt.
"""

import logging
import asyncio
import aiohttp
import os
import re
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
        
        # Get path to safety prompt
        server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.safety_prompt_path = os.path.join(server_dir, '..', 'prompts', 'safety_prompt.txt')
        self.safety_prompt = ""
        
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
    
    async def _load_safety_prompt(self):
        """
        Load the safety prompt from the file.
        """
        try:
            with open(self.safety_prompt_path, 'r') as f:
                self.safety_prompt = f.read()
            logger.info(f"✅ Loaded safety prompt from {self.safety_prompt_path}")
        except Exception as e:
            logger.error(f"❌ Failed to load safety prompt: {str(e)}")
            # Use a basic fallback
            self.safety_prompt = """
            You are a content safety evaluator. Evaluate if the query is safe.
            Respond with EXACTLY "SAFE: true" if the query is safe, or "SAFE: false" if it is not safe.
            """
    
    async def initialize(self) -> bool:
        """
        Initialize the Ollama moderation service.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # Load the safety prompt
            await self._load_safety_prompt()
            
            # Check if the connection works
            if await self.verify_connection():
                logger.info(f"✅ Initialized Ollama moderation service with model {self.model}")
                self.initialized = True
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Failed to initialize Ollama moderation service: {str(e)}")
            return False
    
    async def moderate_content(self, content: str) -> ModerationResult:
        """
        Moderate content using Gemma 3 via Ollama with the safety prompt.
        
        Args:
            content: The text content to moderate
            
        Returns:
            ModerationResult object with moderation details
        """
        try:
            if not self.initialized:
                await self.initialize()
            
            logger.info(f"🔍 Moderating content with {self.model}: {content[:50]}...")
            
            # Get a session
            session = await self._get_session()
            
            # Build the complete prompt with instructions
            full_prompt = f"{self.safety_prompt}\n\nQUERY: {content}"
            
            # Send the request to Ollama
            async with session.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": full_prompt}
                    ],
                    "stream": False,
                    "temperature": 0.0  # Using 0 temperature for consistency
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
            
            # Look for "SAFE: true" or "SAFE: false" in the response
            is_safe = "SAFE: true" in response_text
            is_unsafe = "SAFE: false" in response_text
            
            # If neither pattern is found, default to unsafe
            if not is_safe and not is_unsafe:
                logger.warning(f"⚠️ Unexpected response format: '{response_text}'. Defaulting to unsafe.")
                return ModerationResult(
                    is_flagged=True,
                    categories={"Uncertain": 0.9},
                    provider="ollama",
                    model=self.model,
                    error="Unexpected response format"
                )
            
            # Parse categories - simplified since we don't have specific categories
            categories = {}
            if is_unsafe:
                categories["Policy Violation"] = 0.9
            
            if is_unsafe:
                logger.info(f"🛑 Content flagged as unsafe (Response: '{response_text}')")
            else:
                logger.info(f"✅ Content determined to be safe (Response: '{response_text}')")
            
            return ModerationResult(
                is_flagged=is_unsafe,
                categories=categories,
                provider="ollama",
                model=self.model
            )
                
        except Exception as e:
            logger.error(f"❌ Error in Ollama moderation: {str(e)}")
            return ModerationResult(
                is_flagged=True,
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
            
            # Test with a known safe input
            test_prompt = f"{self.safety_prompt}\n\nQUERY: What is the capital of France?"
            async with session.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": test_prompt}
                    ],
                    "stream": False,
                    "temperature": 0.0
                }
            ) as response:
                if response.status != 200:
                    logger.error(f"❌ Failed to test safety prompt: {response.status}")
                    return False
                
                # Successfully connected
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
                logger.info("Closed Ollama session")
        except Exception as e:
            logger.error(f"❌ Error closing Ollama session: {str(e)}")
        finally:
            self.session = None
            self.initialized = False
