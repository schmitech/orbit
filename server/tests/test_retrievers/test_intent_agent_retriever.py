"""
Tests for the IntentAgentRetriever and supporting agent modules.

This test suite verifies:
- Tool definitions and schema validation
- Tool executor with built-in tools (calculator, date_time, json_transform)
- Response synthesizer formatting
- IntentAgentRetriever integration
"""

import pytest
import asyncio
import sys
import os
import json
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from datetime import datetime

# Add the server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from retrievers.implementations.intent.agent.tool_definitions import (
    ToolParameter,
    ToolDefinition,
    ToolResult,
    ToolResultStatus,
    ToolExecutionConfig,
    ExecutionType,
    ParameterType,
    FunctionSchema,
)
from retrievers.implementations.intent.agent.tool_executor import ToolExecutor, BuiltinTools
from retrievers.implementations.intent.agent.response_synthesizer import ResponseSynthesizer


# ============================================================================
# TOOL DEFINITIONS TESTS
# ============================================================================

class TestToolParameter:
    """Test Pydantic tool parameter schema validation."""

    def test_valid_tool_parameter_schema(self):
        """Test that valid parameters are parsed correctly."""
        param = ToolParameter(
            name="value",
            type=ParameterType.NUMBER,
            required=True,
            description="A numeric value",
            example=100
        )
        assert param.name == "value"
        assert param.type == ParameterType.NUMBER
        assert param.required is True
        assert param.description == "A numeric value"
        assert param.example == 100

    def test_parameter_type_normalization(self):
        """Test that type strings are normalized to ParameterType enum."""
        # Test common aliases
        param_int = ToolParameter(name="test", type="int")
        assert param_int.type == ParameterType.INTEGER

        param_float = ToolParameter(name="test", type="float")
        assert param_float.type == ParameterType.NUMBER

        param_str = ToolParameter(name="test", type="str")
        assert param_str.type == ParameterType.STRING

        param_list = ToolParameter(name="test", type="list")
        assert param_list.type == ParameterType.ARRAY

    def test_parameter_default_values(self):
        """Test default values for optional fields."""
        param = ToolParameter(name="test")
        assert param.type == ParameterType.STRING
        assert param.required is False
        assert param.description == ""
        assert param.default is None

    def test_to_openai_schema(self):
        """Test conversion to OpenAI function calling format."""
        param = ToolParameter(
            name="limit",
            type=ParameterType.INTEGER,
            required=True,
            description="Maximum number of results",
            enum=[10, 20, 50, 100]
        )
        schema = param.to_openai_schema()
        
        assert schema["type"] == "integer"
        assert schema["description"] == "Maximum number of results"
        assert schema["enum"] == [10, 20, 50, 100]


class TestToolDefinition:
    """Test ToolDefinition parsing and schema generation."""

    def test_tool_definition_from_yaml(self):
        """Test creating ToolDefinition from YAML template dict."""
        template = {
            "id": "calculate_percentage",
            "version": "1.0.0",
            "description": "Calculate percentage of a value",
            "tool_type": "function",
            "function_schema": {
                "name": "calculate_percentage",
                "description": "Calculate percentage",
                "parameters": [
                    {"name": "value", "type": "number", "required": True},
                    {"name": "total", "type": "number", "required": True}
                ]
            },
            "execution": {
                "type": "builtin",
                "builtin_function": "calculator",
                "operation": "percentage"
            },
            "nl_examples": ["What percentage is 25 of 100?"],
            "tags": ["math", "percentage"]
        }
        
        tool_def = ToolDefinition.from_template(template)
        
        assert tool_def.id == "calculate_percentage"
        assert tool_def.tool_type == "function"
        assert tool_def.function_schema.name == "calculate_percentage"
        assert len(tool_def.function_schema.parameters) == 2
        assert tool_def.execution.type == ExecutionType.BUILTIN
        assert tool_def.execution.builtin_function == "calculator"
        assert tool_def.execution.operation == "percentage"

    def test_to_openai_tool(self):
        """Test conversion to OpenAI tool format."""
        tool_def = ToolDefinition(
            id="test_tool",
            function_schema=FunctionSchema(
                name="test_function",
                description="A test function",
                parameters=[
                    ToolParameter(name="input", type=ParameterType.STRING, required=True)
                ]
            ),
            execution=ToolExecutionConfig(
                type=ExecutionType.BUILTIN,
                builtin_function="test",
                operation="run"
            )
        )
        
        openai_tool = tool_def.to_openai_tool()
        
        assert openai_tool["type"] == "function"
        assert openai_tool["function"]["name"] == "test_function"
        assert "parameters" in openai_tool["function"]
        assert "input" in openai_tool["function"]["parameters"]["properties"]


