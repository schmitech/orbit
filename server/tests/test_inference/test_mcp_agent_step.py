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

import asyncio
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


class _FakeTrackedProvider(_FakeProvider):
    """Records the cache_prefix_len passed to generate_with_tools_tracked."""

    def __init__(self, results):
        super().__init__(results)
        self.received_cache_prefix_lens = []

    async def generate_with_tools_tracked(self, messages, tools, usage_sink=None, cache_prefix_len=None, **kwargs):
        self.received_cache_prefix_lens.append(cache_prefix_len)
        return await self.generate_with_tools(messages, tools, **kwargs)


class _FakeMCPManager:
    def __init__(self, tools, max_iterations=3, tool_output="TOOL_OUTPUT"):
        self._tools = tools
        self._max = max_iterations
        self._tool_output = tool_output
        self.called_with = []

    def max_tool_iterations_for(self, server_names):
        return self._max

    @staticmethod
    def servers_in_tools(tools):
        return {
            t["function"]["name"].split("__", 1)[0]
            for t in tools
            if "__" in t.get("function", {}).get("name", "")
        }

    async def get_all_tools(self, allowed_servers=None, opportunistic_only=False):
        return self._tools

    async def call_tool(self, name, arguments):
        self.called_with.append((name, arguments))
        return self._tool_output


class _FakeEmptyToolSkillRegistry:
    """No skills configured — matches production behavior with an empty/
    missing config/skills directory, without touching the real filesystem."""

    def matched_for(self, tool_names):
        return []


def _make_step(provider, manager):
    class _Step(MCPAgentStep):
        async def _resolve_provider(self, context):
            return provider

        def _get_mcp_manager(self):
            return manager

        def _get_tool_skill_registry(self):
            return _FakeEmptyToolSkillRegistry()

        async def _build_initial_messages(self, context, surfaced_skills=None):
            return [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": context.message},
            ], None

    return _Step(_FakeContainer())


def _make_step_with_cache_prefix_len(provider, manager, cache_prefix_len):
    class _Step(MCPAgentStep):
        async def _resolve_provider(self, context):
            return provider

        def _get_mcp_manager(self):
            return manager

        def _get_tool_skill_registry(self):
            return _FakeEmptyToolSkillRegistry()

        async def _build_initial_messages(self, context, surfaced_skills=None):
            return [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": context.message},
            ], cache_prefix_len

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

    async def test_cache_prefix_len_from_initial_messages_reaches_the_loop(self):
        """
        Regression: _build_initial_messages computed the system message via
        build_system_message_content() (losing the prefix/tail split) and
        _run_agent_loop never forwarded any breakpoint to run_tool_calling_loop —
        so the explicit mcp-agent skill's Anthropic calls never got a
        cache_control breakpoint either, same bug as the inline opportunistic
        path in llm_inference.py.
        """
        provider = _FakeTrackedProvider([
            ToolCallingResult(
                text="just an answer",
                tool_calls=None,
                assistant_message={"role": "assistant", "content": "just an answer"},
                finish_reason="stop",
            )
        ])
        manager = _FakeMCPManager(_TOOLS)
        step = _make_step_with_cache_prefix_len(provider, manager, cache_prefix_len=42)
        ctx = ProcessingContext(message="hi", adapter_name="mcp-agent-chat")

        await step._run_agent_loop(ctx)

        assert provider.received_cache_prefix_lens == [42]

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


