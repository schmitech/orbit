"""
MCP Agent Step

Executes a bounded multi-step tool-calling loop against configured MCP servers.
Runs only for adapters whose 'type' is 'mcp_agent', replacing LLMInferenceStep
for those adapters (the LLM step already guards against 'mcp_agent').

Architecture:
  1. Resolve the inference provider from the adapter config.
  2. Get the MCPClientManager and discover available tools.
  3. Build the initial messages array (system + history + user).
  4. Loop up to max_tool_iterations:
       - Call provider.generate_with_tools(messages, tools)
       - If tool_calls: execute each via MCPClientManager, append results, repeat
       - If no tool_calls: final answer found, break
  5. Store final response in context.response; tool invocations in context.sources.
"""

import logging
from typing import AsyncGenerator, List, Dict, Any, Optional, Sequence

from ..base import PipelineStep, ProcessingContext
from ..prompt_builder import PromptInstructionBuilder
from ..mcp_tool_loop import run_tool_calling_loop, ToolDispatchResult, TrustedContext
from ._utils import record_usage

logger = logging.getLogger(__name__)

# Reserved namespace for the synthetic tool-skill loader — see
# services/tool_skill_service.py and docs/roadmap/mcp-tool-skills.md §2.2.
_TOOL_SKILL_LOADER_NAME = "orbit__load_tool_skill"


def _get_adapter_type(container, adapter_name: str) -> Optional[str]:
    if not adapter_name or not container.has("adapter_manager"):
        return None
    try:
        mgr = container.get("adapter_manager")
        cfg = mgr.get_adapter_config(adapter_name)
        return cfg.get("type") if cfg else None
    except Exception:
        return None


def _get_mcp_servers_allowlist(container, adapter_name: str) -> Optional[List[str]]:
    """Return the mcp_servers allowlist from adapter capabilities, or None (= all)."""
    if not adapter_name or not container.has("adapter_manager"):
        return None
    try:
        mgr = container.get("adapter_manager")
        cfg = mgr.get_adapter_config(adapter_name)
        if cfg:
            return cfg.get("capabilities", {}).get("mcp_servers")
    except Exception:
        pass
    return None


def _tool_names(tools: Sequence[Dict[str, Any]]) -> List[str]:
    return [t.get("function", {}).get("name", "") for t in tools]


def _tool_skill_loader_schema(surfaced_skills: Sequence) -> Dict[str, Any]:
    """
    The synthetic ``orbit__load_tool_skill`` tool. Its ``name`` enum is built
    from exactly the turn's *surfaced set* (docs/roadmap/mcp-tool-skills.md
    §2.2) — never the full matched set, and never the whole registry. The
    enum is a UX aid only; the dispatcher independently re-checks the
    requested name against this same surfaced set server-side (§2.2).
    """
    return {
        "type": "function",
        "function": {
            "name": _TOOL_SKILL_LOADER_NAME,
            "description": "Read the full procedural playbook for using a set of tools.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "enum": [skill.name for skill in surfaced_skills],
                        "description": "The skill name to load, from the tool playbook catalog.",
                    },
                },
                "required": ["name"],
            },
        },
    }


def _tool_skill_catalog_text(surfaced_skills: Sequence) -> str:
    """Level 1 catalog block appended to the system message (§2.2) — one
    line per surfaced skill, cheap enough to send on every turn."""
    lines = "\n".join(f"- {skill.name}: {skill.description}" for skill in surfaced_skills)
    return (
        "Available tool playbooks (call "
        f"{_TOOL_SKILL_LOADER_NAME} to read one in full):\n{lines}"
    )


