"""
OpenAI decision service implementation.

Calls OpenAI's Decisions API (`POST /v1/decisions`, model `gpt-6-luna`) to answer
typed questions without generating text. Converts ORBIT's System One wire shape
(questions: choice/noul/score with `criteria`; answers keyed by name) to and from
OpenAI's shape (questions: predicate/choice/score with `choices`/`levels`; answers
as an array with `name`).
"""

import asyncio
import json
from typing import Any, Optional

import aiohttp

from ...connection import ConnectionManager, RetryHandler
from ...services import DecisionService

DECISIONS_PATH = "/v1/decisions"


class DecisionRetryableError(Exception):
    """A transient HTTP failure (429/5xx) that may succeed on retry."""

    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body}")
        self.status = status
        self.body = body


def _to_openai_questions(questions: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert ORBIT question definitions into OpenAI's Decisions API question array."""
    converted = []
    for name, spec in questions.items():
        qtype = spec.get("type")
        instructions = spec.get("instructions")
        if qtype == "noul":
            criteria = spec.get("criteria")
            if criteria:
                # Predicate questions have no separate criteria field, so fold it into the
                # instructions to preserve its meaning (TypeSafe would otherwise see the same text).
                instructions = f"{instructions}\n\nCriteria: {criteria}"
        question: dict[str, Any] = {"name": name, "instructions": instructions}
        if qtype == "noul":
            question["type"] = "predicate"
        elif qtype == "choice":
            question["type"] = "choice"
            question["choices"] = [
                {"value": value, "description": description}
                for value, description in spec.get("criteria", {}).items()
            ]
        elif qtype == "score":
            question["type"] = "score"
            question["levels"] = [
                {"label": label, "description": label} for label in spec.get("criteria", [])
            ]
        else:
            raise ValueError(f"Question '{name}' has unsupported type {qtype!r}")
        converted.append(question)
    return converted


def _from_openai_answers(answers: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert OpenAI's answers array into ORBIT's System One answer shape, keyed by name."""
    converted = {}
    for answer in answers:
        name = answer.get("name")
        atype = answer.get("type")
        if atype == "predicate":
            converted[name] = {"type": "noul", "noul": answer.get("probability")}
        elif atype == "choice":
            converted[name] = {
                "type": "choice",
                "choice": answer.get("choice"),
                "probabilities": {
                    item["value"]: item["probability"] for item in answer.get("probabilities", [])
                },
                "confidence": answer.get("confidence"),
            }
        elif atype == "score":
            probabilities = answer.get("probabilities", [])
            # Each probability entry carries its own level `value` index; don't assume the
            # response array is ordered the same as the requested levels.
            converted[name] = {
                "type": "score",
                "score": answer.get("score"),
                "legend": {str(item["value"]): item["label"] for item in probabilities},
                "probabilities": {str(item["value"]): item["probability"] for item in probabilities},
                "confidence": answer.get("confidence"),
            }
        elif atype == "refusal":
            raise ValueError(f"OpenAI decision refused to answer question '{name}'")
        else:
            raise ValueError(f"OpenAI decision returned unsupported answer type {atype!r} for '{name}'")
    return converted


class OpenAIDecisionService(DecisionService):
    """Answer typed decision questions with OpenAI's hosted Decisions API."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config, "openai")
        self.api_key = self._resolve_api_key("OPENAI_API_KEY")
        self.base_url = self._get_base_url("https://api.openai.com").rstrip("/")
        self.model = self._get_model("gpt-6-luna")
        timeout = self._get_timeout_config()
        retry = self._get_retry_config()
        self.connection_manager: Optional[ConnectionManager] = None
        self.timeout_ms = int(timeout["total"])
        # Only transport failures and 429/5xx are retried; invalid requests fail once with provider detail.
        self.retry_handler = RetryHandler(
            max_retries=retry["max_retries"],
            initial_wait_ms=retry["initial_wait_ms"],
            max_wait_ms=retry["max_wait_ms"],
            exponential_base=retry["exponential_base"],
            enabled=retry["enabled"],
            retry_on=(aiohttp.ClientConnectionError, asyncio.TimeoutError, DecisionRetryableError),
        )

    async def initialize(self) -> bool:
        if not self.api_key:
            raise ValueError("OpenAI API key not configured (set OPENAI_API_KEY)")
        self.connection_manager = ConnectionManager(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout_ms=self.timeout_ms,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        self.initialized = True
        return True

    async def verify_connection(self) -> bool:
        try:
            session = await self.connection_manager.get_session()
            async with session.get("/v1/models") as response:
                return response.status == 200
        except Exception as e:  # noqa: BLE001 - connectivity probe is best-effort
            self.logger.warning(f"OpenAI decision service connection check failed: {e}")
            return False

    async def close(self) -> None:
        if self.connection_manager is not None:
            await self.connection_manager.close()
        self.initialized = False

    async def decide(
        self,
        state: dict[str, Any],
        questions: dict[str, dict[str, Any]],
        model: Optional[str] = None,
        **kwargs,
    ) -> dict[str, Any]:
        # The Decisions API takes `input` as text (or user message parts), not an
        # arbitrary object, so the state dict is serialized to JSON text.
        payload = {
            "model": model or self.model,
            "input": json.dumps(state),
            "questions": _to_openai_questions(questions),
        }

        async def _call() -> dict[str, Any]:
            session = await self.connection_manager.get_session()
            async with session.post(DECISIONS_PATH, json=payload) as response:
                if response.status != 200:
                    body = await response.text()
                    if response.status == 429 or response.status >= 500:
                        raise DecisionRetryableError(response.status, body)
                    raise ValueError(f"OpenAI decision error (HTTP {response.status}): {body}")
                data = await response.json()

            if not isinstance(data, dict) or not isinstance(data.get("answers"), list):
                raise ValueError(f"OpenAI decision response did not include answers: {data!r}")
            return {
                "model": data.get("model") or payload["model"],
                "answers": _from_openai_answers(data["answers"]),
                "usage": data.get("usage") or {},
            }

        return await self.retry_handler.execute_with_retry(_call, "OpenAI decision request failed")
