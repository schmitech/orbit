#!/usr/bin/env python3
"""
Unit tests for the message-format conversion logic used by generate_with_tools.

These translations (OpenAI tool-call format <-> each provider's native format)
are the most regression-prone part of the MCP agent feature and are testable
without any network access or full service construction:

  - Gemini: _strip_schema_meta, _extract_system_and_contents_for_tools (static)
  - Anthropic: _convert_messages_for_tools (instance method, but only depends on
    the static _extract_system_message, so we bypass __init__ with __new__)
"""

import json
import os
import sys

import pytest

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(server_dir)

from ai_services.implementations.inference.gemini_inference_service import GeminiInferenceService
from ai_services.implementations.inference.anthropic_inference_service import AnthropicInferenceService
from ai_services.implementations.inference.ollama_inference_service import OllamaInferenceService
from ai_services.implementations.inference.vllm_inference_service import VLLMInferenceService


# ----------------------------------------------------------------------------
# Gemini: $schema stripping
# ----------------------------------------------------------------------------

class TestGeminiStripSchemaMeta:
    def test_strips_top_level_dollar_fields(self):
        cleaned = GeminiInferenceService._strip_schema_meta(
            {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "$id": "x",
                "type": "object",
                "properties": {"a": {"type": "string"}},
            }
        )
        assert "$schema" not in cleaned
        assert "$id" not in cleaned
        assert cleaned["type"] == "object"
        assert cleaned["properties"] == {"a": {"type": "string"}}

    def test_strips_nested_dollar_fields(self):
        cleaned = GeminiInferenceService._strip_schema_meta(
            {
                "type": "object",
                "properties": {
                    "inner": {"$schema": "draft-07", "type": "string"},
                },
                "items": [{"$ref": "#/d", "type": "number"}],
            }
        )
        assert "$schema" not in cleaned["properties"]["inner"]
        assert cleaned["properties"]["inner"]["type"] == "string"
        assert cleaned["items"][0] == {"type": "number"}

    def test_non_dict_returned_unchanged(self):
        assert GeminiInferenceService._strip_schema_meta("nope") == "nope"


# ----------------------------------------------------------------------------
# Gemini: OpenAI messages -> Gemini contents
# ----------------------------------------------------------------------------

class TestGeminiExtractContentsForTools:
    def test_system_extracted_separately(self):
        system, contents = GeminiInferenceService._extract_system_and_contents_for_tools(
            [
                {"role": "system", "content": "be helpful"},
                {"role": "user", "content": "hi"},
            ]
        )
        assert system == "be helpful"
        assert contents == [{"role": "user", "parts": [{"text": "hi"}]}]

    def test_raw_gemini_content_preserved_verbatim(self):
        # Thinking models require the raw Content (with thought_signature) echoed
        # back. When _gemini_raw_content is present it must be used unchanged.
        sentinel = object()
        _, contents = GeminiInferenceService._extract_system_and_contents_for_tools(
            [
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": None, "_gemini_raw_content": sentinel},
            ]
        )
        assert contents[-1] is sentinel

    def test_assistant_tool_calls_reconstructed_when_no_raw(self):
        _, contents = GeminiInferenceService._extract_system_and_contents_for_tools(
            [
                {
                    "role": "assistant",
                    "content": "thinking",
                    "tool_calls": [
                        {
                            "id": "x",
                            "type": "function",
                            "function": {
                                "name": "filesystem__read_file",
                                "arguments": json.dumps({"path": "/tmp/a"}),
                            },
                        }
                    ],
                }
            ]
        )
        model_turn = contents[-1]
        assert model_turn["role"] == "model"
        assert {"text": "thinking"} in model_turn["parts"]
        fc_part = [p for p in model_turn["parts"] if "function_call" in p][0]
        assert fc_part["function_call"]["name"] == "filesystem__read_file"
        assert fc_part["function_call"]["args"] == {"path": "/tmp/a"}

    def test_consecutive_tool_results_merged_into_one_user_turn(self):
        _, contents = GeminiInferenceService._extract_system_and_contents_for_tools(
            [
                {"role": "tool", "name": "a", "content": "r1"},
                {"role": "tool", "name": "b", "content": "r2"},
                {"role": "user", "content": "next"},
            ]
        )
        # First turn holds both function_responses, second is the user message
        assert contents[0]["role"] == "user"
        assert len(contents[0]["parts"]) == 2
        assert contents[0]["parts"][0]["function_response"]["name"] == "a"
        assert contents[0]["parts"][1]["function_response"]["name"] == "b"
        assert contents[1] == {"role": "user", "parts": [{"text": "next"}]}


