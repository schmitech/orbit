"""Tests for provider-agnostic realtime retrieval formatting."""

import os
import sys
from unittest.mock import AsyncMock

import pytest


_server_dir = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _server_dir)

from services.chat_handlers.realtime_grounding import (
    GroundingConfig,
    _format_answer,
    execute_grounding_lookup,
)


@pytest.mark.asyncio
async def test_grounding_forwards_embedding_usage_sink():
    usage = {}
    adapter = AsyncMock()
    adapter.get_relevant_context.return_value = [{"answer": "Twenty dollars."}]
    manager = AsyncMock()
    manager.get_adapter.return_value = adapter
    grounding = GroundingConfig("fees", "lookup", "Look up a fee")

    answer = await execute_grounding_lookup(
        manager, grounding, "How much?", usage_sink=usage
    )

    assert answer == "Twenty dollars."
    adapter.get_relevant_context.assert_awaited_once_with(
        query="How much?", api_key=None, usage_sink=usage
    )


def test_format_answer_uses_structured_intent_rows_not_rendered_table():
    docs = [{
        "content": "Found 2 results:\n| broken table syntax |",
        "metadata": {
            "formatted_data": {
                "result_count": 2,
                "table": {
                    "columns": ["Order ID", "Status", "Total"],
                    "rows": [["A-100", "shipped", "$25.00"], ["A-101", "pending", "$40.00"]],
                },
            },
        },
    }]

    answer = _format_answer(docs, max_chars=120, max_rows=1)

    assert answer == "Found 2 results. Order ID: A-100; Status: shipped; Total: $25.00"
    assert "A-101" not in answer
    assert "|" not in answer


def test_format_answer_drops_whole_rows_before_character_budget():
    docs = [{
        "metadata": {
            "formatted_data": {
                "result_count": 2,
                "table": {
                    "columns": ["Order ID", "Status"],
                    "rows": [["A-100", "shipped"], ["A-101", "pending"]],
                },
            },
        },
    }]

    answer = _format_answer(docs, max_chars=55, max_rows=3)

    assert answer == "Found 2 results. Order ID: A-100; Status: shipped"
    assert len(answer) <= 55
    assert "A-101" not in answer


def test_format_answer_keeps_qa_answer_behavior():
    assert _format_answer([{"answer": "Twenty dollars."}], max_chars=100) == "Twenty dollars."
