"""Command modules for ORBIT CLI."""

from .base import BaseCommand, CommandGroup, OutputCommand, PaginatedCommand
from .registry import CommandRegistry, CommandFactory, register_command

# Import all command modules to ensure they're registered
from . import server
from . import auth
from . import api_keys
from . import config

# Import specific commands for convenience
from .server import (
    StartCommand,
    StopCommand,
    RestartCommand,
    StatusCommand,
    LogsCommand
)

from .auth import (
    LoginCommand,
    LogoutCommand,
    RegisterCommand,
    MeCommand,
    AuthStatusCommand,
    ChangePasswordCommand
)

from .api_keys import ApiKeyCommandGroup
from .config import ConfigCommandGroup

__all__ = [
    # Base classes
    'BaseCommand',
    'CommandGroup',
    'OutputCommand',
    'PaginatedCommand',
    
    # Registry and factory
    'CommandRegistry',
    'CommandFactory',
    'register_command',
    
    # Server commands
    'StartCommand',
    'StopCommand',
    'RestartCommand',
    'StatusCommand',
    'LogsCommand',
    
    # Auth commands
    'LoginCommand',
    'LogoutCommand',
    'RegisterCommand',
    'MeCommand',
    'AuthStatusCommand',
    'ChangePasswordCommand',
    
    # Command groups
    'ApiKeyCommandGroup',
    'ConfigCommandGroup',
]