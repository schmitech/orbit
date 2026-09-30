"""
Decision service interface.

Defines the common interface for "System One" decision models (Jev-style
models such as nimble, tev1, or TypeSafe's jev-latest). These models do not
generate text: they receive a `state` object plus typed `questions`
(choice / noul / score) and return typed answers with probabilities.
"""

from abc import abstractmethod
from typing import Any, Optional

from ..base import ProviderAIService, ServiceType


class DecisionService(ProviderAIService):
    """
    Base class for all decision model services.

    Implementations must return a dict from decide() with:
        model: str      — the model that produced the answers (as resolved by the provider)
        answers: dict   — answer objects keyed by question name, in System One wire shape
        usage: dict     — {"input_tokens": int, "output_tokens": int}
    """

    service_type = ServiceType.DECISION
    # Provider configs live under `decision_models.<provider>` in decision.yaml.
    config_section_key = "decision_models"

    def __init__(self, config: dict[str, Any], provider_name: str):
        super().__init__(config, ServiceType.DECISION, provider_name)

    @abstractmethod
    async def decide(
        self,
        state: dict[str, Any],
        questions: dict[str, dict[str, Any]],
        model: Optional[str] = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Answer typed questions about a state.

        Args:
            state: Context the decision is made about, e.g. {"ticket": "..."}
            questions: Question definitions keyed by name, e.g.
                {"team": {"type": "choice", "instructions": "...", "criteria": {...}}}
            model: Optional per-call model override (defaults to the configured model)

        Returns:
            {"model": str, "answers": dict, "usage": dict}
        """
        pass
