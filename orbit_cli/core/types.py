"""
Type definitions for Orbit CLI
"""

from typing import Dict, List, Optional, Union, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class APIResponse:
    """API response wrapper"""
    status_code: int
    data: Any
    headers: Dict[str, str]
    message: Optional[str] = None


@dataclass
class User:
    """User model"""
    id: str
    username: str
    email: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class APIKey:
    """API key model"""
    id: str
    name: str
    key: str
    is_active: bool
    created_at: datetime
    last_used: Optional[datetime] = None


@dataclass
class SystemPrompt:
    """System prompt model"""
    id: str
    name: str
    content: str
    is_active: bool
    created_at: datetime
    updated_at: datetime 