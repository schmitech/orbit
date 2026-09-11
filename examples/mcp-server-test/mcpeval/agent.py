"""LangGraph ReAct agent wired to the MCP server, plus trajectory capture.

This is the only module that touches LangChain message internals, so a library
upgrade has exactly one place to break.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from .config import Settings, load_system_prompt
from .models import ModelSpec

SERVER_NAME = "orbit-business-sample"


@dataclass
class ToolCallRecord:
    name: str
    args: dict[str, Any]
    id: str
    payload: dict[str, Any] | None = None
    raw_text: str = ""
    is_error: bool = False


@dataclass
class AgentRun:
    answer: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    latency_s: float = 0.0
    error: str | None = None

    @property
    def tool_names(self) -> list[str]:
        return [call.name for call in self.tool_calls]

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "tool_calls": [
                {
                    "name": c.name,
                    "args": c.args,
                    "payload": c.payload,
                    "is_error": c.is_error,
                }
                for c in self.tool_calls
            ],
            "latency_s": round(self.latency_s, 2),
            "error": self.error,
        }


async def load_tools(settings: Settings):
    """Discover the MCP tools once; each invocation opens its own short-lived
    session, which suits the server's stateless per-POST design."""
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(
        {
            SERVER_NAME: {
                "transport": "streamable_http",
                "url": settings.mcp_url,
                "headers": settings.auth_headers,
            }
        }
    )
    return await client.get_tools()


def build_agent(spec: ModelSpec, tools, playbook: str | None):
    # langgraph.prebuilt.create_react_agent is deprecated since LangGraph 1.0
    # and removed in 2.0; langchain.agents.create_agent is the supported entry
    # point. Isolated here so a future move is a one-line change.
    from langchain.agents import create_agent

    return create_agent(spec.build(), tools, system_prompt=load_system_prompt(playbook))


def _text_of(content: Any) -> str:
    """Flatten LangChain content, which may be a string or a block list."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "") if isinstance(block, dict) else str(block) for block in content
        ).strip()
    return str(content)


def _parse_tool_message(message) -> tuple[dict[str, Any] | None, str, bool]:
    text = _text_of(message.content)
    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        return None, text, getattr(message, "status", None) == "error"
    # The server signals failure with isError; adapters may surface that as
    # ToolMessage.status or leave it only in the payload. Accept either.
    is_error = getattr(message, "status", None) == "error" or (
        isinstance(payload, dict) and "error" in payload
    )
    return payload if isinstance(payload, dict) else None, text, is_error


def extract_trajectory(messages) -> tuple[list[ToolCallRecord], str]:
    """Turn the message list into ordered tool calls plus the final answer."""
    from langchain_core.messages import AIMessage, ToolMessage

    calls: dict[str, ToolCallRecord] = {}
    ordered: list[ToolCallRecord] = []
    answer = ""

    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls or []:
                record = ToolCallRecord(name=call["name"], args=call.get("args") or {}, id=call.get("id") or "")
                calls[record.id] = record
                ordered.append(record)
            text = _text_of(message.content)
            if text and not message.tool_calls:
                answer = text
        elif isinstance(message, ToolMessage):
            record = calls.get(message.tool_call_id)
            if record is not None:
                record.payload, record.raw_text, record.is_error = _parse_tool_message(message)

    return ordered, answer


async def run_case(agent, query: str, recursion_limit: int = 20) -> AgentRun:
    started = time.perf_counter()
    try:
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": query}]},
            config={"recursion_limit": recursion_limit},
        )
    except Exception as exc:  # noqa: BLE001 - a failed agent run is a result, not a harness crash
        return AgentRun(answer="", latency_s=time.perf_counter() - started, error=f"{type(exc).__name__}: {exc}")

    calls, answer = extract_trajectory(result["messages"])
    return AgentRun(answer=answer, tool_calls=calls, latency_s=time.perf_counter() - started)
