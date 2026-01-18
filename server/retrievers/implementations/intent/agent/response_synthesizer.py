"""
Response synthesizer for generating natural language responses from tool results.

This module provides the ResponseSynthesizer class that takes tool execution
results and generates human-readable responses using the inference model.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from .tool_definitions import ToolResult, ToolResultStatus

logger = logging.getLogger(__name__)


# Default synthesis prompt template
DEFAULT_SYNTHESIS_PROMPT = """You are a helpful assistant. Based on the tool execution results below, 
provide a clear and concise response to the user's question.

User's Question: {query}

Tool Executed: {tool_id}
Tool Description: {tool_description}

Execution Results:
{results}

Instructions:
- Provide a direct, helpful response based on the results
- Use natural language that is easy to understand
- Include relevant numbers or data from the results
- If the results contain an error, explain what went wrong
- Keep the response concise but informative

Response:"""


class ResponseSynthesizer:
    """
    Generates natural language responses from tool execution results.
    
    Uses the inference model to synthesize human-readable responses
    that incorporate the tool's output data.
    """

    def __init__(
        self, 
        inference_client: Any,
        synthesis_prompt: Optional[str] = None,
        verbose: bool = False,
    ):
        """
        Initialize the response synthesizer.
        
        Args:
            inference_client: The inference client for LLM calls
            synthesis_prompt: Optional custom synthesis prompt template
            verbose: Enable verbose logging
        """
        self.inference_client = inference_client
        self.synthesis_prompt = synthesis_prompt or DEFAULT_SYNTHESIS_PROMPT
        self.verbose = verbose

    async def synthesize(
        self,
        query: str,
        tool_result: ToolResult,
        tool_description: str = "",
        max_result_chars: int = 4000,
    ) -> str:
        """
        Generate a natural language response from tool results.
        
        Args:
            query: The original user query
            tool_result: The result from tool execution
            tool_description: Description of the tool that was executed
            max_result_chars: Maximum characters of result data to include
            
        Returns:
            Synthesized natural language response
        """
        try:
            # Format the results for the prompt
            results_str = self._format_results(tool_result, max_result_chars)
            
            # Build the synthesis prompt
            prompt = self.synthesis_prompt.format(
                query=query,
                tool_id=tool_result.tool_id,
                tool_description=tool_description,
                results=results_str,
            )
            
            if self.verbose:
                logger.debug(f"Synthesis prompt:\n{prompt[:500]}...")
            
            # Generate response using inference client
            response = await self.inference_client.generate(prompt)
            
            if self.verbose:
                logger.debug(f"Synthesized response: {response[:200]}...")
            
            return response.strip()
            
        except Exception as e:
            logger.error(f"Error synthesizing response: {e}")
            # Fallback to simple formatting
            return self._fallback_format(tool_result)

    def _format_results(self, tool_result: ToolResult, max_chars: int) -> str:
        """Format tool results for inclusion in the synthesis prompt."""
        if tool_result.status == ToolResultStatus.ERROR:
            return f"Error: {tool_result.error}"
        
        if tool_result.data is None:
            return "No data returned"
        
        # Handle different result types
        if isinstance(tool_result.data, (dict, list)):
            try:
                formatted = json.dumps(tool_result.data, indent=2, default=str)
            except (TypeError, ValueError):
                formatted = str(tool_result.data)
        else:
            formatted = str(tool_result.data)
        
        # Truncate if too long
        if len(formatted) > max_chars:
            formatted = formatted[:max_chars] + "\n... (truncated)"
        
        return formatted

    def _fallback_format(self, tool_result: ToolResult) -> str:
        """Fallback formatting when synthesis fails."""
        if tool_result.status == ToolResultStatus.ERROR:
            return f"I encountered an error: {tool_result.error}"
        
        if tool_result.data is None:
            return "The operation completed but returned no data."
        
        # Simple formatting for common types
        if isinstance(tool_result.data, (int, float)):
            return f"The result is: {tool_result.data}"
        
        if isinstance(tool_result.data, str):
            return tool_result.data
        
        if isinstance(tool_result.data, list):
            count = len(tool_result.data)
            if count == 0:
                return "No results found."
            return f"Found {count} result(s)."
        
        if isinstance(tool_result.data, dict):
            try:
                return json.dumps(tool_result.data, indent=2, default=str)
            except (TypeError, ValueError):
                return str(tool_result.data)
        
        return str(tool_result.data)

    def format_for_context(
        self,
        tool_result: ToolResult,
        tool_description: str = "",
        synthesized_response: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Format tool results as context items for the pipeline.
        
        Args:
            tool_result: The tool execution result
            tool_description: Description of the executed tool
            synthesized_response: Optional synthesized response to include
            
        Returns:
            List of context items in pipeline-compatible format
        """
        context_items = []
        
        # Build content string
        if synthesized_response:
            content = synthesized_response
        elif tool_result.status == ToolResultStatus.ERROR:
            content = f"Error executing tool: {tool_result.error}"
        elif isinstance(tool_result.data, (int, float, str)):
            content = str(tool_result.data)
        elif isinstance(tool_result.data, (dict, list)):
            try:
                content = json.dumps(tool_result.data, indent=2, default=str)
            except (TypeError, ValueError):
                content = str(tool_result.data)
        else:
            content = str(tool_result.data) if tool_result.data else "No data"
        
        context_item = {
            "content": content,
            "metadata": {
                "tool_id": tool_result.tool_id,
                "tool_description": tool_description,
                "execution_status": tool_result.status.value,
                "execution_time_ms": tool_result.execution_time_ms,
                "source": "agent_tool",
            },
            "score": 1.0 if tool_result.status == ToolResultStatus.SUCCESS else 0.0,
        }
        
        context_items.append(context_item)
        
        # If data is a list, also add individual items
        if (
            tool_result.status == ToolResultStatus.SUCCESS 
            and isinstance(tool_result.data, list)
            and not synthesized_response  # Don't duplicate if we have synthesis
        ):
            for i, item in enumerate(tool_result.data[:10]):  # Limit to 10 items
                item_content = json.dumps(item, default=str) if isinstance(item, dict) else str(item)
                context_items.append({
                    "content": item_content,
                    "metadata": {
                        "tool_id": tool_result.tool_id,
                        "item_index": i,
                        "source": "agent_tool_item",
                    },
                    "score": 0.9,
                })
        
        return context_items
