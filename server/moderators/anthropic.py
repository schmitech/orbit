"""
Anthropic moderator implementation.
"""

import logging
import asyncio
from typing import Dict, Any, Optional

# Configure logging
logger = logging.getLogger(__name__)

from .base import ModeratorService, ModerationResult
from utils import is_true_value

class AnthropicModerator(ModeratorService):
    """
    Implementation of the content moderation service using Anthropic's API.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Anthropic moderation service.
        
        Args:
            config: Configuration dictionary for Anthropic
        """
        super().__init__(config)
        
        # Get configuration from the moderators.anthropic section
        anthropic_config = config.get('moderators', {}).get('anthropic', {})
        
        self.api_key = anthropic_config.get('api_key')
        if not self.api_key:
            raise ValueError("Anthropic API key is required for moderation")
        
        self.model = anthropic_config.get('model', 'claude-3-haiku-20240307')
        self.temperature = anthropic_config.get('temperature', 0.0)
        self.max_tokens = anthropic_config.get('max_tokens', 10)
        self.batch_size = anthropic_config.get('batch_size', 5)
        
        # Initialize Anthropic client
        self.anthropic_client = None
        self.initialized = False
    
    async def initialize(self) -> bool:
        """
        Initialize the Anthropic moderation service.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # Import Anthropic SDK
            from anthropic import AsyncAnthropic
            
            # Initialize Anthropic client
            self.anthropic_client = AsyncAnthropic(api_key=self.api_key)
            
            # Test the connection
            if await self.verify_connection():
                logger.info(f"✅ Initialized Anthropic moderation service with model {self.model}")
                self.initialized = True
                return True
            return False
        except ImportError:
            logger.error("❌ anthropic package not installed or outdated. Please install with: pip install anthropic>=0.50.0")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to initialize Anthropic moderation service: {str(e)}")
            return False
    
    async def moderate_content(self, content: str) -> ModerationResult:
        """
        Moderate content using Anthropic's API.
        
        Args:
            content: The text content to moderate
            
        Returns:
            ModerationResult object with moderation details
        """
        try:
            if not self.initialized or not self.anthropic_client:
                await self.initialize()
            
            # Check if verbose mode is enabled in config
            verbose = self.config.get('general', {}).get('verbose', False)
            
            if is_true_value(verbose):
                logger.info(f"🔍 Moderating content with Anthropic: {content[:50]}...")
            
            # Simpler system prompt to ensure valid JSON response
            system_prompt = """
            You are a content moderation system. Analyze the content and determine if it violates any safety policies.
            You must respond with ONLY a valid, complete JSON object in this exact format:
            {"is_flagged": false, "categories": {"hate": 0.01, "harassment": 0.01, "sexual": 0.01, "violence": 0.01}}
            
            Set "is_flagged" to true if the content violates policies, false otherwise.
            Set category scores between 0.0 and 1.0 indicating confidence.
            """
            
            # User message asking for content moderation - simplified to ensure valid output
            user_message = f"""
            Analyze this content for safety violations: "{content}"
            
            Only respond with a valid JSON object. Do not include any other text or explanations.
            """
            
            # Call Anthropic API with higher max_tokens to ensure we get complete JSON
            response = await self.anthropic_client.messages.create(
                model=self.model,
                max_tokens=100,  # Increased to ensure we get complete JSON
                temperature=0.0,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_message}
                ]
            )
            
            # Extract the response text
            response_text = response.content[0].text.strip()
            
            # Try to fix common JSON parsing issues
            if response_text.startswith("```json"):
                response_text = response_text.replace("```json", "", 1)
            if response_text.endswith("```"):
                response_text = response_text.replace("```", "", 1)
            response_text = response_text.strip()
            
            # Handle incomplete JSON by providing default values
            if response_text.endswith("}") == False:
                logger.warning(f"⚠️ Received incomplete JSON from Anthropic: {response_text}")
                # Default to flagging the content when we get invalid JSON
                return ModerationResult(
                    is_flagged=True,
                    categories={"error": 1.0},
                    provider="anthropic",
                    model=self.model,
                    error=f"Invalid JSON response: {response_text}"
                )
            
            # Parse the JSON response
            import json
            try:
                result = json.loads(response_text)
                
                # Check for required fields
                if "is_flagged" not in result:
                    logger.warning(f"⚠️ Anthropic response missing 'is_flagged' field: {response_text}")
                    result["is_flagged"] = True  # Default to flagged if missing
                
                if "categories" not in result:
                    logger.warning(f"⚠️ Anthropic response missing 'categories' field: {response_text}")
                    result["categories"] = {}
                
                is_flagged = result["is_flagged"]
                categories = result["categories"]
                
                # Only log high confidence categories in verbose mode
                if is_true_value(verbose):
                    # Log high confidence categories
                    high_confidence_categories = {k: v for k, v in categories.items() if v > 0.5}
                    if high_confidence_categories:
                        logger.info(f"⚠️ Content flagged for: {high_confidence_categories}")
                    
                    if is_flagged:
                        logger.info(f"🛑 Anthropic flagged content as unsafe")
                    else:
                        logger.info(f"✅ Anthropic determined content is safe")
                
                return ModerationResult(
                    is_flagged=is_flagged,
                    categories=categories,
                    provider="anthropic",
                    model=self.model
                )
            except json.JSONDecodeError as json_error:
                logger.error(f"❌ Failed to parse Anthropic response as JSON: {response_text}")
                logger.error(f"JSON error: {str(json_error)}")
                # If we can't parse the response, default to flagging the content
                return ModerationResult(
                    is_flagged=True,
                    categories={"parse_error": 1.0},
                    provider="anthropic",
                    model=self.model,
                    error=f"Failed to parse response: {response_text}"
                )
                
        except Exception as e:
            logger.error(f"❌ Error in Anthropic moderation: {str(e)}")
            return ModerationResult(
                is_flagged=True,  # Default to blocking on error
                provider="anthropic",
                model=self.model,
                error=f"Request error: {str(e)}"
            )
    
    async def moderate_batch(self, contents: list[str]) -> list[ModerationResult]:
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
        Verify the connection to the Anthropic API.
        
        Returns:
            True if the connection is working, False otherwise
        """
        try:
            if not self.anthropic_client:
                from anthropic import AsyncAnthropic
                self.anthropic_client = AsyncAnthropic(api_key=self.api_key)
            
            # Try a simple moderation request
            response = await self.anthropic_client.messages.create(
                model=self.model,
                max_tokens=10,
                temperature=0,
                messages=[
                    {"role": "user", "content": "Test connection"}
                ]
            )
            
            # Don't log success here, only in initialize()
            return True
        except Exception as e:
            logger.error(f"❌ Error verifying connection to Anthropic API: {str(e)}")
            return False
    
    async def close(self) -> None:
        """
        Close the moderation service and release any resources.
        """
        try:
            if self.anthropic_client and hasattr(self.anthropic_client, "close"):
                await self.anthropic_client.close()
                logger.info("Closed Anthropic client session")
        except Exception as e:
            logger.error(f"❌ Error closing Anthropic client: {str(e)}")
        
        self.initialized = False