# ----------------------------------------------------------------------------
# Anthropic: OpenAI messages -> Anthropic messages
# ----------------------------------------------------------------------------

class TestAnthropicConvertMessages:
    def _svc(self):
        # Bypass __init__ (no network / config needed) — the method only uses
        # the static _extract_system_message.
        return object.__new__(AnthropicInferenceService)

    def test_system_pulled_out(self):
        system, msgs = self._svc()._convert_messages_for_tools(
            [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hi"},
            ]
        )
        assert system == "sys"
        assert msgs == [{"role": "user", "content": "hi"}]

    def test_assistant_tool_calls_become_tool_use_blocks(self):
        _, msgs = self._svc()._convert_messages_for_tools(
            [
                {
                    "role": "assistant",
                    "content": "let me check",
                    "tool_calls": [
                        {
                            "id": "tu_1",
                            "type": "function",
                            "function": {
                                "name": "github__list_issues",
                                "arguments": json.dumps({"state": "open"}),
                            },
                        }
                    ],
                }
            ]
        )
        blocks = msgs[0]["content"]
        assert {"type": "text", "text": "let me check"} in blocks
        tool_use = [b for b in blocks if b["type"] == "tool_use"][0]
        assert tool_use["id"] == "tu_1"
        assert tool_use["name"] == "github__list_issues"
        assert tool_use["input"] == {"state": "open"}

    def test_consecutive_tool_results_merged_into_one_user_turn(self):
        _, msgs = self._svc()._convert_messages_for_tools(
            [
                {"role": "tool", "tool_call_id": "tu_1", "content": "r1"},
                {"role": "tool", "tool_call_id": "tu_2", "content": "r2"},
            ]
        )
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        results = msgs[0]["content"]
        assert len(results) == 2
        assert results[0] == {"type": "tool_result", "tool_use_id": "tu_1", "content": "r1"}
        assert results[1] == {"type": "tool_result", "tool_use_id": "tu_2", "content": "r2"}


# ----------------------------------------------------------------------------
# Ollama: OpenAI loop history -> Ollama /api/chat messages
# ----------------------------------------------------------------------------

class TestOllamaNormalizeMessages:
    _norm = staticmethod(OllamaInferenceService._normalize_messages_for_ollama)

    def test_tool_result_keeps_name_as_tool_name(self):
        # The loop emits role:"tool" with both name and tool_call_id; Ollama
        # needs tool_name to disambiguate parallel results.
        out = self._norm(
            [{"role": "tool", "tool_call_id": "c1", "name": "fs__read", "content": "data"}]
        )
        assert out == [{"role": "tool", "content": "data", "tool_name": "fs__read"}]

    def test_tool_result_without_name_omits_tool_name(self):
        out = self._norm([{"role": "tool", "content": "data"}])
        assert out == [{"role": "tool", "content": "data"}]

    def test_assistant_string_args_decoded_to_dict(self):
        out = self._norm(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {"id": "c1", "type": "function",
                         "function": {"name": "fs__read", "arguments": json.dumps({"path": "/x"})}}
                    ],
                }
            ]
        )
        assert out[0]["role"] == "assistant"
        assert out[0]["content"] == ""  # None coerced to "" for Ollama
        assert out[0]["tool_calls"][0]["function"] == {"name": "fs__read", "arguments": {"path": "/x"}}

    def test_assistant_dict_args_passed_through(self):
        out = self._norm(
            [
                {
                    "role": "assistant",
                    "content": "x",
                    "tool_calls": [
                        {"function": {"name": "t", "arguments": {"a": 1}}}
                    ],
                }
            ]
        )
        assert out[0]["tool_calls"][0]["function"]["arguments"] == {"a": 1}

    def test_malformed_args_become_empty_dict(self):
        out = self._norm(
            [
                {
                    "role": "assistant",
                    "content": "x",
                    "tool_calls": [
                        {"function": {"name": "t", "arguments": "{not json"}}
                    ],
                }
            ]
        )
        assert out[0]["tool_calls"][0]["function"]["arguments"] == {}

    def test_user_and_system_pass_through_unchanged(self):
        history = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
        assert self._norm(history) == history


# ----------------------------------------------------------------------------
# vLLM: direct (in-process) mode does not support tool calling
# ----------------------------------------------------------------------------

class TestVLLMDirectModeUnsupported:
    async def test_direct_mode_raises_not_implemented(self):
        # Bypass __init__ (no engine load / network) and set only the two
        # attributes the method reads before the mode guard fires.
        svc = object.__new__(VLLMInferenceService)
        svc.initialized = True
        svc.mode = "direct"
        with pytest.raises(NotImplementedError, match="only supported in API mode"):
            await svc.generate_with_tools([{"role": "user", "content": "hi"}], [])
