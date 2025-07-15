"""
OpenAI moderator implementation.
"""

import logging
import asyncio
from typing import Dict, Any, Optional
from openai import OpenAI

from .base import ModeratorService, ModerationResult
from config.config_manager import _is_true_value

# Configure logging
logger = logging.getLogger(__name__)

class OpenAIModerator(ModeratorService):
    """
    Implementation of the content moderation service using OpenAI's moderation API.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the OpenAI moderation service.
        
        Args:
            config: Configuration dictionary for OpenAI
        """
        super().__init__(config)
        
        # Get configuration from the moderators.openai section
        openai_config = config.get('moderators', {}).get('openai', {})
        
        self.api_key = openai_config.get('api_key')
        if not self.api_key:
            raise ValueError("OpenAI API key is required for moderation. Please set the OPENAI_API_KEY environment variable or configure it in moderators.yaml")
        
        self.model = openai_config.get('model', 'omni-moderation-latest')
        
        # Initialize OpenAI client
        self.client = OpenAI(api_key=self.api_key)
        self.initialized = True
    
    async def initialize(self) -> bool:
        """
        Initialize the OpenAI moderation service.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # Test the connection
            if await self.verify_connection():
                logger.info(f"Initialized OpenAI moderation service with model {self.model}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI moderation service: {str(e)}")
            return False
    
    async def moderate_content(self, content: str) -> ModerationResult:
        """
        Moderate content using OpenAI's moderation API.
        
        Args:
            content: The text content to moderate
            
        Returns:
            ModerationResult object with moderation details
        """
        try:
            # Use the OpenAI client to create a moderation
            response = await asyncio.to_thread(
                self.client.moderations.create,
                model=self.model,
                input=content
            )
            
            # Get the first result
            result = response.results[0]
            
            # If flagged is true, content is not safe
            is_flagged = result.flagged
            
            # Convert CategoryScores to a regular dictionary
            categories = {}
            for category_name, score in vars(result.category_scores).items():
                if isinstance(score, float):
                    categories[category_name] = score
            
            # Check if verbose mode is enabled in config
            verbose = self.config.get('general', {}).get('verbose', False)
            if _is_true_value(verbose):
                # Log any high confidence categories only in verbose mode
                for category, score in categories.items():
                    if score > 0.5:  # Log categories with >50% confidence
                        logger.info(f"Content flagged for {category} with confidence {score}")
            
            return ModerationResult(
                is_flagged=is_flagged,
                categories=categories,
                provider="openai",
                model=self.model
            )
                
        except Exception as e:
            logger.error(f"Error in OpenAI moderation: {str(e)}")
            return ModerationResult(
                is_flagged=True,  # Default to blocking on error
                provider="openai",
                model=self.model,
                error=f"Request error: {str(e)}"
            )
    
    async def verify_connection(self) -> bool:
        """
        Verify the connection to the OpenAI moderation API.
        
        Returns:
            True if the connection is working, False otherwise
        """
        try:
            # Try to moderate a simple test string
            result = await self.moderate_content("test connection")
            return result.error is None
        except Exception as e:
            logger.error(f"Error verifying connection to OpenAI moderation API: {str(e)}")
            return False
    
    async def close(self) -> None:
        """
        Close the moderation service and release any resources.
        """
        # The OpenAI client doesn't need explicit closing
        self.initialized = False