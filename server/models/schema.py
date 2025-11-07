"""
Pydantic models for the API
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, model_validator


class ChatMessage(BaseModel):
    """Chat message model"""
    message: str
    stream: bool = Field(default=True, description="Whether to stream the response")


class HealthStatus(BaseModel):
    """Health status model"""
    status: str = Field(description="Overall health status of the server")


class ApiKeyCreate(BaseModel):
    """API key creation request model"""
    client_name: str
    notes: Optional[str] = None
    system_prompt_id: Optional[str] = None
    adapter_name: str  # Required adapter name
    
    @model_validator(mode='before')
    @classmethod
    def validate_adapter(cls, values):
        """Validate that adapter_name is provided"""
        if isinstance(values, dict):
            if not values.get('adapter_name'):
                raise ValueError('adapter_name must be provided')
        return values


class ApiKeyResponse(BaseModel):
    """API key response model"""
    api_key: str
    client_name: str
    notes: Optional[str] = None
    created_at: float  # This expects a Unix timestamp
    active: bool = True
    system_prompt_id: Optional[str] = None
    adapter_name: Optional[str] = None


class ApiKeyDeactivate(BaseModel):
    """API key deactivation request model"""
    api_key: str


class SystemPromptCreate(BaseModel):
    """System prompt creation request model"""
    name: str
    prompt: str
    version: str = "1.0"


class SystemPromptUpdate(BaseModel):
    """System prompt update request model"""
    prompt: str
    version: Optional[str] = None


class SystemPromptResponse(BaseModel):
    """System prompt response model"""
    id: str
    name: str
    prompt: str
    version: str
    created_at: float  # Unix timestamp
    updated_at: float  # Unix timestamp


class ApiKeyPromptAssociate(BaseModel):
    """API key and system prompt association request model"""
    prompt_id: str


class ChatHistoryClearResponse(BaseModel):
    """Response model for chat history clear operation"""
    status: str
    message: str
    session_id: str
    deleted_count: int
    timestamp: str


class AdapterReloadResponse(BaseModel):
    """Response model for adapter reload operation"""
    status: str
    message: str
    summary: Dict[str, Any]
    timestamp: str


class MCPMessage(BaseModel):
    """MCP protocol message model"""
    id: str = Field(description="Unique identifier for the message")
    object: str = Field(default="thread.message", description="Object type")
    role: str = Field(description="Role of the message (user or assistant)")
    content: List[Dict[str, Any]] = Field(description="Content of the message")
    created_at: int = Field(default=0, description="Unix timestamp when message was created")
    

class MCPChatRequest(BaseModel):
    """MCP protocol chat request model"""
    messages: List[MCPMessage] = Field(description="Messages in the conversation")
    stream: bool = Field(default=True, description="Whether to stream the response")
    

class MCPChatResponse(BaseModel):
    """MCP protocol chat response model"""
    id: str = Field(description="Unique identifier for the response")
    object: str = Field(default="thread.message", description="Object type")
    created_at: int = Field(description="Unix timestamp when response was created")
    role: str = Field(default="assistant", description="Role of the message")
    content: List[Dict[str, Any]] = Field(description="Content of the response")
    

class MCPChatChunk(BaseModel):
    """MCP protocol streaming chunk model"""
    id: str = Field(description="Unique identifier for the chunk")
    object: str = Field(default="thread.message.delta", description="Object type")
    created_at: int = Field(description="Unix timestamp when chunk was created")
    delta: Dict[str, Any] = Field(description="Delta content for streaming")


class MCPJsonRpcRequest(BaseModel):
    """JSON-RPC 2.0 request model for Anthropic's MCP protocol"""
    jsonrpc: str = Field(default="2.0", description="JSON-RPC version")
    method: str = Field(description="Method name to invoke")
    params: Dict[str, Any] = Field(description="Method parameters")
    id: str = Field(description="Unique identifier for the request")


class MCPJsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 response model for Anthropic's MCP protocol"""
    jsonrpc: str = Field(default="2.0", description="JSON-RPC version")
    result: Optional[Dict[str, Any]] = Field(default=None, description="Result object")
    error: Optional[Dict[str, Any]] = Field(default=None, description="Error object")
    id: str = Field(description="Request identifier that this is a response to")


class MCPJsonRpcError(BaseModel):
    """JSON-RPC 2.0 error model for Anthropic's MCP protocol"""
    code: int = Field(description="Error code")
    message: str = Field(description="Error message")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Additional error data")
