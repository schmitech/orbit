"""
Pydantic models for the API
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """Chat message model"""
    message: str
    stream: bool = Field(default=True, description="Whether to stream the response")


class HealthStatus(BaseModel):
    status: str
    components: Dict[str, Dict[str, Any]]


class ApiKeyCreate(BaseModel):
    """API key creation request model"""
    collection_name: str
    client_name: str
    notes: Optional[str] = None


class ApiKeyResponse(BaseModel):
    """API key response model"""
    api_key: str
    client_name: str
    collection: str  # This must match what's returned from the service
    notes: Optional[str] = None
    created_at: float  # This expects a Unix timestamp
    active: bool = True


class ApiKeyDeactivate(BaseModel):
    """API key deactivation request model"""
    api_key: str