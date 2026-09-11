"""The regression gate.

Mirrors server/tests/intent_eval/test_regression.py: run every suite against
every available model and assert the result does not fall below the checked-in
floor in baseline.json.

Marked integration+slow because it drives real provider APIs and costs money —
it is never part of a default run. Missing prerequisites (server down, no API
key, no baseline recorded) skip with an explanation rather than failing, so a
missing key never masquerades as a behavioural regression.

    .venv/bin/python -m pytest tests/test_regression.py -q -m "" -s
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from mcpeval import report
from mcpeval.agent import load_tools
from mcpeval.config import CASES_DIR
from mcpeval.judge import build_judge
from mcpeval.models import ModelSpec, registry
from mcpeval.runner import run_eval
from mcpeval.sandbox import TicketSandbox
from mcpeval.schema import load_suites

pytestmark = [pytest.mark.integration, pytest.mark.slow]

BASELINE_PATH = Path(__file__).resolve().parent.parent / "baseline.json"

# Which prompt variants to gate on. The playbook variant is what ORBIT actually
# runs in production, so it is the default; set MCP_EVAL_VARIANTS=base,playbook
# to gate on both (doubles the cost).
VARIANTS = tuple(os.getenv("MCP_EVAL_VARIANTS", "playbook").split(","))


def load_baseline() -> dict:
    if not BASELINE_PATH.exists():
        return {}
    return json.loads(BASELINE_PATH.read_text())


def _params():
    for suite in load_suites(CASES_DIR):
        for spec in registry():
            # A suite with no playbook has nothing to inject, so it always runs
            # as "base" — otherwise the default playbook-only run would skip it
            # entirely and silently lose its coverage.
            variants = {("base" if not suite.playbook else variant) for variant in VARIANTS}
            for variant in sorted(variants):
                yield pytest.param(suite, spec, variant, id=f"{suite.name}-{spec.key}-{variant}")


@pytest.fixture(scope="session")
async def mcp_tools(mcp_server):
    return await load_tools(mcp_server)


@pytest.fixture(scope="session")
def ticket_sandbox(raw_client):
    """Snapshot the ticket table for the whole session and restore afterwards.

    The mutating cases only ever touch tickets this sandbox created, but the
    snapshot is the backstop for an agent that does something unexpected.
    """
    sandbox = TicketSandbox.capture(raw_client)
    yield sandbox
    repaired = sandbox.restore()
    drift = sandbox.drifted()
    if drift:
        pytest.fail(
            f"Support-ticket state did not return to its starting point: {drift}. "
            f"Repairs attempted: {repaired}. Restart the sample server to restore the seed."
        )


@pytest.fixture(scope="session")
def collected_results():
    results: list = []
    yield results
    if results:
        json_path, md_path = report.write(results, label="pytest")
        print(f"\nreports written:\n  {json_path}\n  {md_path}")


@pytest.mark.parametrize(("suite", "spec", "variant"), list(_params()))
async def test_suite_meets_baseline(suite, spec: ModelSpec, variant, mcp_tools, raw_client, mcp_server, ticket_sandbox, collected_results):
    if not spec.available():
        missing = ", ".join(spec.missing_env())
        pytest.skip(f"{missing} is not set, so {spec.key} cannot be evaluated.")

    baseline = load_baseline()
    key = f"{suite.name}::{spec.key}::{variant}"
    floor = baseline.get(key)
    if floor is None:
        pytest.skip(f"No baseline recorded for {key} — see the regeneration command in this file.")

    result = await run_eval(
        suite, spec, variant,
        tools=mcp_tools, raw_client=raw_client,
        judge=build_judge(spec), sandbox=ticket_sandbox,
    )
    collected_results.append(result)
    summary = result.summary()
    print(f"\n{key}: {json.dumps(summary, indent=2)}")

    assert result.total == floor["total"], (
        f"Corpus size changed ({result.total} vs baseline {floor['total']}) — "
        "review the diff, then regenerate the baseline."
    )

    # Raw counts, never rates. Storing a rounded rate and comparing it against a
    # freshly computed float invents 1-ULP 'regressions' that aren't real — the
    # same reasoning as server/tests/intent_eval.
    if result.checks_passed < floor["checks_passed"]:
        detail = "\n".join(
            f"  {row['case_id']} / {row['check']}: {row['comment']}\n"
            f"    tools: {row['tools_called']}"
            for row in result.failures
        )
        pytest.fail(
            f"Checks passed regressed: {result.checks_passed}/{result.checks_total} < "
            f"baseline {floor['checks_passed']}/{floor['checks_total']}\n\nFailures:\n{detail}"
        )

    assert result.cases_passed >= floor["cases_passed"], (
        f"Cases passed regressed: {result.cases_passed}/{result.total} < "
        f"baseline {floor['cases_passed']}/{floor['total']}"
    )

    assert result.agent_errors <= floor.get("agent_errors", 0), (
        f"More agent errors than baseline: {result.agent_errors} > {floor.get('agent_errors', 0)}"
    )


# The judge score is deliberately NOT ratcheted. It is the noisiest signal in
# the suite (an LLM grading prose), and gating on it would produce flaky
# failures that teach people to ignore the gate. It is recorded in every report
# so a trend is visible; promote it to an assertion only once you have watched
# its variance across several runs.
#
# To regenerate baseline.json after a genuine improvement — never to silence a
# real regression:
#
#   .venv/bin/python -m pytest tests/test_regression.py -q -m "" -s
#   .venv/bin/python -c "
#   import json, glob
#   run = json.load(open(sorted(glob.glob('results/pytest-*.json'))[-1]))
#   print(json.dumps({
#       s['key']: {k: s[k] for k in ('total','cases_passed','checks_total','checks_passed','agent_errors')}
#       for s in run['summaries']}, indent=2))
#   " > baseline.json
