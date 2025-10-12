"""
OpenAI moderation service implementation using unified architecture.

This is a migrated version of the OpenAI moderator that uses
the new unified AI services architecture.
"""

from typing import Dict, Any, List
import asyncio

from ..providers import OpenAIBaseService
from ..services import ModerationService, ModerationResult
from ..base import ServiceType


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
        OpenAIBaseService.__init__(self, config, ServiceType.MODERATION)
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
            # Use the OpenAI async client to create a moderation
            response = await self.client.moderations.create(
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

            # Log moderation details at DEBUG level
            if self.logger.isEnabledFor(10):  # DEBUG level
                self.logger.debug(f"OpenAI Moderation - flagged={is_flagged}, all_scores={categories}")
                # Also log high confidence categories
                high_scores = {k: v for k, v in categories.items() if v > 0.5}
                if high_scores:
                    self.logger.debug(f"High confidence categories (>0.5): {high_scores}")

            return ModerationResult(
                is_flagged=is_flagged,
                categories=categories,
                provider="openai",
                model=self.model
            )

        except Exception as e:
            self._handle_openai_error(e, "content moderation")
            # Log the error but don't block - technical failures shouldn't block safe content
            self.logger.warning(f"Moderation check failed, allowing content through: {str(e)}")
            return ModerationResult(
                is_flagged=False,  # Allow on error - better UX
                provider="openai",
                model=self.model,
                error=f"Moderation check failed (allowed): {str(e)}"
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
