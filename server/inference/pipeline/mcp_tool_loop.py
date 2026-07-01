"""
Shared MCP tool-calling loop.

Used by both MCPAgentStep (adapter type == "mcp_agent", explicit skill swap)
and LLMInferenceStep's inline opportunistic path (capabilities.mcp_tools on a
normal conversational/passthrough adapter). Extracted so the bounded
loop/cancellation/executor logic is implemented once.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_RESULT_TRUNCATION_CHARS = 2000

# Sentinel returned by await_or_cancel when the client cancelled mid-call.
_CANCELLED = object()


async def await_or_cancel(coro, cancel_event: Optional[asyncio.Event]):
    """
    Await ``coro``, but abandon it if ``cancel_event`` fires first.

    Returns the coroutine's result (re-raising any exception it raised), or
    the ``_CANCELLED`` sentinel if the cancel event fires first. On
    cancellation the in-flight task is cancelled and awaited so the
    underlying HTTP request / tool subprocess is torn down promptly rather
    than left running.
    """
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


async def run_tool_calling_loop(
    provider,
    mcp_manager,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    max_iterations: int,
    cancel_event: Optional[asyncio.Event] = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
) -> Tuple[Optional[str], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Execute the bounded tool-calling loop.

    Args:
        provider: Inference provider exposing generate_with_tools(messages, tools).
        mcp_manager: MCPClientManager-like object exposing call_tool(name, args).
        messages: Initial OpenAI-format messages list (mutated in place).
        tools: OpenAI-format tool schemas to expose to the model.
        max_iterations: Maximum tool-calling rounds before forcing a final answer.
        cancel_event: Optional asyncio.Event; when set, in-flight calls are torn down.
        is_cancelled: Optional callable checked between iterations for a cheap
            fast-path cancellation check.

    Returns:
        (final_text, sources, messages) — messages is the same list passed in,
        mutated with all assistant/tool turns, so a caller that wants to make a
        follow-up call can reuse it instead of re-deriving conversation state.
    """
    sources: List[Dict[str, Any]] = []
    # Best answer text seen so far, returned if the caller cancels mid-loop.
    last_text: Optional[str] = None

    def _cancelled() -> bool:
        return bool(is_cancelled and is_cancelled())

    for iteration in range(max_iterations):
        # Honor cancellation between steps (cheap fast-path). The provider
        # and tool awaits below are additionally raced against cancel_event
        # so an in-flight call is torn down promptly.
        if _cancelled():
            logger.info("MCP tool loop cancelled before iteration %d/%d", iteration + 1, max_iterations)
            return last_text or "", sources, messages

        logger.debug(
            "MCP tool loop iteration %d/%d, messages=%d, tools=%d",
            iteration + 1,
            max_iterations,
            len(messages),
            len(tools),
        )

        result = await await_or_cancel(
            provider.generate_with_tools(messages, tools), cancel_event
        )
        if result is _CANCELLED:
            logger.info("MCP tool loop cancelled during model call (iteration %d)", iteration + 1)
            return last_text or "", sources, messages
        if result.text:
            last_text = result.text

        if not result.tool_calls:
            # Model produced a final answer
            return result.text, sources, messages

        # Append the assistant's tool-call turn
        messages.append(result.assistant_message)

        # Execute each tool call
        for tc in result.tool_calls:
            tool_name = tc["name"]
            arguments = tc["arguments"]
            tool_call_id = tc["id"]

            logger.debug("MCP tool call: %s(%s)", tool_name, arguments)

            try:
                tool_result_text = await await_or_cancel(
                    mcp_manager.call_tool(tool_name, arguments), cancel_event
                )
            except Exception as exc:
                tool_result_text = f"Error calling tool '{tool_name}': {exc}"
                logger.warning("MCP tool error [%s]: %s", tool_name, exc)

            if tool_result_text is _CANCELLED:
                logger.info("MCP tool loop cancelled during tool call '%s'", tool_name)
                return last_text or "", sources, messages

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
        "MCP tool loop exhausted %d iterations without a final answer; "
        "forcing a final text answer.",
        max_iterations,
    )
    # Ask the model one final time with NO tools, so it is forced to produce
    # a text answer from the accumulated history instead of requesting yet
    # more tool calls we can no longer execute (which would yield empty text).
    if _cancelled():
        return last_text or "", sources, messages
    try:
        final_result = await await_or_cancel(
            provider.generate_with_tools(messages, []), cancel_event
        )
        if final_result is _CANCELLED:
            return last_text or "", sources, messages
        if final_result.text:
            return final_result.text, sources, messages
        logger.warning("Final MCP tool loop synthesis returned no text.")
        return (
            "I gathered information from the available tools but could not "
            "compose a final answer within the allowed number of steps.",
            sources,
            messages,
        )
    except Exception as exc:
        logger.error("Final MCP tool loop synthesis failed: %s", exc)
        return "I was unable to complete the tool-calling loop.", sources, messages
