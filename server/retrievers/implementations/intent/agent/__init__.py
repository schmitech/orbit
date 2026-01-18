"""
Agent module for function-calling capabilities in intent retrievers.

This module provides tool execution and response synthesis for the
IntentAgentRetriever, enabling function-calling patterns similar to
FunctionGemma and other agentic AI systems.
"""

from .tool_definitions import (
    ToolParameter,
    ToolDefinition,
    ToolResult,
    ToolExecutionConfig,
)
from .tool_executor import ToolExecutor
from .response_synthesizer import ResponseSynthesizer

__all__ = [
    'ToolParameter',
    'ToolDefinition',
    'ToolResult',
    'ToolExecutionConfig',
    'ToolExecutor',
    'ResponseSynthesizer',
]
