"""
Tests for shared prompt instruction building.
"""

import os
import sys
import types
from collections import OrderedDict
from unittest.mock import AsyncMock, MagicMock

import pytest

_server_dir = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, _server_dir)

if 'inference' not in sys.modules:
    _pkg = types.ModuleType('inference')
    _pkg.__path__ = [os.path.join(_server_dir, 'inference')]
    _pkg.__package__ = 'inference'
    sys.modules['inference'] = _pkg

from inference.pipeline.base import ProcessingContext
from inference.pipeline.prompt_builder import PromptInstructionBuilder


@pytest.mark.asyncio
async def test_prompt_builder_uses_prompt_service_text():
    prompt_service = AsyncMock()
    prompt_service.get_prompt_by_id.return_value = {"prompt": "You are a pirate captain."}

    builder = PromptInstructionBuilder(
        config={},
        prompt_service=prompt_service,
        prompt_cache=OrderedDict(),
    )

    context = ProcessingContext(
        adapter_name="voice-chat",
        system_prompt_id="prompt-123",
    )

    result = await builder.build_system_message_content(context)

    assert "You are a pirate captain." in result
    assert "Answer based on the system prompt. Maintain your persona." in result
    prompt_service.get_prompt_by_id.assert_awaited_once_with("prompt-123")


@pytest.mark.asyncio
async def test_prompt_builder_clear_prompt_cache_removes_specific_prompt():
    prompt_service = AsyncMock()
    prompt_service.get_prompt_by_id.side_effect = [
        {"prompt": "Original persona."},
        {"prompt": "Updated persona."},
    ]

    cache = OrderedDict()
    builder = PromptInstructionBuilder(
        config={},
        prompt_service=prompt_service,
        prompt_cache=cache,
    )
    context = ProcessingContext(
        adapter_name="voice-chat",
        system_prompt_id="prompt-123",
    )

    assert await builder.get_system_prompt(context) == "Original persona."
    assert await builder.get_system_prompt(context) == "Original persona."
    assert prompt_service.get_prompt_by_id.await_count == 1

    assert builder.clear_prompt_cache("prompt-123") == 1
    assert await builder.get_system_prompt(context) == "Updated persona."
    assert prompt_service.get_prompt_by_id.await_count == 2


@pytest.mark.asyncio
async def test_prompt_builder_falls_back_to_default_prompt():
    builder = PromptInstructionBuilder(config={})
    context = ProcessingContext(adapter_name="voice-chat")

    result = await builder.build_system_message_content(context)

    assert "You are a helpful assistant." in result


@pytest.mark.asyncio
async def test_prompt_builder_includes_time_instruction_when_clock_service_enabled():
    clock_service = MagicMock()
    clock_service.enabled = True
    clock_service.get_time_instruction.return_value = "Current time is 2026-04-08 10:00."

    builder = PromptInstructionBuilder(
        config={},
        clock_service=clock_service,
    )
    context = ProcessingContext(
        adapter_name="voice-chat",
        timezone="America/Toronto",
        time_format="%Y-%m-%d %H:%M",
    )

    result = await builder.build_system_message_content(context)

    assert "Current time is 2026-04-08 10:00." in result
    clock_service.get_time_instruction.assert_called_once_with("America/Toronto", "%Y-%m-%d %H:%M")


def test_build_chart_instruction_contains_all_chart_types():
    builder = PromptInstructionBuilder(config={})
    instruction = builder.build_chart_instruction()

    for chart_type in ("bar", "line", "pie", "area", "scatter", "composed", "radar", "funnel", "radialbar"):
        assert chart_type in instruction, f"Chart type '{chart_type}' missing from chart instruction"


def test_build_chart_instruction_contains_new_config_options():
    builder = PromptInstructionBuilder(config={})
    instruction = builder.build_chart_instruction()

    assert "layout" in instruction
    assert "innerRadius" in instruction
    assert "outerRadius" in instruction
    assert "horizontal" in instruction


def test_build_chart_instruction_contains_usage_notes_for_new_types():
    builder = PromptInstructionBuilder(config={})
    instruction = builder.build_chart_instruction()

    assert "radar" in instruction
    assert "funnel" in instruction
    assert "radialbar" in instruction
    assert "xKey" in instruction


def test_build_chart_instruction_rules_updated():
    builder = PromptInstructionBuilder(config={})
    instruction = builder.build_chart_instruction()

    # Rule 7 — radar xKey guidance
    assert "spoke" in instruction or "radar" in instruction
    # Rule 8 — horizontal bar guidance
    assert "layout: horizontal" in instruction
