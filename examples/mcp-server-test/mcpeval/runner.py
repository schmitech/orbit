"""Orchestration: cases x models x prompt variants -> EvalResult.

Mirrors server/tests/intent_eval/runner.py: a dataclass of RAW COUNTS with a
`.summary()` for humans. Counts, not rates, because the ratchet in
test_regression.py compares them directly and rounding a stored rate against a
freshly computed float manufactures regressions that aren't real.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .agent import AgentRun, build_agent, run_case
from .evaluators import CheckContext, CheckOutcome, run_checks
from .ground_truth import resolve
from .models import ModelSpec
from .sandbox import TicketSandbox
from .schema import Case, Suite, resolve_templates

VARIANTS = ("base", "playbook")


@dataclass
class CaseOutcome:
    case_id: str
    suite: str
    passed: bool
    outcomes: list[CheckOutcome]
    run: AgentRun
    ground_truth: dict[str, Any]
    judge_score: float | None = None
    judge_comment: str = ""


@dataclass
class EvalResult:
    suite: str
    model_key: str
    variant: str
    cases: list[CaseOutcome] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def cases_passed(self) -> int:
        return sum(1 for case in self.cases if case.passed)

    @property
    def checks_total(self) -> int:
        return sum(len(case.outcomes) for case in self.cases)

    @property
    def checks_passed(self) -> int:
        return sum(1 for case in self.cases for outcome in case.outcomes if outcome.passed)

    @property
    def agent_errors(self) -> int:
        return sum(1 for case in self.cases if case.run.error)

    @property
    def judge_scores(self) -> list[float]:
        return [case.judge_score for case in self.cases if case.judge_score is not None]

    @property
    def failures(self) -> list[dict[str, Any]]:
        rows = []
        for case in self.cases:
            for outcome in case.outcomes:
                if not outcome.passed:
                    rows.append(
                        {
                            "case_id": case.case_id,
                            "check": outcome.type,
                            "score": outcome.score,
                            "hard": outcome.hard,
                            "comment": outcome.comment,
                            "tools_called": case.run.tool_names,
                            "answer_excerpt": case.run.answer[:300],
                        }
                    )
        return rows

    def key(self) -> str:
        return f"{self.suite}::{self.model_key}::{self.variant}"

    def summary(self) -> dict[str, Any]:
        judged = self.judge_scores
        return {
            "key": self.key(),
            "total": self.total,
            "cases_passed": self.cases_passed,
            "checks_total": self.checks_total,
            "checks_passed": self.checks_passed,
            "agent_errors": self.agent_errors,
            "case_pass_rate": round(self.cases_passed / self.total, 3) if self.total else 0.0,
            "check_pass_rate": round(self.checks_passed / self.checks_total, 3) if self.checks_total else 0.0,
            "judge_mean": round(sum(judged) / len(judged), 3) if judged else None,
            "judged_cases": len(judged),
        }


def apply_setup(case: Case, sandbox: TicketSandbox | None) -> dict[str, Any]:
    """Run a case's `setup` steps and return the bindings they produce.

    Only `create_ticket` exists: a mutating case gets a disposable ticket it is
    allowed to change or destroy, so the agent can never touch seeded data.
    """
    bindings: dict[str, Any] = {}
    for step in case.setup:
        if "create_ticket" not in step:
            raise ValueError(f"case {case.id}: unknown setup step {sorted(step)}")
        if sandbox is None:
            raise RuntimeError(f"case {case.id} needs a ticket sandbox but none was provided")
        spec = dict(step["create_ticket"])
        bindings[step["as"]] = sandbox.create_disposable(
            spec.pop("customerId"), spec.pop("subject"), **spec
        )
    return bindings


async def run_one_case(
    case: Case,
    agent,
    raw_client,
    *,
    judge=None,
    sandbox: TicketSandbox | None = None,
) -> CaseOutcome:
    ground_truth = apply_setup(case, sandbox)
    ground_truth.update(resolve(case, raw_client))
    # The query may reference setup or ground-truth bindings, e.g. the id of
    # the disposable ticket the sandbox just created.
    query = resolve_templates(case.query, ground_truth)
    run = await run_case(agent, query)
    outcomes = run_checks(CheckContext(case=case, run=run, ground_truth=ground_truth))
    passed = all(outcome.passed for outcome in outcomes if outcome.hard)

    judge_score, judge_comment = None, ""
    if judge is not None and not run.error:
        wants_judge = any(check.type == "groundedness" for check in case.checks)
        if wants_judge:
            judge_score, judge_comment = judge(case, run, ground_truth)

    return CaseOutcome(
        case_id=case.id,
        suite=case.suite,
        passed=passed,
        outcomes=outcomes,
        run=run,
        ground_truth=ground_truth,
        judge_score=judge_score,
        judge_comment=judge_comment,
    )


async def run_eval(
    suite: Suite,
    spec: ModelSpec,
    variant: str,
    *,
    tools,
    raw_client,
    judge=None,
    only: set[str] | None = None,
    sandbox: TicketSandbox | None = None,
    include_mutating: bool = True,
) -> EvalResult:
    """Run one suite against one model under one prompt variant.

    `variant` selects whether the suite's playbook is injected alongside the
    base system prompt, which is what makes the base/playbook delta readable.
    """
    playbook = suite.playbook if variant == "playbook" else None
    agent = build_agent(spec, tools, playbook)
    result = EvalResult(suite=suite.name, model_key=spec.key, variant=variant)

    # Read-only cases first; mutating ones last so they cannot perturb the
    # ground truth of anything that follows.
    cases = [case for case in suite.cases if not only or case.id in only]
    if not include_mutating:
        cases = [case for case in cases if not case.mutating]
    for case in sorted(cases, key=lambda c: c.mutating):
        result.cases.append(await run_one_case(case, agent, raw_client, judge=judge, sandbox=sandbox))
    return result
