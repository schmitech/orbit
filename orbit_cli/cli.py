"""Main CLI class for ORBIT that ties all modules together."""

import argparse
import sys
from pathlib import Path
from typing import Optional

from .__version__ import __version__, __description__
from .config import ConfigManager
from .api import ApiManager
from .server import ServerController
from .output.formatter import OutputFormatter
from .commands import CommandFactory
from .utils.logging import setup_logging, get_logger
from .core.exceptions import OrbitError


class OrbitCLI:
    """Main CLI class for ORBIT command-line interface."""
    
    def __init__(self):
        """Initialize the ORBIT CLI."""
        self.config_manager = ConfigManager()
        self.formatter = OutputFormatter()
        self.logger = None
        
        # These will be initialized as needed
        self._api_manager = None
        self._server_controller = None
        self._command_factory = None
    
    @property
    def api_manager(self) -> ApiManager:
        """Lazy-load API manager."""
        if self._api_manager is None:
            self._api_manager = ApiManager(self.config_manager)
        return self._api_manager
    
    @property
    def server_controller(self) -> ServerController:
        """Lazy-load server controller."""
        if self._server_controller is None:
            self._server_controller = ServerController(formatter=self.formatter)
        return self._server_controller
    
    @property
    def command_factory(self) -> CommandFactory:
        """Lazy-load command factory."""
        if self._command_factory is None:
            self._command_factory = CommandFactory(
                config_manager=self.config_manager,
                api_manager=self.api_manager,
                server_controller=self.server_controller,
                formatter=self.formatter
            )
            # Register built-in commands
            self._command_factory.register_builtin_commands()
        return self._command_factory
    
    def create_parser(self) -> argparse.ArgumentParser:
        """Create the argument parser for the CLI."""
        parser = argparse.ArgumentParser(
            prog='orbit',
            description=__description__,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=self._get_epilog()
        )
        
        # Global arguments
        parser.add_argument(
            '--version',
            action='version',
            version=f'%(prog)s {__version__}'
        )
        parser.add_argument(
            '--server-url',
            help='Server URL (default: from config or localhost:3000)'
        )
        parser.add_argument(
            '--config',
            help='Path to configuration file'
        )
        parser.add_argument(
            '-v', '--verbose',
            action='store_true',
            help='Enable verbose output'
        )
        parser.add_argument(
            '--output',
            choices=['table', 'json'],
            help='Output format'
        )
        parser.add_argument(
            '--no-color',
            action='store_true',
            help='Disable colored output'
        )
        parser.add_argument(
            '--log-file',
            help='Path to log file'
        )
        
        # Create subparsers for commands
        subparsers = parser.add_subparsers(
            dest='command',
            help='Available commands',
            metavar='COMMAND'
        )
        
        # Add all registered commands
        self._add_commands_to_parser(subparsers)
        
        return parser
    
    def _add_commands_to_parser(self, subparsers) -> None:
        """Add all registered commands to the parser."""
        for cmd_name in self.command_factory.get_available_commands():
            command = self.command_factory.create_command(cmd_name)
            if command:
                # Create subparser for this command
                cmd_parser = subparsers.add_parser(
                    cmd_name,
                    help=command.get_help(),
                    description=command.get_description()
                )
                
                # Let the command add its own arguments
                command.add_arguments(cmd_parser)
                
                # Store command name for execution
                cmd_parser.set_defaults(command_name=cmd_name)
    
    def _get_epilog(self) -> str:
        """Get epilog text for the parser."""
        return """
For more information about a specific command, use:
  orbit <command> --help

Configuration files are stored in ~/.orbit/
Authentication tokens are stored based on config (keychain or ~/.orbit/.env)

Examples:
  orbit start                    # Start the server
  orbit login                    # Login to the server
  orbit key list                 # List API keys
  orbit config show              # Show configuration

Report issues at: https://github.com/schmitech/orbit/issues
"""
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the parsed command."""
        try:
            # Set up logging
            log_file = Path(args.log_file) if args.log_file else None
            self.logger = setup_logging(
                verbose=args.verbose,
                log_file=log_file,
                console=self.formatter.console
            )
            
            # Configure output formatter
            if args.output:
                self.formatter.format = args.output
            if args.no_color:
                self.formatter.color = False
            
            # Handle server URL override
            if args.server_url:
                # Re-initialize API manager with new URL
                self._api_manager = ApiManager(
                    self.config_manager,
                    server_url=args.server_url
                )
            
            # Execute the command
            if hasattr(args, 'command_name'):
                command = self.command_factory.create_command(args.command_name)
                if command:
                    # Update command's formatter to match global settings
                    command.formatter = self.formatter
                    return command.run(args)
                else:
                    self.formatter.error(f"Unknown command: {args.command_name}")
                    return 1
            
            # No command specified
            parser = self.create_parser()
            parser.print_help()
            return 1
            
        except OrbitError as e:
            self.formatter.error(str(e))
            if self.logger:
                self.logger.debug(f"OrbitError: {e}", exc_info=True)
            return 1
        except KeyboardInterrupt:
            self.formatter.warning("\nOperation cancelled by user")
            return 130
        except Exception as e:
            self.formatter.error(f"Unexpected error: {str(e)}")
            if self.logger:
                self.logger.error(f"Unexpected error: {e}", exc_info=True)
            return 1
    
    def run(self, argv: Optional[list] = None) -> int:
        """
        Run the CLI with the given arguments.
        
        Args:
            argv: Command line arguments (uses sys.argv if None)
            
        Returns:
            Exit code
        """
        parser = self.create_parser()
        
        # Parse arguments
        args = parser.parse_args(argv)
        
        # Execute command
        return self.execute(args)


def main():
    """Main entry point for the ORBIT CLI."""
    cli = OrbitCLI()
    exit_code = cli.run()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()