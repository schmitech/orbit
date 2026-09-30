"""
Ollama decision service implementation.

Calls Ollama's System One endpoint (`POST /v1/systemone`, Ollama 0.35+) to run
local Jev-style decision models such as nimble, tev1 and tev1:0.8b.
"""

import asyncio
from typing import Any, Optional

import aiohttp

from ...connection import ConnectionManager, RetryHandler
from ...services import DecisionService

SYSTEMONE_PATH = "/v1/systemone"


class DecisionRetryableError(Exception):
    """A transient HTTP failure (429/5xx) that may succeed on retry."""

    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body}")
        self.status = status
        self.body = body


class OllamaDecisionService(DecisionService):
    """Answer typed decision questions with a local Ollama decision model."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config, "ollama")
        self.base_url = self._get_base_url("http://localhost:11434").rstrip("/")
        self.model = self._get_model("nimble")
        timeout = self._get_timeout_config()
        retry = self._get_retry_config()
        self.connection_manager = ConnectionManager(base_url=self.base_url, timeout_ms=int(timeout["total"]))
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
        self.initialized = True
        return True

    async def verify_connection(self) -> bool:
        try:
            session = await self.connection_manager.get_session()
            async with session.get("/api/tags") as response:
                return response.status == 200
        except Exception as e:  # noqa: BLE001 - connectivity probe is best-effort
            self.logger.warning(f"Ollama decision service connection check failed: {e}")
            return False

    async def close(self) -> None:
        await self.connection_manager.close()
        self.initialized = False

    async def decide(
        self,
        state: dict[str, Any],
        questions: dict[str, dict[str, Any]],
        model: Optional[str] = None,
        **kwargs,
    ) -> dict[str, Any]:
        payload = {"model": model or self.model, "state": state, "questions": questions}

        async def _call() -> dict[str, Any]:
            session = await self.connection_manager.get_session()
            async with session.post(SYSTEMONE_PATH, json=payload) as response:
                if response.status != 200:
                    body = await response.text()
                    if response.status == 429 or response.status >= 500:
                        raise DecisionRetryableError(response.status, body)
                    raise ValueError(f"Ollama decision error (HTTP {response.status}): {body}")
                data = await response.json()

            if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
                raise ValueError(f"Ollama decision response did not include answers: {data!r}")
            return {
                "model": data.get("model") or payload["model"],
                "answers": data["answers"],
                "usage": data.get("usage") or {},
            }

        return await self.retry_handler.execute_with_retry(_call, "Ollama decision request failed")
