"""
Ollama moderation service implementation using unified architecture.

This is a migrated version of the Ollama moderator that uses
the new unified AI services architecture and integrates with existing
ollama_utils for maximum compatibility.
"""

import logging
from typing import Dict, Any, List
import asyncio
import json

from ..providers import OllamaBaseService
from ..services import ModerationService, ModerationResult
from ..base import ServiceType

logger = logging.getLogger(__name__)


class OllamaModerationService(ModerationService, OllamaBaseService):
    """
    Ollama moderation service using unified architecture.

    This implementation leverages:
    1. Ollama utilities integration from OllamaBaseService
    2. Model warm-up and retry logic inherited
    3. Configuration parsing from base classes
    4. Connection verification automatic

    Uses a local model (typically Gemma 3:12b) to classify content safety
    with structured JSON output.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Ollama moderation service.

        Args:
            config: Configuration dictionary
        """
        # Initialize base classes
        OllamaBaseService.__init__(self, config, ServiceType.MODERATION)
        ModerationService.__init__(self, config, "ollama")

        # Get moderation-specific configuration
        provider_config = self._extract_provider_config()
        self.batch_size = provider_config.get('batch_size', 1)

        # System prompt for JSON-based moderation
        self.system_prompt = """
You are a content moderation system. Analyze the content and determine if it violates any safety policies.
You must respond with ONLY a valid, complete JSON object in this exact format:
{"is_flagged": false, "categories": {"hate": 0.01, "harassment": 0.01, "sexual": 0.01, "violence": 0.01}}

Set "is_flagged" to true if the content violates policies, false otherwise.
Set category scores between 0.0 and 1.0 indicating confidence.

IMPORTANT: You must respond with ONLY the JSON object. No other text, no explanations, no markdown formatting.
"""

    async def initialize(self) -> bool:
        """
        Initialize the Ollama moderation service.

        Uses the base class initialization with chat endpoint warmup.

        Returns:
            True if initialization was successful, False otherwise
        """
        # Use base class initialization - it automatically determines the warmup endpoint
        # based on service type (moderation -> chat)
        return await OllamaBaseService.initialize(self)

    async def moderate_content(self, content: str) -> ModerationResult:
        """
        Moderate content using a local Ollama model with JSON-based moderation.

        Args:
            content: The text content to moderate

        Returns:
            ModerationResult object with moderation details
        """
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize Ollama moderation service")

        # User message asking for content moderation
        user_message = f"""
Analyze this content for safety violations: "{content}"

Respond with ONLY a valid JSON object in this format:
{{"is_flagged": false, "categories": {{"hate": 0.01, "harassment": 0.01, "sexual": 0.01, "violence": 0.01}}}}

No other text or explanations.
"""

        async def _moderate():
            # Get a session
            session = await self.session_manager.get_session()

            # Send the request to Ollama
            async with session.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    "stream": False,
                    "temperature": 0.0,  # Using 0 temperature for consistency
                    "options": {
                        "num_predict": 100  # Limit response length
                    }
                }
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Ollama API error: {error_text}")
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
                logger.warning(f"Received incomplete JSON from Ollama: {response_text}")

                # Try to interpret partial responses
                response_lower = response_text.lower()

                # If the model says "unsafe" or similar, treat as unsafe (check this first)
                if any(word in response_lower for word in ["unsafe", "bad", "harmful", "dangerous", "inappropriate", "block"]):
                    logger.info(f"Interpreting partial response '{response_text}' as unsafe")
                    return ModerationResult(
                        is_flagged=True,
                        categories={"interpreted": 0.8},
                        provider="ollama",
                        model=self.model,
                        error=f"Partial response interpreted: {response_text}"
                    )

                # If the model just says "safe" or similar, treat as safe
                if any(word in response_lower for word in ["safe", "ok", "good", "fine", "acceptable", "pass"]):
                    logger.info(f"Interpreting partial response '{response_text}' as safe")
                    return ModerationResult(
                        is_flagged=False,
                        categories={"interpreted": 0.5},
                        provider="ollama",
                        model=self.model,
                        error=f"Partial response interpreted: {response_text}"
                    )

                # Allow content through on parse errors (likely config issue, not security)
                return ModerationResult(
                    is_flagged=False,
                    categories={"parse_error": 0.5},
                    provider="ollama",
                    model=self.model,
                    error=f"Invalid JSON response (allowed): {response_text}"
                )

            # Parse the JSON response
            try:
                result = json.loads(response_text)

                # Check for required fields
                if "is_flagged" not in result:
                    logger.warning(f"Ollama response missing 'is_flagged' field: {response_text}")
                    result["is_flagged"] = True  # Default to flagged if missing

                if "categories" not in result:
                    logger.warning(f"Ollama response missing 'categories' field: {response_text}")
                    result["categories"] = {}

                is_flagged = result["is_flagged"]
                categories = result["categories"]

                # Only log high confidence categories in debug mode
                if self.logger.isEnabledFor(10):  # DEBUG level
                    high_confidence_categories = {k: v for k, v in categories.items() if v > 0.5}
                    if high_confidence_categories:
                        logger.debug(f"Content flagged for: {high_confidence_categories}")

                    if is_flagged:
                        logger.debug("Ollama flagged content as unsafe")
                    else:
                        logger.debug("Ollama determined content is safe")

                return ModerationResult(
                    is_flagged=is_flagged,
                    categories=categories,
                    provider="ollama",
                    model=self.model
                )

            except json.JSONDecodeError as json_error:
                logger.error(f"Failed to parse Ollama response as JSON: {response_text}")
                logger.error(f"JSON error: {str(json_error)}")
                # Allow content through on parse errors (likely config issue, not security)
                return ModerationResult(
                    is_flagged=False,
                    categories={"parse_error": 0.5},
                    provider="ollama",
                    model=self.model,
                    error=f"Failed to parse response (allowed): {response_text}"
                )

        try:
            # Execute with retry logic from Ollama base class
            return await self.execute_with_retry(_moderate)

        except Exception as e:
            logger.error(f"Error in Ollama moderation: {str(e)}")
            logger.warning(f"Moderation check failed, allowing content through: {str(e)}")
            return ModerationResult(
                is_flagged=False,  # Allow on error - better UX
                provider="ollama",
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
