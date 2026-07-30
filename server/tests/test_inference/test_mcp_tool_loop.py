#!/usr/bin/env python3
"""
Unit tests for the shared MCP tool-calling loop
(server/inference/pipeline/mcp_tool_loop.py).

This is the canonical test suite for the loop's behavior — extracted from
MCPAgentStep so it can be exercised directly (no ProcessingContext, no
service container), and reused by LLMInferenceStep's opportunistic path.
See test_mcp_agent_step.py for the equivalent coverage of the MCPAgentStep
wrapper, kept intact to guard the extraction against regressions.
"""

import asyncio
import os
import sys

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, server_dir)

from ai_services.services import ToolCallingResult
from inference.pipeline.mcp_tool_loop import run_tool_calling_loop


class _FakeProvider:
    """Returns queued ToolCallingResults and records every call's tool list."""

    def __init__(self, results):
        self._results = list(results)
        self.calls = []  # list of (messages_len, tools_len)

    async def generate_with_tools(self, messages, tools, **kwargs):
        self.calls.append((len(messages), len(tools)))
        if self._results:
            return self._results.pop(0)
        return ToolCallingResult(
            text="default-final",
            tool_calls=None,
            assistant_message={"role": "assistant", "content": "default-final"},
            finish_reason="stop",
        )


class _FakeTrackedProvider:
    """
    Returns queued ToolCallingResults like _FakeProvider, but also implements
    generate_with_tools_tracked and fills whatever usage_sink it's given with
    a queued usage dict — mirroring a real UsageReportingMixin-based provider.
    Used to verify the loop sums usage across iterations correctly, since
    _report_usage() overwrites a sink rather than accumulating (each call
    must receive its own fresh sink).
    """

    def __init__(self, results, usages=None):
        self._results = list(results)
        self._usages = list(usages or [])
        self.calls = []
        self.received_sinks = []

    async def generate_with_tools(self, messages, tools, **kwargs):
        raise AssertionError("generate_with_tools_tracked should be used, not the plain method")

    async def generate_with_tools_tracked(self, messages, tools, usage_sink=None, **kwargs):
        self.calls.append((len(messages), len(tools)))
        self.received_sinks.append(usage_sink)
        if usage_sink is not None and self._usages:
            usage_sink.update(self._usages.pop(0))
        if self._results:
            return self._results.pop(0)
        return ToolCallingResult(
            text="default-final",
            tool_calls=None,
            assistant_message={"role": "assistant", "content": "default-final"},
            finish_reason="stop",
        )


class _FakeNonReportingTrackedProvider:
    """A provider that implements generate_with_tools_tracked but never
    actually reports usage (e.g. a provider whose SDK response carried no
    usage this turn) — the sink it's given is left untouched."""

    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    async def generate_with_tools_tracked(self, messages, tools, usage_sink=None, **kwargs):
        self.calls.append((len(messages), len(tools)))
        if self._results:
            return self._results.pop(0)
        return ToolCallingResult(
            text="default-final", tool_calls=None,
            assistant_message={"role": "assistant", "content": "default-final"},
            finish_reason="stop",
        )


class _FakeMCPManager:
    def __init__(self, tool_output="TOOL_OUTPUT"):
        self._tool_output = tool_output
        self.called_with = []

    async def call_tool(self, name, arguments):
        self.called_with.append((name, arguments))
        return self._tool_output


def _tool_call_result(name="filesystem__read_file", args=None):
    args = args or {"path": "/tmp/x"}
    return ToolCallingResult(
        text=None,
        tool_calls=[{"id": "c1", "name": name, "arguments": args}],
        assistant_message={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": name, "arguments": "{}"}}
            ],
        },
        finish_reason="tool_calls",
    )


_TOOLS = [{"type": "function", "function": {"name": "filesystem__read_file", "parameters": {}}}]


def _initial_messages(message="hi"):
    return [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": message},
    ]


