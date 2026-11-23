"""
Laya decision service implementation.

Runs the local, in-process Laya "System One" decision model
(https://github.com/nandhakishorm/laya) via the `laya` package. Unlike the ollama/openai/typesafe
providers, Laya is not called over HTTP: `laya.load()` loads a checkpoint (from the Hugging Face
Hub, a checkpoint alias, or a local path) into memory once, and the loaded agent answers questions
directly in this process. Laya's own question shape already matches ORBIT's System One wire format
(choice/score/noul, with `instructions`/`criteria`), so questions are passed through unconverted.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

import laya

from ...services import DecisionService


class LayaDecisionService(DecisionService):
    """Answer typed decision questions with a local, in-process Laya model."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config, "laya")
        provider_config = self._extract_provider_config()
        self.model = self._get_model("english")
        self.device = provider_config.get("device")
        self.agent = None
        # laya.load() and agent.predict() are synchronous and CPU/GPU-bound; run them off the event loop.
        self._executor = ThreadPoolExecutor(max_workers=1)
        # Guards the checkpoint load: concurrent callers join the same in-flight future instead
        # of starting a second load, and `shield` below means one caller's cancellation doesn't
        # kill the worker thread - the load keeps running for whoever awaits it next.
        self._load_lock = asyncio.Lock()
        self._load_future: Optional[asyncio.Future] = None

    async def initialize(self) -> bool:
        # Cheap on purpose: adapters that set `decision_provider` are preloaded at startup
        # (see AdapterLoader), and loading Laya's checkpoint there would block startup on a
        # model download/GPU allocation for an adapter that may never be called. The agent
        # loads lazily instead, on the first decide()/verify_connection() call.
        self.initialized = True
        return True

    async def _ensure_agent(self) -> Any:
        if self.agent is not None:
            return self.agent
        async with self._load_lock:
            if self.agent is not None:
                return self.agent
            if self._load_future is None:
                loop = asyncio.get_event_loop()
                self._load_future = loop.run_in_executor(
                    self._executor, lambda: laya.load(self.model, device=self.device)
                )
            load_future = self._load_future
        try:
            agent = await asyncio.shield(load_future)
        except asyncio.CancelledError:
            raise
        except Exception:
            async with self._load_lock:
                if self._load_future is load_future:
                    self._load_future = None
            raise
        self.agent = agent
        return agent

    async def verify_connection(self) -> bool:
        try:
            return await self._ensure_agent() is not None
        except Exception as e:  # noqa: BLE001 - connectivity probe is best-effort
            self.logger.warning(f"Laya decision service connection check failed: {e}")
            return False

    async def close(self) -> None:
        self.agent = None
        self._load_future = None
        self._executor.shutdown(wait=False)
        self.initialized = False

    async def decide(
        self,
        state: dict[str, Any],
        questions: dict[str, dict[str, Any]],
        model: Optional[str] = None,
        **kwargs,
    ) -> dict[str, Any]:
        if model and model != self.model:
            # The agent is loaded once with a fixed checkpoint, unlike the HTTP providers that
            # can swap models per request - so a per-call override here would need a different
            # cached service, keyed by model, which is how the decision cache already works.
            self.logger.warning(
                f"Laya decision service is loaded with model '{self.model}'; "
                f"ignoring per-call override to '{model}'."
            )
        agent = await self._ensure_agent()

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor, lambda: agent.predict(state, questions)
        )
        if not isinstance(result, dict) or not isinstance(result.get("answers"), dict):
            raise ValueError(f"Laya decision response did not include answers: {result!r}")
        return {
            "model": self.model,
            "answers": result["answers"],
            "usage": result.get("usage") or {},
        }
