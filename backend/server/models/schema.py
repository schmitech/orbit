"""
Pydantic models for the API
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    message: str
    voiceEnabled: bool = False
    stream: bool = Field(default=True, description="Whether to stream the response")


class HealthStatus(BaseModel):
    status: str
    components: Dict[str, Dict[str, Any]]