class TestRunToolCallingLoop:
    async def test_no_tool_calls_returns_text_immediately(self):
        provider = _FakeProvider([
            ToolCallingResult(
                text="just an answer",
                tool_calls=None,
                assistant_message={"role": "assistant", "content": "just an answer"},
                finish_reason="stop",
            )
        ])
        manager = _FakeMCPManager()

        text, sources, messages = await run_tool_calling_loop(
            provider, manager, _initial_messages(), _TOOLS, max_iterations=3,
        )

        assert text == "just an answer"
        assert sources == []
        assert manager.called_with == []
        assert len(provider.calls) == 1
        assert messages[0]["role"] == "system"

    async def test_single_tool_call_then_final_answer(self):
        provider = _FakeProvider([
            _tool_call_result(),
            ToolCallingResult(
                text="here is the file",
                tool_calls=None,
                assistant_message={"role": "assistant", "content": "here is the file"},
                finish_reason="stop",
            ),
        ])
        manager = _FakeMCPManager(tool_output="file-contents")

        text, sources, _ = await run_tool_calling_loop(
            provider, manager, _initial_messages("read it"), _TOOLS, max_iterations=3,
        )

        assert text == "here is the file"
        assert manager.called_with == [("filesystem__read_file", {"path": "/tmp/x"})]
        assert len(sources) == 1
        src = sources[0]
        assert src["type"] == "mcp_tool_call"
        assert src["tool"] == "filesystem__read_file"
        assert src["result_preview"] == "file-contents"

    async def test_exhaustion_forces_final_call_without_tools(self):
        results = [_tool_call_result() for _ in range(3)]
        results.append(
            ToolCallingResult(
                text="synthesized answer",
                tool_calls=None,
                assistant_message={"role": "assistant", "content": "synthesized answer"},
                finish_reason="stop",
            )
        )
        provider = _FakeProvider(results)
        manager = _FakeMCPManager()

        text, sources, _ = await run_tool_calling_loop(
            provider, manager, _initial_messages("loop forever"), _TOOLS, max_iterations=3,
        )

        assert text == "synthesized answer"
        assert len(provider.calls) == 4
        assert provider.calls[-1][1] == 0
        assert len(manager.called_with) == 3

    async def test_exhaustion_with_empty_final_text_returns_fallback(self):
        results = [_tool_call_result() for _ in range(2)]
        results.append(
            ToolCallingResult(
                text=None,
                tool_calls=None,
                assistant_message={"role": "assistant", "content": None},
                finish_reason="stop",
            )
        )
        provider = _FakeProvider(results)
        manager = _FakeMCPManager()

        text, sources, _ = await run_tool_calling_loop(
            provider, manager, _initial_messages("x"), _TOOLS, max_iterations=2,
        )

        assert text
        assert "could not" in text.lower() or "unable" in text.lower()


class TestRunToolCallingLoopCancellation:
    async def test_precancelled_does_no_work(self):
        provider = _FakeProvider([])
        manager = _FakeMCPManager()
        ev = asyncio.Event()
        ev.set()

        text, sources, _ = await run_tool_calling_loop(
            provider, manager, _initial_messages("x"), _TOOLS, max_iterations=3,
            cancel_event=ev, is_cancelled=ev.is_set,
        )

        assert text == ""
        assert provider.calls == []
        assert manager.called_with == []

    async def test_cancel_during_tool_call_halts_loop(self):
        ev = asyncio.Event()

        class _CancelOnToolManager(_FakeMCPManager):
            async def call_tool(self, name, arguments):
                ev.set()
                return await super().call_tool(name, arguments)

        provider = _FakeProvider([_tool_call_result(), _tool_call_result()])
        manager = _CancelOnToolManager()

        await run_tool_calling_loop(
            provider, manager, _initial_messages("x"), _TOOLS, max_iterations=5,
            cancel_event=ev, is_cancelled=ev.is_set,
        )

        assert len(provider.calls) == 1

    async def test_cancel_interrupts_slow_tool_call_midflight(self):
        ev = asyncio.Event()
        started = asyncio.Event()

        class _SlowManager(_FakeMCPManager):
            async def call_tool(self, name, arguments):
                started.set()
                await asyncio.sleep(30)
                return "never reached"

        provider = _FakeProvider([_tool_call_result()])
        manager = _SlowManager()

        async def _stop_once_tool_starts():
            await started.wait()
            ev.set()

        loop_task = asyncio.ensure_future(
            run_tool_calling_loop(
                provider, manager, _initial_messages("x"), _TOOLS, max_iterations=5,
                cancel_event=ev, is_cancelled=ev.is_set,
            )
        )
        await asyncio.wait_for(asyncio.gather(loop_task, _stop_once_tool_starts()), timeout=5)

        text, sources, _ = loop_task.result()
        assert len(provider.calls) == 1
        assert sources == []


