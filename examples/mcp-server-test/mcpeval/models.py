"""The models under test. A tuple, not a framework.

Defaults track the models config/inference.yaml actually configures, so the
harness measures the behaviour ORBIT would really get.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    key: str  # stable identifier used in baseline.json keys
    provider: str
    model: str  # for Azure this is the deployment name, which is what Azure routes on
    env_key: str
    # Azure AI Foundry binds a deployment to its own endpoint, so unlike the
    # other providers it needs a second variable before it can run at all.
    endpoint_key: str | None = None
    # Who actually trained the model, which is what the judge's independence
    # depends on. Azure serves OpenAI models, so azure and openai share a
    # family even though they are separate providers here. Defaults to the
    # provider when they are the same thing.
    _family: str = ""

    @property
    def family(self) -> str:
        return self._family or self.provider

    def missing_env(self) -> list[str]:
        """Which required variables are absent. Drives the skip message, so a
        half-configured provider says which half."""
        required = [self.env_key] + ([self.endpoint_key] if self.endpoint_key else [])
        return [name for name in required if not os.getenv(name)]

    def available(self) -> bool:
        return not self.missing_env()

    def build(self):
        """Construct the chat model. Imported lazily so an absent provider
        package never breaks collection of the LLM-free tests."""
        # gpt-5.x are reasoning models and reject an explicit temperature.
        no_temperature = self.model.startswith("gpt-5")
        if self.provider == "openai":
            from langchain_openai import ChatOpenAI

            kwargs = {} if no_temperature else {"temperature": 0}
            return ChatOpenAI(model=self.model, **kwargs)
        if self.provider == "azure":
            from langchain_openai import ChatOpenAI

            # Deliberately ChatOpenAI, not AzureChatOpenAI. ORBIT drives Azure
            # AI Foundry through the versionless /openai/v1 endpoint with the
            # plain OpenAI SDK (server/ai_services/providers/azure_base.py),
            # rather than the older dated api_version + /deployments URL shape
            # AzureChatOpenAI builds. The harness mirrors what ORBIT does.
            kwargs = {} if no_temperature else {"temperature": 0}
            return ChatOpenAI(
                model=self.model,
                base_url=os.environ[self.endpoint_key],
                api_key=os.environ[self.env_key],
                **kwargs,
            )
        if self.provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(model=self.model, temperature=0, max_tokens=4096)
        raise ValueError(f"unknown provider {self.provider!r}")


def registry() -> tuple[ModelSpec, ...]:
    openai_model = os.getenv("EVAL_OPENAI_MODEL", "gpt-5.4-mini")
    anthropic_model = os.getenv("EVAL_ANTHROPIC_MODEL", "claude-sonnet-4-6")
    # An Azure deployment name, not a model id — Azure routes on the deployment.
    azure_deployment = os.getenv("EVAL_AZURE_DEPLOYMENT", "gpt-5-mini")
    return (
        ModelSpec(f"openai:{openai_model}", "openai", openai_model, "OPENAI_API_KEY"),
        ModelSpec(f"anthropic:{anthropic_model}", "anthropic", anthropic_model, "ANTHROPIC_API_KEY"),
        ModelSpec(
            f"azure:{azure_deployment}",
            "azure",
            azure_deployment,
            "AZURE_ACCESS_KEY",
            endpoint_key="AZURE_INFERENCE_ENDPOINT",
            _family="openai",
        ),
    )


def available() -> list[ModelSpec]:
    """Models whose provider key is present. Settings.from_env() must have run
    first so a repo-root .env has been loaded into the environment."""
    return [spec for spec in registry() if spec.available()]


def judge_spec(model_under_test: ModelSpec | None = None) -> ModelSpec | None:
    """Pick a judge, preferring a different model family than the one under test.

    A model grading its own output is a known bias; when only one family has a
    key we allow it but the report flags the run as self-judged.

    Family, not provider: Azure serves OpenAI models, so an Azure deployment
    grading an OpenAI run is very nearly a model grading itself.
    """
    candidates = [spec for spec in registry() if spec.available()]
    if not candidates:
        return None
    if model_under_test is not None:
        other = [spec for spec in candidates if spec.family != model_under_test.family]
        if other:
            return other[0]
    return candidates[0]
