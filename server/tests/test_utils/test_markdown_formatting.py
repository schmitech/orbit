"""Tests for the markdown clean-up applied to chat responses."""

import pytest
from utils.text_utils import _fix_markdown_syntax


@pytest.mark.parametrize("text", [
    "**Note:** read this.",
    "*Emphasis* at start.",
    "Intro\n\n---\n\nAfter rule",
    "3.14 is pi.",
    "-5 degrees outside.",
])
def test_line_starts_that_are_not_list_items_are_left_alone(text):
    assert _fix_markdown_syntax(text) == text


@pytest.mark.parametrize("text", [
    "```python\nx = a * b * c\n```",
    "```python\n    indented()\n```",
    "```\n__init__ and __ spaced __\n```",
])
def test_code_blocks_are_not_rewritten(text):
    assert _fix_markdown_syntax(text) == text


def test_intended_fixes_still_apply():
    assert _fix_markdown_syntax("- item one\n-item two") == "- item one\n- item two"
    assert _fix_markdown_syntax("1.First\n2.Second") == "1. First\n2. Second"
    assert _fix_markdown_syntax("#Title") == "# Title"
    assert _fix_markdown_syntax("Text * spaced * here") == "Text *spaced* here"


def test_code_fence_gets_newlines_without_an_extra_blank_line():
    assert _fix_markdown_syntax("```python x = 1\n```") == "```python\nx = 1\n```"
    assert _fix_markdown_syntax("Before\n```\ncode\n```\nAfter") == "Before\n```\ncode\n```\nAfter"
