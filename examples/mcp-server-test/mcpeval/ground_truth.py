"""Compute each case's expected values at run time, against the live server.

Nothing is hardcoded. A case declares an ordered program of read-only tool
calls; each step's payload is bound to a name that later steps and the checks
can reference with ${binding.path}.

This is not a stylistic preference. The sample data is only *partly*
deterministic: ids, names, ARR, health scores, seats and stages are stable
under faker.seed(4242), but renewalDate, closeDate, lastExecutiveMeeting and
ticket createdAt come from faker.date.soon()/recent() and therefore move every
day. Ticket state also drifts as the CRUD cases run. Computing expectations
from the same server the agent just queried makes all of that a non-issue.
"""

from __future__ import annotations

from typing import Any

from .protocol import RawMcpClient
from .schema import Case, resolve_templates


def _attainment(rep: dict[str, Any]) -> int:
    """attainmentPct arrives as a formatted string like '76%'."""
    return int(str(rep["attainmentPct"]).rstrip("%"))


def reps_by_attainment_desc(payload: dict[str, Any]) -> list[str]:
    """Rep names ranked by quota attainment, highest first.

    get_sales_rep_performance returns reps in seed order, but the
    sales-performance playbook says to rank by attainmentPct — so the expected
    ranking has to be derived rather than read off the response.
    """
    return [rep["name"] for rep in sorted(payload["salesReps"], key=_attainment, reverse=True)]


def reps_below_quota_threshold(payload: dict[str, Any]) -> list[str]:
    """Reps the playbook says to flag as at-risk (attainment under 70%)."""
    return [rep["name"] for rep in payload["salesReps"] if _attainment(rep) < 70]


def customer_names(payload: dict[str, Any]) -> list[str]:
    return [customer["name"] for customer in payload["customers"]]


DERIVERS: dict[str, Any] = {
    "reps_by_attainment_desc": reps_by_attainment_desc,
    "reps_below_quota_threshold": reps_below_quota_threshold,
    "customer_names": customer_names,
}


def resolve(case: Case, client: RawMcpClient) -> dict[str, Any]:
    """Run the case's ground-truth program and return its bindings.

    Uses call_readonly, so a resolver can never mutate the state it observes.
    """
    bindings: dict[str, Any] = {}
    for step in case.ground_truth:
        if step.derive:
            deriver = DERIVERS.get(step.derive)
            if deriver is None:
                raise ValueError(f"case {case.id}: unknown deriver {step.derive!r}")
            bindings[step.as_] = deriver(bindings[step.from_])
            continue
        args = resolve_templates(step.args, bindings)
        result = client.call_readonly(step.tool, args)
        if result.is_error:
            raise RuntimeError(
                f"case {case.id}: ground-truth step {step.as_!r} ({step.tool}) "
                f"returned an error: {result.payload}"
            )
        bindings[step.as_] = result.payload
    return bindings
