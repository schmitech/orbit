#!/usr/bin/env python3
"""
Unit tests for LLMInferenceStep's opportunistic (inline) MCP tool-calling
path (server/inference/pipeline/steps/llm_inference.py).

Covers: default-off behavior, the happy path where the tool loop runs
inline, and the fallback cases (provider lacks generate_with_tools, no
tools discovered, mcp_client not enabled/opportunistic-gated) — plus that
RAG/file context (formatted_context) and MCP tools coexist in the same
system message.
"""

import os
import sys

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, server_dir)

if 'inference' not in sys.modules:
    import types
    _pkg = types.ModuleType('inference')
    _pkg.__path__ = [os.path.join(server_dir, 'inference')]
    _pkg.__package__ = 'inference'
    sys.modules['inference'] = _pkg

from ai_services.services import ToolCallingResult
from inference.pipeline.base import ProcessingContext
from inference.pipeline.steps.llm_inference import LLMInferenceStep


class _FakeContainer:
    """Minimal container: no adapter_manager, so provider resolution falls
    back to the plain 'llm_provider' entry."""

    def __init__(self, llm_provider):
        self._llm_provider = llm_provider

    def has(self, name):
        return name == 'llm_provider'

    def get(self, name):
        if name == 'llm_provider':
            return self._llm_provider
        return None

    def get_or_none(self, name):
        return None


class _FakeProvider:
    def __init__(self, generate_with_tools_result=None, generate_with_tools_error=None,
                 generate_text="plain-generate-response"):
        self._gwt_result = generate_with_tools_result
        self._gwt_error = generate_with_tools_error
        self._generate_text = generate_text
        self.generate_calls = 0
        self.generate_with_tools_calls = 0

    async def generate(self, prompt, **kwargs):
        self.generate_calls += 1
        return self._generate_text

    async def generate_with_tools(self, messages, tools, **kwargs):
        self.generate_with_tools_calls += 1
        if self._gwt_error:
            raise self._gwt_error
        return self._gwt_result


class _FakeMCPManager:
    def __init__(self, tools, allow_opportunistic=True, tool_output="TOOL_OUTPUT", max_iterations=3):
        self._tools = tools
        self.allow_opportunistic = allow_opportunistic
        self._tool_output = tool_output
        self._max = max_iterations

    @property
    def max_tool_iterations(self):
        return self._max

    async def get_all_tools(self, allowed_servers=None):
        return self._tools

    async def call_tool(self, name, arguments):
        return self._tool_output


_TOOLS = [{"type": "function", "function": {"name": "filesystem__read_file", "parameters": {}}}]


def _final_result(text="tool-derived answer"):
    return ToolCallingResult(
        text=text, tool_calls=None,
        assistant_message={"role": "assistant", "content": text},
        finish_reason="stop",
    )


def _make_step(provider, mcp_manager):
    class _Step(LLMInferenceStep):
        def _get_mcp_manager(self):
            return mcp_manager

    return _Step(_FakeContainer(provider))


class TestOpportunisticMCPToolsDisabledByDefault:
    async def test_mcp_tools_unset_never_touches_mcp(self):
        provider = _FakeProvider()
        manager = _FakeMCPManager(_TOOLS)
        step = _make_step(provider, manager)
        ctx = ProcessingContext(message="hi", adapter_name="simple-chat")

        assert step._should_run_mcp_tools(ctx) is False

        result_ctx = await step.process(ctx)

        assert provider.generate_with_tools_calls == 0
        assert provider.generate_calls == 1
        assert result_ctx.response == "plain-generate-response"


