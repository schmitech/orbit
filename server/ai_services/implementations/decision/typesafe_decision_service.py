"""
TypeSafe decision service implementation.

Uses the official `typesafe-sdk` (AsyncTypeSafeClient) to call TypeSafe's hosted
System One API (https://api.typesafe.ai/v1/systemone). Retries are handled by the SDK.
"""

from typing import Any, Optional

from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, Score, TypeSafeError

from ...services import DecisionService

_QUESTION_TYPES = {"choice": Choice, "noul": Noul, "score": Score}


def to_sdk_questions(questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Convert YAML/JSON question dicts into SDK Choice/Noul/Score objects."""
    converted = {}
    for name, spec in questions.items():
        cls = _QUESTION_TYPES.get(spec.get("type"))
        if cls is None:
            raise ValueError(f"Question '{name}' has unsupported type {spec.get('type')!r}")
        kwargs = {"instructions": spec.get("instructions")}
        if spec.get("criteria") is not None:
            kwargs["criteria"] = spec["criteria"]
        converted[name] = cls(**kwargs)
    return converted


class TypeSafeDecisionService(DecisionService):
    """Answer typed decision questions with TypeSafe's hosted Jev models."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config, "typesafe")
        self.api_key = self._resolve_api_key("TYPESAFE_API_KEY")
        self.base_url = self._get_base_url("https://api.typesafe.ai")
        self.model = self._get_model("jev-latest")
        # decision.yaml stores milliseconds; the SDK takes seconds.
        self.timeout_seconds = self._get_timeout_config()["total"] / 1000
        self.client: Optional[AsyncTypeSafeClient] = None

    def _get_client(self) -> AsyncTypeSafeClient:
        if self.client is None:
            self.client = AsyncTypeSafeClient(
                api_key=self.api_key,
                base_url=self.base_url,
                model=self.model,
                timeout=self.timeout_seconds,
            )
        return self.client

    async def initialize(self) -> bool:
        if not self.api_key:
            raise ValueError("TypeSafe API key not configured (set TYPESAFE_API_KEY)")
        self._get_client()
        self.initialized = True
        return True

    async def verify_connection(self) -> bool:
        try:
            await self._get_client().models.list()
            return True
        except Exception as e:  # noqa: BLE001 - connectivity probe is best-effort
            self.logger.warning(f"TypeSafe connection check failed: {e}")
            return False

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()
            self.client = None
        self.initialized = False

    async def decide(
        self,
        state: dict[str, Any],
        questions: dict[str, dict[str, Any]],
        model: Optional[str] = None,
        **kwargs,
    ) -> dict[str, Any]:
        try:
            response = await self._get_client().system_one(
                state=state,
                questions=to_sdk_questions(questions),
                model=model or self.model,
            )
        except TypeSafeError as e:
            raise ValueError(f"TypeSafe decision error: {e}") from e

        data = response.model_dump(mode="json")
        return {
            "model": data.get("model"),
            "answers": data.get("answers") or {},
            "usage": data.get("usage") or {},
        }
