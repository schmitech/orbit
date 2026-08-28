"""
Shared MCP tool-calling loop.

Used by both MCPAgentStep (adapter type == "mcp_agent", explicit skill swap)
and LLMInferenceStep's inline opportunistic path (capabilities.mcp_tools on a
normal conversational/passthrough adapter). Extracted so the bounded
loop/cancellation/executor logic is implemented once.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from ai_services.providers.usage_reporting import accumulate_usage_sink

logger = logging.getLogger(__name__)

_RESULT_TRUNCATION_CHARS = 2000

# Sentinel returned by await_or_cancel when the client cancelled mid-call.
_CANCELLED = object()


@dataclass
class TrustedContext:
    """
    A trusted, admin-authored attachment riding alongside a tool call's own
    (untrusted) result — e.g. a tool skill body (see
    docs/roadmap/mcp-tool-skills.md §2.8). ``version`` lives per-item, not on
    ``ToolDispatchResult``, because one dispatch's ``trusted_context`` is a
    list and can in principle carry more than one matched skill.
    """

    name: str
    body: str
    kind: str = "tool_skill"
    version: Optional[str] = None


@dataclass
class ToolDispatchResult:
    """
    The result of dispatching one tool call, returned by the ``dispatch``
    callable passed to :func:`run_tool_calling_loop` (see
    docs/roadmap/mcp-tool-skills.md §2.8).

    ``content`` is always untrusted text — the tool's own output — and is
    wrapped in ``<tool_result>`` exactly as a bare string result was before
    this type existed. ``trusted_context`` holds zero or more *additional*,
    admin-authored segments (e.g. a tool skill body) that ride alongside
    ``content`` in the same ``role: "tool"`` message, each delimited
    separately and never treated as if it came from the tool/MCP server.

    A single ``trusted: bool`` cannot represent Level 3's mixed-trust case
    (untrusted tool output + a trusted skill body attached to the same call),
    which is why this is a list of segments rather than one flag.
    """

    content: str
    source_type: str = "mcp_tool_call"  # "mcp_tool_call" | "tool_skill_load" | future local kinds
    trusted_context: List[TrustedContext] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


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


def _call_with_tools(
    provider,
    messages,
    tools,
    usage_sink: Optional[Dict[str, Any]],
    cache_prefix_len: Optional[int] = None,
):
    """
    Call generate_with_tools_tracked when the provider has it, else fall back
    to plain generate_with_tools. Some test doubles and third-party providers
    implement only generate_with_tools directly rather than subclassing
    LLMProvider (which provides the tracked default) — this keeps the loop
    working for them, just without usage reporting/prompt caching for that call.
    """
    if hasattr(provider, "generate_with_tools_tracked"):
        return provider.generate_with_tools_tracked(
            messages, tools, usage_sink=usage_sink, cache_prefix_len=cache_prefix_len
        )
    return provider.generate_with_tools(messages, tools)


async def run_tool_calling_loop(
    provider,
    mcp_manager,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    max_iterations: int,
    cancel_event: Optional[asyncio.Event] = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
    usage_sink: Optional[Dict[str, Any]] = None,
    cache_prefix_len: Optional[int] = None,
    dispatch: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
) -> Tuple[Optional[str], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Execute the bounded tool-calling loop.

    Args:
        provider: Inference provider exposing generate_with_tools(messages, tools).
        mcp_manager: MCPClientManager-like object exposing call_tool(name, args).
            Used as the default dispatch target when ``dispatch`` is not given.
        messages: Initial OpenAI-format messages list (mutated in place).
        tools: OpenAI-format tool schemas to expose to the model.
        max_iterations: Maximum tool-calling rounds before forcing a final answer.
        cancel_event: Optional asyncio.Event; when set, in-flight calls are torn down.
        is_cancelled: Optional callable checked between iterations for a cheap
            fast-path cancellation check.
        dispatch: Optional async callable ``(tool_name, arguments) -> ToolDispatchResult``
            (or a bare string, for backward compatibility with callers that
            haven't adopted the structured contract). Defaults to a thin
            wrapper around ``mcp_manager.call_tool`` that reproduces today's
            behavior exactly (a plain MCP call, ``source_type="mcp_tool_call"``,
            no trusted context) — see docs/roadmap/mcp-tool-skills.md §2.3/§2.8.
            Callers that want tool skills (or any other local/synthetic tool)
            pass their own dispatcher; everything else about the loop is
            unchanged by that choice.
        usage_sink: Optional caller-owned dict that accumulates token usage
            summed across every provider call this loop makes. A fresh sink is
            used per call (see accumulate_usage_sink) since _report_usage()
            overwrites rather than accumulates — reusing one sink across calls
            would silently drop all but the last iteration's counts.
        cache_prefix_len: Optional prompt-caching breakpoint (see
            PromptInstructionBuilder.build_system_message), forwarded to every
            call this loop makes including the final no-tools synthesis call —
            the system message doesn't change mid-loop, so the same breakpoint
            applies to all of them. Dropped by providers that don't support it
            (see generate_with_tools_tracked's SUPPORTS_PROMPT_CACHING gate).

    Returns:
        (final_text, sources, messages) — messages is the same list passed in,
        mutated with all assistant/tool turns, so a caller that wants to make a
        follow-up call can reuse it instead of re-deriving conversation state.
    """
    sources: List[Dict[str, Any]] = []
    # Best answer text seen so far, returned if the caller cancels mid-loop.
    last_text: Optional[str] = None

    if dispatch is None:
        async def dispatch(tool_name: str, arguments: Dict[str, Any]) -> ToolDispatchResult:
            content = await mcp_manager.call_tool(tool_name, arguments)
            return ToolDispatchResult(content=content, source_type="mcp_tool_call")

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

        iter_sink: Optional[Dict[str, Any]] = {} if usage_sink is not None else None
        result = await await_or_cancel(
            _call_with_tools(provider, messages, tools, iter_sink, cache_prefix_len), cancel_event
        )
        if usage_sink is not None:
            accumulate_usage_sink(usage_sink, iter_sink)
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
                dispatch_result = await await_or_cancel(
                    dispatch(tool_name, arguments), cancel_event
                )
            except Exception as exc:
                dispatch_result = ToolDispatchResult(
                    content=f"Error calling tool '{tool_name}': {exc}",
                    source_type="mcp_tool_call",
                )
                logger.warning("MCP tool error [%s]: %s", tool_name, exc)

            if dispatch_result is _CANCELLED:
                logger.info("MCP tool loop cancelled during tool call '%s'", tool_name)
                return last_text or "", sources, messages

            # A dispatcher predating the ToolDispatchResult contract (or a
            # third-party one) may still return a bare string — treat it
            # exactly like the pre-Phase-1 default behavior.
            if not isinstance(dispatch_result, ToolDispatchResult):
                dispatch_result = ToolDispatchResult(content=str(dispatch_result), source_type="mcp_tool_call")

            # Wrap the untrusted tool output in delimiters to reduce
            # prompt-injection risk (content from MCP servers is untrusted;
            # the tags make it harder for a malicious result to impersonate
            # system instructions), then append each trusted segment (e.g. a
            # tool skill body) in its own, separately-delimited tag — never
            # inside <tool_result>, and never as a new message/role (see
            # docs/roadmap/mcp-tool-skills.md §2.2/§2.8).
            wrapped = f"<tool_result>\n{dispatch_result.content}\n</tool_result>"
            for trusted in dispatch_result.trusted_context:
                wrapped += f'\n<trusted_skill name="{trusted.name}">\n{trusted.body}\n</trusted_skill>'

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": tool_name,
                "content": wrapped,
            })

            # Record for transparency. A local dispatch (source_type !=
            # "mcp_tool_call", e.g. a tool skill load) never gets an
            # mcp_tool_call-shaped entry — it never called an external MCP
            # server, and must not be mistaken for one downstream (analytics,
            # mcp_tools_used aggregates, etc). Each trusted_context item gets
            # its own entry instead, with no body preview.
            if dispatch_result.source_type == "mcp_tool_call":
                sources.append({
                    "type": "mcp_tool_call",
                    "tool": tool_name,
                    "arguments": arguments,
                    "result_preview": dispatch_result.content[:_RESULT_TRUNCATION_CHARS],
                })
            for trusted in dispatch_result.trusted_context:
                sources.append({
                    "type": "tool_skill_load",
                    "skill": trusted.name,
                    "version": trusted.version,
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
        final_iter_sink: Optional[Dict[str, Any]] = {} if usage_sink is not None else None
        final_result = await await_or_cancel(
            _call_with_tools(provider, messages, [], final_iter_sink, cache_prefix_len), cancel_event
        )
        if usage_sink is not None:
            accumulate_usage_sink(usage_sink, final_iter_sink)
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
