"""
Test OpenAICompatibleBaseService._build_messages, the shared prompt-parsing
helper used by all OpenAI-compatible inference providers.
"""

import os
import sys

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(server_dir)

from ai_services.providers.openai_compatible_base import OpenAICompatibleBaseService


class TestBuildMessages:
    """Test cases for the shared _build_messages helper."""

    def test_plain_prompt_becomes_single_user_message(self):
        kwargs = {}
        messages = OpenAICompatibleBaseService._build_messages("Hello there", kwargs)

        assert messages == [{"role": "user", "content": "Hello there"}]
        assert kwargs == {}

    def test_formatted_prompt_splits_into_system_and_user(self):
        prompt = "You are helpful.\nUser: What is 2+2?\nAssistant:"
        kwargs = {}
        messages = OpenAICompatibleBaseService._build_messages(prompt, kwargs)

        assert messages == [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "What is 2+2?"},
        ]

    def test_prompt_with_only_one_marker_is_not_split(self):
        kwargs = {}
        messages = OpenAICompatibleBaseService._build_messages(
            "\nUser: no assistant marker here", kwargs
        )

        assert messages == [
            {"role": "user", "content": "\nUser: no assistant marker here"}
        ]

    def test_explicit_messages_kwarg_passes_through_unchanged(self):
        explicit_messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        ]
        kwargs = {"messages": explicit_messages}

        messages = OpenAICompatibleBaseService._build_messages("ignored prompt", kwargs)

        assert messages is explicit_messages
        assert "messages" not in kwargs

    def test_explicit_messages_kwarg_takes_priority_over_prompt_parsing(self):
        kwargs = {"messages": [{"role": "user", "content": "explicit"}]}
        messages = OpenAICompatibleBaseService._build_messages(
            "You are helpful.\nUser: ignored\nAssistant:", kwargs
        )

        assert messages == [{"role": "user", "content": "explicit"}]