class TestOpportunisticMCPToolsEnabled:
    async def test_runs_tool_loop_inline_and_sets_sources(self):
        provider = _FakeProvider(generate_with_tools_result=_final_result())
        manager = _FakeMCPManager(_TOOLS, tool_output="doc-contents")
        step = _make_step(provider, manager)
        ctx = ProcessingContext(
            message="what's in the docs?", adapter_name="simple-chat-with-files",
            mcp_tools=True, mcp_servers_allowlist=["filesystem"],
        )

        result_ctx = await step.process(ctx)

        assert provider.generate_calls == 0  # plain generate() never invoked
        assert provider.generate_with_tools_calls == 1
        assert result_ctx.response == "tool-derived answer"

    async def test_streaming_yields_final_text_and_sets_sources(self):
        provider = _FakeProvider(generate_with_tools_result=_final_result("streamed tool answer"))
        manager = _FakeMCPManager(_TOOLS)
        step = _make_step(provider, manager)
        ctx = ProcessingContext(message="x", adapter_name="simple-chat-with-files", mcp_tools=True)

        chunks = [c async for c in step.process_stream(ctx)]

        assert chunks == ["streamed tool answer"]
        assert ctx.response == "streamed tool answer"


class TestOpportunisticMCPToolsFallback:
    async def test_provider_lacks_tool_support_falls_back_to_generate(self):
        provider = _FakeProvider(generate_with_tools_error=NotImplementedError())
        manager = _FakeMCPManager(_TOOLS)
        step = _make_step(provider, manager)
        ctx = ProcessingContext(message="x", adapter_name="simple-chat-with-files", mcp_tools=True)

        result_ctx = await step.process(ctx)

        assert provider.generate_with_tools_calls == 1
        assert provider.generate_calls == 1
        assert result_ctx.response == "plain-generate-response"
        assert not result_ctx.has_error()

    async def test_fallback_warning_blames_runtime_provider_not_adapter_default(self, caplog):
        # Regression: when a request uses a runtime "model" override (e.g. a
        # provider without tool-calling support), the fallback warning must
        # name the provider that actually failed (runtime_provider), not the
        # adapter's static default inference_provider.
        provider = _FakeProvider(generate_with_tools_error=NotImplementedError())
        manager = _FakeMCPManager(_TOOLS)
        step = _make_step(provider, manager)
        ctx = ProcessingContext(
            message="x", adapter_name="simple-chat", mcp_tools=True,
            inference_provider="openai", runtime_provider="openrouter",
            runtime_model_name="nemotron-3-ultra",
        )

        with caplog.at_level("WARNING"):
            await step.process(ctx)

        assert any("openrouter" in record.message for record in caplog.records)
        assert not any("provider 'openai'" in record.message for record in caplog.records)

    async def test_no_tools_discovered_falls_back_to_generate(self):
        provider = _FakeProvider()
        manager = _FakeMCPManager(tools=[])
        step = _make_step(provider, manager)
        ctx = ProcessingContext(message="x", adapter_name="simple-chat-with-files", mcp_tools=True)

        result_ctx = await step.process(ctx)

        assert provider.generate_with_tools_calls == 0
        assert provider.generate_calls == 1
        assert result_ctx.response == "plain-generate-response"

    async def test_mcp_tools_true_but_allow_opportunistic_false(self):
        provider = _FakeProvider()
        manager = _FakeMCPManager(_TOOLS, allow_opportunistic=False)
        step = _make_step(provider, manager)
        ctx = ProcessingContext(message="x", adapter_name="simple-chat-with-files", mcp_tools=True)

        assert step._should_run_mcp_tools(ctx) is False

        result_ctx = await step.process(ctx)

        assert provider.generate_with_tools_calls == 0
        assert result_ctx.response == "plain-generate-response"

    async def test_mcp_client_not_configured(self):
        provider = _FakeProvider()
        step = _make_step(provider, mcp_manager=None)
        ctx = ProcessingContext(message="x", adapter_name="simple-chat-with-files", mcp_tools=True)

        assert step._should_run_mcp_tools(ctx) is False


class TestRagContextAndMcpToolsCoexist:
    async def test_formatted_context_included_in_tool_loop_system_message(self):
        provider = _FakeProvider(generate_with_tools_result=_final_result())
        manager = _FakeMCPManager(_TOOLS)
        step = _make_step(provider, manager)
        ctx = ProcessingContext(
            message="what does the file say?", adapter_name="simple-chat-with-files",
            mcp_tools=True, formatted_context="Uploaded doc: the sky is blue.",
        )

        await step.process(ctx)

        assert ctx.messages is not None
        system_message = ctx.messages[0]["content"]
        assert "the sky is blue" in system_message
        assert "UPLOADED FILE CONTENT" in system_message
