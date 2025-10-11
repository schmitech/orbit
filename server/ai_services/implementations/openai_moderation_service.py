"""
OpenAI moderation service implementation using unified architecture.

This is a migrated version of the OpenAI moderator that uses
the new unified AI services architecture.
"""

from typing import Dict, Any, List
import asyncio

from ..providers import OpenAIBaseService
from ..services import ModerationService, ModerationResult


class OpenAIModerationService(ModerationService, OpenAIBaseService):
    """
    OpenAI moderation service using unified architecture.

    This implementation leverages:
    1. API key management from OpenAIBaseService
    2. Client initialization automatic
    3. Configuration parsing from base classes
    4. Error handling via _handle_openai_error()

    Simplified with automatic handling of setup and configuration.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the OpenAI moderation service.

        Args:
            config: Configuration dictionary
        """
        # Initialize base classes
        OpenAIBaseService.__init__(self, config, ModerationService.service_type)
        ModerationService.__init__(self, config, "openai")

        # Get moderation-specific configuration (model defaults to latest)
        provider_config = self._extract_provider_config()
        self.model = provider_config.get('model', 'omni-moderation-latest')

    async def moderate_content(self, content: str) -> ModerationResult:
        """
        Moderate content using OpenAI's moderation API.

        Args:
            content: The text content to moderate

        Returns:
            ModerationResult object with moderation details
        """
        if not self.initialized:
            await self.initialize()

        try:
            # Use the OpenAI client to create a moderation
            # Note: OpenAI SDK is sync, so we use asyncio.to_thread
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

            # Log high confidence categories if verbose
            if self.logger.isEnabledFor(10):  # DEBUG level
                for category, score in categories.items():
                    if score > 0.5:  # Log categories with >50% confidence
                        self.logger.debug(f"Content flagged for {category} with confidence {score}")

            return ModerationResult(
                is_flagged=is_flagged,
                categories=categories,
                provider="openai",
                model=self.model
            )

        except Exception as e:
            self._handle_openai_error(e, "content moderation")
            # Default to blocking on error
            return ModerationResult(
                is_flagged=True,
                provider="openai",
                model=self.model,
                error=f"Request error: {str(e)}"
            )

    async def moderate_batch(self, contents: List[str]) -> List[ModerationResult]:
        """
        Moderate multiple content items in a batch.

        OpenAI doesn't support native batch moderation, so we process
        each item individually using asyncio.gather for parallel execution.

        Args:
            contents: List of text content to moderate

        Returns:
            List of ModerationResult objects
        """
        # Process all items in parallel
        tasks = [self.moderate_content(content) for content in contents]
        return await asyncio.gather(*tasks)
