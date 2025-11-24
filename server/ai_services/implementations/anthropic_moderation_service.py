"""
Anthropic moderation service implementation using unified architecture.

This is a migrated version of the Anthropic moderator that uses
the new unified AI services architecture.
"""

import logging
from typing import Dict, Any, List
import asyncio
import json

from ..providers import AnthropicBaseService
from ..services import ModerationService, ModerationResult
from ..base import ServiceType

logger = logging.getLogger(__name__)


class AnthropicModerationService(ModerationService, AnthropicBaseService):
    """
    Anthropic moderation service using unified architecture.

    This implementation leverages:
    1. API key management from AnthropicBaseService
    2. AsyncAnthropic client initialization automatic
    3. Configuration parsing from base classes
    4. Error handling via _handle_anthropic_error()

    Uses Claude to classify content safety with structured JSON output.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Anthropic moderation service.

        Args:
            config: Configuration dictionary
        """
        # Initialize base classes
        AnthropicBaseService.__init__(self, config, ServiceType.MODERATION)
        ModerationService.__init__(self, config, "anthropic")

        # Get moderation-specific configuration
        provider_config = self._extract_provider_config()
        self.model = provider_config.get('model', 'claude-3-haiku-20240307')
        self.temperature = provider_config.get('temperature', 0.0)
        self.max_tokens = provider_config.get('max_tokens', 100)
        self.batch_size = provider_config.get('batch_size', 5)

        # System prompt for JSON-based moderation
        self.system_prompt = """
You are a content moderation system. Analyze the content and determine if it violates any safety policies.
You must respond with ONLY a valid, complete JSON object in this exact format:
{"is_flagged": false, "categories": {"hate": 0.01, "harassment": 0.01, "sexual": 0.01, "violence": 0.01}}

Set "is_flagged" to true if the content violates policies, false otherwise.
Set category scores between 0.0 and 1.0 indicating confidence.
"""

    async def moderate_content(self, content: str) -> ModerationResult:
        """
        Moderate content using Anthropic's API.

        Args:
            content: The text content to moderate

        Returns:
            ModerationResult object with moderation details
        """
        if not self.initialized:
            await self.initialize()

        try:
            # User message asking for content moderation - simplified to ensure valid output
            user_message = f"""
Analyze this content for safety violations: "{content}"

Only respond with a valid JSON object. Do not include any other text or explanations.
"""

            # Call Anthropic API
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=self.system_prompt,
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
            if not response_text.endswith("}"):
                logger.warning(f"Received incomplete JSON from Anthropic: {response_text}")
                # Allow content through on parse errors (likely config issue, not security)
                return ModerationResult(
                    is_flagged=False,
                    categories={"parse_error": 0.5},
                    provider="anthropic",
                    model=self.model,
                    error=f"Invalid JSON response (allowed): {response_text}"
                )

            # Parse the JSON response
            try:
                result = json.loads(response_text)

                # Check for required fields
                if "is_flagged" not in result:
                    logger.warning(f"Anthropic response missing 'is_flagged' field: {response_text}")
                    result["is_flagged"] = True  # Default to flagged if missing

                if "categories" not in result:
                    logger.warning(f"Anthropic response missing 'categories' field: {response_text}")
                    result["categories"] = {}

                is_flagged = result["is_flagged"]
                categories = result["categories"]

                # Only log high confidence categories in debug mode
                if self.logger.isEnabledFor(10):  # DEBUG level
                    high_confidence_categories = {k: v for k, v in categories.items() if v > 0.5}
                    if high_confidence_categories:
                        logger.debug(f"Content flagged for: {high_confidence_categories}")

                    if is_flagged:
                        logger.debug("Anthropic flagged content as unsafe")
                    else:
                        logger.debug("Anthropic determined content is safe")

                return ModerationResult(
                    is_flagged=is_flagged,
                    categories=categories,
                    provider="anthropic",
                    model=self.model
                )

            except json.JSONDecodeError as json_error:
                logger.error(f"Failed to parse Anthropic response as JSON: {response_text}")
                logger.error(f"JSON error: {str(json_error)}")
                # Allow content through on parse errors (likely config issue, not security)
                return ModerationResult(
                    is_flagged=False,
                    categories={"parse_error": 0.5},
                    provider="anthropic",
                    model=self.model,
                    error=f"Failed to parse response (allowed): {response_text}"
                )

        except Exception as e:
            self._handle_anthropic_error(e, "content moderation")
            logger.warning(f"Moderation check failed, allowing content through: {str(e)}")
            return ModerationResult(
                is_flagged=False,  # Allow on error - better UX
                provider="anthropic",
                model=self.model,
                error=f"Moderation check failed (allowed): {str(e)}"
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