class TestMCPAgentCancellation:
    async def test_precancelled_does_no_work(self):
        # A Stop that arrives before the loop starts must skip all model/tool calls.
        provider = _FakeProvider([])
        manager = _FakeMCPManager(_TOOLS)
        step = _make_step(provider, manager)
        ev = asyncio.Event()
        ev.set()
        ctx = ProcessingContext(message="x", adapter_name="mcp-agent-chat", cancel_event=ev)

        text, sources = await step._run_agent_loop(ctx)

        assert text == ""
        assert provider.calls == []       # never called the model
        assert manager.called_with == []  # never executed a tool

    async def test_cancel_during_tool_call_halts_loop(self):
        # The tool call itself trips the cancel; the raced await returns the
        # cancelled sentinel, so the loop bails without a second model call.
        ev = asyncio.Event()

        class _CancelOnToolManager(_FakeMCPManager):
            async def call_tool(self, name, arguments):
                ev.set()
                return await super().call_tool(name, arguments)

        provider = _FakeProvider([_tool_call_result(), _tool_call_result()])
        manager = _CancelOnToolManager(_TOOLS, max_iterations=5)
        step = _make_step(provider, manager)
        ctx = ProcessingContext(message="x", adapter_name="mcp-agent-chat", cancel_event=ev)

        await step._run_agent_loop(ctx)

        # Only the first model call ran; the loop did not start a second iteration.
        assert len(provider.calls) == 1

    async def test_cancel_interrupts_slow_tool_call_midflight(self):
        # A tool that would block for 30s must be torn down the instant Stop is
        # signalled — proving cancellation interrupts mid-call, not just between
        # steps. Without mid-call cancellation this test would hit the timeout.
        ev = asyncio.Event()
        started = asyncio.Event()

        class _SlowManager(_FakeMCPManager):
            async def call_tool(self, name, arguments):
                started.set()
                await asyncio.sleep(30)  # would hang the loop without mid-call cancel
                return "never reached"

        provider = _FakeProvider([_tool_call_result()])
        manager = _SlowManager(_TOOLS, max_iterations=5)
        step = _make_step(provider, manager)
        ctx = ProcessingContext(message="x", adapter_name="mcp-agent-chat", cancel_event=ev)

        async def _stop_once_tool_starts():
            await started.wait()
            ev.set()

        loop_task = asyncio.ensure_future(step._run_agent_loop(ctx))
        await asyncio.wait_for(asyncio.gather(loop_task, _stop_once_tool_starts()), timeout=5)

        text, sources = loop_task.result()
        assert len(provider.calls) == 1
        assert sources == []  # the interrupted tool call was not recorded


class _FakeSkill:
    """Minimal stand-in for services.tool_skill_service.ToolSkill."""

    def __init__(self, name, description, body="Some procedural guidance.", version="1.0",
                 mcp_tools=None):
        self.name = name
        self.description = description
        self.body = body
        self.version = version
        # Only consulted by Level 3 JIT (build_dispatch), never by the fake
        # registry's matched_for above — defaults to "binds nothing" so
        # existing Phase 1 tests (which never call a real bound tool) are
        # unaffected by this field's addition.
        self._mcp_tools = mcp_tools or []

    def matches(self, tool_name):
        return tool_name in self._mcp_tools


class _FakeToolSkillRegistry:
    """Records the tool names it was asked to match against, and always
    returns the (pre-sorted) skills it was constructed with — the surfaced
    set truncation is MCPAgentStep's job, not the registry's, so a fake here
    only needs to stand in for `matched_for`."""

    def __init__(self, skills):
        self._skills = list(skills)
        self.received_tool_names = None

    def matched_for(self, tool_names):
        self.received_tool_names = list(tool_names)
        return list(self._skills)


class _FakeToolsCapturingProvider:
    """Like _FakeProvider, but also records the raw `tools` list passed on
    every call, so a test can inspect the synthetic loader tool's schema."""

    def __init__(self, results):
        self._results = list(results)
        self.tools_seen = []

    async def generate_with_tools(self, messages, tools, **kwargs):
        self.tools_seen.append(tools)
        if self._results:
            return self._results.pop(0)
        return ToolCallingResult(
            text="default-final", tool_calls=None,
            assistant_message={"role": "assistant", "content": "default-final"},
            finish_reason="stop",
        )


def _make_step_with_registry(provider, manager, registry):
    """Uses the REAL _build_initial_messages (unlike _make_step) so catalog
    injection and cache_prefix_len interaction are exercised end to end."""
    class _Step(MCPAgentStep):
        async def _resolve_provider(self, context):
            return provider

        def _get_mcp_manager(self):
            return manager

        def _get_tool_skill_registry(self):
            return registry

    return _Step(_FakeContainer())


