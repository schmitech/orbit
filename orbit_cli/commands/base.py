"""Enhanced base command classes for ORBIT CLI commands."""

import argparse
from abc import ABC, abstractmethod
from typing import Any, Optional, Dict, List, Type

from ..config import ConfigManager
from ..api import ApiManager
from ..server import ServerController
from ..output.formatter import OutputFormatter
from ..utils.logging import get_logger
from ..core.exceptions import OrbitError


class BaseCommand(ABC):
    """Base class for all ORBIT CLI commands."""
    
    # Command metadata
    name: str = ""
    help: str = ""
    description: str = ""
    
    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        api_manager: Optional[ApiManager] = None,
        server_controller: Optional[ServerController] = None,
        formatter: Optional[OutputFormatter] = None
    ):
        """
        Initialize the base command with injected dependencies.
        
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
        self.logger = get_logger(self.__class__.__name__)
    
    @classmethod
    def get_name(cls) -> str:
        """Get the command name."""
        return cls.name or cls.__name__.lower().replace('command', '')
    
    @classmethod
    def get_help(cls) -> str:
        """Get help text for this command."""
        return cls.help or f"{cls.get_name()} command"
    
    @classmethod
    def get_description(cls) -> str:
        """Get description for this command."""
        return cls.description or cls.get_help()
    
    @abstractmethod
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """
        Add command-specific arguments to the parser.
        
        Args:
            parser: Argument parser or subparser for this command
        """
        pass
    
    @abstractmethod
    def execute(self, args: argparse.Namespace) -> int:
        """
        Execute the command with the given arguments.
        
        Args:
            args: Parsed command line arguments
            
        Returns:
            Exit code (0 for success, non-zero for failure)
        """
        pass
    
    def pre_execute(self, args: argparse.Namespace) -> None:
        """
        Hook called before execute. Can be overridden by subclasses.
        
        Args:
            args: Parsed command line arguments
        """
        # Update formatter based on args
        self.update_formatter(args)
    
    def post_execute(self, args: argparse.Namespace, exit_code: int) -> int:
        """
        Hook called after execute. Can be overridden by subclasses.
        
        Args:
            args: Parsed command line arguments
            exit_code: Exit code from execute
            
        Returns:
            Potentially modified exit code
        """
        return exit_code
    
    def run(self, args: argparse.Namespace) -> int:
        """
        Run the command with pre/post hooks.
        
        Args:
            args: Parsed command line arguments
            
        Returns:
            Exit code
        """
        try:
            self.pre_execute(args)
            exit_code = self.execute(args)
            return self.post_execute(args, exit_code)
        except OrbitError as e:
            return self.handle_error(e)
        except KeyboardInterrupt:
            self.formatter.warning("\nOperation cancelled by user")
            return 130
        except Exception as e:
            return self.handle_error(e, "Unexpected error")
    
    def handle_error(self, error: Exception, message: Optional[str] = None) -> int:
        """
        Handle an error in a consistent way.
        
        Args:
            error: The exception that occurred
            message: Optional custom error message
            
        Returns:
            Exit code (always 1)
        """
        error_msg = message or str(error)
        if message:
            error_msg = f"{message}: {error}"
        
        self.formatter.error(error_msg)
        self.logger.debug(f"Error in {self.__class__.__name__}: {error}", exc_info=True)
        return 1
    
    def require_confirmation(
        self,
        message: str,
        default: bool = False,
        skip_flag: str = "force"
    ) -> bool:
        """
        Ask for user confirmation unless skip flag is set.
        
        Args:
            message: Confirmation message
            default: Default answer if user just presses Enter
            skip_flag: Argument name to check for skipping confirmation
            
        Returns:
            True if confirmed, False otherwise
        """
        # Check if skip flag is set
        if hasattr(self, '_args') and getattr(self._args, skip_flag, False):
            return True
        
        from rich.prompt import Confirm
        return Confirm.ask(message, default=default)
    
    def update_formatter(self, args: argparse.Namespace) -> None:
        """
        Update formatter based on command arguments.
        
        Args:
            args: Parsed arguments
        """
        # Store args for later use
        self._args = args
        
        if hasattr(args, 'output'):
            self.formatter.format = args.output
        if hasattr(args, 'no_color') and args.no_color:
            self.formatter.color = False
    
    def ensure_authenticated(self) -> None:
        """Ensure user is authenticated before proceeding."""
        if not self.api_manager:
            raise OrbitError("API manager not initialized")
        self.api_manager.ensure_authenticated()
    
    def get_server_url(self, args: argparse.Namespace) -> str:
        """
        Get server URL from args or config.
        
        Args:
            args: Parsed arguments
            
        Returns:
            Server URL
        """
        if hasattr(args, 'server_url') and args.server_url:
            return args.server_url
        
        if self.config_manager:
            return self.config_manager.get('server.default_url', 'http://localhost:3000')
        
        return 'http://localhost:3000'


class CommandGroup(BaseCommand):
    """Base class for command groups (e.g., 'orbit key', 'orbit user')."""
    
    def __init__(self, *args, **kwargs):
        """Initialize the command group."""
        super().__init__(*args, **kwargs)
        self.subcommands: Dict[str, BaseCommand] = {}
        self._load_subcommands()
    
    def _load_subcommands(self) -> None:
        """Load subcommands. Should be overridden by subclasses."""
        for name, command_class in self.get_subcommands().items():
            self.subcommands[name] = command_class(
                config_manager=self.config_manager,
                api_manager=self.api_manager,
                server_controller=self.server_controller,
                formatter=self.formatter
            )
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add subcommands to the parser."""
        subparsers = parser.add_subparsers(
            dest=f'{self.get_name()}_command',
            help=f'{self.get_name()} operations',
            metavar='COMMAND'
        )
        
        for name, command in self.subcommands.items():
            subparser = subparsers.add_parser(
                name,
                help=command.get_help(),
                description=command.get_description()
            )
            command.add_arguments(subparser)
            # Set the command instance as default
            subparser.set_defaults(command_instance=command)
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the appropriate subcommand."""
        subcommand_attr = f'{self.get_name()}_command'
        subcommand_name = getattr(args, subcommand_attr, None)
        
        if not subcommand_name:
            self.formatter.error(f"No subcommand specified for '{self.get_name()}'")
            self.formatter.info(f"Use 'orbit {self.get_name()} --help' for available commands")
            return 1
        
        # Get the command instance
        if hasattr(args, 'command_instance'):
            command = args.command_instance
            return command.run(args)
        
        return 1
    
    @abstractmethod
    def get_subcommands(self) -> Dict[str, Type[BaseCommand]]:
        """
        Get the subcommands for this group.
        
        Returns:
            Dictionary mapping subcommand names to command classes
        """
        pass


class OutputCommand(BaseCommand):
    """Base class for commands that support multiple output formats."""
    
    def add_output_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add standard output format arguments."""
        parser.add_argument(
            '--output',
            choices=['table', 'json'],
            help='Output format (default: table)'
        )
        parser.add_argument(
            '--no-color',
            action='store_true',
            help='Disable colored output'
        )
    
    def format_output(self, data: Any, headers: Optional[List[str]] = None) -> None:
        """
        Format and display output based on configured format.
        
        Args:
            data: Data to display
            headers: Optional headers for table format
        """
        if self.formatter.format == 'json':
            self.formatter.format_json(data)
        elif self.formatter.format == 'table' and isinstance(data, list) and headers:
            self.formatter.format_table(data, headers)
        else:
            # Default to JSON for complex data
            self.formatter.format_json(data)


class PaginatedCommand(OutputCommand):
    """Base class for commands that support pagination."""
    
    def add_pagination_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add standard pagination arguments."""
        parser.add_argument(
            '--limit',
            type=int,
            default=100,
            help='Maximum number of items to return (default: 100)'
        )
        parser.add_argument(
            '--offset',
            type=int,
            default=0,
            help='Number of items to skip (default: 0)'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Fetch all items (ignore limit/offset)'
        )
    
    def get_pagination_params(self, args: argparse.Namespace) -> Dict[str, Any]:
        """
        Get pagination parameters from args.
        
        Args:
            args: Parsed arguments
            
        Returns:
            Dictionary with limit and offset
        """
        if getattr(args, 'all', False):
            return {'limit': 1000, 'offset': 0, 'fetch_all': True}
        
        return {
            'limit': getattr(args, 'limit', 100),
            'offset': getattr(args, 'offset', 0),
            'fetch_all': False
        }