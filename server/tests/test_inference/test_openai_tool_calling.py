"""Regression tests for OpenAI Responses API tool calls."""

import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(server_dir)

from ai_services.implementations.inference.openai_inference_service import (
    OpenAIInferenceService,
)


class TestOpenAIResponsesTools:
    async def test_gpt_56_tools_use_responses_api_with_reasoning(self):
        """GPT-5.6 MCP calls use Responses, where reasoning and tools coexist."""
        service = object.__new__(OpenAIInferenceService)
        service.initialized = True
        service.model = "gpt-5.6"
        service.temperature = 0.1
        service.top_p = 1.0
        service._resolve_token_value = lambda _name, _kwargs: 2000
        service._supports_temperature = lambda: False
        service._supports_top_p = lambda: False

        response = SimpleNamespace(
            output_text="",
            output=[
                {
                    "type": "reasoning",
                    "id": "rs_1",
                    "summary": [],
                },
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "read",
                    "arguments": '{"path":"/tmp/a"}',
                },
            ],
        )
        create = AsyncMock(return_value=response)
        service.client = SimpleNamespace(responses=SimpleNamespace(create=create))

        tools = [{"type": "function", "function": {"name": "read", "parameters": {}}}]
        result = await service.generate_with_tools(
            [{"role": "user", "content": "Read the file"}],
            tools,
            reasoning_effort="high",
        )

        request = create.call_args.kwargs
        assert request["tools"] == [
            {"type": "function", "name": "read", "parameters": {}, "strict": False}
        ]
        assert request["reasoning"] == {"effort": "high"}
        assert request["input"] == [{"role": "user", "content": "Read the file"}]
        assert "reasoning_effort" not in request
        assert result.tool_calls == [
            {"id": "call_1", "name": "read", "arguments": {"path": "/tmp/a"}}
        ]

    def test_replays_responses_items_and_tool_output(self):
        messages = [
            {"role": "user", "content": "Read the file"},
            {
                "role": "assistant",
                "content": None,
                "_openai_responses_output": [
                    {"type": "reasoning", "id": "rs_1", "summary": []},
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "read",
                        "arguments": '{"path":"/tmp/a"}',
                    },
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "name": "read",
                "content": "file contents",
            },
        ]

        assert OpenAIInferenceService._messages_to_responses_input(messages) == [
            {"role": "user", "content": "Read the file"},
            {"type": "reasoning", "id": "rs_1", "summary": []},
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "read",
                "arguments": '{"path":"/tmp/a"}',
            },
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": "file contents",
            },
        ]