class TestMCPAgentToolSkills:
    """
    Phase 1 of docs/roadmap/mcp-tool-skills.md: the synthetic
    orbit__load_tool_skill loader, the Level 1 catalog, and dispatcher
    authorization/idempotence, exercised through MCPAgentStep end to end.
    """

    async def test_catalog_and_loader_tool_appended_when_a_skill_matches(self):
        skill = _FakeSkill(name="crm-pipeline-playbook", description="How to use the CRM tools.")
        registry = _FakeToolSkillRegistry([skill])
        provider = _FakeToolsCapturingProvider([
            _tool_call_result(name="orbit__load_tool_skill", args={"name": "crm-pipeline-playbook"}),
            ToolCallingResult(
                text="final", tool_calls=None,
                assistant_message={"role": "assistant", "content": "final"},
                finish_reason="stop",
            ),
        ])
        manager = _FakeMCPManager(_TOOLS)
        step = _make_step_with_registry(provider, manager, registry)
        ctx = ProcessingContext(message="hi", adapter_name="mcp-agent-chat")

        text, sources = await step._run_agent_loop(ctx)

        assert text == "final"
        # The matched-set query is built from the (post-selector) MCP tool list.
        assert registry.received_tool_names == ["filesystem__read_file"]

        first_call_tools = provider.tools_seen[0]
        assert len(first_call_tools) == 2  # the real tool + the synthetic loader
        loader = next(t for t in first_call_tools if t["function"]["name"] == "orbit__load_tool_skill")
        assert loader["function"]["parameters"]["properties"]["name"]["enum"] == ["crm-pipeline-playbook"]

        assert sources == [{
            "type": "tool_skill_load",
            "skill": "crm-pipeline-playbook",
            "version": "1.0",
        }]

    async def test_no_synthetic_tool_when_nothing_matches(self):
        registry = _FakeToolSkillRegistry([])
        provider = _FakeToolsCapturingProvider([
            ToolCallingResult(
                text="final", tool_calls=None,
                assistant_message={"role": "assistant", "content": "final"},
                finish_reason="stop",
            ),
        ])
        manager = _FakeMCPManager(_TOOLS)
        step = _make_step_with_registry(provider, manager, registry)
        ctx = ProcessingContext(message="hi", adapter_name="mcp-agent-chat")

        await step._run_agent_loop(ctx)

        assert len(provider.tools_seen[0]) == 1  # just the real tool, no loader

    async def test_real_mcp_tool_named_like_the_loader_is_never_shadowed(self):
        """A real MCP tool namespaced exactly 'orbit__load_tool_skill' (e.g. an
        MCP server literally named 'orbit') must stay reachable and unique in
        the tool list — tool skills are disabled for the whole turn rather
        than risk a duplicate schema or hijacking the real tool's calls."""
        colliding_tools = [
            {"type": "function", "function": {"name": "orbit__load_tool_skill", "parameters": {}}}
        ]
        skill = _FakeSkill(name="crm-pipeline-playbook", description="d")
        registry = _FakeToolSkillRegistry([skill])  # would otherwise "match" every turn
        provider = _FakeToolsCapturingProvider([
            _tool_call_result(name="orbit__load_tool_skill", args={"path": "/tmp/x"}),
            ToolCallingResult(
                text="final", tool_calls=None,
                assistant_message={"role": "assistant", "content": "final"},
                finish_reason="stop",
            ),
        ])
        manager = _FakeMCPManager(colliding_tools, tool_output="real-tool-output")
        step = _make_step_with_registry(provider, manager, registry)
        ctx = ProcessingContext(message="hi", adapter_name="mcp-agent-chat")

        text, sources = await step._run_agent_loop(ctx)

        assert text == "final"
        # Exactly one schema for the name — no duplicate synthetic entry appended.
        assert len(provider.tools_seen[0]) == 1
        assert provider.tools_seen[0][0]["function"]["name"] == "orbit__load_tool_skill"
        # The call reached the REAL MCP tool, not the local skill loader.
        assert manager.called_with == [("orbit__load_tool_skill", {"path": "/tmp/x"})]
        assert sources == [{
            "type": "mcp_tool_call",
            "tool": "orbit__load_tool_skill",
            "arguments": {"path": "/tmp/x"},
            "result_preview": "real-tool-output",
        }]

    async def test_repeated_load_is_idempotent_and_sources_only_once(self):
        skill = _FakeSkill(name="crm-pipeline-playbook", description="d")
        registry = _FakeToolSkillRegistry([skill])
        provider = _FakeProvider([
            _tool_call_result(name="orbit__load_tool_skill", args={"name": "crm-pipeline-playbook"}),
            _tool_call_result(name="orbit__load_tool_skill", args={"name": "crm-pipeline-playbook"}),
            ToolCallingResult(
                text="final", tool_calls=None,
                assistant_message={"role": "assistant", "content": "final"},
                finish_reason="stop",
            ),
        ])
        manager = _FakeMCPManager(_TOOLS, max_iterations=5)
        step = _make_step_with_registry(provider, manager, registry)
        ctx = ProcessingContext(message="hi", adapter_name="mcp-agent-chat")

        text, sources = await step._run_agent_loop(ctx)

        assert text == "final"
        skill_sources = [s for s in sources if s["type"] == "tool_skill_load"]
        assert len(skill_sources) == 1

    async def test_dispatcher_rejects_a_name_outside_the_surfaced_set(self):
        """A guessed/hallucinated skill name (or one truncated out of the
        surfaced set) must be rejected server-side, not resolved against a
        wider set — docs/roadmap/mcp-tool-skills.md §2.2."""
        skill = _FakeSkill(name="crm-pipeline-playbook", description="d")
        registry = _FakeToolSkillRegistry([skill])
        provider = _FakeProvider([
            _tool_call_result(name="orbit__load_tool_skill", args={"name": "totally-made-up"}),
            ToolCallingResult(
                text="final", tool_calls=None,
                assistant_message={"role": "assistant", "content": "final"},
                finish_reason="stop",
            ),
        ])
        manager = _FakeMCPManager(_TOOLS)
        step = _make_step_with_registry(provider, manager, registry)
        ctx = ProcessingContext(message="hi", adapter_name="mcp-agent-chat")

        text, sources = await step._run_agent_loop(ctx)

        assert text == "final"
        assert sources == []  # no tool_skill_load entry for a rejected/unknown name

    async def test_surfaced_set_cap_truncates_the_loader_enum_and_catalog(self):
        many_skills = [
            _FakeSkill(name=f"skill-{i:02d}", description=f"skill number {i}")
            for i in range(15)
        ]
        registry = _FakeToolSkillRegistry(many_skills)
        provider = _FakeToolsCapturingProvider([
            ToolCallingResult(
                text="final", tool_calls=None,
                assistant_message={"role": "assistant", "content": "final"},
                finish_reason="stop",
            ),
        ])
        manager = _FakeMCPManager(_TOOLS)
        step = _make_step_with_registry(provider, manager, registry)
        ctx = ProcessingContext(message="hi", adapter_name="mcp-agent-chat")

        await step._run_agent_loop(ctx)

        loader = next(t for t in provider.tools_seen[0] if t["function"]["name"] == "orbit__load_tool_skill")
        assert len(loader["function"]["parameters"]["properties"]["name"]["enum"]) == 10

    async def test_max_iterations_computed_before_synthetic_tool_is_appended(self):
        """servers_in_tools()/max_tool_iterations_for() must see only the real
        MCP tool list — a synthetic orbit__* entry has no server-level
        max_tool_iterations override to resolve against."""
        skill = _FakeSkill(name="crm-pipeline-playbook", description="d")
        registry = _FakeToolSkillRegistry([skill])

        class _RecordingManager(_FakeMCPManager):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self.iteration_query_tools = None

            def max_tool_iterations_for(self, server_names):
                self.iteration_query_tools = server_names
                return self._max

        provider = _FakeProvider([
            ToolCallingResult(
                text="final", tool_calls=None,
                assistant_message={"role": "assistant", "content": "final"},
                finish_reason="stop",
            ),
        ])
        manager = _RecordingManager(_TOOLS)
        step = _make_step_with_registry(provider, manager, registry)
        ctx = ProcessingContext(message="hi", adapter_name="mcp-agent-chat")

        await step._run_agent_loop(ctx)

        # servers_in_tools(tools) is derived only from filesystem__read_file,
        # never from orbit__load_tool_skill (which would parse as server "orbit").
        assert manager.iteration_query_tools == {"filesystem"}


