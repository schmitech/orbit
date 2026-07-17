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
from typing import AsyncGenerator, List, Dict, Any, Optional

from ..base import PipelineStep, ProcessingContext
from ..prompt_builder import PromptInstructionBuilder
from ..mcp_tool_loop import run_tool_calling_loop

logger = logging.getLogger(__name__)

_DEFAULT_MAX_ITERATIONS = 5


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
                "MCP client is not enabled. Set mcp_client.enabled: true in config."
            )

        allowed_servers = _get_mcp_servers_allowlist(self.container, context.adapter_name)
        tools = await mcp_manager.get_all_tools(allowed_servers=allowed_servers)

        if not tools:
            raise RuntimeError(
                "No MCP tools available. "
                "Check mcp_client configuration and server connectivity."
            )

        messages = await self._build_initial_messages(context)

        final_text, sources, _ = await run_tool_calling_loop(
            provider=provider,
            mcp_manager=mcp_manager,
            messages=messages,
            tools=tools,
            max_iterations=mcp_manager.max_tool_iterations,
            cancel_event=context.cancel_event,
            is_cancelled=context.is_cancelled,
        )
        return final_text, sources

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _build_initial_messages(
        self, context: ProcessingContext
    ) -> List[Dict[str, Any]]:
        """Build the initial OpenAI-format messages list from the processing context."""
        prompt_builder = PromptInstructionBuilder(
            config=self.container.get_or_none("config") or {},
            prompt_service=self.container.get_or_none("prompt_service"),
            clock_service=self.container.get_or_none("clock_service"),
        )
        system_content = await prompt_builder.build_system_message_content(context)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_content}
        ]

        for msg in context.context_messages or []:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        messages.append({"role": "user", "content": context.message})
        return messages

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
