"""Optional LangSmith integration.

Strictly additive: with LANGSMITH_API_KEY unset, nothing here runs and the
harness is fully offline. With it set, cases are pushed as a dataset and
evaluated through `langsmith.evaluate()` using THE SAME check functions the
offline runner uses — there is no second implementation to drift.

Ground truth is deliberately NOT frozen into the uploaded dataset. It is
recomputed inside the target function on every run, because the sample server's
dates move daily and its ticket state changes as the CRUD cases run.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .agent import build_agent, load_tools, run_case
from .config import Settings
from .evaluators import CheckContext, run_checks
from .ground_truth import resolve
from .models import ModelSpec
from .protocol import RawMcpClient
from .schema import Case, Suite, resolve_templates

# One stable feedback key per family, because LangSmith compares experiments by
# key and a per-case key would make the charts useless.
FAMILIES: dict[str, tuple[str, ...]] = {
    "tool_selection": ("required_tools", "tool_choice", "no_tool_calls"),
    "safety": ("forbidden_tools", "max_tool_calls", "no_id_enumeration"),
    "trajectory": ("tool_order", "tool_sequence", "recovers_after_error"),
    "arguments": ("arg_matches", "arg_bound"),
    "answer_facts": ("answer_contains", "answer_not_contains", "answer_ordering", "tool_error_handled"),
}


def dataset_name(suite: Suite, spec: ModelSpec, variant: str) -> str:
    return f"orbit-mcp/{suite.name}/{spec.key}/{variant}"


def eligible_cases(suite: Suite) -> dict[str, Case]:
    """The cases LangSmith may run, keyed by id.

    Mutating cases are excluded: LangSmith may run examples concurrently, which
    the sandbox's snapshot/restore model cannot make safe.

    Both the uploaded dataset and the target's lookup map come from here, and
    they must agree — an example present in the dataset but absent from the map
    makes the target raise KeyError before any evaluator runs.
    """
    return {case.id: case for case in suite.cases if not case.mutating}


def push_dataset(suite: Suite, name: str) -> str:
    """Create or refresh the dataset. Idempotent by name."""
    from langsmith import Client

    client = Client()
    if client.has_dataset(dataset_name=name):
        dataset = client.read_dataset(dataset_name=name)
    else:
        dataset = client.create_dataset(
            dataset_name=name,
            description=f"ORBIT business MCP agent cases — suite {suite.name}",
        )
    keep = eligible_cases(suite)
    existing = {
        example.metadata.get("case_id"): example.id
        for example in client.list_examples(dataset_id=dataset.id)
    }
    # A dataset written before a case became mutating — or before this filter
    # existed — still holds examples the target can no longer resolve, so drop
    # them rather than let the experiment fail on them.
    stale = [example_id for case_id, example_id in existing.items() if case_id not in keep]
    if stale:
        client.delete_examples(example_ids=stale)
    new_cases = [case for case in keep.values() if case.id not in existing]
    if new_cases:
        client.create_examples(
            dataset_id=dataset.id,
            examples=[
                {
                    "inputs": {"query": case.query, "case_id": case.id},
                    "outputs": {"checks": [{"type": c.type, **c.params} for c in case.checks]},
                    "metadata": {"case_id": case.id, "suite": case.suite, "tags": list(case.tags)},
                }
                for case in new_cases
            ],
        )
    return str(dataset.id)


def make_evaluators(cases_by_id: dict[str, Case]):
    """Family-level evaluators with LangSmith's (inputs, outputs, reference_outputs) signature.

    Each one filters the case's checks for the types it owns and returns their
    mean, or None when the case has no check in that family so LangSmith does
    not record a misleading zero.
    """

    def build(family: str, types: tuple[str, ...]):
        def evaluator(inputs: dict, outputs: dict, reference_outputs: dict | None = None) -> dict:
            relevant = [outcome for outcome in outputs["outcomes"] if outcome["type"] in types]
            if not relevant:
                return {"key": family, "score": None, "comment": "no checks of this family"}
            score = sum(outcome["score"] for outcome in relevant) / len(relevant)
            failed = [f"{o['type']}: {o['comment']}" for o in relevant if o["score"] < 1.0]
            return {"key": family, "score": score, "comment": "; ".join(failed) or "all passed"}

        evaluator.__name__ = family
        return evaluator

    return [build(family, types) for family, types in FAMILIES.items()]


def make_target(spec: ModelSpec, tools, settings: Settings, cases_by_id: dict[str, Case], variant: str, playbook: str | None):
    """The function LangSmith runs per example.

    Identical work to the offline runner: resolve ground truth live, run the
    agent, score the checks.
    """
    from langsmith import traceable

    agent = build_agent(spec, tools, playbook if variant == "playbook" else None)

    @traceable(name="mcp_case")
    def target(inputs: dict) -> dict[str, Any]:
        case = cases_by_id[inputs["case_id"]]
        with RawMcpClient(settings) as client:
            ground_truth = resolve(case, client)
        query = resolve_templates(case.query, ground_truth)
        run = asyncio.run(run_case(agent, query))
        outcomes = run_checks(CheckContext(case=case, run=run, ground_truth=ground_truth))
        return {
            "answer": run.answer,
            "tool_calls": run.tool_names,
            "outcomes": [
                {"type": o.type, "score": o.score, "hard": o.hard, "comment": o.comment} for o in outcomes
            ],
        }

    return target


async def run_experiment(suite: Suite, spec: ModelSpec, variant: str, settings: Settings):
    """Push the dataset and run one LangSmith experiment.

    Mutating cases are excluded from both the dataset and the target — see
    eligible_cases().
    """
    from langsmith import evaluate

    name = dataset_name(suite, spec, variant)
    push_dataset(suite, name)
    cases_by_id = eligible_cases(suite)
    tools = await load_tools(settings)
    return evaluate(
        make_target(spec, tools, settings, cases_by_id, variant, suite.playbook),
        data=name,
        evaluators=make_evaluators(cases_by_id),
        experiment_prefix=f"{suite.name}-{spec.key}-{variant}",
        max_concurrency=1,
    )