class _FakeAdapterManagerContainer:
    """Container with an adapter_manager exposing a fixed capabilities dict —
    used to exercise the capabilities.tool_skills allowlist (§2.7)."""

    def __init__(self, capabilities: dict):
        self._capabilities = capabilities

    def has(self, name):
        return name == "adapter_manager"

    def get(self, name):
        if name == "adapter_manager":
            return self
        return None

    def get_or_none(self, name):
        return None

    def get_adapter_config(self, adapter_name):
        return {"capabilities": self._capabilities}


def _make_step_with_registry_and_container(provider, manager, registry, container):
    class _Step(MCPAgentStep):
        async def _resolve_provider(self, context):
            return provider

        def _get_mcp_manager(self):
            return manager

        def _get_tool_skill_registry(self):
            return registry

    return _Step(container)


class TestMCPAgentPhase2JustInTimeInjection:
    """
    Phase 2 of docs/roadmap/mcp-tool-skills.md: Level 3 auto-injection after
    the first invocation of a bound tool, the shared Level 2/3 per-turn
    budget, and the capabilities.tool_skills allowlist.
    """

    async def test_jit_injects_after_first_call_to_a_bound_tool(self):
        """A skill bound to filesystem__read_file is delivered as trusted
        context on that call's own result — without the model ever calling
        orbit__load_tool_skill."""
        skill = _FakeSkill(name="fs-playbook", description="d", mcp_tools=["filesystem__read_file"])
        registry = _FakeToolSkillRegistry([skill])
        provider = _FakeProvider([
            _tool_call_result(name="filesystem__read_file"),
            ToolCallingResult(
                text="final", tool_calls=None,
                assistant_message={"role": "assistant", "content": "final"},
                finish_reason="stop",
            ),
        ])
        manager = _FakeMCPManager(_TOOLS, tool_output="file-contents")
        step = _make_step_with_registry(provider, manager, registry)
        ctx = ProcessingContext(message="hi", adapter_name="mcp-agent-chat")

        text, sources = await step._run_agent_loop(ctx)

        assert text == "final"
        assert {"type": "mcp_tool_call", "tool": "filesystem__read_file",
                "arguments": {"path": "/tmp/x"}, "result_preview": "file-contents"} in sources
        assert {"type": "tool_skill_load", "skill": "fs-playbook", "version": "1.0"} in sources

    async def test_jit_fires_once_per_skill_per_turn(self):
        skill = _FakeSkill(name="fs-playbook", description="d", mcp_tools=["filesystem__read_file"])
        registry = _FakeToolSkillRegistry([skill])
        provider = _FakeProvider([
            _tool_call_result(name="filesystem__read_file"),
            _tool_call_result(name="filesystem__read_file"),
            ToolCallingResult(
                text="final", tool_calls=None,
                assistant_message={"role": "assistant", "content": "final"},
                finish_reason="stop",
            ),
        ])
        manager = _FakeMCPManager(_TOOLS, max_iterations=5)
        step = _make_step_with_registry(provider, manager, registry)
        ctx = ProcessingContext(message="hi", adapter_name="mcp-agent-chat")

        text, sources = await step._run_agent_loop(ctx)

        skill_loads = [s for s in sources if s["type"] == "tool_skill_load"]
        assert len(skill_loads) == 1

    async def test_level2_and_level3_share_one_idempotence_state(self):
        """A skill loaded via Level 2 (explicit orbit__load_tool_skill call)
        must not also be JIT-injected on a later call to its bound tool in
        the same turn — one shared per-turn budget/idempotence state."""
        skill = _FakeSkill(name="fs-playbook", description="d", mcp_tools=["filesystem__read_file"])
        registry = _FakeToolSkillRegistry([skill])
        provider = _FakeProvider([
            _tool_call_result(name="orbit__load_tool_skill", args={"name": "fs-playbook"}),
            _tool_call_result(name="filesystem__read_file"),
            ToolCallingResult(
                text="final", tool_calls=None,
                assistant_message={"role": "assistant", "content": "final"},
                finish_reason="stop",
            ),
        ])
        manager = _FakeMCPManager(_TOOLS, max_iterations=5)
        step = _make_step_with_registry(provider, manager, registry)
        ctx = ProcessingContext(message="hi", adapter_name="mcp-agent-chat")

        text, sources = await step._run_agent_loop(ctx)

        skill_loads = [s for s in sources if s["type"] == "tool_skill_load"]
        assert len(skill_loads) == 1

    async def test_sibling_tool_call_in_same_turn_unaffected(self):
        """Two tool calls requested in one assistant turn: only the one bound
        to the skill gets the trusted context attached; the unrelated
        sibling call's own result carries none."""
        skill = _FakeSkill(name="fs-playbook", description="d", mcp_tools=["filesystem__read_file"])
        registry = _FakeToolSkillRegistry([skill])
        sibling_result = ToolCallingResult(
            text=None,
            tool_calls=[
                {"id": "c1", "name": "filesystem__read_file", "arguments": {"path": "/tmp/x"}},
                {"id": "c2", "name": "web__search", "arguments": {"q": "x"}},
            ],
            assistant_message={"role": "assistant", "content": None, "tool_calls": []},
            finish_reason="tool_calls",
        )
        provider = _FakeProvider([
            sibling_result,
            ToolCallingResult(
                text="final", tool_calls=None,
                assistant_message={"role": "assistant", "content": "final"},
                finish_reason="stop",
            ),
        ])
        tools = _TOOLS + [{"type": "function", "function": {"name": "web__search", "parameters": {}}}]
        manager = _FakeMCPManager(tools)
        step = _make_step_with_registry(provider, manager, registry)
        ctx = ProcessingContext(message="hi", adapter_name="mcp-agent-chat")

        text, sources = await step._run_agent_loop(ctx)

        skill_loads = [s for s in sources if s["type"] == "tool_skill_load"]
        assert len(skill_loads) == 1
        assert skill_loads[0]["skill"] == "fs-playbook"

    async def test_turn_with_no_bound_tool_call_injects_nothing(self):
        skill = _FakeSkill(name="other-playbook", description="d", mcp_tools=["other__tool"])
        registry = _FakeToolSkillRegistry([skill])
        provider = _FakeProvider([
            _tool_call_result(name="filesystem__read_file"),
            ToolCallingResult(
                text="final", tool_calls=None,
                assistant_message={"role": "assistant", "content": "final"},
                finish_reason="stop",
            ),
        ])
        manager = _FakeMCPManager(_TOOLS)
        step = _make_step_with_registry(provider, manager, registry)
        ctx = ProcessingContext(message="hi", adapter_name="mcp-agent-chat")

        text, sources = await step._run_agent_loop(ctx)

        assert [s for s in sources if s["type"] == "tool_skill_load"] == []

    async def test_budget_drops_lowest_priority_skill_and_logs_it(self, caplog):
        """Four skills all bound to the same tool exceeds the 3-skill budget;
        the registry already returns them sorted (priority desc, name), so the
        4th (lowest-priority) one is dropped and logged, not silently lost."""
        skills = [
            _FakeSkill(name=f"playbook-{i}", description="d", mcp_tools=["filesystem__read_file"])
            for i in range(4)
        ]
        registry = _FakeToolSkillRegistry(skills)
        provider = _FakeProvider([
            _tool_call_result(name="filesystem__read_file"),
            ToolCallingResult(
                text="final", tool_calls=None,
                assistant_message={"role": "assistant", "content": "final"},
                finish_reason="stop",
            ),
        ])
        manager = _FakeMCPManager(_TOOLS)
        step = _make_step_with_registry(provider, manager, registry)
        ctx = ProcessingContext(message="hi", adapter_name="mcp-agent-chat")

        with caplog.at_level("INFO"):
            text, sources = await step._run_agent_loop(ctx)

        skill_loads = {s["skill"] for s in sources if s["type"] == "tool_skill_load"}
        assert skill_loads == {"playbook-0", "playbook-1", "playbook-2"}
        assert any("playbook-3" in record.message and "budget" in record.message for record in caplog.records)

    async def test_budget_preserves_priority_regardless_of_call_order(self):
        """
        Regression (P2 review): a model calling three low-priority bound
        tools before a high-priority one must still get the high-priority
        skill delivered — admission is decided from the whole turn's
        candidate set up front, not first-come-first-served per call.
        _FakeToolSkillRegistry.matched_for returns skills in the order
        given here, mirroring the real registry's priority-desc/name sort,
        so "high-priority" is first even though its bound tool is called last.
        """
        high = _FakeSkill(name="high-priority", description="d", mcp_tools=["tool-h"])
        low0 = _FakeSkill(name="low-0", description="d", mcp_tools=["tool-l0"])
        low1 = _FakeSkill(name="low-1", description="d", mcp_tools=["tool-l1"])
        low2 = _FakeSkill(name="low-2", description="d", mcp_tools=["tool-l2"])
        registry = _FakeToolSkillRegistry([high, low0, low1, low2])
        provider = _FakeProvider([
            _tool_call_result(name="tool-l0"),
            _tool_call_result(name="tool-l1"),
            _tool_call_result(name="tool-l2"),
            _tool_call_result(name="tool-h"),
            ToolCallingResult(
                text="final", tool_calls=None,
                assistant_message={"role": "assistant", "content": "final"},
                finish_reason="stop",
            ),
        ])
        tools = [
            {"type": "function", "function": {"name": n, "parameters": {}}}
            for n in ("tool-l0", "tool-l1", "tool-l2", "tool-h")
        ]
        manager = _FakeMCPManager(tools, max_iterations=6)
        step = _make_step_with_registry(provider, manager, registry)
        ctx = ProcessingContext(message="hi", adapter_name="mcp-agent-chat")

        text, sources = await step._run_agent_loop(ctx)

        skill_loads = {s["skill"] for s in sources if s["type"] == "tool_skill_load"}
        # The 3-skill budget admits the 3 highest-priority candidates
        # (high-priority, low-0, low-1) regardless of call order — low-2 is
        # the one dropped, not high-priority.
        assert skill_loads == {"high-priority", "low-0", "low-1"}

    async def test_tool_skills_allowlist_excludes_a_matched_skill(self):
        """capabilities.tool_skills, when set, restricts both the surfaced
        set and Level 3's full matched set — an omitted skill never
        surfaces and is never JIT-injected either (§2.7)."""
        allowed_skill = _FakeSkill(name="allowed", description="d", mcp_tools=["filesystem__read_file"])
        excluded_skill = _FakeSkill(name="excluded", description="d", mcp_tools=["filesystem__read_file"])
        registry = _FakeToolSkillRegistry([allowed_skill, excluded_skill])
        provider = _FakeProvider([
            _tool_call_result(name="filesystem__read_file"),
            ToolCallingResult(
                text="final", tool_calls=None,
                assistant_message={"role": "assistant", "content": "final"},
                finish_reason="stop",
            ),
        ])
        manager = _FakeMCPManager(_TOOLS)
        container = _FakeAdapterManagerContainer({"tool_skills": ["allowed"]})
        step = _make_step_with_registry_and_container(provider, manager, registry, container)
        ctx = ProcessingContext(message="hi", adapter_name="mcp-agent-chat")

        text, sources = await step._run_agent_loop(ctx)

        skill_loads = {s["skill"] for s in sources if s["type"] == "tool_skill_load"}
        assert skill_loads == {"allowed"}


