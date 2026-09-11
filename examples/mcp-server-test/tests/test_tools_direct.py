"""Server invariants the ground-truth resolvers rely on. No LLM, no API keys.

ground_truth.py computes expected values by calling these same tools, so if the
server's contract drifts, the resolvers would silently redefine "correct" and
every agent score would still look green. These tests make that drift fail
loudly and independently.

Only *stable* properties are pinned. Dates are deliberately excluded: data.js
uses faker.date.soon()/recent(), which are relative to wall-clock now, so
renewalDate, closeDate, lastExecutiveMeeting and createdAt change every day
even though the seed is fixed.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

DEFAULT_LIMIT = 10
MAX_LIMIT = 25
TOTAL_OPPORTUNITIES = 72
SALES_REPS = ["Avery Chen", "Maya Patel", "Noah Brooks", "Sofia Rivera", "Theo Morgan"]


def _money(value: str) -> int:
    return int(value.replace("$", "").replace(",", ""))


class TestLimits:
    def test_default_limit_is_ten(self, raw_client):
        assert raw_client.call_readonly("list_customers", {}).payload["count"] == DEFAULT_LIMIT

    @pytest.mark.parametrize("tool", ["list_customers", "search_opportunities", "list_support_tickets"])
    def test_limit_clamps_to_twenty_five(self, raw_client, tool):
        assert raw_client.call_readonly(tool, {"limit": 100}).payload["count"] == MAX_LIMIT


class TestOrdering:
    def test_customers_sort_by_arr_descending(self, raw_client):
        rows = raw_client.call_readonly("list_customers", {"limit": 25}).payload["customers"]
        amounts = [_money(row["arr"]) for row in rows]
        assert amounts == sorted(amounts, reverse=True)

    def test_opportunities_sort_by_weighted_amount_descending(self, raw_client):
        rows = raw_client.call_readonly("search_opportunities", {"limit": 25}).payload["opportunities"]
        amounts = [_money(row["weightedAmount"]) for row in rows]
        assert amounts == sorted(amounts, reverse=True)

    def test_support_tickets_are_returned_in_id_order_not_sorted(self, raw_client):
        """list_support_tickets filters then slices without sorting.

        Ground truth for "first N tickets" therefore means insertion order, not
        any ranking — worth pinning so a future sort doesn't silently pass.
        """
        rows = raw_client.call_readonly("list_support_tickets", {"limit": 25}).payload["tickets"]
        assert [row["id"] for row in rows] == sorted(row["id"] for row in rows)


class TestFilters:
    def test_region_filter_is_case_insensitive(self, raw_client):
        lower = raw_client.call_readonly("list_customers", {"region": "emea", "limit": 25}).payload
        exact = raw_client.call_readonly("list_customers", {"region": "EMEA", "limit": 25}).payload
        assert lower["count"] == exact["count"] > 0
        assert {row["region"] for row in exact["customers"]} == {"EMEA"}

    def test_segment_filter_narrows_results(self, raw_client):
        rows = raw_client.call_readonly("list_customers", {"segment": "Enterprise", "limit": 25}).payload["customers"]
        assert rows and {row["segment"] for row in rows} == {"Enterprise"}

    def test_summarize_pipeline_excludes_closed_by_default(self, raw_client):
        open_only = raw_client.call_readonly("summarize_pipeline", {}).payload
        everything = raw_client.call_readonly("summarize_pipeline", {"includeClosed": True}).payload
        assert everything["opportunityCount"] == TOTAL_OPPORTUNITIES
        assert open_only["opportunityCount"] < everything["opportunityCount"]
        assert not any(stage.startswith("Closed") for stage in open_only["byStage"])


class TestErrorShape:
    @pytest.mark.parametrize(
        ("tool", "args"),
        [
            ("get_customer_health", {"customerId": "cus_9999"}),
            ("get_product_telemetry", {"customerId": "cus_9999"}),
            ("get_support_ticket", {"ticketId": "tkt_9999"}),
            ("simulate_churn_risk_scenario", {"customerId": "cus_9999"}),
        ],
    )
    def test_unknown_id_returns_is_error_with_an_error_message(self, raw_client, tool, args):
        result = raw_client.call_readonly(tool, args)
        assert result.is_error is True
        assert "not found" in result.payload["error"].lower()


class TestStableShapes:
    def test_sales_reps_are_the_five_seeded_owners(self, raw_client):
        payload = raw_client.call_readonly("get_sales_rep_performance", {}).payload
        assert [rep["name"] for rep in payload["salesReps"]] == SALES_REPS

    def test_telemetry_reports_seat_utilization(self, raw_client):
        seats = raw_client.call_readonly("get_product_telemetry", {"customerId": "cus_0001"}).payload["seats"]
        assert seats["activeWeekly"] <= seats["assigned"] <= seats["purchased"]
        assert 0 <= seats["utilizationRatePct"] <= 100

    def test_churn_simulation_returns_drivers(self, raw_client):
        results = raw_client.call_readonly(
            "simulate_churn_risk_scenario", {"customerId": "cus_0001"}
        ).payload["simulationResults"]
        assert results["churnProbabilityPct"].endswith("%")
        assert "riskCategory" in results and isinstance(results["keyDrivers"], list)