class TestToolResult:
    """Test ToolResult creation and serialization."""

    def test_success_result(self):
        """Test creating a successful result."""
        result = ToolResult.success(
            data={"answer": 42},
            tool_id="test_tool",
            execution_time_ms=10.5
        )
        
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data == {"answer": 42}
        assert result.tool_id == "test_tool"
        assert result.execution_time_ms == 10.5
        assert result.error is None

    def test_error_result(self):
        """Test creating an error result."""
        result = ToolResult.create_error(
            error_msg="Division by zero",
            tool_id="calculator"
        )
        
        assert result.status == ToolResultStatus.ERROR
        assert result.error == "Division by zero"
        assert result.data is None

    def test_to_dict(self):
        """Test serialization to dictionary."""
        result = ToolResult.success(data=100, tool_id="calc")
        result_dict = result.to_dict()
        
        assert result_dict["status"] == "success"
        assert result_dict["data"] == 100
        assert result_dict["tool_id"] == "calc"


# ============================================================================
# TOOL EXECUTOR TESTS
# ============================================================================

class TestBuiltinTools:
    """Test built-in tool implementations."""

    def test_calculator_percentage(self):
        """Test percentage calculation."""
        result = BuiltinTools.calculator_percentage(25, 100)
        assert result == 25.0
        
        result = BuiltinTools.calculator_percentage(50, 200)
        assert result == 25.0

    def test_calculator_percentage_zero_total(self):
        """Test percentage with zero total raises error."""
        with pytest.raises(ValueError, match="total of 0"):
            BuiltinTools.calculator_percentage(25, 0)

    def test_calculator_add(self):
        """Test adding numbers."""
        result = BuiltinTools.calculator_add([10, 20, 30])
        assert result == 60

    def test_calculator_subtract(self):
        """Test subtraction."""
        result = BuiltinTools.calculator_subtract(100, 30)
        assert result == 70

    def test_calculator_multiply(self):
        """Test multiplication."""
        result = BuiltinTools.calculator_multiply([2, 3, 4])
        assert result == 24

    def test_calculator_divide(self):
        """Test division."""
        result = BuiltinTools.calculator_divide(100, 4)
        assert result == 25.0

    def test_calculator_divide_by_zero(self):
        """Test division by zero raises error."""
        with pytest.raises(ValueError, match="divide by zero"):
            BuiltinTools.calculator_divide(100, 0)

    def test_calculator_average(self):
        """Test average calculation."""
        result = BuiltinTools.calculator_average([10, 20, 30, 40])
        assert result == 25.0

    def test_calculator_average_empty_list(self):
        """Test average of empty list raises error."""
        with pytest.raises(ValueError, match="empty list"):
            BuiltinTools.calculator_average([])

    def test_calculator_round(self):
        """Test rounding."""
        result = BuiltinTools.calculator_round(3.14159, 2)
        assert result == 3.14

    def test_date_time_now(self):
        """Test getting current datetime."""
        result = BuiltinTools.date_time_now()
        # Should be a valid ISO format string
        parsed = datetime.fromisoformat(result)
        assert parsed is not None

    def test_date_time_format(self):
        """Test date formatting."""
        result = BuiltinTools.date_time_format("2025-01-18", "%B %d, %Y")
        assert result == "January 18, 2025"

    def test_date_time_diff(self):
        """Test date difference calculation."""
        result = BuiltinTools.date_time_diff(
            "2025-01-01", 
            "2025-01-11", 
            "days"
        )
        assert result == 10.0

    def test_date_time_add_days(self):
        """Test adding days to date."""
        result = BuiltinTools.date_time_add_days("2025-01-01", 10)
        assert "2025-01-11" in result

    def test_json_transform_filter(self):
        """Test JSON filtering."""
        data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
            {"name": "Charlie", "age": 35}
        ]
        
        result = BuiltinTools.json_transform_filter(data, "age", "gt", 28)
        assert len(result) == 2
        assert all(item["age"] > 28 for item in result)

    def test_json_transform_sort(self):
        """Test JSON sorting."""
        data = [
            {"name": "Charlie", "age": 35},
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25}
        ]
        
        result = BuiltinTools.json_transform_sort(data, "age", "asc")
        assert result[0]["age"] == 25
        assert result[2]["age"] == 35

    def test_json_transform_select(self):
        """Test JSON field selection."""
        data = [
            {"name": "Alice", "age": 30, "email": "alice@example.com"},
            {"name": "Bob", "age": 25, "email": "bob@example.com"}
        ]
        
        result = BuiltinTools.json_transform_select(data, ["name", "age"])
        assert "email" not in result[0]
        assert result[0]["name"] == "Alice"

    def test_json_transform_aggregate(self):
        """Test JSON aggregation."""
        data = [
            {"name": "Item 1", "price": 100},
            {"name": "Item 2", "price": 200},
            {"name": "Item 3", "price": 300}
        ]
        
        result_sum = BuiltinTools.json_transform_aggregate(data, "price", "sum")
        assert result_sum == 600
        
        result_avg = BuiltinTools.json_transform_aggregate(data, "price", "avg")
        assert result_avg == 200.0
        
        result_count = BuiltinTools.json_transform_aggregate(data, "price", "count")
        assert result_count == 3


