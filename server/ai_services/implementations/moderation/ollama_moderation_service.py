"""
Ollama moderation service implementation using Llama Guard 3.

This implementation uses Meta's Llama Guard 3 model which is specifically
designed for content safety classification using the MLCommons taxonomy.
"""

import logging
from typing import Dict, Any, List
import asyncio

from ...providers import OllamaBaseService
from ...services import ModerationService, ModerationResult
from ...base import ServiceType

logger = logging.getLogger(__name__)


# Llama Guard 3 hazard categories (MLCommons taxonomy)
LLAMA_GUARD_CATEGORIES = {
    "S1": "violent_crimes",
    "S2": "non_violent_crimes",
    "S3": "sex_related_crimes",
    "S4": "child_exploitation",
    "S5": "defamation",
    "S6": "specialized_advice",
    "S7": "privacy",
    "S8": "intellectual_property",
    "S9": "indiscriminate_weapons",
    "S10": "hate",
    "S11": "self_harm",
    "S12": "sexual",
    "S13": "elections",
    "S14": "code_interpreter_abuse",
}


class OllamaModerationService(ModerationService, OllamaBaseService):
    """
    Ollama moderation service using Llama Guard 3.

    This implementation leverages:
    1. Meta's Llama Guard 3 model for content safety classification
    2. MLCommons hazard taxonomy with 14 categories
    3. Simple "safe" / "unsafe" output parsing
    4. Ollama utilities integration from OllamaBaseService

    Llama Guard 3 is specifically trained for content moderation and
    provides more accurate classification than general-purpose LLMs.
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

        # Override model to use Llama Guard 3 by default
        if not provider_config.get('model'):
            self.model = "llama-guard3:8b"
            logger.info(f"Using default Llama Guard 3 model: {self.model}")

    async def initialize(self) -> bool:
        """
        Initialize the Ollama moderation service.

        Uses the base class initialization with generate endpoint warmup
        since Llama Guard 3 uses the generate API.

        Returns:
            True if initialization was successful, False otherwise
        """
        return await OllamaBaseService.initialize(self)

    def _parse_llama_guard_response(self, response_text: str) -> tuple[bool, Dict[str, float]]:
        """
        Parse Llama Guard 3's response format.

        Llama Guard 3 returns:
        - "safe" for safe content
        - "unsafe\\nS1" (or other S-code) for unsafe content

        Args:
            response_text: Raw response from Llama Guard 3

        Returns:
            Tuple of (is_flagged, categories_dict)
        """
        response_text = response_text.strip().lower()

        # Check for safe response
        if response_text == "safe" or response_text.startswith("safe"):
            return False, {}

        # Check for unsafe response
        if "unsafe" in response_text:
            categories = {}
            lines = response_text.split('\n')

            for line in lines:
                line = line.strip().upper()
                # Look for S-codes (S1-S14)
                for code, category_name in LLAMA_GUARD_CATEGORIES.items():
                    if code in line:
                        categories[category_name] = 1.0

            # If no specific category found but marked unsafe, use generic
            if not categories:
                categories["policy_violation"] = 1.0

            return True, categories

        # Ambiguous response - log and treat as safe (fail-open)
        logger.warning(f"Ambiguous Llama Guard response: '{response_text}', treating as safe")
        return False, {"ambiguous_response": 0.5}

    async def moderate_content(self, content: str) -> ModerationResult:
        """
        Moderate content using Llama Guard 3.

        Args:
            content: The text content to moderate

        Returns:
            ModerationResult object with moderation details
        """
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize Ollama moderation service")

        # Llama Guard 3 prompt format
        # The model expects content in a specific format for classification
        prompt = f"""<|begin_of_text|><|start_header_id|>user<|end_header_id|>

Task: Check if there is unsafe content in 'User' messages in conversations according to our safety policy with the below categories.

<BEGIN UNSAFE CONTENT CATEGORIES>
S1: Violent Crimes - Content that enables, encourages, or excuses violent crimes.
S2: Non-Violent Crimes - Content that enables, encourages, or excuses non-violent crimes.
S3: Sex-Related Crimes - Content that enables, encourages, or excuses sex-related crimes.
S4: Child Sexual Exploitation - Content that depicts child sexual exploitation.
S5: Defamation - Content that defames specific individuals.
S6: Specialized Advice - Content that provides specialized advice without disclaimers.
S7: Privacy - Content that violates privacy of individuals.
S8: Intellectual Property - Content that violates intellectual property rights.
S9: Indiscriminate Weapons - Content about creating weapons of mass destruction.
S10: Hate - Content that demeans people based on protected characteristics.
S11: Suicide & Self-Harm - Content that encourages suicide or self-harm.
S12: Sexual Content - Explicit sexual content.
S13: Elections - Content that contains false information about elections.
S14: Code Interpreter Abuse - Content that attempts to abuse code interpreters.
<END UNSAFE CONTENT CATEGORIES>

<BEGIN CONVERSATION>

User: {content}

<END CONVERSATION>

Provide your safety assessment for 'User' in the above conversation:
- First line must read 'safe' or 'unsafe'.
- If unsafe, a second line must include a comma-separated list of violated categories.<|eot_id|><|start_header_id|>assistant<|end_header_id|>

"""

        async def _moderate():
            # Get a session
            session = await self.session_manager.get_session()

            # Send the request to Ollama using generate endpoint
            async with session.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.0,  # Deterministic output
                        "num_predict": 50,   # Short response expected
                        "stop": ["<|eot_id|>", "\n\n"]  # Stop tokens
                    }
                }
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Ollama API error: {error_text}")
                    return ModerationResult(
                        is_flagged=False,  # Fail-open on API errors
                        categories={"api_error": 0.5},
                        provider="ollama",
                        model=self.model,
                        error=f"API error (allowed): {error_text}"
                    )

                data = await response.json()

            # Extract the response
            response_text = data.get("response", "").strip()
            logger.debug(f"Llama Guard raw response: '{response_text}'")

            # Parse the response
            is_flagged, categories = self._parse_llama_guard_response(response_text)

            # Log the result
            if is_flagged:
                logger.debug(f"Llama Guard flagged content - categories: {categories}")
            else:
                logger.debug("Llama Guard determined content is safe")

            return ModerationResult(
                is_flagged=is_flagged,
                categories=categories,
                provider="ollama",
                model=self.model
            )

        try:
            # Execute with retry logic from Ollama base class
            return await self.execute_with_retry(_moderate)

        except Exception as e:
            logger.error(f"Error in Ollama moderation: {str(e)}")
            logger.warning(f"Moderation check failed, allowing content through: {str(e)}")
            return ModerationResult(
                is_flagged=False,  # Fail-open on errors
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
