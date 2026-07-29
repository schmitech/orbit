"""
Token usage data shared between inference services and the pipeline.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class TokenUsage:
    """Token usage reported by a single generate()/generate_stream() call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    # Subset of completion_tokens spent on reasoning/thinking (OpenAI o-series
    # /gpt-5 completion_tokens_details.reasoning_tokens, Gemini
    # thoughts_token_count). Purely informational — already folded into
    # completion_tokens for cost purposes, so this is None whenever the
    # provider doesn't break it out separately.
    reasoning_tokens: Optional[int] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    reported: bool = False  # False => the provider gave us nothing to report
