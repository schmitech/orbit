"""
Tool executor for built-in and HTTP-based tool execution.

This module provides the ToolExecutor class that handles execution of
YAML-defined tools, including built-in operations (calculator, date_time,
json_transform) and HTTP calls.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Union

from .tool_definitions import (
    ExecutionType,
    ToolDefinition,
    ToolResult,
)

logger = logging.getLogger(__name__)


class BuiltinTools:
    """
    Collection of built-in tool implementations.
    
    Provides calculator, date_time, and json_transform operations
    that can be executed without external API calls.
    """

    # ========================================================================
    # CALCULATOR OPERATIONS
    # ========================================================================

    @staticmethod
    def calculator_percentage(value: Union[int, float], total: Union[int, float]) -> float:
        """Calculate what percentage value is of total."""
        if total == 0:
            raise ValueError("Cannot calculate percentage with total of 0")
        return (value / total) * 100

    @staticmethod
    def calculator_add(values: List[Union[int, float]]) -> Union[int, float]:
        """Add a list of numbers."""
        return sum(values)

    @staticmethod
    def calculator_subtract(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
        """Subtract b from a."""
        return a - b

    @staticmethod
    def calculator_multiply(values: List[Union[int, float]]) -> Union[int, float]:
        """Multiply a list of numbers."""
        result = 1
        for v in values:
            result *= v
        return result

    @staticmethod
    def calculator_divide(a: Union[int, float], b: Union[int, float]) -> float:
        """Divide a by b."""
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b

    @staticmethod
    def calculator_average(values: List[Union[int, float]]) -> float:
        """Calculate average of a list of numbers."""
        if not values:
            raise ValueError("Cannot calculate average of empty list")
        return sum(values) / len(values)

    @staticmethod
    def calculator_round(value: Union[int, float], decimals: int = 0) -> Union[int, float]:
        """Round a number to specified decimal places."""
        return round(value, decimals)

    # ========================================================================
    # DATE/TIME OPERATIONS
    # ========================================================================

    @staticmethod
    def _parse_date_flexible(date_string: str) -> datetime:
        """
        Flexibly parse a date string in various formats.

        Handles:
        - ISO format: 2025-01-01, 2025-01-01T00:00:00
        - Non-zero-padded: 2025-1-1, 2025-12-31
        - Slash format: 2025/01/01, 2025/1/1
        - Other common formats

        Args:
            date_string: Date string to parse

        Returns:
            datetime object
        """
        # Clean up the string
        date_string = str(date_string).strip()

        # Handle Z timezone marker
        date_string = date_string.replace('Z', '+00:00')

        # Try ISO format first (handles timezone-aware strings)
        try:
            return datetime.fromisoformat(date_string)
        except ValueError:
            pass

        # Try common formats (including non-zero-padded)
        formats = [
            "%Y-%m-%d",           # 2025-01-01
            "%Y-%m-%d %H:%M:%S",  # 2025-01-01 00:00:00
            "%Y-%m-%dT%H:%M:%S",  # 2025-01-01T00:00:00
            "%Y/%m/%d",           # 2025/01/01
            "%Y/%m/%d %H:%M:%S",  # 2025/01/01 00:00:00
            "%d-%m-%Y",           # 01-01-2025
            "%d/%m/%Y",           # 01/01/2025
            "%m-%d-%Y",           # 01-01-2025
            "%m/%d/%Y",           # 01/01/2025
            "%B %d, %Y",          # January 1, 2025
            "%b %d, %Y",          # Jan 1, 2025
            "%d %B %Y",           # 1 January 2025
            "%d %b %Y",           # 1 Jan 2025
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_string, fmt)
            except ValueError:
                continue

        # Try to normalize non-zero-padded dates like "2025-1-1" to "2025-01-01"
        # This handles cases where month/day are single digits

        # Match patterns like 2025-1-1 or 2025-1-31
        match = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})(.*)$', date_string)
        if match:
            year, month, day, rest = match.groups()
            normalized = f"{year}-{int(month):02d}-{int(day):02d}{rest}"
            try:
                return datetime.fromisoformat(normalized)
            except ValueError:
                pass

        # Match patterns like 2025/1/1
        match = re.match(r'^(\d{4})/(\d{1,2})/(\d{1,2})(.*)$', date_string)
        if match:
            year, month, day, rest = match.groups()
            normalized = f"{year}-{int(month):02d}-{int(day):02d}"
            try:
                return datetime.fromisoformat(normalized)
            except ValueError:
                pass

        raise ValueError(f"Could not parse date string: {date_string}")

    @staticmethod
    def date_time_now() -> str:
        """Get current datetime as ISO string."""
        return datetime.now().isoformat()

    @staticmethod
    def date_time_format(date: str, format_string: str) -> str:
        """Format a date string according to the specified format."""
        dt = BuiltinTools._parse_date_flexible(date)
        return dt.strftime(format_string)

    @staticmethod
    def date_time_diff(date1: str, date2: str, unit: str = "days") -> float:
        """Calculate difference between two dates."""
        dt1 = BuiltinTools._parse_date_flexible(date1)
        dt2 = BuiltinTools._parse_date_flexible(date2)
        delta = dt2 - dt1

        unit_map = {
            "seconds": delta.total_seconds(),
            "minutes": delta.total_seconds() / 60,
            "hours": delta.total_seconds() / 3600,
            "days": delta.days + delta.seconds / 86400,
            "weeks": (delta.days + delta.seconds / 86400) / 7,
        }
        return unit_map.get(unit, delta.days)

    @staticmethod
    def date_time_add_days(date: str, days: int) -> str:
        """Add days to a date."""
        dt = BuiltinTools._parse_date_flexible(date)
        result = dt + timedelta(days=days)
        return result.isoformat()

    @staticmethod
    def date_time_parse(date_string: str, format_string: str = None) -> str:
        """Parse a date string and return ISO format."""
        if format_string:
            dt = datetime.strptime(date_string, format_string)
        else:
            dt = BuiltinTools._parse_date_flexible(date_string)
        return dt.isoformat()

    # ========================================================================
    # JSON TRANSFORM OPERATIONS
    # ========================================================================

    @staticmethod
    def _validate_data_array(data: Any, operation_name: str) -> List[Dict[str, Any]]:
        """
        Validate that data is a list of dictionaries.

        Args:
            data: The data to validate
            operation_name: Name of the operation for error messages

        Returns:
            The validated data as List[Dict]

        Raises:
            ValueError: If data is not a valid array of objects
        """
        if not isinstance(data, list):
            raise ValueError(
                f"json_transform.{operation_name} requires 'data' to be an array of objects, "
                f"but received {type(data).__name__}: {str(data)[:100]}"
            )

        if not data:
            return []

        # Check if first element is a dict (assumes homogeneous array)
        if not isinstance(data[0], dict):
            raise ValueError(
                f"json_transform.{operation_name} requires 'data' to be an array of objects "
                f"(e.g., [{{'name': 'item1', 'price': 10}}, ...]), but received an array of "
                f"{type(data[0]).__name__} values: {str(data)[:100]}. "
                f"These operations work on structured data with fields, not primitive arrays."
            )

        return data

    @staticmethod
    def json_transform_filter(
        data: List[Dict[str, Any]],
        field: str,
        operator: str,
        value: Any
    ) -> List[Dict[str, Any]]:
        """Filter an array by condition."""
        data = BuiltinTools._validate_data_array(data, "filter")

        operators = {
            "eq": lambda x, v: x == v,
            "ne": lambda x, v: x != v,
            "gt": lambda x, v: x > v,
            "gte": lambda x, v: x >= v,
            "lt": lambda x, v: x < v,
            "lte": lambda x, v: x <= v,
            "contains": lambda x, v: v in str(x),
            "startswith": lambda x, v: str(x).startswith(str(v)),
            "endswith": lambda x, v: str(x).endswith(str(v)),
            "in": lambda x, v: x in v,
        }

        op_func = operators.get(operator, operators["eq"])
        return [item for item in data if field in item and op_func(item[field], value)]

    @staticmethod
    def json_transform_sort(
        data: List[Dict[str, Any]],
        field: str,
        order: str = "asc"
    ) -> List[Dict[str, Any]]:
        """Sort an array by field."""
        data = BuiltinTools._validate_data_array(data, "sort")

        if not data:
            return []

        reverse = order.lower() in ("desc", "descending")
        return sorted(data, key=lambda x: x.get(field, ""), reverse=reverse)

    @staticmethod
    def json_transform_select(
        data: List[Dict[str, Any]],
        fields: List[str]
    ) -> List[Dict[str, Any]]:
        """Select specific fields from each item."""
        data = BuiltinTools._validate_data_array(data, "select")
        return [{k: v for k, v in item.items() if k in fields} for item in data]

    @staticmethod
    def json_transform_aggregate(
        data: List[Dict[str, Any]],
        field: str,
        operation: str
    ) -> Union[int, float]:
        """Aggregate values from a field."""
        data = BuiltinTools._validate_data_array(data, "aggregate")

        valid_operations = ["sum", "avg", "count", "min", "max"]
        if operation not in valid_operations:
            raise ValueError(
                f"Unknown aggregation operation: '{operation}'. "
                f"Valid operations are: {valid_operations}"
            )

        values = [item.get(field, 0) for item in data if field in item]

        if operation == "sum":
            return sum(values)
        elif operation == "avg":
            return sum(values) / len(values) if values else 0
        elif operation == "count":
            return len(values)
        elif operation == "min":
            return min(values) if values else 0
        elif operation == "max":
            return max(values) if values else 0
        else:
            raise ValueError(f"Unknown aggregation operation: {operation}")


class ToolExecutor:
    """
    Executes tools defined in YAML templates.
    
    Supports:
    - Built-in tools (calculator, date_time, json_transform)
    - HTTP calls (delegated to parent retriever)
    """

    def __init__(self, http_executor: Optional[Callable] = None, verbose: bool = False):
        """
        Initialize the tool executor.
        
        Args:
            http_executor: Optional callback for HTTP execution (from parent retriever)
            verbose: Enable verbose logging
        """
        self.http_executor = http_executor
        self.verbose = verbose
        self._builtin_tools = BuiltinTools()
        
        # Map of builtin function names to their operation handlers
        self._builtin_registry: Dict[str, Dict[str, Callable]] = {
            "calculator": {
                "percentage": self._builtin_tools.calculator_percentage,
                "add": self._builtin_tools.calculator_add,
                "subtract": self._builtin_tools.calculator_subtract,
                "multiply": self._builtin_tools.calculator_multiply,
                "divide": self._builtin_tools.calculator_divide,
                "average": self._builtin_tools.calculator_average,
                "round": self._builtin_tools.calculator_round,
            },
            "date_time": {
                "now": self._builtin_tools.date_time_now,
                "format": self._builtin_tools.date_time_format,
                "diff": self._builtin_tools.date_time_diff,
                "add_days": self._builtin_tools.date_time_add_days,
                "parse": self._builtin_tools.date_time_parse,
            },
            "json_transform": {
                "filter": self._builtin_tools.json_transform_filter,
                "sort": self._builtin_tools.json_transform_sort,
                "select": self._builtin_tools.json_transform_select,
                "aggregate": self._builtin_tools.json_transform_aggregate,
            },
        }

    def get_available_tools(self) -> Dict[str, List[str]]:
        """Return available built-in tools and their operations."""
        return {
            name: list(ops.keys()) 
            for name, ops in self._builtin_registry.items()
        }

    async def execute(
        self, 
        tool_definition: ToolDefinition, 
        parameters: Dict[str, Any]
    ) -> ToolResult:
        """
        Execute a tool with the given parameters.
        
        Args:
            tool_definition: The tool definition from YAML
            parameters: Extracted parameters for execution
            
        Returns:
            ToolResult with execution status and data
        """
        start_time = time.time()
        tool_id = tool_definition.id
        
        try:
            execution_config = tool_definition.execution
            
            if self.verbose:
                logger.debug(f"Executing tool '{tool_id}' with params: {parameters}")
            
            if execution_config.type == ExecutionType.BUILTIN:
                result_data = self._execute_builtin(
                    execution_config.builtin_function,
                    execution_config.operation,
                    parameters,
                )
            elif execution_config.type == ExecutionType.HTTP_CALL:
                result_data = await self._execute_http(tool_definition, parameters)
            else:
                return ToolResult.create_error(
                    f"Unknown execution type: {execution_config.type}",
                    tool_id=tool_id,
                )
            
            execution_time = (time.time() - start_time) * 1000
            
            if self.verbose:
                logger.debug(f"Tool '{tool_id}' completed in {execution_time:.2f}ms")
            
            return ToolResult.success(
                data=result_data,
                tool_id=tool_id,
                execution_time_ms=execution_time,
            )
            
        except Exception as e:
            logger.error(f"Error executing tool '{tool_id}': {e}")
            return ToolResult.create_error(str(e), tool_id=tool_id)

    def _coerce_value(self, value: Any) -> Any:
        """Coerce a value to appropriate numeric type if possible."""
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            # Try to convert string to number
            try:
                if '.' in value:
                    return float(value)
                return int(value)
            except ValueError:
                return value
        if isinstance(value, list):
            # Recursively coerce list elements
            return [self._coerce_value(v) for v in value]
        if isinstance(value, dict):
            # Recursively coerce dict values
            return {k: self._coerce_value(v) for k, v in value.items()}
        return value

    def _execute_builtin(
        self,
        function_name: str,
        operation: str,
        parameters: Dict[str, Any]
    ) -> Any:
        """Execute a built-in tool operation."""
        if function_name not in self._builtin_registry:
            raise ValueError(f"Unknown built-in function: {function_name}")

        operations = self._builtin_registry[function_name]

        if operation not in operations:
            available = list(operations.keys())
            raise ValueError(
                f"Unknown operation '{operation}' for {function_name}. "
                f"Available: {available}"
            )

        func = operations[operation]

        # Coerce parameter values to appropriate types
        parameters = {k: self._coerce_value(v) for k, v in parameters.items()}

        # Get function signature to map parameters correctly
        import inspect
        sig = inspect.signature(func)
        param_names = list(sig.parameters.keys())

        # Identify which parameters are required (no default value)
        required_params = [
            name for name, param in sig.parameters.items()
            if param.default is inspect.Parameter.empty
        ]

        if self.verbose:
            logger.debug(f"Function {function_name}.{operation} expects params: {param_names}")
            logger.debug(f"Required params (no defaults): {required_params}")
            logger.debug(f"Received parameters (after coercion): {parameters}")

        # Build kwargs from parameters
        kwargs = {}
        for name in param_names:
            if name in parameters:
                kwargs[name] = parameters[name]

        # Handle special cases for functions with no required params
        if not param_names:
            return func()

        # Check for missing REQUIRED parameters (those without defaults)
        missing_required = [p for p in required_params if p not in kwargs]
        if missing_required:
            # Try to map parameters by position if names don't match
            # This handles cases where LLM uses different parameter names
            param_values = list(parameters.values())
            if len(param_values) >= len(required_params):
                logger.info("Parameter names don't match, attempting positional mapping")
                for i, name in enumerate(param_names):
                    if name not in kwargs and i < len(param_values):
                        kwargs[name] = param_values[i]
                        logger.debug(f"Mapped positional value {param_values[i]} to parameter '{name}'")

            # Check again after positional mapping - only required params
            still_missing = [p for p in required_params if p not in kwargs]
            if still_missing:
                raise ValueError(
                    f"Missing required parameters for {function_name}.{operation}: {still_missing}. "
                    f"Required: {required_params}, Got: {list(parameters.keys())}"
                )

        if self.verbose:
            logger.debug(f"Calling {function_name}.{operation} with kwargs: {kwargs}")

        return func(**kwargs)

    async def _execute_http(
        self, 
        tool_definition: ToolDefinition, 
        parameters: Dict[str, Any]
    ) -> Any:
        """Execute an HTTP-based tool (delegates to parent retriever)."""
        if not self.http_executor:
            raise ValueError(
                "HTTP executor not configured. Cannot execute HTTP tools."
            )
        
        execution_config = tool_definition.execution
        
        # Build HTTP template dict for parent execution
        http_template = {
            'id': tool_definition.id,
            'http_method': execution_config.http_method or 'GET',
            'endpoint_template': execution_config.endpoint_template,
            'headers': execution_config.headers or {},
            'query_params': execution_config.query_params or {},
        }
        
        if execution_config.body_template:
            http_template['body_template'] = execution_config.body_template
        
        # Call the HTTP executor (from parent retriever)
        results, error = await self.http_executor(http_template, parameters)
        
        if error:
            raise ValueError(f"HTTP execution failed: {error}")
        
        return results

    def convert_template_to_tool_definition(
        self, 
        template: Dict[str, Any]
    ) -> Optional[ToolDefinition]:
        """
        Convert a YAML template dict to a ToolDefinition.
        
        Args:
            template: Template dictionary from YAML
            
        Returns:
            ToolDefinition if template is a function tool, None otherwise
        """
        tool_type = template.get('tool_type', 'query')
        
        if tool_type != 'function':
            return None
        
        try:
            return ToolDefinition.from_template(template)
        except Exception as e:
            logger.error(f"Failed to parse tool definition: {e}")
            return None

    def build_openai_tools(
        self, 
        tool_definitions: List[ToolDefinition]
    ) -> List[Dict[str, Any]]:
        """
        Convert tool definitions to OpenAI function calling format.
        
        Args:
            tool_definitions: List of tool definitions
            
        Returns:
            List of OpenAI-compatible tool schemas
        """
        return [tool.to_openai_tool() for tool in tool_definitions]