class MCPAgentStep(PipelineStep):
    """
    Agentic tool-calling loop over external MCP servers.

    Executes instead of LLMInferenceStep for 'mcp_agent' adapter types.
    """

    def should_execute(self, context: ProcessingContext) -> bool:
        if context.is_blocked:
            return False
        return _get_adapter_type(self.container, context.adapter_name) == "mcp_agent"

    def supports_streaming(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Non-streaming path
    # ------------------------------------------------------------------

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        try:
            final_text, sources = await self._run_agent_loop(context)
            context.response = final_text or ""
            context.sources = sources
        except Exception as exc:
            logger.exception("MCPAgentStep error")
            context.set_error(f"MCP agent failed: {exc}")
        return context

    # ------------------------------------------------------------------
    # Streaming path
    # ------------------------------------------------------------------

    async def process_stream(
        self, context: ProcessingContext
    ) -> AsyncGenerator[str, None]:
        try:
            final_text, sources = await self._run_agent_loop(context)
            context.response = final_text or ""
            context.sources = sources
            # Emit the final text as a single chunk followed by done
            yield final_text or ""
        except Exception as exc:
            logger.exception("MCPAgentStep streaming error")
            error_msg = f"MCP agent failed: {exc}"
            context.set_error(error_msg)
            yield error_msg

    # ------------------------------------------------------------------
    # Core agent loop
    # ------------------------------------------------------------------

    async def _run_agent_loop(self, context: ProcessingContext):
        """
        Execute the bounded tool-calling loop.

        Returns (final_text, sources_list).
        """
        provider = await self._resolve_provider(context)
        if provider is None:
            raise RuntimeError(
                "No inference provider available for MCP agent. "
                "Check the adapter's inference_provider configuration."
            )

        mcp_manager = self._get_mcp_manager()
        if mcp_manager is None:
            raise RuntimeError(
                "MCP client is not enabled. Set mcp_clients.enabled: true in config."
            )

        allowed_servers = _get_mcp_servers_allowlist(self.container, context.adapter_name)
        tools = await mcp_manager.get_all_tools(allowed_servers=allowed_servers)

        if not tools:
            raise RuntimeError(
                "No MCP tools available. "
                "Check mcp_clients configuration and server connectivity."
            )

        usage_sink: dict = {}
        tools = await self._select_relevant_tools(context, tools, usage_sink)

        # Computed from the real MCP tool list BEFORE the synthetic
        # orbit__load_tool_skill entry (if any) is appended below —
        # servers_in_tools() parses server names out of the <server>__<tool>
        # prefix, and a synthetic orbit__* entry has no corresponding
        # server-level max_tool_iterations override to resolve (see
        # docs/roadmap/mcp-tool-skills.md §2.5).
        max_iterations = mcp_manager.max_tool_iterations_for(
            mcp_manager.servers_in_tools(tools)
        )

        # Resolve the matched/surfaced skill sets against the *filtered* tool
        # list, before building the system message, so the Level 1 catalog
        # can be appended to it in the same step — after cache_prefix_len,
        # never inside it (docs/roadmap/mcp-tool-skills.md §2.4/§2.5).
        #
        # Guard against a namespace collision: an MCP server literally named
        # "orbit" exposing a "load_tool_skill" tool namespaces to exactly
        # _TOOL_SKILL_LOADER_NAME. Appending the synthetic schema on top would
        # duplicate that function name in the tool list, and unconditionally
        # intercepting it in the dispatcher would make the REAL tool
        # permanently unreachable — even on turns where no skill ever
        # matched. Tool skills are disabled entirely for this turn instead;
        # the real MCP tool always wins the name.
        real_tool_names = set(_tool_names(tools))
        loader_name_collides = _TOOL_SKILL_LOADER_NAME in real_tool_names
        if loader_name_collides:
            logger.warning(
                "An MCP tool named '%s' is already exposed this turn; tool skills "
                "are disabled for it so the real tool stays reachable.",
                _TOOL_SKILL_LOADER_NAME,
            )
            surfaced_skills = []
        else:
            registry = self._get_tool_skill_registry()
            surfaced_skills = registry.matched_for(_tool_names(tools))[:self._surfaced_set_cap()]

        messages, cache_prefix_len = await self._build_initial_messages(context, surfaced_skills)

        if surfaced_skills:
            tools = list(tools) + [_tool_skill_loader_schema(surfaced_skills)]

        dispatch = self._build_dispatch(mcp_manager, surfaced_skills)

        final_text, sources, _ = await run_tool_calling_loop(
            provider=provider,
            mcp_manager=mcp_manager,
            messages=messages,
            tools=tools,
            max_iterations=max_iterations,
            cancel_event=context.cancel_event,
            is_cancelled=context.is_cancelled,
            usage_sink=usage_sink,
            cache_prefix_len=cache_prefix_len,
            dispatch=dispatch,
        )
        provider_name = usage_sink.get("provider") or getattr(context, 'runtime_provider', None)
        model_name = usage_sink.get("model") or getattr(context, 'runtime_model_name', None)
        partial = bool(context.is_cancelled()) or not usage_sink.get("reported")
        record_usage(
            self.container, context, usage_sink, provider_name, model_name,
            extra={"partial": partial, "calls": usage_sink.get("calls", 0), "source": "mcp_agent"},
        )
        return final_text, sources

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _select_relevant_tools(self, context: ProcessingContext, tools: list, usage_sink: dict) -> list:
        """
        Relevance-filter the full MCP tool list down to what this turn
        actually needs (see services.mcp_tool_selector). Embedding cost is
        accumulated into the same usage_sink the tool-calling loop reports
        into, so it lands on this request's audit record. Falls back to the
        unfiltered list — this must never block a turn over a missing
        adapter_manager or embedding provider.
        """
        if not self.container.has('adapter_manager'):
            return tools
        from services.mcp_tool_selector import MCPToolSelector
        config = self.container.get_or_none('config') or {}
        adapter_manager = self.container.get('adapter_manager')
        selector = MCPToolSelector(config, adapter_manager)
        return await selector.select_tools(
            message=context.message,
            tools=tools,
            adapter_name=context.adapter_name,
            context_messages=context.context_messages,
            usage_sink=usage_sink,
        )

    async def _build_initial_messages(
        self, context: ProcessingContext, surfaced_skills: Optional[Sequence] = None
    ) -> "tuple[List[Dict[str, Any]], Optional[int]]":
        """
        Build the initial OpenAI-format messages list from the processing
        context, plus the prompt-caching breakpoint (see
        PromptInstructionBuilder.build_system_message) for the stable prefix
        of the system message just built — the caller forwards this to
        run_tool_calling_loop so Anthropic's cache_control breakpoint applies
        to the tool-calling path the same way it already does for plain
        generation (see llm_inference.py's _run_inline_mcp_tools).

        When ``surfaced_skills`` is non-empty, the Level 1 tool-skill catalog
        (docs/roadmap/mcp-tool-skills.md §2.2) is appended to the system
        message AFTER the returned ``cache_prefix_len`` — the catalog varies
        with the turn's tool list, and appending it past the breakpoint is
        what keeps prompt caching intact (§2.4). ``cache_prefix_len`` itself
        is unchanged: it still marks only the stable prefix
        ``build_system_message`` computed, before any catalog text exists.
        """
        prompt_builder = PromptInstructionBuilder(
            config=self.container.get_or_none("config") or {},
            prompt_service=self.container.get_or_none("prompt_service"),
            clock_service=self.container.get_or_none("clock_service"),
        )
        system_content, cache_prefix_len = await prompt_builder.build_system_message(context)

        if surfaced_skills:
            system_content = system_content + "\n\n" + _tool_skill_catalog_text(surfaced_skills)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_content}
        ]

        for msg in context.context_messages or []:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        messages.append({"role": "user", "content": context.message})
        return messages, cache_prefix_len

    async def _resolve_provider(self, context: ProcessingContext):
        """Resolve the inference provider, preferring the adapter's configured provider."""
        if self.container.has("adapter_manager"):
            mgr = self.container.get("adapter_manager")
            adapter_name = context.adapter_name

            if context.runtime_provider and context.runtime_model_name:
                return await mgr.get_overridden_provider(
                    context.runtime_provider,
                    adapter_name,
                    explicit_model_override=context.runtime_model_name,
                    explicit_param_overrides=context.runtime_param_overrides,
                )
            if context.inference_provider:
                return await mgr.get_overridden_provider(
                    context.inference_provider, adapter_name
                )

        return self.container.get_or_none("llm_provider")

    def _get_mcp_manager(self):
        """Get (or lazily initialize) the MCPClientManager from config."""
        config = self.container.get_or_none("config") or {}
        from services.mcp_client_service import get_mcp_client_manager
        return get_mcp_client_manager(config)

    def _get_tool_skill_registry(self):
        """Get (or lazily initialize) the ToolSkillRegistry from config."""
        config = self.container.get_or_none("config") or {}
        from services.tool_skill_service import get_tool_skill_registry
        return get_tool_skill_registry(config)

    def _surfaced_set_cap(self) -> int:
        from services.tool_skill_service import SURFACED_SET_CAP
        return SURFACED_SET_CAP

    def _build_dispatch(self, mcp_manager, surfaced_skills: Sequence):
        """
        Build this turn's dispatcher: ``orbit__load_tool_skill`` routes to a
        local skill load (Level 2, docs/roadmap/mcp-tool-skills.md §2.2),
        everything else reaches the real MCP server unchanged.

        Authorization and idempotence both live in this closure, scoped to
        one turn:
          - only a name in ``surfaced_skills`` (the turn's capped surfaced
            set, matching the loader's enum) can be loaded — a guessed,
            hallucinated, or matched-but-capped-out name is rejected exactly
            like an unknown tool name, never resolved against the wider
            matched set or the registry as a whole (§2.2).
          - a skill already loaded once this turn returns a short fixed
            result instead of its body again, so a repeated call cannot
            re-inflate context (§2.2).

        Interception of the loader name is itself gated on ``surfaced_skills``
        being non-empty — defense in depth alongside the collision guard in
        ``_run_agent_loop``. If a turn has no surfaced skills at all (either
        because nothing matched, or because a real MCP tool happens to be
        namespaced exactly ``orbit__load_tool_skill``), this dispatcher must
        never swallow that name; it falls straight through to the real
        ``mcp_manager.call_tool`` instead, so a genuine MCP tool by that name
        stays reachable.
        """
        surfaced_by_name = {skill.name: skill for skill in surfaced_skills}
        loaded: set = set()

        async def dispatch(tool_name: str, arguments: Dict[str, Any]) -> ToolDispatchResult:
            if tool_name == _TOOL_SKILL_LOADER_NAME and surfaced_by_name:
                requested = arguments.get("name") if isinstance(arguments, dict) else None
                skill = surfaced_by_name.get(requested)
                if skill is None:
                    return ToolDispatchResult(
                        content=f"Unknown or unavailable tool skill '{requested}'.",
                        source_type="tool_skill_load",
                    )
                if requested in loaded:
                    return ToolDispatchResult(
                        content=f"'{requested}' already loaded this turn.",
                        source_type="tool_skill_load",
                    )
                loaded.add(requested)
                return ToolDispatchResult(
                    content="",
                    source_type="tool_skill_load",
                    trusted_context=[
                        TrustedContext(name=skill.name, body=skill.body, version=skill.version)
                    ],
                )

            content = await mcp_manager.call_tool(tool_name, arguments)
            return ToolDispatchResult(content=content, source_type="mcp_tool_call")

        return dispatch
