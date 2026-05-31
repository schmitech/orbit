#!/usr/bin/env python3
"""
Unit tests for MCPAgentStep's tool-calling loop
(server/inference/pipeline/steps/mcp_agent.py).

The provider, MCP manager, and initial-message construction are injected via a
thin subclass so the loop orchestration can be tested in isolation — no real
inference provider, MCP server, or service container is needed.

In particular these cover the exhaustion path: when the model keeps requesting
tools past max_iterations, the final synthesis call must be made with NO tools
(so the model is forced to return text) and must never return an empty string.
"""

import os
import sys
import types

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, server_dir)

# Pre-register the top-level 'inference' package pointing at server/inference.
# Other test modules / dependencies can shadow it with a namespace package that
# lacks the 'pipeline' submodule, so we pin it here (mirrors test_prompt_builder).
if 'inference' not in sys.modules:
    _pkg = types.ModuleType('inference')
    _pkg.__path__ = [os.path.join(server_dir, 'inference')]
    _pkg.__package__ = 'inference'
    sys.modules['inference'] = _pkg

from ai_services.services import ToolCallingResult
from inference.pipeline.base import ProcessingContext
from inference.pipeline.steps.mcp_agent import MCPAgentStep


class _FakeContainer:
    """Minimal container: no adapter_manager, so the allowlist resolves to None."""

    def has(self, name):
        return False

    def get(self, name):
        return None

    def get_or_none(self, name):
        return None


class _FakeProvider:
    """Returns queued ToolCallingResults and records every call's tool list."""

    def __init__(self, results):
        self._results = list(results)
        self.calls = []  # list of (messages_len, tools_len)

    async def generate_with_tools(self, messages, tools, **kwargs):
        self.calls.append((len(messages), len(tools)))
        if self._results:
            return self._results.pop(0)
        # Default: a plain text answer with no tool calls.
        return ToolCallingResult(
            text="default-final",
            tool_calls=None,
            assistant_message={"role": "assistant", "content": "default-final"},
            finish_reason="stop",
        )


class _FakeMCPManager:
    def __init__(self, tools, max_iterations=3, tool_output="TOOL_OUTPUT"):
        self._tools = tools
        self._max = max_iterations
        self._tool_output = tool_output
        self.called_with = []

    @property
    def max_tool_iterations(self):
        return self._max

    async def get_all_tools(self, allowed_servers=None):
        return self._tools

    async def call_tool(self, name, arguments):
        self.called_with.append((name, arguments))
        return self._tool_output


def _make_step(provider, manager):
    class _Step(MCPAgentStep):
        async def _resolve_provider(self, context):
            return provider

        def _get_mcp_manager(self):
            return manager

        async def _build_initial_messages(self, context):
            return [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": context.message},
            ]

    return _Step(_FakeContainer())


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


class TestMCPAgentLoop:
    async def test_no_tool_calls_returns_text_immediately(self):
        provider = _FakeProvider([
            ToolCallingResult(
                text="just an answer",
                tool_calls=None,
                assistant_message={"role": "assistant", "content": "just an answer"},
                finish_reason="stop",
            )
        ])
        manager = _FakeMCPManager(_TOOLS)
        step = _make_step(provider, manager)
        ctx = ProcessingContext(message="hi", adapter_name="mcp-agent-chat")

        text, sources = await step._run_agent_loop(ctx)

        assert text == "just an answer"
        assert sources == []
        assert manager.called_with == []  # no tool executed
        assert len(provider.calls) == 1

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
        manager = _FakeMCPManager(_TOOLS, tool_output="file-contents")
        step = _make_step(provider, manager)
        ctx = ProcessingContext(message="read it", adapter_name="mcp-agent-chat")

        text, sources = await step._run_agent_loop(ctx)

        assert text == "here is the file"
        assert manager.called_with == [("filesystem__read_file", {"path": "/tmp/x"})]
        assert len(sources) == 1
        src = sources[0]
        assert src["type"] == "mcp_tool_call"
        assert src["tool"] == "filesystem__read_file"
        assert src["result_preview"] == "file-contents"

    async def test_exhaustion_forces_final_call_without_tools(self):
        # Model requests tools on every iteration; after max_iterations the step
        # must make ONE more call with an empty tools list to force a text answer.
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
        manager = _FakeMCPManager(_TOOLS, max_iterations=3)
        step = _make_step(provider, manager)
        ctx = ProcessingContext(message="loop forever", adapter_name="mcp-agent-chat")

        text, sources = await step._run_agent_loop(ctx)

        assert text == "synthesized answer"
        # 3 loop iterations + 1 final synthesis call
        assert len(provider.calls) == 4
        # The final call must be made WITH NO TOOLS (this is the bug-#1 fix).
        assert provider.calls[-1][1] == 0
        # All 3 loop iterations executed a tool.
        assert len(manager.called_with) == 3

    async def test_exhaustion_with_empty_final_text_returns_fallback(self):
        # Even the no-tools synthesis can come back empty; we must not surface "".
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
        manager = _FakeMCPManager(_TOOLS, max_iterations=2)
        step = _make_step(provider, manager)
        ctx = ProcessingContext(message="x", adapter_name="mcp-agent-chat")

        text, sources = await step._run_agent_loop(ctx)

        assert text  # non-empty fallback message
        assert "could not" in text.lower() or "unable" in text.lower()
