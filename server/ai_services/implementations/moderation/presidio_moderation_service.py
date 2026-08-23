"""
Presidio moderation service for PII detection.

This implementation calls the Presidio analyzer's REST API rather than loading
Presidio's Python packages in-process, so it adds no dependencies (spaCy and the
~600MB NER model stay inside the analyzer container). This mirrors how other
gateways integrate Presidio.

Presidio moved from microsoft/presidio to the Data Privacy Stack organisation
(https://presidio.dataprivacystack.org/). The REST contract is unchanged; only
the container registry moved:
    docker run -d -p 5002:3000 ghcr.io/data-privacy-stack/presidio-analyzer:latest

Detected entities are reported as ModerationResult categories using the
"pii.<entity>" naming scheme (e.g. "pii.email_address"), matching the
privacy_filter provider so audit logs stay consistent between the two PII
moderators.

Unlike privacy_filter, this service does NOT fail open on its own: because the
analyzer is a network dependency, transport and protocol errors are raised so
ModeratorService applies the operator's configured retry and `allow_on_timeout`
policy from config/guardrails.yaml (which blocks by default).
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

from ...connection import ConnectionManager
from ...services import ModerationService, ModerationResult

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://localhost:5002"
DEFAULT_LANGUAGE = "en"
DEFAULT_SCORE_THRESHOLD = 0.5
DEFAULT_REQUEST_TIMEOUT = 10
DEFAULT_BATCH_SIZE = 8

# Presidio supports ~100 entity types across many locales. Enabling all of them
# would flag ordinary prose constantly (DATE_TIME, LOCATION and NRP in
# particular), so the default is a conservative set of high-confidence
# identifiers. Operators opt into more via `entities` in config/moderators.yaml;
# the analyzer's own list is available at GET /supportedentities.
DEFAULT_ENTITIES = [
    "CREDIT_CARD",
    "CRYPTO",
    "EMAIL_ADDRESS",
    "IBAN_CODE",
    "IP_ADDRESS",
    "MEDICAL_LICENSE",
    "PHONE_NUMBER",
    "US_BANK_NUMBER",
    "US_SSN",
]


class PresidioModerationService(ModerationService):
    """
    PII moderation service backed by a Presidio analyzer HTTP service.

    Configuration (config/moderators.yaml under moderations.presidio):
        base_url: analyzer base URL (default: http://localhost:5002); the
            PRESIDIO_ANALYZER_API_BASE environment variable takes precedence
        language: analyzer language code (default: en)
        score_threshold: minimum entity score to count a detection (default: 0.5)
        entities: entity types that flag content (default: DEFAULT_ENTITIES)
        request_timeout: per-request timeout in seconds (default: 10)
        batch_size: max concurrent analyze calls in moderate_batch (default: 8,
            minimum 1)
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Presidio moderation service.

        Args:
            config: Configuration dictionary
        """
        super().__init__(config, "presidio")

        provider_config = self._extract_provider_config()

        # Environment wins so containerized deploys can point at the analyzer
        # without editing YAML (same variable name other gateways use).
        base_url = os.environ.get('PRESIDIO_ANALYZER_API_BASE') or self._get_base_url(DEFAULT_BASE_URL)
        # Accept a base URL with or without a trailing slash, and with a path
        # prefix (e.g. behind a reverse proxy) - build absolute request URLs so
        # aiohttp's base_url path restriction does not apply.
        self.base_url = base_url.rstrip('/')
        self.language = provider_config.get('language', DEFAULT_LANGUAGE)
        self.score_threshold = float(provider_config.get('score_threshold', DEFAULT_SCORE_THRESHOLD))
        self.request_timeout = provider_config.get('request_timeout', DEFAULT_REQUEST_TIMEOUT)
        # Clamped to >= 1: a configured 0 would make moderate_batch's semaphore
        # block forever, and a negative value would raise on every batch call.
        configured_batch_size = int(provider_config.get('batch_size', DEFAULT_BATCH_SIZE))
        if configured_batch_size < 1:
            logger.warning(
                f"Invalid presidio batch_size {configured_batch_size}; using 1 "
                f"(requests will be issued serially)"
            )
        self.batch_size = max(1, configured_batch_size)

        entities = provider_config.get('entities') or DEFAULT_ENTITIES
        self.entities = [str(entity).upper() for entity in entities]

        self.model = "presidio-analyzer"

        self.connection_manager = ConnectionManager(
            base_url=self._origin(self.base_url),
            timeout_ms=int(self.request_timeout * 1000),
        )

    @staticmethod
    def _origin(base_url: str) -> str:
        """
        Return the scheme://host:port of a URL.

        aiohttp rejects a ClientSession base_url that carries a path, so the
        session is anchored at the origin and requests use absolute URLs.
        """
        from urllib.parse import urlsplit

        parts = urlsplit(base_url)
        return f"{parts.scheme}://{parts.netloc}"

    def _url(self, path: str) -> str:
        """Build an absolute analyzer URL for the given path."""
        return f"{self.base_url}/{path.lstrip('/')}"

    async def initialize(self) -> bool:
        """
        Mark the service ready and log the analyzer's entity coverage.

        A warning is emitted for configured entities the running analyzer does
        not support (coverage depends on language and loaded recognizers). An
        unreachable analyzer is not fatal here - moderate_content raises so the
        configured safety policy decides what to do.
        """
        supported = await self._fetch_supported_entities()
        if supported is not None:
            unsupported = [entity for entity in self.entities if entity not in supported]
            if unsupported:
                logger.warning(
                    f"Presidio analyzer at {self.base_url} does not support configured "
                    f"entities {unsupported} for language '{self.language}'. "
                    f"They will never be detected."
                )

        self.initialized = True
        return True

    async def _fetch_supported_entities(self) -> Optional[List[str]]:
        """Return the analyzer's supported entity types, or None if unavailable."""
        try:
            session = await self.connection_manager.get_session()
            async with session.get(
                self._url('/supportedentities'),
                params={'language': self.language}
            ) as response:
                if response.status != 200:
                    logger.warning(
                        f"Presidio /supportedentities returned HTTP {response.status}; "
                        f"skipping entity validation"
                    )
                    return None
                supported = await response.json()
        except Exception as exc:
            logger.warning(
                f"Could not reach Presidio analyzer at {self.base_url} during "
                f"initialization ({exc}); skipping entity validation"
            )
            return None

        if not isinstance(supported, list):
            logger.warning(
                f"Unexpected Presidio /supportedentities response ({supported!r}); "
                f"skipping entity validation"
            )
            return None
        return supported

    async def verify_connection(self) -> bool:
        """Check the analyzer's health endpoint."""
        try:
            session = await self.connection_manager.get_session()
            async with session.get(self._url('/health')) as response:
                return response.status == 200
        except Exception as exc:
            logger.warning(f"Presidio analyzer connection check failed: {exc}")
            return False

    async def close(self) -> None:
        """Close the HTTP session and release resources."""
        await self.connection_manager.close()
        self.initialized = False

    def _results_to_result(self, results: List[Dict[str, Any]]) -> ModerationResult:
        """
        Convert analyzer results into a ModerationResult.

        Args:
            results: Analyzer response entries, each with 'entity_type' and 'score'

        Returns:
            ModerationResult with pii.<entity> scores; flagged when a configured
            entity is detected at or above the score threshold
        """
        categories: Dict[str, float] = {}
        is_flagged = False

        for entry in results:
            entity_type = entry.get('entity_type')
            if not entity_type:
                continue
            score = float(entry.get('score', 0.0))

            key = f"pii.{entity_type.lower()}"
            # Keep the highest-confidence detection per entity type
            categories[key] = max(categories.get(key, 0.0), score)

            # The analyzer already filters by entities and score_threshold; this
            # repeats the check so an analyzer that ignores those parameters
            # cannot widen what ORBIT blocks.
            if entity_type in self.entities and score >= self.score_threshold:
                is_flagged = True

        if is_flagged:
            logger.debug(f"Presidio flagged content - categories: {categories}")

        return ModerationResult(
            is_flagged=is_flagged,
            categories=categories,
            provider="presidio",
            model=self.model
        )

    async def _analyze(self, content: str) -> List[Dict[str, Any]]:
        """
        Call the analyzer's /analyze endpoint.

        Raises:
            RuntimeError: if the analyzer returns a non-200 status or a payload
                that is not a JSON array. Transport errors propagate as-is.
        """
        payload = {
            "text": content,
            "language": self.language,
            "entities": self.entities,
            "score_threshold": self.score_threshold,
        }

        session = await self.connection_manager.get_session()
        async with session.post(self._url('/analyze'), json=payload) as response:
            if response.status != 200:
                error_text = await response.text()
                raise RuntimeError(
                    f"Presidio analyze failed with HTTP {response.status}: {error_text[:200]}"
                )
            results = await response.json()

        if not isinstance(results, list):
            raise RuntimeError(f"Unexpected Presidio analyze response: {results!r}")

        return results

    async def moderate_content(self, content: str) -> ModerationResult:
        """
        Detect PII in content using the Presidio analyzer.

        Args:
            content: The text content to moderate

        Returns:
            ModerationResult object with per-entity PII scores

        Raises:
            Exception: on any analyzer failure, so ModeratorService can apply
                the configured retry and allow_on_timeout policy
        """
        if not self.initialized:
            await self.initialize()

        results = await self._analyze(content)
        return self._results_to_result(results)

    async def moderate_batch(self, contents: List[str]) -> List[ModerationResult]:
        """
        Moderate multiple content items concurrently.

        The analyzer has no batch endpoint, so requests are issued in parallel
        up to batch_size. Results preserve the input order.

        Args:
            contents: List of text content to moderate

        Returns:
            List of ModerationResult objects
        """
        if not contents:
            return []

        if not self.initialized:
            await self.initialize()

        semaphore = asyncio.Semaphore(self.batch_size)

        async def analyze_one(text: str) -> ModerationResult:
            async with semaphore:
                results = await self._analyze(text)
                return self._results_to_result(results)

        return await asyncio.gather(*(analyze_one(text) for text in contents))
