"""
Anthropic moderation service implementation using unified architecture.

This is a migrated version of the Anthropic moderator that uses
the new unified AI services architecture with expanded safety categories.
"""

import logging
from typing import Dict, Any, List
import asyncio
import json

from ...providers import AnthropicBaseService
from ...services import ModerationService, ModerationResult
from ...base import ServiceType

logger = logging.getLogger(__name__)


# Expanded category set aligned with MLCommons taxonomy and OpenAI categories
ANTHROPIC_CATEGORIES = [
    "violent_crimes",
    "non_violent_crimes",
    "sex_related_crimes",
    "child_exploitation",
    "defamation",
    "specialized_advice",
    "privacy",
    "intellectual_property",
    "indiscriminate_weapons",
    "hate",
    "harassment",
    "self_harm",
    "sexual",
    "elections",
    "code_interpreter_abuse",
]


class AnthropicModerationService(ModerationService, AnthropicBaseService):
    """
    Anthropic moderation service using unified architecture.

    This implementation leverages:
    1. API key management from AnthropicBaseService
    2. AsyncAnthropic client initialization automatic
    3. Configuration parsing from base classes
    4. Error handling via _handle_anthropic_error()
    5. Expanded category set aligned with MLCommons taxonomy

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
        self.max_tokens = provider_config.get('max_tokens', 200)
        self.batch_size = provider_config.get('batch_size', 5)

        # Build category scores template for JSON output
        self._category_template = {cat: 0.0 for cat in ANTHROPIC_CATEGORIES}

        # System prompt for JSON-based moderation with expanded categories
        self.system_prompt = """You are a content moderation system. Analyze the content and determine if it violates any safety policies.

You must respond with ONLY a valid JSON object in this exact format:
{"is_flagged": false, "categories": {"violent_crimes": 0.0, "non_violent_crimes": 0.0, "sex_related_crimes": 0.0, "child_exploitation": 0.0, "defamation": 0.0, "specialized_advice": 0.0, "privacy": 0.0, "intellectual_property": 0.0, "indiscriminate_weapons": 0.0, "hate": 0.0, "harassment": 0.0, "self_harm": 0.0, "sexual": 0.0, "elections": 0.0, "code_interpreter_abuse": 0.0}}

Category definitions:
- violent_crimes: Content enabling, encouraging, or excusing violent crimes
- non_violent_crimes: Content enabling, encouraging, or excusing non-violent crimes (theft, fraud, hacking)
- sex_related_crimes: Content enabling, encouraging, or excusing sex-related crimes
- child_exploitation: Any content depicting or enabling child exploitation
- defamation: Content that defames specific individuals
- specialized_advice: Dangerous advice (medical, legal, financial) without proper disclaimers
- privacy: Content that violates individual privacy
- intellectual_property: Content that violates intellectual property rights
- indiscriminate_weapons: Content about creating weapons of mass destruction
- hate: Content that demeans people based on protected characteristics
- harassment: Threatening or abusive content targeting individuals
- self_harm: Content that encourages suicide or self-harm
- sexual: Explicit sexual content
- elections: False information about elections or voting
- code_interpreter_abuse: Attempts to abuse code interpreters or systems

Set "is_flagged" to true if the content violates ANY policy, false otherwise.
Set category scores between 0.0 (not present) and 1.0 (definitely present).
Only output the JSON object, nothing else."""

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
            # User message asking for content moderation
            user_message = f"""Analyze this content for safety violations:

"{content}"

Respond with only the JSON object."""

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

            # Clean up common JSON formatting issues
            response_text = self._clean_json_response(response_text)

            # Parse the JSON response
            try:
                result = json.loads(response_text)

                # Validate and extract fields
                is_flagged = result.get("is_flagged", False)
                categories = result.get("categories", {})

                # Ensure all category values are floats
                categories = {k: float(v) for k, v in categories.items() if isinstance(v, (int, float))}

                # Log the result
                if is_flagged:
                    high_scores = {k: v for k, v in categories.items() if v > 0.5}
                    logger.debug(f"Anthropic flagged content - high score categories: {high_scores}")
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

                # Try to interpret the response if it contains safety keywords
                return self._interpret_non_json_response(response_text)

        except Exception as e:
            self._handle_anthropic_error(e, "content moderation")
            logger.warning(f"Moderation check failed, allowing content through: {str(e)}")
            return ModerationResult(
                is_flagged=False,  # Fail-open on errors
                provider="anthropic",
                model=self.model,
                error=f"Moderation check failed (allowed): {str(e)}"
            )

    def _clean_json_response(self, response_text: str) -> str:
        """
        Clean up common JSON formatting issues in LLM responses.

        Args:
            response_text: Raw response text

        Returns:
            Cleaned JSON string
        """
        # Remove markdown code blocks
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        elif response_text.startswith("```"):
            response_text = response_text[3:]

        if response_text.endswith("```"):
            response_text = response_text[:-3]

        # Remove any leading/trailing whitespace
        response_text = response_text.strip()

        # Remove any text before the first {
        if '{' in response_text:
            response_text = response_text[response_text.index('{'):]

        # Remove any text after the last }
        if '}' in response_text:
            response_text = response_text[:response_text.rindex('}')+1]

        return response_text

    def _interpret_non_json_response(self, response_text: str) -> ModerationResult:
        """
        Attempt to interpret a non-JSON response for safety signals.

        Args:
            response_text: The non-JSON response text

        Returns:
            ModerationResult based on interpretation
        """
        response_lower = response_text.lower()

        # Check for unsafe indicators
        unsafe_keywords = ["unsafe", "violates", "harmful", "dangerous", "inappropriate",
                          "blocked", "reject", "cannot assist", "not allowed"]
        safe_keywords = ["safe", "acceptable", "allowed", "appropriate", "no violation"]

        # Check unsafe first (fail-safe)
        if any(keyword in response_lower for keyword in unsafe_keywords):
            logger.info(f"Interpreted non-JSON response as unsafe: {response_text[:100]}")
            return ModerationResult(
                is_flagged=True,
                categories={"interpreted_unsafe": 0.8},
                provider="anthropic",
                model=self.model,
                error=f"Non-JSON response interpreted as unsafe"
            )

        # Check for safe indicators
        if any(keyword in response_lower for keyword in safe_keywords):
            logger.info(f"Interpreted non-JSON response as safe: {response_text[:100]}")
            return ModerationResult(
                is_flagged=False,
                categories={"interpreted_safe": 0.5},
                provider="anthropic",
                model=self.model,
                error=f"Non-JSON response interpreted as safe"
            )

        # Ambiguous - fail-open
        logger.warning(f"Could not interpret response, allowing through: {response_text[:100]}")
        return ModerationResult(
            is_flagged=False,
            categories={"parse_error": 0.5},
            provider="anthropic",
            model=self.model,
            error=f"Failed to parse response (allowed): {response_text[:100]}"
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
