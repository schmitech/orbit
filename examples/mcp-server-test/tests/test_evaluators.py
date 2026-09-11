"""Evaluator unit tests. No server, no API keys, no network.

The evaluators are the thing that decides whether an agent passed, so they get
tested the same way any other logic would — with synthetic runs where the right
answer is obvious.
"""

from __future__ import annotations

import pytest
from mcpeval.agent import AgentRun, ToolCallRecord
from mcpeval.evaluators import CheckContext, answer_mentions, run_checks
from mcpeval.schema import Case, Check

pytestmark = pytest.mark.unit


def make_case(*checks: dict, **kwargs) -> Case:
    return Case(
        id=kwargs.get("id", "t"),
        query="q",
        suite="s",
        playbook=None,
        checks=tuple(Check(type=c.pop("type"), params=c) for c in (dict(c) for c in checks)),
    )


def make_run(calls: list[tuple[str, dict]] | None = None, answer: str = "", errors: set[str] = frozenset()) -> AgentRun:
    records = [
        ToolCallRecord(name=name, args=args, id=str(i), is_error=name in errors)
        for i, (name, args) in enumerate(calls or [])
    ]
    return AgentRun(answer=answer, tool_calls=records)


def score(case: Case, run: AgentRun, ground_truth: dict | None = None) -> dict[str, float]:
    outcomes = run_checks(CheckContext(case=case, run=run, ground_truth=ground_truth or {}))
    return {o.type: o.score for o in outcomes}


class TestAnswerMentions:
    @pytest.mark.parametrize(
        ("answer", "value"),
        [
            ("ARR is $1,007,966 this year", "$1,007,966"),
            ("ARR is 1007966", "$1,007,966"),
            ("ARR is **$1,007,966**", 1007966),
            ("Utilization sits at 42%", "42%"),
            ("McLaughlin Inc leads EMEA", "McLaughlin Inc"),
            ("mclaughlin inc leads", "McLaughlin Inc"),
        ],
    )
    def test_matches_across_formatting(self, answer, value):
        assert answer_mentions(answer, value)

    @pytest.mark.parametrize(("answer", "value"), [("ARR is $2,000", "$1,007,966"), ("nothing here", "Acme")])
    def test_rejects_absent_values(self, answer, value):
        assert not answer_mentions(answer, value)


class TestToolChecks:
    def test_required_tools_partial_credit(self):
        case = make_case({"type": "required_tools", "tools": ["list_customers", "get_customer_health"]})
        assert score(case, make_run([("list_customers", {})]))["required_tools"] == 0.5

    def test_forbidden_tool_fails(self):
        case = make_case({"type": "forbidden_tools", "tools": ["delete_support_ticket"]})
        assert score(case, make_run([("delete_support_ticket", {"ticketId": "tkt_1"})]))["forbidden_tools"] == 0.0
        assert score(case, make_run([("get_support_ticket", {})]))["forbidden_tools"] == 1.0

    def test_tool_order_enforced_only_when_later_tool_used(self):
        case = make_case({"type": "tool_order", "before": "get_support_ticket", "after": "update_support_ticket"})
        assert score(case, make_run([("update_support_ticket", {})]))["tool_order"] == 0.0
        assert score(case, make_run([("get_support_ticket", {}), ("update_support_ticket", {})]))["tool_order"] == 1.0
        assert score(case, make_run([("update_support_ticket", {}), ("get_support_ticket", {})]))["tool_order"] == 0.0
        # Rule does not bind if the later tool was never called.
        assert score(case, make_run([("list_customers", {})]))["tool_order"] == 1.0

    def test_arg_bound_catches_oversized_limit(self):
        case = make_case({"type": "arg_bound", "tool": "search_opportunities", "arg": "limit", "max": 25})
        assert score(case, make_run([("search_opportunities", {"limit": 100})]))["arg_bound"] == 0.0
        assert score(case, make_run([("search_opportunities", {"limit": 25})]))["arg_bound"] == 1.0

    def test_tool_choice_prefers_the_aggregate_tool(self):
        case = make_case({"type": "tool_choice", "prefer": "summarize_pipeline", "instead_of": "search_opportunities"})
        assert score(case, make_run([("summarize_pipeline", {})]))["tool_choice"] == 1.0
        assert score(case, make_run([("search_opportunities", {})]))["tool_choice"] == 0.0
        assert score(case, make_run([]))["tool_choice"] == 0.0

    def test_id_enumeration_detected(self):
        case = make_case({"type": "no_id_enumeration", "prefix": "cus_"})
        walking = make_run([("get_customer_health", {"customerId": f"cus_{i:04d}"}) for i in (1, 2, 3)])
        assert score(case, walking)["no_id_enumeration"] == 0.0
        targeted = make_run([("get_customer_health", {"customerId": "cus_0025"})])
        assert score(case, targeted)["no_id_enumeration"] == 1.0