class TestMCPAgentBuildInitialMessagesWithSkills:
    """Direct coverage of the catalog-injection contract in
    _build_initial_messages, independent of the rest of the loop."""

    async def test_catalog_is_appended_after_cache_prefix_len(self):
        step = MCPAgentStep(_FakeContainer())
        ctx = ProcessingContext(message="hi", adapter_name="mcp-agent-chat")
        skill = _FakeSkill(name="crm-pipeline-playbook", description="How to use the CRM tools.")

        messages, cache_prefix_len = await step._build_initial_messages(ctx, [skill])

        system_content = messages[0]["content"]
        assert cache_prefix_len is not None
        prefix = system_content[:cache_prefix_len]
        assert "crm-pipeline-playbook" not in prefix
        assert "crm-pipeline-playbook" in system_content
        assert "orbit__load_tool_skill" in system_content

    async def test_no_skills_leaves_system_message_unchanged(self):
        step = MCPAgentStep(_FakeContainer())
        ctx = ProcessingContext(message="hi", adapter_name="mcp-agent-chat")

        messages_without_arg, prefix_without = await step._build_initial_messages(ctx)
        messages_empty_list, prefix_empty = await step._build_initial_messages(ctx, [])

        assert messages_without_arg[0]["content"] == messages_empty_list[0]["content"]
        assert prefix_without == prefix_empty
        assert "orbit__load_tool_skill" not in messages_without_arg[0]["content"]
