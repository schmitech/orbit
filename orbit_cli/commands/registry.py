"""Command registry and factory for ORBIT CLI."""

from typing import Dict, Type, Optional, List
import importlib
import pkgutil

from .base import BaseCommand, CommandGroup
from ..config import ConfigManager
from ..api import ApiManager
from ..server import ServerController
from ..output.formatter import OutputFormatter
from ..utils.logging import get_logger

logger = get_logger(__name__)


class CommandRegistry:
    """Registry for all available commands."""
    
    def __init__(self):
        """Initialize the command registry."""
        self._commands: Dict[str, Type[BaseCommand]] = {}
        self._groups: Dict[str, Type[CommandGroup]] = {}
        self._loaded = False
    
    def register_command(self, command_class: Type[BaseCommand]) -> None:
        """
        Register a command class.
        
        Args:
            command_class: Command class to register
        """
        name = command_class.get_name()
        
        if issubclass(command_class, CommandGroup):
            self._groups[name] = command_class
            logger.debug(f"Registered command group: {name}")
        else:
            self._commands[name] = command_class
            logger.debug(f"Registered command: {name}")
    
    def get_command(self, name: str) -> Optional[Type[BaseCommand]]:
        """
        Get a command class by name.
        
        Args:
            name: Command name
            
        Returns:
            Command class or None if not found
        """
        return self._commands.get(name) or self._groups.get(name)
    
    def get_all_commands(self) -> Dict[str, Type[BaseCommand]]:
        """Get all registered commands including groups."""
        all_commands = {}
        all_commands.update(self._commands)
        all_commands.update(self._groups)
        return all_commands
    
    def get_command_names(self) -> List[str]:
        """Get sorted list of all command names."""
        return sorted(list(self._commands.keys()) + list(self._groups.keys()))
    
    def auto_discover(self, package_name: str = "orbit_cli.commands") -> None:
        """
        Auto-discover and register commands from a package.
        
        Args:
            package_name: Package to search for commands
        """
        if self._loaded:
            return
        
        try:
            # Import the package
            package = importlib.import_module(package_name)
            
            # Walk through all modules in the package
            for importer, modname, ispkg in pkgutil.walk_packages(
                package.__path__,
                prefix=package.__name__ + "."
            ):
                if ispkg:
                    continue  # Skip sub-packages
                
                # Skip base and registry modules
                if modname.endswith(('.base', '.registry', '__init__')):
                    continue
                
                try:
                    # Import the module
                    module = importlib.import_module(modname)
                    
                    # Look for command classes
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        
                        # Check if it's a command class
                        if (isinstance(attr, type) and 
                            issubclass(attr, BaseCommand) and 
                            attr not in (BaseCommand, CommandGroup) and
                            hasattr(attr, 'name') and attr.name):
                            
                            self.register_command(attr)
                            
                except Exception as e:
                    logger.warning(f"Failed to import module {modname}: {e}")
            
            self._loaded = True
            logger.info(f"Auto-discovered {len(self._commands)} commands and {len(self._groups)} groups")
            
        except Exception as e:
            logger.error(f"Failed to auto-discover commands: {e}")


class CommandFactory:
    """Factory for creating command instances with dependency injection."""
    
    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        api_manager: Optional[ApiManager] = None,
        server_controller: Optional[ServerController] = None,
        formatter: Optional[OutputFormatter] = None
    ):
        """
        Initialize the command factory.
        
        Args:
            config_manager: Configuration manager instance
            api_manager: API manager instance
            server_controller: Server controller instance
            formatter: Output formatter instance
        """
        self.config_manager = config_manager
        self.api_manager = api_manager
        self.server_controller = server_controller
        self.formatter = formatter or OutputFormatter()
        self.registry = CommandRegistry()
    
    def create_command(self, name: str) -> Optional[BaseCommand]:
        """
        Create a command instance by name.
        
        Args:
            name: Command name
            
        Returns:
            Command instance or None if not found
        """
        command_class = self.registry.get_command(name)
        
        if not command_class:
            return None
        
        # Create instance with dependency injection
        return command_class(
            config_manager=self.config_manager,
            api_manager=self.api_manager,
            server_controller=self.server_controller,
            formatter=self.formatter
        )
    
    def get_available_commands(self) -> List[str]:
        """Get list of available command names."""
        return self.registry.get_command_names()
    
    def register_builtin_commands(self) -> None:
        """Register all built-in commands."""
        from .server import StartCommand, StopCommand, RestartCommand, StatusCommand, LogsCommand
        from .auth import (
            LoginCommand, LogoutCommand, RegisterCommand,
            MeCommand, AuthStatusCommand, ChangePasswordCommand
        )
        from .api_keys import ApiKeyCommandGroup
        from .config import ConfigCommandGroup
        
        # Register server commands
        self.registry.register_command(StartCommand)
        self.registry.register_command(StopCommand)
        self.registry.register_command(RestartCommand)
        self.registry.register_command(StatusCommand)
        self.registry.register_command(LogsCommand)
        
        # Register auth commands
        self.registry.register_command(LoginCommand)
        self.registry.register_command(LogoutCommand)
        self.registry.register_command(RegisterCommand)
        self.registry.register_command(MeCommand)
        self.registry.register_command(AuthStatusCommand)
        self.registry.register_command(ChangePasswordCommand)
        
        # Register command groups
        self.registry.register_command(ApiKeyCommandGroup)
        self.registry.register_command(ConfigCommandGroup)
        
        # Register additional command groups as they're implemented
        try:
            from .users import UserCommandGroup
            self.registry.register_command(UserCommandGroup)
        except ImportError:
            pass
        
        try:
            from .prompts import PromptCommandGroup
            self.registry.register_command(PromptCommandGroup)
        except ImportError:
            pass


# Global registry instance
_global_registry = CommandRegistry()


def get_global_registry() -> CommandRegistry:
    """Get the global command registry."""
    return _global_registry


def register_command(command_class: Type[BaseCommand]) -> Type[BaseCommand]:
    """
    Decorator to register a command with the global registry.
    
    Usage:
        @register_command
        class MyCommand(BaseCommand):
            name = "mycommand"
            ...
    """
    _global_registry.register_command(command_class)
    return command_class