"""Shieldstral moderation through OpenAI-compatible local servers."""

import logging
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from ...services import ModerationResult, ModerationService


logger = logging.getLogger(__name__)


DEFAULT_SHIELDSTRAL_POLICY = """Disallow content that enables, encourages, or excuses:
- violent crimes, non-violent crimes, sex-related crimes, child sexual exploitation, or weapons of mass destruction;
- defamation, privacy violations, intellectual-property violations, or election misinformation;
- specialized medical, legal, or financial advice presented without appropriate professional safeguards;
- hate, explicit sexual content, suicide or self-harm, or attempts to abuse code interpreters and other systems.
"""


class ShieldstralModerationService(ModerationService):
    """Moderate content with Shieldstral served by vLLM or llama.cpp."""

    _BACKEND_DEFAULT_URLS = {
        "vllm": "http://localhost:8000/v1",
        "llama_cpp": "http://localhost:8080/v1",
    }

    def __init__(self, config: dict[str, Any]):
        super().__init__(config, "shieldstral")

        provider_config = self._extract_provider_config()
        self.backend = provider_config.get("backend", "vllm")
        if self.backend not in self._BACKEND_DEFAULT_URLS:
            raise ValueError("Shieldstral moderation backend must be 'vllm' or 'llama_cpp'")

        self.base_url = provider_config.get("base_url", self._BACKEND_DEFAULT_URLS[self.backend])
        self.model = provider_config.get("model", "mistralai/Shieldstral-1.0-3B")
        self.max_tokens = provider_config.get("max_tokens", 8)
        self.temperature = provider_config.get("temperature", 0.0)
        self.request_timeout = provider_config.get("request_timeout", 15)
        self.policy = self._load_policy(provider_config)
        self.client = AsyncOpenAI(
            api_key=self._resolve_api_key("SHIELDSTRAL_API_KEY") or "not-needed",
            base_url=self.base_url,
            timeout=self.request_timeout,
        )

    def _load_policy(self, provider_config: dict[str, Any]) -> str:
        """Return inline policy, then a policy file, then the bundled default."""
        inline_policy = provider_config.get("policy")
        if isinstance(inline_policy, str) and inline_policy.strip():
            return inline_policy.strip()

        policy_path = provider_config.get("policy_path")
        if policy_path:
            path = Path(policy_path)
            if not path.is_absolute():
                path = Path(__file__).resolve().parents[4] / path
            try:
                return path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                logger.warning("Could not load Shieldstral policy file %s: %s", path, exc)

        return DEFAULT_SHIELDSTRAL_POLICY

    def _build_messages(self, content: str) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "You are a content safety classifier. Determine whether the user content "
                    "violates the following policy. Answer exactly 'Yes' if it violates the "
                    "policy or exactly 'No' if it does not.\n\n"
                    f"<policy>\n{self.policy}\n</policy>"
                ),
            },
            {"role": "user", "content": f"<content>\n{content}\n</content>"},
        ]

    @staticmethod
    def _parse_response(response_text: str) -> tuple[bool, dict[str, float]]:
        """Parse Shieldstral's binary answer, failing open on ambiguity."""
        normalized = (response_text or "").strip().lower().rstrip(".")
        if normalized == "yes":
            return True, {"policy_violation": 1.0}
        if normalized == "no":
            return False, {}

        logger.warning("Ambiguous Shieldstral response %r; allowing content", response_text)
        return False, {"ambiguous_response": 0.5}

    async def initialize(self) -> bool:
        self.initialized = True
        return True

    async def verify_connection(self) -> bool:
        try:
            await self.client.models.list()
            return True
        except Exception as exc:
            logger.warning("Shieldstral %s connection check failed: %s", self.backend, exc)
            return False

    async def close(self) -> None:
        await self.client.close()
        self.initialized = False

    async def moderate_content(self, content: str) -> ModerationResult:
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize Shieldstral moderation service")

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=self._build_messages(content),
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            response_text = response.choices[0].message.content or ""
            is_flagged, categories = self._parse_response(response_text)
            return ModerationResult(
                is_flagged=is_flagged,
                categories=categories,
                provider="shieldstral",
                model=self.model,
            )
        except Exception as exc:
            logger.error("Shieldstral moderation failed; allowing content: %s", exc)
            return ModerationResult(
                is_flagged=False,
                categories={"api_error": 0.5},
                provider="shieldstral",
                model=self.model,
                error=f"Moderation check failed (allowed): {exc}",
            )