class TestToolExecutor:
    """Test the ToolExecutor class."""

    @pytest.fixture
    def executor(self):
        """Create a ToolExecutor instance."""
        return ToolExecutor(http_executor=None, verbose=True)

    def test_get_available_tools(self, executor):
        """Test listing available built-in tools."""
        tools = executor.get_available_tools()
        
        assert "calculator" in tools
        assert "date_time" in tools
        assert "json_transform" in tools
        
        assert "percentage" in tools["calculator"]
        assert "now" in tools["date_time"]
        assert "filter" in tools["json_transform"]

    @pytest.mark.asyncio
    async def test_execute_builtin_calculator(self, executor):
        """Test executing a calculator tool."""
        tool_def = ToolDefinition(
            id="test_percentage",
            function_schema=FunctionSchema(
                name="percentage",
                description="Calculate percentage",
                parameters=[]
            ),
            execution=ToolExecutionConfig(
                type=ExecutionType.BUILTIN,
                builtin_function="calculator",
                operation="percentage"
            )
        )
        
        result = await executor.execute(
            tool_def, 
            {"value": 25, "total": 100}
        )
        
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data == 25.0

    @pytest.mark.asyncio
    async def test_execute_builtin_datetime_now(self, executor):
        """Test executing date_time now tool."""
        tool_def = ToolDefinition(
            id="test_now",
            function_schema=FunctionSchema(
                name="now",
                description="Get current time",
                parameters=[]
            ),
            execution=ToolExecutionConfig(
                type=ExecutionType.BUILTIN,
                builtin_function="date_time",
                operation="now"
            )
        )
        
        result = await executor.execute(tool_def, {})
        
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data is not None
        # Should be valid ISO format
        datetime.fromisoformat(result.data)

    @pytest.mark.asyncio
    async def test_execute_unknown_function_error(self, executor):
        """Test that unknown function raises error."""
        tool_def = ToolDefinition(
            id="test_unknown",
            function_schema=FunctionSchema(
                name="unknown",
                description="Unknown function",
                parameters=[]
            ),
            execution=ToolExecutionConfig(
                type=ExecutionType.BUILTIN,
                builtin_function="nonexistent_function",
                operation="test"
            )
        )
        
        result = await executor.execute(tool_def, {})
        
        assert result.status == ToolResultStatus.ERROR
        assert "Unknown built-in function" in result.error

    def test_convert_template_to_tool_definition(self, executor):
        """Test converting YAML template to ToolDefinition."""
        template = {
            "id": "add_numbers",
            "tool_type": "function",
            "function_schema": {
                "name": "add",
                "description": "Add numbers",
                "parameters": [
                    {"name": "values", "type": "array", "required": True}
                ]
            },
            "execution": {
                "type": "builtin",
                "builtin_function": "calculator",
                "operation": "add"
            }
        }
        
        tool_def = executor.convert_template_to_tool_definition(template)
        
        assert tool_def is not None
        assert tool_def.id == "add_numbers"

    def test_convert_query_template_returns_none(self, executor):
        """Test that query templates return None."""
        template = {
            "id": "some_query",
            "tool_type": "query",  # Not a function
            "endpoint_template": "/api/data"
        }
        
        tool_def = executor.convert_template_to_tool_definition(template)
        assert tool_def is None


