"""
Privacy Filter moderation service for PII detection.

This implementation uses OpenAI's privacy-filter model, a local bidirectional
token-classification model for personally identifiable information (PII)
detection (https://huggingface.co/openai/privacy-filter). The model labels
an input sequence in a single forward pass and decodes coherent PII spans,
so it runs fully on-premises with no external API calls.

Detected spans are reported as ModerationResult categories using the
"pii.<category>" naming scheme (e.g. "pii.private_email"), so this service
composes with the safety/guardrail configuration like any other moderator.
"""

import asyncio
import logging
from typing import Any, Dict, List

from ...providers import TransformersBaseService
from ...services import ModerationService, ModerationResult
from ...base import ServiceType

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "openai/privacy-filter"

# Privacy span categories detected by openai/privacy-filter
PRIVACY_FILTER_CATEGORIES = [
    "account_number",
    "private_address",
    "private_email",
    "private_person",
    "private_phone",
    "private_url",
    "private_date",
    "secret",
]


class PrivacyFilterModerationService(ModerationService, TransformersBaseService):
    """
    PII moderation service using the openai/privacy-filter model.

    Runs the model in-process via the transformers token-classification
    pipeline. Requires the 'huggingface' dependency profile
    (transformers + torch), installed via:
        ./install/setup.sh --profile huggingface

    Configuration (config/moderators.yaml under moderations.privacy_filter):
        model: HuggingFace model id (default: openai/privacy-filter)
        threshold: minimum span confidence to count a detection (default: 0.5)
        flag_categories: categories that set is_flagged when detected above
            the threshold (default: all 8 categories)
        device: "auto", "cpu", "cuda", or "mps" (default: auto)
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the privacy filter moderation service.

        Args:
            config: Configuration dictionary
        """
        # Initialize base classes (mirrors the other moderation services)
        TransformersBaseService.__init__(self, config, ServiceType.MODERATION, "privacy_filter")
        ModerationService.__init__(self, config, "privacy_filter")

        provider_config = self._extract_provider_config()
        self.threshold = float(provider_config.get('threshold', 0.5))

        flag_categories = provider_config.get('flag_categories', PRIVACY_FILTER_CATEGORIES)
        unknown = [c for c in flag_categories if c not in PRIVACY_FILTER_CATEGORIES]
        if unknown:
            logger.warning(
                f"Ignoring unknown privacy filter flag_categories: {unknown}. "
                f"Valid categories: {PRIVACY_FILTER_CATEGORIES}"
            )
        self.flag_categories = {c for c in flag_categories if c in PRIVACY_FILTER_CATEGORIES}

        # Populated during initialize()
        self.pipeline = None

    def _get_model(self, default_model=None):
        """Default to the openai/privacy-filter model when none is configured."""
        return super()._get_model(default_model or DEFAULT_MODEL)

    def _load_model(self) -> None:
        """Load the token-classification pipeline. Runs in a thread via executor."""
        try:
            from transformers import pipeline

            logger.info(f"Loading privacy filter model: {self.model}")

            self.pipeline = pipeline(
                task="token-classification",
                model=self.model,
                device=self.device,
                aggregation_strategy="simple",
            )

            # Expose the underlying model/tokenizer so the base class
            # verify_connection() and close() work unchanged
            self.model_instance = self.pipeline.model
            self.tokenizer = self.pipeline.tokenizer

            logger.info(f"Privacy filter model loaded: {self.model} (device={self.device})")

        except ImportError:
            error_msg = (
                "transformers package not installed. Install the 'huggingface' "
                "dependency profile: ./install/setup.sh --profile huggingface"
            )
            logger.error(error_msg)
            raise ImportError(error_msg)
        except Exception as e:
            logger.error(f"Error loading privacy filter model: {e}")
            raise

    def _spans_to_result(self, spans: List[Dict[str, Any]]) -> ModerationResult:
        """
        Convert pipeline output spans into a ModerationResult.

        Args:
            spans: Aggregated entity spans from the token-classification
                pipeline, each with 'entity_group' and 'score'

        Returns:
            ModerationResult with pii.<category> scores; flagged when any
            configured category is detected at or above the threshold
        """
        categories: Dict[str, float] = {}
        is_flagged = False

        for span in spans:
            label = span.get('entity_group')
            score = float(span.get('score', 0.0))
            if label not in PRIVACY_FILTER_CATEGORIES:
                continue

            key = f"pii.{label}"
            # Keep the highest-confidence detection per category
            categories[key] = max(categories.get(key, 0.0), score)

            if label in self.flag_categories and score >= self.threshold:
                is_flagged = True

        if is_flagged:
            logger.debug(f"Privacy filter flagged content - categories: {categories}")

        return ModerationResult(
            is_flagged=is_flagged,
            categories=categories,
            provider="privacy_filter",
            model=self.model
        )

    async def moderate_content(self, content: str) -> ModerationResult:
        """
        Detect PII in content using the privacy filter model.

        Args:
            content: The text content to moderate

        Returns:
            ModerationResult object with per-category PII scores
        """
        if not self.initialized:
            if not await self.initialize():
                logger.warning("Privacy filter initialization failed, allowing content through")
                return ModerationResult(
                    is_flagged=False,  # Fail-open, consistent with other moderators
                    provider="privacy_filter",
                    model=self.model,
                    error="Privacy filter initialization failed (allowed)"
                )

        try:
            loop = asyncio.get_event_loop()
            spans = await loop.run_in_executor(self.executor, self.pipeline, content)
            return self._spans_to_result(spans)

        except Exception as e:
            logger.error(f"Error in privacy filter moderation: {str(e)}")
            logger.warning(f"Moderation check failed, allowing content through: {str(e)}")
            return ModerationResult(
                is_flagged=False,  # Fail-open on errors
                provider="privacy_filter",
                model=self.model,
                error=f"Moderation check failed (allowed): {str(e)}"
            )

    async def moderate_batch(self, contents: List[str]) -> List[ModerationResult]:
        """
        Moderate multiple content items in a single pipeline call.

        The transformers pipeline natively supports list inputs, so the
        batch is processed in one executor round trip.

        Args:
            contents: List of text content to moderate

        Returns:
            List of ModerationResult objects
        """
        if not contents:
            return []

        if not self.initialized:
            if not await self.initialize():
                return [
                    ModerationResult(
                        is_flagged=False,
                        provider="privacy_filter",
                        model=self.model,
                        error="Privacy filter initialization failed (allowed)"
                    )
                    for _ in contents
                ]

        try:
            loop = asyncio.get_event_loop()
            batch_spans = await loop.run_in_executor(self.executor, self.pipeline, contents)
            # A single-item list returns one span list rather than a list of lists
            if len(contents) == 1 and (not batch_spans or isinstance(batch_spans[0], dict)):
                batch_spans = [batch_spans]
            return [self._spans_to_result(spans) for spans in batch_spans]

        except Exception as e:
            logger.error(f"Error in privacy filter batch moderation: {str(e)}")
            return [
                ModerationResult(
                    is_flagged=False,
                    provider="privacy_filter",
                    model=self.model,
                    error=f"Moderation check failed (allowed): {str(e)}"
                )
                for _ in contents
            ]
