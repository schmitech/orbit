"""
Pydantic models for tool/function definitions in agent templates.

These schemas define the structure for YAML-defined tools, including
parameter validation, execution configuration, and result formatting.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class ParameterType(str, Enum):
    """Supported parameter types for tool functions."""
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


class ToolParameter(BaseModel):
    """Definition of a single tool parameter."""
    
    name: str = Field(..., description="Parameter name")
    type: ParameterType = Field(default=ParameterType.STRING, description="Parameter data type")
    required: bool = Field(default=False, description="Whether parameter is required")
    description: str = Field(default="", description="Human-readable description")
    default: Optional[Any] = Field(default=None, description="Default value if not provided")
    enum: Optional[List[Any]] = Field(default=None, description="Allowed values")
    min: Optional[Union[int, float]] = Field(default=None, description="Minimum value for numbers")
    max: Optional[Union[int, float]] = Field(default=None, description="Maximum value for numbers")
    example: Optional[Any] = Field(default=None, description="Example value")

    @field_validator('type', mode='before')
    @classmethod
    def normalize_type(cls, v: Any) -> ParameterType:
        """Normalize type strings to ParameterType enum."""
        if isinstance(v, ParameterType):
            return v
        if isinstance(v, str):
            v_lower = v.lower()
            # Handle common aliases
            type_map = {
                'str': ParameterType.STRING,
                'int': ParameterType.INTEGER,
                'float': ParameterType.NUMBER,
                'num': ParameterType.NUMBER,
                'bool': ParameterType.BOOLEAN,
                'list': ParameterType.ARRAY,
                'dict': ParameterType.OBJECT,
            }
            if v_lower in type_map:
                return type_map[v_lower]
            try:
                return ParameterType(v_lower)
            except ValueError:
                logger.warning(f"Unknown parameter type '{v}', defaulting to string")
                return ParameterType.STRING
        return ParameterType.STRING

    def to_openai_schema(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling parameter schema."""
        schema: Dict[str, Any] = {
            "type": self.type.value,
            "description": self.description or self.name,
        }
        if self.enum:
            schema["enum"] = self.enum
        if self.default is not None:
            schema["default"] = self.default
        return schema


class ExecutionType(str, Enum):
    """Types of tool execution."""
    BUILTIN = "builtin"
    HTTP_CALL = "http_call"


class ToolExecutionConfig(BaseModel):
    """Configuration for how a tool should be executed."""
    
    type: ExecutionType = Field(..., description="Execution type")
    builtin_function: Optional[str] = Field(
        default=None, 
        description="Name of built-in function (calculator, date_time, json_transform)"
    )
    operation: Optional[str] = Field(
        default=None, 
        description="Specific operation within the builtin function"
    )
    # HTTP execution fields (reuses parent HTTP logic)
    http_method: Optional[str] = Field(default="GET", description="HTTP method")
    endpoint_template: Optional[str] = Field(default=None, description="URL endpoint template")
    headers: Optional[Dict[str, str]] = Field(default=None, description="Request headers")
    query_params: Optional[Dict[str, str]] = Field(default=None, description="Query parameters")
    body_template: Optional[Dict[str, Any]] = Field(default=None, description="Request body template")

    @field_validator('type', mode='before')
    @classmethod
    def normalize_type(cls, v: Any) -> ExecutionType:
        """Normalize execution type strings."""
        if isinstance(v, ExecutionType):
            return v
        if isinstance(v, str):
            try:
                return ExecutionType(v.lower())
            except ValueError:
                logger.warning(f"Unknown execution type '{v}', defaulting to builtin")
                return ExecutionType.BUILTIN
        return ExecutionType.BUILTIN


class FunctionSchema(BaseModel):
    """Schema for a function/tool definition."""
    
    name: str = Field(..., description="Function name")
    description: str = Field(default="", description="Function description")
    parameters: List[ToolParameter] = Field(default_factory=list, description="Function parameters")

    def to_openai_schema(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling schema format."""
        properties = {}
        required = []
        
        for param in self.parameters:
            properties[param.name] = param.to_openai_schema()
            if param.required:
                required.append(param.name)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                }
            }
        }


class ToolDefinition(BaseModel):
    """Complete definition of a tool from YAML template."""
    
    id: str = Field(..., description="Unique tool identifier")
    version: str = Field(default="1.0.0", description="Tool version")
    description: str = Field(default="", description="Tool description")
    tool_type: str = Field(default="function", description="Type identifier (function)")
    function_schema: FunctionSchema = Field(..., description="Function schema")
    execution: ToolExecutionConfig = Field(..., description="Execution configuration")
    nl_examples: List[str] = Field(default_factory=list, description="Natural language examples")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")
    semantic_tags: Optional[Dict[str, Any]] = Field(default=None, description="Semantic metadata")

    @classmethod
    def from_template(cls, template: Dict[str, Any]) -> "ToolDefinition":
        """Create ToolDefinition from a YAML template dictionary."""
        # Parse function_schema
        func_schema_data = template.get('function_schema', {})
        parameters = [
            ToolParameter(**p) for p in func_schema_data.get('parameters', [])
        ]
        function_schema = FunctionSchema(
            name=func_schema_data.get('name', template.get('id', 'unknown')),
            description=func_schema_data.get('description', template.get('description', '')),
            parameters=parameters,
        )
        
        # Parse execution config
        exec_data = template.get('execution', {})
        execution = ToolExecutionConfig(**exec_data)
        
        return cls(
            id=template.get('id', 'unknown'),
            version=template.get('version', '1.0.0'),
            description=template.get('description', ''),
            tool_type=template.get('tool_type', 'function'),
            function_schema=function_schema,
            execution=execution,
            nl_examples=template.get('nl_examples', []),
            tags=template.get('tags', []),
            semantic_tags=template.get('semantic_tags'),
        )

    def to_openai_tool(self) -> Dict[str, Any]:
        """Convert to OpenAI tool format for function calling."""
        return self.function_schema.to_openai_schema()


class ToolResultStatus(str, Enum):
    """Status of tool execution."""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    INVALID_PARAMS = "invalid_params"


class ToolResult(BaseModel):
    """Result of a tool execution."""
    
    status: ToolResultStatus = Field(..., description="Execution status")
    data: Optional[Any] = Field(default=None, description="Result data")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    tool_id: str = Field(default="", description="ID of executed tool")
    execution_time_ms: Optional[float] = Field(default=None, description="Execution time in ms")

    @classmethod
    def success(cls, data: Any, tool_id: str = "", execution_time_ms: float = None) -> "ToolResult":
        """Create a successful result."""
        return cls(
            status=ToolResultStatus.SUCCESS,
            data=data,
            tool_id=tool_id,
            execution_time_ms=execution_time_ms,
        )

    @classmethod
    def create_error(cls, error_msg: str, tool_id: str = "") -> "ToolResult":
        """Create an error result."""
        return cls(
            status=ToolResultStatus.ERROR,
            error=error_msg,
            tool_id=tool_id,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "status": self.status.value,
            "data": self.data,
            "error": self.error,
            "tool_id": self.tool_id,
            "execution_time_ms": self.execution_time_ms,
        }