# ============================================================================
# RESPONSE SYNTHESIZER TESTS
# ============================================================================

class TestResponseSynthesizer:
    """Test response generation from tool results."""

    @pytest.fixture
    def mock_inference_client(self):
        """Create a mock inference client."""
        client = AsyncMock()
        client.generate = AsyncMock(return_value="The calculation result is 25%.")
        return client

    @pytest.fixture
    def synthesizer(self, mock_inference_client):
        """Create a ResponseSynthesizer instance."""
        return ResponseSynthesizer(
            inference_client=mock_inference_client,
            verbose=True
        )

    @pytest.mark.asyncio
    async def test_synthesize_from_tool_results(self, synthesizer):
        """Test generating response from tool results."""
        tool_result = ToolResult.success(
            data=25.0,
            tool_id="calculate_percentage"
        )
        
        response = await synthesizer.synthesize(
            query="What percentage is 25 of 100?",
            tool_result=tool_result,
            tool_description="Calculate percentage"
        )
        
        assert "25" in response

    @pytest.mark.asyncio
    async def test_synthesize_handles_error_result(self, synthesizer, mock_inference_client):
        """Test handling error results in synthesis."""
        mock_inference_client.generate = AsyncMock(
            return_value="I encountered an error while processing your request."
        )
        
        tool_result = ToolResult.create_error(
            error_msg="Division by zero",
            tool_id="calculator"
        )
        
        response = await synthesizer.synthesize(
            query="Divide 100 by 0",
            tool_result=tool_result
        )
        
        # Should include error info in prompt
        assert response is not None

    def test_format_for_context(self, synthesizer):
        """Test formatting results as context items."""
        tool_result = ToolResult.success(
            data={"answer": 42, "unit": "percent"},
            tool_id="calculator"
        )
        
        context_items = synthesizer.format_for_context(
            tool_result=tool_result,
            tool_description="Calculate something",
            synthesized_response="The answer is 42 percent."
        )
        
        assert len(context_items) >= 1
        assert context_items[0]["content"] == "The answer is 42 percent."
        assert context_items[0]["metadata"]["tool_id"] == "calculator"
        assert context_items[0]["score"] == 1.0

    def test_format_for_context_list_data(self, synthesizer):
        """Test formatting list data as context items."""
        tool_result = ToolResult.success(
            data=[
                {"name": "Item 1", "value": 100},
                {"name": "Item 2", "value": 200}
            ],
            tool_id="query_tool"
        )
        
        context_items = synthesizer.format_for_context(tool_result=tool_result)
        
        # Should include main result and individual items
        assert len(context_items) >= 1

    def test_fallback_format_numeric(self, synthesizer):
        """Test fallback formatting for numeric results."""
        tool_result = ToolResult.success(data=42.5, tool_id="calc")
        
        formatted = synthesizer._fallback_format(tool_result)
        assert "42.5" in formatted

    def test_fallback_format_error(self, synthesizer):
        """Test fallback formatting for error results."""
        tool_result = ToolResult.create_error(
            error_msg="Something went wrong",
            tool_id="tool"
        )
        
        formatted = synthesizer._fallback_format(tool_result)
        assert "error" in formatted.lower()
        assert "Something went wrong" in formatted


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntentAgentRetrieverIntegration:
    """Integration tests for IntentAgentRetriever."""

    @pytest.fixture
    def test_config(self, tmp_path):
        """Create a test configuration for the agent retriever."""
        return {
            "datasources": {
                "http": {
                    "base_url": "http://localhost:8080",
                    "timeout": 30
                }
            },
            "general": {},
            "inference": {
                "ollama": {
                    "enabled": True,
                    "base_url": "http://localhost:11434",
                    "model": "llama3"
                }
            },
            "embedding": {
                "provider": "ollama"
            },
            "embeddings": {
                "ollama": {
                    "enabled": True,
                    "base_url": "http://localhost:11434",
                    "model": "nomic-embed-text"
                }
            },
            "stores": {
                "vector_stores": {
                    "chroma": {
                        "enabled": True,
                        "type": "chroma",
                        "connection_params": {
                            "persist_directory": str(tmp_path / "chroma_db")
                        }
                    }
                }
            },
            "adapter_config": {
                "domain_config_path": "examples/intent-templates/agent-template/domain.yaml",
                "template_library_path": ["examples/intent-templates/agent-template/tools.yaml"],
                "template_collection_name": "test_agent_tools",
                "store_name": "chroma",
                "confidence_threshold": 0.4,
                "max_templates": 5,
                "return_results": 10,
                "enable_builtin_tools": True,
                "synthesize_response": True,
                "function_output_format": "json",
                "reload_templates_on_start": False,
                "force_reload_templates": False,
                "base_url": "http://localhost:8080",
                "default_timeout": 30,
                "verbose": True
            },
            "inference_provider": "ollama"
        }

    def test_config_parsing(self, test_config):
        """Test that config is properly parsed."""
        adapter_config = test_config.get("adapter_config", {})
        
        assert adapter_config.get("enable_builtin_tools") is True
        assert adapter_config.get("synthesize_response") is True
        assert adapter_config.get("base_url") == "http://localhost:8080"

    @pytest.mark.asyncio
    async def test_tool_executor_integration(self):
        """Test full tool execution flow."""
        executor = ToolExecutor(verbose=True)
        
        # Create a percentage calculation tool
        tool_def = ToolDefinition(
            id="calc_percentage",
            function_schema=FunctionSchema(
                name="calculate_percentage",
                description="Calculate percentage",
                parameters=[
                    ToolParameter(name="value", type=ParameterType.NUMBER, required=True),
                    ToolParameter(name="total", type=ParameterType.NUMBER, required=True)
                ]
            ),
            execution=ToolExecutionConfig(
                type=ExecutionType.BUILTIN,
                builtin_function="calculator",
                operation="percentage"
            )
        )
        
        # Execute with parameters
        result = await executor.execute(
            tool_def,
            {"value": 50, "total": 200}
        )
        
        assert result.status == ToolResultStatus.SUCCESS
        assert result.data == 25.0
        assert result.execution_time_ms is not None
        assert result.execution_time_ms > 0