class TestRunToolCallingLoopUsageTracking:
    """
    Regression coverage for summing token usage across the loop's N provider
    calls (see accumulate_usage_sink in ai_services/providers/usage_reporting.py).
    Before this, usage was never tracked at all in the MCP loop — the docs'
    "Known limitations" section flagged multi-call usage as unsummed and
    unreported.
    """

    async def test_tokens_summed_across_iterations(self):
        provider = _FakeTrackedProvider(
            [_tool_call_result()],
            usages=[
                {"reported": True, "prompt_tokens": 100, "completion_tokens": 20,
                 "total_tokens": 120, "provider": "openai", "model": "gpt-5.4"},
                {"reported": True, "prompt_tokens": 150, "completion_tokens": 30,
                 "total_tokens": 180, "provider": "openai", "model": "gpt-5.4"},
            ],
        )
        manager = _FakeMCPManager()
        usage_sink: dict = {}

        text, sources, _ = await run_tool_calling_loop(
            provider, manager, _initial_messages("x"), _TOOLS, max_iterations=5,
            usage_sink=usage_sink,
        )

        assert len(provider.calls) == 2
        assert usage_sink["reported"] is True
        assert usage_sink["calls"] == 2
        assert usage_sink["prompt_tokens"] == 250
        assert usage_sink["completion_tokens"] == 50
        assert usage_sink["total_tokens"] == 300
        assert usage_sink["provider"] == "openai"
        assert usage_sink["model"] == "gpt-5.4"

    async def test_fresh_sink_used_per_iteration_not_shared(self):
        """
        A provider whose tracked method receives the SAME sink object across
        calls would silently lose earlier iterations' counts, because
        _report_usage() overwrites rather than accumulates. Assert the loop
        hands each call a distinct dict, so a regression back to one shared
        sink would break this test rather than just under-reporting silently.
        """
        provider = _FakeTrackedProvider(
            [_tool_call_result()],
            usages=[
                {"reported": True, "prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
                {"reported": True, "prompt_tokens": 20, "completion_tokens": 2, "total_tokens": 22},
            ],
        )
        manager = _FakeMCPManager()
        usage_sink: dict = {}

        await run_tool_calling_loop(
            provider, manager, _initial_messages("x"), _TOOLS, max_iterations=5,
            usage_sink=usage_sink,
        )

        assert len(provider.received_sinks) == 2
        assert provider.received_sinks[0] is not provider.received_sinks[1]
        # If a shared sink had been reused, total_tokens would read 22 (last
        # call's value only) instead of the true sum.
        assert usage_sink["total_tokens"] == 33

    async def test_non_reporting_provider_leaves_sink_unreported(self):
        """A provider that never fills its sink must leave usage_sink empty/
        unreported — never silently defaulting to zero tokens."""
        provider = _FakeNonReportingTrackedProvider([
            ToolCallingResult(
                text="answer", tool_calls=None,
                assistant_message={"role": "assistant", "content": "answer"},
                finish_reason="stop",
            )
        ])
        manager = _FakeMCPManager()
        usage_sink: dict = {}

        await run_tool_calling_loop(
            provider, manager, _initial_messages("x"), _TOOLS, max_iterations=5,
            usage_sink=usage_sink,
        )

        assert usage_sink.get("reported") is not True
        assert "prompt_tokens" not in usage_sink

    async def test_cancellation_mid_loop_keeps_partial_totals(self):
        """Tokens from iterations completed before a mid-loop cancellation
        must survive in the accumulator — cancellation shouldn't discard
        usage that was already reported."""
        ev = asyncio.Event()

        class _CancelAfterToolCallManager(_FakeMCPManager):
            async def call_tool(self, name, arguments):
                result = await super().call_tool(name, arguments)
                ev.set()  # trip cancellation once the first iteration's tool call completes
                return result

        provider = _FakeTrackedProvider(
            [_tool_call_result(), _tool_call_result()],
            usages=[
                {"reported": True, "prompt_tokens": 40, "completion_tokens": 5, "total_tokens": 45},
                {"reported": True, "prompt_tokens": 999, "completion_tokens": 999, "total_tokens": 1998},
            ],
        )
        manager = _CancelAfterToolCallManager()
        usage_sink: dict = {}

        await run_tool_calling_loop(
            provider, manager, _initial_messages("x"), _TOOLS, max_iterations=5,
            cancel_event=ev, is_cancelled=ev.is_set, usage_sink=usage_sink,
        )

        # Only the first call's usage should have landed — cancellation is
        # detected at the top of the next iteration, before the second
        # provider call ever happens.
        assert usage_sink["total_tokens"] == 45
        assert usage_sink["calls"] == 1
        assert len(provider.calls) == 1

    async def test_legacy_provider_never_receives_usage_sink(self):
        """
        A provider implementing only the plain generate_with_tools (no
        _tracked variant — the un-migrated/legacy shape) must never be
        passed usage_sink at all, since un-migrated implementations splat
        **kwargs straight into the provider SDK and an unrecognized
        usage_sink kwarg would 400 the request.
        """
        provider = _FakeProvider([
            ToolCallingResult(
                text="answer", tool_calls=None,
                assistant_message={"role": "assistant", "content": "answer"},
                finish_reason="stop",
            )
        ])
        manager = _FakeMCPManager()
        usage_sink: dict = {}

        await run_tool_calling_loop(
            provider, manager, _initial_messages("x"), _TOOLS, max_iterations=5,
            usage_sink=usage_sink,
        )

        assert usage_sink == {}
        assert len(provider.calls) == 1