class TestAnswerChecks:
    def test_arg_matches_resolves_ground_truth_templates(self):
        case = make_case({"type": "arg_matches", "tool": "get_customer_health", "arg": "customerId", "equals": "${top.customers[0].id}"})
        gt = {"top": {"customers": [{"id": "cus_0025"}]}}
        assert score(case, make_run([("get_customer_health", {"customerId": "cus_0025"})]), gt)["arg_matches"] == 1.0
        assert score(case, make_run([("get_customer_health", {"customerId": "cus_0001"})]), gt)["arg_matches"] == 0.0

    def test_answer_ordering_requires_the_ranked_sequence(self):
        case = make_case({"type": "answer_ordering", "values": ["Maya Patel", "Avery Chen"]})
        assert score(case, make_run(answer="1. Maya Patel 2. Avery Chen"))["answer_ordering"] == 1.0
        assert score(case, make_run(answer="1. Avery Chen 2. Maya Patel"))["answer_ordering"] == 0.0

    def test_no_tool_calls_wants_a_real_answer(self):
        case = make_case({"type": "no_tool_calls"})
        assert score(case, make_run(answer="ARR means annual recurring revenue, " * 3))["no_tool_calls"] == 1.0
        assert score(case, make_run([("list_customers", {})], answer="x" * 80))["no_tool_calls"] == 0.0
        assert score(case, make_run(answer="no"))["no_tool_calls"] == 0.0


class TestErrorHandling:
    def test_error_must_be_acknowledged_without_fabrication(self):
        case = make_case({"type": "tool_error_handled", "must_not_contain": ["$500,000"]})
        run = make_run([("get_customer_health", {"customerId": "cus_9999"})], answer="Customer cus_9999 was not found.", errors={"get_customer_health"})
        assert score(case, run)["tool_error_handled"] == 1.0

        silent = make_run([("get_customer_health", {})], answer="The customer is healthy with strong usage.", errors={"get_customer_health"})
        assert score(case, silent)["tool_error_handled"] == 0.0

        invented = make_run([("get_customer_health", {})], answer="Not found, but ARR is about $500,000.", errors={"get_customer_health"})
        assert score(case, invented)["tool_error_handled"] == 0.0


def test_agent_error_short_circuits_all_checks():
    case = make_case({"type": "required_tools", "tools": ["list_customers"]})
    run = AgentRun(answer="", error="GraphRecursionError: limit reached")
    outcomes = run_checks(CheckContext(case=case, run=run, ground_truth={}))
    assert [o.type for o in outcomes] == ["agent_error"] and outcomes[0].score == 0.0


def test_unknown_check_type_is_rejected_loudly():
    case = make_case({"type": "does_not_exist"})
    with pytest.raises(ValueError, match="unknown check type"):
        run_checks(CheckContext(case=case, run=make_run(), ground_truth={}))


# ----------------------------------------------- multi-step workflow checks


def test_tool_sequence_allows_unrelated_calls_in_between():
    """The agent may do more than the minimum, just not in the wrong order."""
    case = make_case({"type": "tool_sequence", "tools": ["a", "b", "c"]})
    run = make_run([("a", {}), ("x", {}), ("b", {}), ("y", {}), ("c", {})])
    assert score(case, run)["tool_sequence"] == 1.0


def test_tool_sequence_rejects_a_step_out_of_order():
    case = make_case({"type": "tool_sequence", "tools": ["a", "b", "c"]})
    assert score(case, make_run([("a", {}), ("c", {}), ("b", {})]))["tool_sequence"] == 0.0


def test_tool_sequence_rejects_a_missing_step():
    case = make_case({"type": "tool_sequence", "tools": ["a", "b", "c"]})
    assert score(case, make_run([("a", {}), ("c", {})]))["tool_sequence"] == 0.0