class TestFunctionGemmaParser:
    """Tests for FunctionGemma response parsing."""

    @pytest.fixture
    def mock_retriever(self):
        """Create a mock retriever with parser methods for testing."""
        import re
        import json

        class MockRetriever:
            """Mock retriever with just the parser methods."""

            def _parse_functiongemma_response(self, response):
                """Parse FunctionGemma's custom output format."""
                if not response:
                    return None

                # Look for the function call pattern
                pattern = r'<start_function_call>call:(\w+)\{([^}]*)\}<end_function_call>'
                match = re.search(pattern, response)

                if not match:
                    # Try without the special tokens
                    pattern_simple = r'call:(\w+)\{([^}]*)\}'
                    match = re.search(pattern_simple, response)

                if not match:
                    return None

                function_name = match.group(1)
                params_str = match.group(2)

                # Parse parameters
                arguments = {}
                if params_str:
                    param_pattern = r'(\w+):<escape>([^<]*)<escape>'
                    param_matches = re.findall(param_pattern, params_str)

                    for param_name, param_value in param_matches:
                        param_value = param_value.strip()
                        try:
                            if '.' in param_value:
                                arguments[param_name] = float(param_value)
                            else:
                                arguments[param_name] = int(param_value)
                        except ValueError:
                            if param_value.lower() == 'true':
                                arguments[param_name] = True
                            elif param_value.lower() == 'false':
                                arguments[param_name] = False
                            elif param_value.startswith('[') and param_value.endswith(']'):
                                try:
                                    arguments[param_name] = json.loads(param_value)
                                except json.JSONDecodeError:
                                    arguments[param_name] = param_value
                            else:
                                arguments[param_name] = param_value

                    if not arguments and ':' in params_str:
                        simple_pattern = r'(\w+):([^,}]+)'
                        simple_matches = re.findall(simple_pattern, params_str)
                        for param_name, param_value in simple_matches:
                            param_value = param_value.strip()
                            try:
                                if '.' in param_value:
                                    arguments[param_name] = float(param_value)
                                else:
                                    arguments[param_name] = int(param_value)
                            except ValueError:
                                arguments[param_name] = param_value

                return {"name": function_name, "arguments": arguments}

            def _build_functiongemma_prompt(self, query, tools):
                """Build a prompt in FunctionGemma's expected format."""
                tool_json = json.dumps(tools, indent=2)
                prompt = f"""<start_of_turn>developer
You are a model that can do function calling with the following functions:

{tool_json}

Based on the user's query, call the appropriate function with the correct parameters.
Output format: <start_function_call>call:function_name{{param:<escape>value<escape>}}<end_function_call>
<end_of_turn>
<start_of_turn>user
{query}
<end_of_turn>
<start_of_turn>model
"""
                return prompt

        return MockRetriever()

    def test_parse_functiongemma_basic_response(self, mock_retriever):
        """Test parsing a basic FunctionGemma response."""
        response = "<start_function_call>call:get_current_temperature{location:<escape>London<escape>}<end_function_call>"
        result = mock_retriever._parse_functiongemma_response(response)

        assert result is not None
        assert result["name"] == "get_current_temperature"
        assert result["arguments"]["location"] == "London"

    def test_parse_functiongemma_numeric_params(self, mock_retriever):
        """Test parsing numeric parameters."""
        response = "<start_function_call>call:calculate_percentage{value:<escape>25<escape>,total:<escape>100<escape>}<end_function_call>"
        result = mock_retriever._parse_functiongemma_response(response)

        assert result is not None
        assert result["name"] == "calculate_percentage"
        assert result["arguments"]["value"] == 25
        assert result["arguments"]["total"] == 100

    def test_parse_functiongemma_float_params(self, mock_retriever):
        """Test parsing float parameters."""
        response = "<start_function_call>call:divide_numbers{a:<escape>100.5<escape>,b:<escape>2.5<escape>}<end_function_call>"
        result = mock_retriever._parse_functiongemma_response(response)

        assert result is not None
        assert result["name"] == "divide_numbers"
        assert result["arguments"]["a"] == 100.5
        assert result["arguments"]["b"] == 2.5

    def test_parse_functiongemma_no_params(self, mock_retriever):
        """Test parsing function call with no parameters."""
        response = "<start_function_call>call:get_current_datetime{}<end_function_call>"
        result = mock_retriever._parse_functiongemma_response(response)

        assert result is not None
        assert result["name"] == "get_current_datetime"
        assert result["arguments"] == {}

    def test_parse_functiongemma_without_special_tokens(self, mock_retriever):
        """Test parsing when special tokens are stripped."""
        response = "call:add_numbers{values:<escape>[10, 20, 30]<escape>}"
        result = mock_retriever._parse_functiongemma_response(response)

        assert result is not None
        assert result["name"] == "add_numbers"
        assert result["arguments"]["values"] == [10, 20, 30]

    def test_parse_functiongemma_invalid_response(self, mock_retriever):
        """Test parsing invalid response returns None."""
        response = "I don't understand that query."
        result = mock_retriever._parse_functiongemma_response(response)

        assert result is None

    def test_parse_functiongemma_empty_response(self, mock_retriever):
        """Test parsing empty response returns None."""
        result = mock_retriever._parse_functiongemma_response("")
        assert result is None

        result = mock_retriever._parse_functiongemma_response(None)
        assert result is None

    def test_build_functiongemma_prompt(self, mock_retriever):
        """Test building FunctionGemma-style prompt."""
        tools = [{
            "type": "function",
            "function": {
                "name": "get_temperature",
                "description": "Get temperature for a location",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City name"}
                    },
                    "required": ["location"]
                }
            }
        }]

        prompt = mock_retriever._build_functiongemma_prompt("What's the weather in Paris?", tools)

        # Check essential parts of the prompt
        assert "<start_of_turn>developer" in prompt
        assert "function calling" in prompt
        assert "get_temperature" in prompt
        assert "<start_of_turn>user" in prompt
        assert "What's the weather in Paris?" in prompt
        assert "<start_of_turn>model" in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
