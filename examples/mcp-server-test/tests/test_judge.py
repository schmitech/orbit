"""Judge calibration.

The groundedness judge is the only non-deterministic evaluator, so it gets a
discrimination test rather than a calibration one: a faithful answer must score
clearly higher than one that invents data. Exact scores are not asserted —
separation is what makes the signal usable.

Costs an API call, hence slow.
"""

from __future__ import annotations

import pytest
from mcpeval.agent import AgentRun, ToolCallRecord
from mcpeval.judge import build_judge
from mcpeval.models import available
from mcpeval.schema import Case

pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.fixture(scope="module")
def pipeline_call(raw_client):
    result = raw_client.call_readonly("summarize_pipeline", {})
    return ToolCallRecord(
        name="summarize_pipeline", args={}, id="1", payload=result.payload, raw_text=result.raw_text
    )


@pytest.fixture(scope="module")
def judge(mcp_server):
    specs = available()
    if not specs:
        pytest.skip("No provider API key set, so the judge cannot run.")
    return build_judge(specs[0])


def _case() -> Case:
    return Case(id="judge", query="Summarize the open pipeline by stage.", suite="t", playbook=None, checks=())


def test_faithful_answer_scores_high(judge, pipeline_call):
    payload = pipeline_call.payload
    answer = (
        f"Open pipeline totals {payload['totalPipeline']} across {payload['opportunityCount']} "
        f"opportunities, weighted to {payload['weightedPipeline']}. This suggests healthy "
        "late-stage coverage and is worth reviewing with the regional leads."
    )
    score, comment = judge(_case(), AgentRun(answer=answer, tool_calls=[pipeline_call]), {})
    assert score is not None, comment
    assert score >= 0.8, f"faithful answer scored {score}: {comment}"


def test_fabricated_answer_scores_low(judge, pipeline_call):
    """The invented owner breakdown is exactly what crm-pipeline-playbook
    forbids: summarize_pipeline returns no owner data at all."""
    payload = pipeline_call.payload
    answer = (
        f"Open pipeline totals {payload['totalPipeline']}. Avery Chen owns $2,400,000 of it and "
        "Maya Patel $1,900,000. Pipeline grew 18% quarter over quarter, and 42 open support "
        "tickets are attached to these deals."
    )
    score, comment = judge(_case(), AgentRun(answer=answer, tool_calls=[pipeline_call]), {})
    assert score is not None, comment
    assert score <= 0.5, f"fabricated answer scored {score}: {comment}"


def test_analysis_is_not_counted_as_fabrication(judge, pipeline_call):
    """The business prompt asks for proactive analysis, so hedged commentary
    must not be scored as invented data."""
    payload = pipeline_call.payload
    answer = (
        f"Weighted pipeline is {payload['weightedPipeline']}. That likely understates true coverage "
        "if late-stage deals slip, and it may be worth tightening qualification — though the "
        "underlying driver could simply be seasonality."
    )
    score, comment = judge(_case(), AgentRun(answer=answer, tool_calls=[pipeline_call]), {})
    assert score is not None, comment
    assert score >= 0.8, f"hedged analysis was penalised as fabrication ({score}): {comment}"
