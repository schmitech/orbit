"""
Pydantic models for the API
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, model_validator


class ChatMessage(BaseModel):
    """Chat message model"""
    message: str
    stream: bool = Field(default=True, description="Whether to stream the response")


class AllowedModel(BaseModel):
    """A single model option allowed for an adapter."""
    name: str
    provider: str
    model: str


class AdapterModelsResponse(BaseModel):
    """Response listing models available for an adapter."""
    adapter_name: str
    models: List[AllowedModel]
    has_restrictions: bool


class SkillInfo(BaseModel):
    """Metadata for a skill exposed by an adapter."""
    name: str
    description: str
    adapter_name: str
    enabled: bool


class SkillsResponse(BaseModel):
    """Response listing all registered skills."""
    skills: List[SkillInfo]


class AdapterSkillsResponse(BaseModel):
    """Response listing skills available to a specific adapter."""
    adapter_name: str
    available_skills: List[str]


class HealthStatus(BaseModel):
    """Health status model"""
    status: str = Field(description="Overall health status of the server")


class ApiKeyCreate(BaseModel):
    """API key creation request model"""
    client_name: str
    notes: Optional[str] = Field(default=None, max_length=2000)
    system_prompt_id: Optional[str] = None
    adapter_name: str  # Required adapter name
    allowed_user_ids: Optional[List[str]] = None  # Restrict to these ORBIT user ids; None/empty = unrestricted
    allowed_emails: Optional[List[str]] = None  # Restrict to these authenticated email addresses

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
    allowed_user_ids: Optional[List[str]] = None
    allowed_emails: Optional[List[str]] = None


class ApiKeyUpdate(BaseModel):
    """API key metadata update request model"""
    client_name: str = Field(min_length=1, max_length=100)
    adapter_name: str = Field(min_length=1)
    system_prompt_id: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=2000)
    allowed_user_ids: Optional[List[str]] = None
    allowed_emails: Optional[List[str]] = None


class ApiKeyDeactivate(BaseModel):
    """API key deactivation request model"""
    api_key: str


class ApiKeyRename(BaseModel):
    """API key rename request model"""
    new_api_key: str = Field(min_length=8, description="New API key value")


class ApiKeyQuota(BaseModel):
    """Quota configuration for an API key"""
    daily_limit: Optional[int] = Field(default=None, description="Daily request limit (None = unlimited)")
    monthly_limit: Optional[int] = Field(default=None, description="Monthly request limit (None = unlimited)")
    throttle_enabled: bool = Field(default=True, description="Enable throttling for this key")
    throttle_priority: int = Field(default=5, ge=1, le=10, description="Priority 1-10, lower = less delay")


class ApiKeyQuotaUpdate(BaseModel):
    """Request model for updating API key quota"""
    daily_limit: Optional[int] = Field(default=None, description="Daily request limit (None = unlimited)")
    monthly_limit: Optional[int] = Field(default=None, description="Monthly request limit (None = unlimited)")
    throttle_enabled: Optional[bool] = Field(default=None, description="Enable throttling for this key")
    throttle_priority: Optional[int] = Field(default=None, ge=1, le=10, description="Priority 1-10")


class ApiKeyUsage(BaseModel):
    """Current usage statistics for an API key"""
    daily_used: int = Field(default=0, description="Requests used today")
    monthly_used: int = Field(default=0, description="Requests used this month")
    daily_reset_at: float = Field(description="Unix timestamp of daily reset")
    monthly_reset_at: float = Field(description="Unix timestamp of monthly reset")
    last_request_at: Optional[float] = Field(default=None, description="Unix timestamp of last request")


class ApiKeyQuotaResponse(BaseModel):
    """Response model for quota status endpoint"""
    api_key_masked: str = Field(description="Masked API key for display")
    quota: ApiKeyQuota = Field(description="Quota configuration")
    usage: ApiKeyUsage = Field(description="Current usage statistics")
    daily_remaining: Optional[int] = Field(default=None, description="Requests remaining today (None if unlimited)")
    monthly_remaining: Optional[int] = Field(default=None, description="Requests remaining this month (None if unlimited)")
    throttle_delay_ms: int = Field(default=0, description="Current throttle delay in milliseconds")


class SystemPromptCreate(BaseModel):
    """System prompt creation request model"""
    name: str
    prompt: str = Field(min_length=1, max_length=25000)
    version: str = "1.0"


class SystemPromptUpdate(BaseModel):
    """System prompt update request model"""
    prompt: str = Field(min_length=1, max_length=25000)
    version: Optional[str] = None


class SystemPromptResponse(BaseModel):
    """System prompt response model"""
    id: str
    name: str
    prompt: str
    version: str
    created_at: float  # Unix timestamp
    updated_at: float  # Unix timestamp


class ToolSkillCreate(BaseModel):
    """Tool skill creation request model (docs/roadmap/mcp-tool-skills.md Phase 3)."""
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=500)
    mcp_tools: List[str] = Field(min_length=1, max_length=64)
    body: str = Field(min_length=1, max_length=24_576)
    enabled: bool = True
    version: Optional[str] = None
    priority: int = 0


class ToolSkillUpdate(BaseModel):
    """Tool skill update request model. Name is immutable — delete and recreate to rename."""
    description: Optional[str] = Field(default=None, min_length=1, max_length=500)
    mcp_tools: Optional[List[str]] = Field(default=None, min_length=1, max_length=64)
    body: Optional[str] = Field(default=None, min_length=1, max_length=24_576)
    enabled: Optional[bool] = None
    version: Optional[str] = None
    priority: Optional[int] = None


class ToolSkillResponse(BaseModel):
    """Tool skill response model."""
    id: str
    name: str
    description: str
    mcp_tools: List[str]
    body: str
    enabled: bool
    version: Optional[str] = None
    priority: int
    created_at: float
    updated_at: float


class APIError(BaseModel):
    """Standard error envelope for all API error responses."""
    code: str       # machine-readable: "SERVICE_UNAVAILABLE", "NOT_FOUND", "VALIDATION_ERROR"
    message: str    # human-readable description
    details: Optional[Any] = None


class ApiKeyListItem(BaseModel):
    """A single API key record returned in list and detail endpoints."""
    id: Optional[str] = None           # canonical id (same value as legacy _id)
    api_key: str                       # masked: "***xxxx"
    adapter_name: Optional[str] = None
    collection_name: Optional[str] = None  # legacy field
    client_name: Optional[str] = None
    notes: Optional[str] = None
    active: bool = True
    created_at: Optional[float] = None     # Unix timestamp
    system_prompt_id: Optional[str] = None
    system_prompt_name: Optional[str] = None


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


class TemplateReloadResponse(BaseModel):
    """Response model for template reload operation"""
    status: str
    message: str
    summary: Dict[str, Any]
    timestamp: str


class TemplateTestRequest(BaseModel):
    """Request model for testing an intent retriever template"""
    query: str = Field(description="Natural language query to test against the adapter's templates")
    max_templates: int = Field(default=5, description="Maximum template candidates to return")
    execute: bool = Field(default=True, description="Whether to execute the query against the datasource")
    include_all_candidates: bool = Field(default=False, description="Include full details for all candidates")
    verbose: bool = Field(default=False, description="Include extended diagnostics (vector store, inventory, domain, semantic analysis)")


class TemplateFeedbackRequest(BaseModel):
    """Request model for recording human feedback on an intent template match/miss"""
    verdict: str = Field(description="Feedback verdict, e.g. 'correct', 'incorrect', 'no_match_expected'")
    request_id: Optional[str] = Field(default=None, description="Request id the feedback refers to, if known")
    template_id: Optional[str] = Field(default=None, description="Template the retriever actually matched, if any")
    expected_template_id: Optional[str] = Field(default=None, description="Template that should have matched, for growing the eval corpus")


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