def test_pairwise_tool_order_false_alarms_where_tool_sequence_does_not():
    """b, a, b, c contains a valid a -> b -> c workflow.

    tool_order compares FIRST occurrences, so the stray leading b makes
    index(a)=1 > index(b)=0 and it reports a failure that did not happen. That
    is the flaky direction, and it gets worse the longer the workflow. The
    subsequence walk sees the real ordering.
    """
    trajectory = make_run([("b", {}), ("a", {}), ("b", {}), ("c", {})])
    pairwise = make_case({"type": "tool_order", "before": "a", "after": "b"})
    assert score(pairwise, trajectory)["tool_order"] == 0.0  # false alarm
    sequenced = make_case({"type": "tool_sequence", "tools": ["a", "b", "c"]})
    assert score(sequenced, trajectory)["tool_sequence"] == 1.0


def test_arg_matches_any_is_the_default_and_tolerates_one_good_call():
    case = make_case({"type": "arg_matches", "tool": "t", "arg": "id", "equals": "cus_1"})
    run = make_run([("t", {"id": "cus_9"}), ("t", {"id": "cus_1"})])
    assert score(case, run)["arg_matches"] == 1.0


def test_arg_matches_all_catches_a_wrong_call_hidden_behind_a_right_one():
    """The repeated-call blind spot: 'any' passes while half the workflow is wrong."""
    case = make_case({"type": "arg_matches", "tool": "t", "arg": "id", "equals": "cus_1", "which": "all"})
    run = make_run([("t", {"id": "cus_9"}), ("t", {"id": "cus_1"})])
    assert score(case, run)["arg_matches"] == 0.0


def test_arg_matches_first_and_last_select_one_call():
    run = make_run([("t", {"id": "cus_1"}), ("t", {"id": "cus_9"})])
    first = make_case({"type": "arg_matches", "tool": "t", "arg": "id", "equals": "cus_1", "which": "first"})
    last = make_case({"type": "arg_matches", "tool": "t", "arg": "id", "equals": "cus_1", "which": "last"})
    assert score(first, run)["arg_matches"] == 1.0
    assert score(last, run)["arg_matches"] == 0.0


def test_arg_matches_rejects_an_unknown_selector():
    case = make_case({"type": "arg_matches", "tool": "t", "arg": "id", "equals": "x", "which": "most"})
    with pytest.raises(ValueError, match="unknown which"):
        score(case, make_run([("t", {"id": "x"})]))


def test_recovery_requires_an_error_to_have_happened():
    case = make_case({"type": "recovers_after_error"})
    assert score(case, make_run([("a", {})]))["recovers_after_error"] == 0.0


def test_giving_up_after_an_error_is_not_recovery():
    """The failure mode this exists to catch: the workflow stops at the error."""
    case = make_case({"type": "recovers_after_error"})
    run = make_run([("a", {}), ("boom", {})], answer="I could not find it.", errors={"boom"})
    assert score(case, run)["recovers_after_error"] == 0.0


def test_recovery_needs_a_successful_call_after_the_error():
    case = make_case({"type": "recovers_after_error"})
    run = make_run([("boom", {}), ("b", {})], answer="Found it instead.", errors={"boom"})
    assert score(case, run)["recovers_after_error"] == 1.0


def test_recovery_can_require_which_tools_completed():
    case = make_case({"type": "recovers_after_error", "then_tools": ["c"]})
    partial = make_run([("boom", {}), ("b", {})], answer="ok", errors={"boom"})
    complete = make_run([("boom", {}), ("b", {}), ("c", {})], answer="ok", errors={"boom"})
    assert score(case, partial)["recovers_after_error"] == 0.0
    assert score(case, complete)["recovers_after_error"] == 1.0


def test_recovery_without_an_answer_does_not_count():
    case = make_case({"type": "recovers_after_error"})
    run = make_run([("boom", {}), ("b", {})], answer="   ", errors={"boom"})
    assert score(case, run)["recovers_after_error"] == 0.0


def test_an_error_after_recovery_does_not_undo_it():
    """Only the FIRST error opens the recovery window; later noise is not fatal."""
    case = make_case({"type": "recovers_after_error"})
    run = make_run([("boom", {}), ("b", {}), ("boom2", {})], answer="ok", errors={"boom", "boom2"})
    assert score(case, run)["recovers_after_error"] == 1.0


def test_markdown_emphasis_does_not_hide_an_honest_error_report():
    """Models bold their words: "does **not** exist" must still match."""
    case = make_case({"type": "tool_error_handled"})
    run = make_run([("boom", {})], answer="Ticket **tkt_9999** does **not** exist.", errors={"boom"})
    assert score(case, run)["tool_error_handled"] == 1.0


def test_emphasis_stripping_keeps_underscores_in_ids():
    assert answer_mentions("the account is `cus_0025` today", "cus_0025")
