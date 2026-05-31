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

import asyncio
import logging
from typing import AsyncGenerator, List, Dict, Any, Optional

from ..base import PipelineStep, ProcessingContext
from ..prompt_builder import PromptInstructionBuilder

logger = logging.getLogger(__name__)

_DEFAULT_MAX_ITERATIONS = 5
_RESULT_TRUNCATION_CHARS = 2000

# Sentinel returned by _await_or_cancel when the client cancelled mid-call.
_CANCELLED = object()


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

    @staticmethod
    async def _await_or_cancel(coro, context: ProcessingContext):
        """
        Await ``coro``, but abandon it if the client cancels mid-flight.

        Returns the coroutine's result (re-raising any exception it raised), or
        the ``_CANCELLED`` sentinel if the context's cancel event fires first.
        On cancellation the in-flight task is cancelled and awaited so the
        underlying HTTP request / tool subprocess is torn down promptly rather
        than left running — this is what makes Stop interrupt a slow tool call
        mid-execution instead of only between steps.
        """
        cancel_event = context.cancel_event
        if cancel_event is None:
            return await coro

        task = asyncio.ensure_future(coro)
        waiter = asyncio.ensure_future(cancel_event.wait())
        try:
            await asyncio.wait({task, waiter}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            waiter.cancel()

        if cancel_event.is_set():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            return _CANCELLED

        # Task finished first — surface its result (or re-raise its exception).
        return task.result()

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
        max_iterations = mcp_manager.max_tool_iterations
        sources: List[Dict[str, Any]] = []
        # Best answer text seen so far, returned if the client cancels mid-loop.
        last_text: Optional[str] = None

        for iteration in range(max_iterations):
            # Honor a client Stop between steps (cheap fast-path). The provider
            # and tool awaits below are additionally raced against the cancel
            # event so an in-flight call is torn down promptly — Stop interrupts
            # even a slow tool mid-call rather than waiting for it to return.
            if context.is_cancelled():
                logger.info("MCP agent cancelled before iteration %d/%d", iteration + 1, max_iterations)
                return last_text or "", sources

            logger.debug(
                "MCP agent iteration %d/%d, messages=%d, tools=%d",
                iteration + 1,
                max_iterations,
                len(messages),
                len(tools),
            )

            result = await self._await_or_cancel(
                provider.generate_with_tools(messages, tools), context
            )
            if result is _CANCELLED:
                logger.info("MCP agent cancelled during model call (iteration %d)", iteration + 1)
                return last_text or "", sources
            if result.text:
                last_text = result.text

            if not result.tool_calls:
                # Model produced a final answer
                return result.text, sources

            # Append the assistant's tool-call turn
            messages.append(result.assistant_message)

            # Execute each tool call
            for tc in result.tool_calls:
                tool_name = tc["name"]
                arguments = tc["arguments"]
                tool_call_id = tc["id"]

                logger.info("MCP tool call: %s(%s)", tool_name, arguments)

                try:
                    tool_result_text = await self._await_or_cancel(
                        mcp_manager.call_tool(tool_name, arguments), context
                    )
                except Exception as exc:
                    tool_result_text = f"Error calling tool '{tool_name}': {exc}"
                    logger.warning("MCP tool error [%s]: %s", tool_name, exc)

                if tool_result_text is _CANCELLED:
                    logger.info("MCP agent cancelled during tool call '%s'", tool_name)
                    return last_text or "", sources

                # Wrap result in delimiters to reduce prompt-injection risk.
                # Content from MCP servers is untrusted; the tags make it harder
                # for a malicious result to impersonate system instructions.
                wrapped = f"<tool_result>\n{tool_result_text}\n</tool_result>"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": tool_name,
                    "content": wrapped,
                })

                # Record for transparency
                sources.append({
                    "type": "mcp_tool_call",
                    "tool": tool_name,
                    "arguments": arguments,
                    "result_preview": tool_result_text[:_RESULT_TRUNCATION_CHARS],
                })

        # If we exhaust iterations without a final answer, synthesize from last response
        logger.warning(
            "MCP agent exhausted %d iterations without a final answer; "
            "forcing a final text answer.",
            max_iterations,
        )
        # Ask the model one final time with NO tools, so it is forced to produce
        # a text answer from the accumulated history instead of requesting yet
        # more tool calls we can no longer execute (which would yield empty text).
        if context.is_cancelled():
            return last_text or "", sources
        try:
            final_result = await self._await_or_cancel(
                provider.generate_with_tools(messages, []), context
            )
            if final_result is _CANCELLED:
                return last_text or "", sources
            if final_result.text:
                return final_result.text, sources
            logger.warning("Final MCP agent synthesis returned no text.")
            return (
                "I gathered information from the available tools but could not "
                "compose a final answer within the allowed number of steps.",
                sources,
            )
        except Exception as exc:
            logger.error("Final MCP agent synthesis failed: %s", exc)
            return "I was unable to complete the tool-calling loop.", sources

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
