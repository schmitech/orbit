"""
Main CLI orchestrator for ORBIT.

This module provides the command registry and routing logic, following
the Command pattern and Single Responsibility Principle.
"""

import sys
import argparse
import logging
from pathlib import Path
from typing import Optional, Any

from rich.console import Console
from rich.logging import RichHandler

from bin.orbit.services.config_service import ConfigService
from bin.orbit.services.api_client import ApiClient
from bin.orbit.services.auth_service import AuthService
from bin.orbit.services.api_service import ApiService
from bin.orbit.services.server_service import ServerService
from bin.orbit.utils.output import OutputFormatter
from bin.orbit.utils.exceptions import OrbitError, AuthenticationError, NetworkError

# Import all commands
from bin.orbit.commands.server import (
    ServerStartCommand, ServerStopCommand, ServerRestartCommand, ServerStatusCommand
)
from bin.orbit.commands.auth import (
    LoginCommand, LogoutCommand, RegisterCommand, MeCommand, AuthStatusCommand
)
from bin.orbit.commands.keys import (
    KeyCreateCommand, KeyListCommand, KeyTestCommand, KeyStatusCommand,
    KeyRenameCommand, KeyDeactivateCommand, KeyDeleteCommand, KeyListAdaptersCommand
)
from bin.orbit.commands.prompts import (
    PromptCreateCommand, PromptListCommand, PromptGetCommand,
    PromptUpdateCommand, PromptDeleteCommand, PromptAssociateCommand
)
from bin.orbit.commands.users import (
    UserListCommand, UserResetPasswordCommand, UserDeleteCommand,
    UserDeactivateCommand, UserActivateCommand, UserChangePasswordCommand
)
from bin.orbit.commands.config import (
    ConfigShowCommand, ConfigEffectiveCommand, ConfigSetCommand, ConfigResetCommand
)
from bin.orbit.commands.admin import AdminReloadAdaptersCommand, AdminReloadTemplatesCommand
from bin.orbit.commands.quota import (
    QuotaGetCommand, QuotaSetCommand, QuotaResetCommand, QuotaReportCommand
)

# Version information
__version__ = "2.4.0"
__author__ = "Remsy Schmilinsky"

# Initialize rich console
console = Console()


def setup_logging(verbose: bool = False, log_file: Optional[Path] = None) -> logging.Logger:
    """Set up logging with rich formatting."""
    log_level = logging.DEBUG if verbose else logging.INFO
    
    logger = logging.getLogger("orbit")
    logger.setLevel(log_level)
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Console handler with rich formatting
    console_handler = RichHandler(
        console=console,
        show_time=False,
        show_path=False,
        markup=True
    )
    console_handler.setLevel(log_level)
    logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger


class OrbitCLI:
    """
    Main CLI orchestrator for ORBIT.
    
    This class manages command registration, argument parsing, and execution.
    It follows the Command pattern and uses dependency injection for services.
    """
    
    def __init__(self):
        """Initialize the ORBIT CLI."""
        self.config_service = ConfigService()
        self.formatter = OutputFormatter()
        
        # Initialize services (lazy initialization for API services)
        self.api_client = None
        self.auth_service = None
        self.api_service = None
        self.server_service = None
        
    def _initialize_api_services(self, server_url: Optional[str] = None):
        """Initialize API-related services."""
        if self.api_client is None or server_url:
            # If server_url is provided, use it; otherwise get from config
            if not server_url:
                server_url = self.config_service.get_server_url()
            else:
                server_url = server_url.rstrip('/')
            self.api_client = ApiClient(
                server_url=server_url,
                timeout=self.config_service.get_timeout(),
                retry_attempts=self.config_service.get_retry_attempts()
            )
            self.auth_service = AuthService(self.config_service, server_url)
            self.api_service = ApiService(self.api_client, self.auth_service)
    
    def _initialize_server_service(self):
        """Initialize server service."""
        if self.server_service is None:
            self._initialize_api_services()
            # Get project root (__file__ is bin/orbit/cli.py, so parent.parent is project root)
            script_dir = Path(__file__).parent.parent
            project_root = script_dir.parent  # Go up one more level to get project root
            self.server_service = ServerService(
                api_client=self.api_client,
                auth_service=self.auth_service,
                project_root=project_root,
                formatter=self.formatter
            )
    
    def _get_api_service(self, server_url: Optional[str] = None) -> ApiService:
        """Get or create API service."""
        if server_url:
            # Create new instance with different server URL
            api_client = ApiClient(
                server_url=server_url,
                timeout=self.config_service.get_timeout(),
                retry_attempts=self.config_service.get_retry_attempts()
            )
            auth_service = AuthService(self.config_service, server_url)
            return ApiService(api_client, auth_service)
        self._initialize_api_services(server_url)
        return self.api_service
    
    def _get_auth_service(self, server_url: Optional[str] = None) -> AuthService:
        """Get or create auth service."""
        self._initialize_api_services(server_url)
        return self.auth_service
    
    def _get_server_service(self) -> ServerService:
        """Get or create server service."""
        self._initialize_server_service()
        return self.server_service
    
    def _update_command_services(self, cmd: Any, args: argparse.Namespace) -> None:
        """Update command's services if server_url is provided in args."""
        server_url = getattr(args, 'server_url', None)
        if server_url:
            # Get fresh services with the new server URL
            api_service = self._get_api_service(server_url)
            auth_service = self._get_auth_service(server_url)
            
            # Update command's services if they exist
            if hasattr(cmd, 'api_service'):
                cmd.api_service = api_service
            if hasattr(cmd, 'auth_service'):
                cmd.auth_service = auth_service
            if hasattr(cmd, 'server_service'):
                # For server commands, we need to recreate server_service with new api_client/auth_service
                # Clear the cached server_service to force recreation
                self.server_service = None
                # Reinitialize with the new server URL
                self._initialize_api_services(server_url)
                # Get fresh server_service
                cmd.server_service = self._get_server_service()
    
    def create_parser(self) -> argparse.ArgumentParser:
        """Create the argument parser for the CLI."""
        parser = argparse.ArgumentParser(
            prog='orbit',
            description='ORBIT Control CLI - ORBIT management',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
For more information about a specific command, use:
  orbit <command> --help

Configuration files are stored in ~/.orbit/
Authentication tokens are stored based on config (keychain or ~/.orbit/.env)
Server settings must be managed through server API endpoints.

Report issues at: https://github.com/schmitech/orbit/issues
"""
        )
        
        # Global arguments
        parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
        parser.add_argument('--server-url', help='Server URL (default: from config or localhost:3000)')
        parser.add_argument('--config', help='Path to configuration file (for server start/restart)')
        parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
        parser.add_argument('--output', choices=['table', 'json'], help='Output format')
        parser.add_argument('--no-color', action='store_true', help='Disable colored output')
        parser.add_argument('--log-file', help='Path to log file')
        
        # Create subparsers for different command groups
        subparsers = parser.add_subparsers(dest='command', help='Available commands')
        
        # Server control commands
        self._add_server_commands(subparsers)
        
        # Authentication commands
        self._add_auth_commands(subparsers)
        
        # API key management commands
        self._add_key_commands(subparsers)
        
        # System prompt management commands
        self._add_prompt_commands(subparsers)
        
        # User management commands
        self._add_user_commands(subparsers)
        
        # Configuration commands
        self._add_config_commands(subparsers)
        
        # Admin management commands
        self._add_admin_commands(subparsers)

        # Quota management commands
        self._add_quota_commands(subparsers)

        return parser
    
    def _add_server_commands(self, subparsers):
        """Add server control commands."""
        start_parser = subparsers.add_parser('start', help='Start the ORBIT server')
        start_cmd = ServerStartCommand(self._get_server_service(), self.formatter)
        start_cmd.add_arguments(start_parser)
        start_parser.set_defaults(func=lambda args, cmd=start_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        stop_parser = subparsers.add_parser('stop', help='Stop the ORBIT server')
        stop_cmd = ServerStopCommand(self._get_server_service(), self.formatter)
        stop_cmd.add_arguments(stop_parser)
        stop_parser.set_defaults(func=lambda args, cmd=stop_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        restart_parser = subparsers.add_parser('restart', help='Restart the ORBIT server')
        restart_cmd = ServerRestartCommand(self._get_server_service(), self.formatter)
        restart_cmd.add_arguments(restart_parser)
        restart_parser.set_defaults(func=lambda args, cmd=restart_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        status_parser = subparsers.add_parser('status', help='Check ORBIT server status')
        status_cmd = ServerStatusCommand(self._get_server_service(), self.formatter)
        status_cmd.add_arguments(status_parser)
        status_parser.set_defaults(func=lambda args, cmd=status_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
    
    def _add_auth_commands(self, subparsers):
        """Add authentication commands."""
        login_parser = subparsers.add_parser('login', help='Login to the ORBIT server')
        login_cmd = LoginCommand(self._get_api_service(), self._get_auth_service(), self.formatter)
        login_cmd.add_arguments(login_parser)
        login_parser.set_defaults(func=lambda args, cmd=login_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        logout_parser = subparsers.add_parser('logout', help='Logout from the ORBIT server')
        logout_cmd = LogoutCommand(self._get_api_service(), self.formatter)
        logout_cmd.add_arguments(logout_parser)
        logout_parser.set_defaults(func=lambda args, cmd=logout_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        register_parser = subparsers.add_parser('register', help='Register a new user (admin only)')
        register_cmd = RegisterCommand(self._get_api_service(), self.formatter)
        register_cmd.add_arguments(register_parser)
        register_parser.set_defaults(func=lambda args, cmd=register_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        me_parser = subparsers.add_parser('me', help='Show current user information')
        me_cmd = MeCommand(self._get_api_service(), self.formatter)
        me_cmd.add_arguments(me_parser)
        me_parser.set_defaults(func=lambda args, cmd=me_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        auth_status_parser = subparsers.add_parser('auth-status', help='Check authentication status')
        auth_status_cmd = AuthStatusCommand(self._get_api_service(), self.formatter)
        auth_status_cmd.add_arguments(auth_status_parser)
        auth_status_parser.set_defaults(func=lambda args, cmd=auth_status_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
    
    def _add_key_commands(self, subparsers):
        """Add API key management commands."""
        key_parser = subparsers.add_parser('key', help='Manage API keys')
        key_subparsers = key_parser.add_subparsers(dest='key_command', help='API key operations', required=False)
        
        # Create command
        create_parser = key_subparsers.add_parser('create', help='Create a new API key')
        create_cmd = KeyCreateCommand(self._get_api_service(), self.formatter)
        create_cmd.add_arguments(create_parser)
        create_parser.set_defaults(func=lambda args, cmd=create_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        # List command
        list_parser = key_subparsers.add_parser('list', help='List all API keys')
        list_cmd = KeyListCommand(self._get_api_service(), self.formatter)
        list_cmd.add_arguments(list_parser)
        list_parser.set_defaults(func=lambda args, cmd=list_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        # Test command
        test_parser = key_subparsers.add_parser('test', help='Test an API key')
        test_cmd = KeyTestCommand(self._get_api_service(), self.formatter)
        test_cmd.add_arguments(test_parser)
        test_parser.set_defaults(func=lambda args, cmd=test_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        # Status command
        status_parser = key_subparsers.add_parser('status', help='Get API key status')
        status_cmd = KeyStatusCommand(self._get_api_service(), self.formatter)
        status_cmd.add_arguments(status_parser)
        status_parser.set_defaults(func=lambda args, cmd=status_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        # Rename command
        rename_parser = key_subparsers.add_parser('rename', help='Rename an API key')
        rename_cmd = KeyRenameCommand(self._get_api_service(), self.formatter)
        rename_cmd.add_arguments(rename_parser)
        rename_parser.set_defaults(func=lambda args, cmd=rename_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        # Deactivate command
        deactivate_parser = key_subparsers.add_parser('deactivate', help='Deactivate an API key')
        deactivate_cmd = KeyDeactivateCommand(self._get_api_service(), self.formatter)
        deactivate_cmd.add_arguments(deactivate_parser)
        deactivate_parser.set_defaults(func=lambda args, cmd=deactivate_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        # Delete command
        delete_parser = key_subparsers.add_parser('delete', help='Delete an API key')
        delete_cmd = KeyDeleteCommand(self._get_api_service(), self.formatter)
        delete_cmd.add_arguments(delete_parser)
        delete_parser.set_defaults(func=lambda args, cmd=delete_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        # List adapters command
        list_adapters_parser = key_subparsers.add_parser('list-adapters', help='List available adapters')
        list_adapters_cmd = KeyListAdaptersCommand(self.config_service, self.formatter)
        list_adapters_cmd.add_arguments(list_adapters_parser)
        list_adapters_parser.set_defaults(func=lambda args, cmd=list_adapters_cmd: cmd.execute(args))
    
    def _add_prompt_commands(self, subparsers):
        """Add system prompt management commands."""
        prompt_parser = subparsers.add_parser('prompt', help='Manage system prompts')
        prompt_subparsers = prompt_parser.add_subparsers(dest='prompt_command', help='System prompt operations', required=False)
        
        # Create command
        create_parser = prompt_subparsers.add_parser('create', help='Create a new system prompt')
        create_cmd = PromptCreateCommand(self._get_api_service(), self.formatter)
        create_cmd.add_arguments(create_parser)
        create_parser.set_defaults(func=lambda args, cmd=create_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        # List command
        list_parser = prompt_subparsers.add_parser('list', help='List all system prompts')
        list_cmd = PromptListCommand(self._get_api_service(), self.formatter)
        list_cmd.add_arguments(list_parser)
        list_parser.set_defaults(func=lambda args, cmd=list_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        # Get command
        get_parser = prompt_subparsers.add_parser('get', help='Get a system prompt')
        get_cmd = PromptGetCommand(self._get_api_service(), self.formatter)
        get_cmd.add_arguments(get_parser)
        get_parser.set_defaults(func=lambda args, cmd=get_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        # Update command
        update_parser = prompt_subparsers.add_parser('update', help='Update a system prompt')
        update_cmd = PromptUpdateCommand(self._get_api_service(), self.formatter)
        update_cmd.add_arguments(update_parser)
        update_parser.set_defaults(func=lambda args, cmd=update_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        # Delete command
        delete_parser = prompt_subparsers.add_parser('delete', help='Delete a system prompt')
        delete_cmd = PromptDeleteCommand(self._get_api_service(), self.formatter)
        delete_cmd.add_arguments(delete_parser)
        delete_parser.set_defaults(func=lambda args, cmd=delete_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        # Associate command
        associate_parser = prompt_subparsers.add_parser('associate', help='Associate prompt with API key')
        associate_cmd = PromptAssociateCommand(self._get_api_service(), self.formatter)
        associate_cmd.add_arguments(associate_parser)
        associate_parser.set_defaults(func=lambda args, cmd=associate_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
    
    def _add_user_commands(self, subparsers):
        """Add user management commands."""
        user_parser = subparsers.add_parser('user', help='Manage users (admin only)')
        user_subparsers = user_parser.add_subparsers(dest='user_command', help='User management operations', required=False)
        
        # List command
        list_parser = user_subparsers.add_parser('list', help='List all users')
        list_cmd = UserListCommand(self._get_api_service(), self.formatter)
        list_cmd.add_arguments(list_parser)
        list_parser.set_defaults(func=lambda args, cmd=list_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        # Reset password command
        reset_parser = user_subparsers.add_parser('reset-password', help='Reset user password')
        reset_cmd = UserResetPasswordCommand(self._get_api_service(), self.formatter)
        reset_cmd.add_arguments(reset_parser)
        reset_parser.set_defaults(func=lambda args, cmd=reset_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        # Delete command
        delete_parser = user_subparsers.add_parser('delete', help='Delete a user')
        delete_cmd = UserDeleteCommand(self._get_api_service(), self.formatter)
        delete_cmd.add_arguments(delete_parser)
        delete_parser.set_defaults(func=lambda args, cmd=delete_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        # Deactivate command
        deactivate_parser = user_subparsers.add_parser('deactivate', help='Deactivate a user')
        deactivate_cmd = UserDeactivateCommand(self._get_api_service(), self.formatter)
        deactivate_cmd.add_arguments(deactivate_parser)
        deactivate_parser.set_defaults(func=lambda args, cmd=deactivate_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        # Activate command
        activate_parser = user_subparsers.add_parser('activate', help='Activate a user')
        activate_cmd = UserActivateCommand(self._get_api_service(), self.formatter)
        activate_cmd.add_arguments(activate_parser)
        activate_parser.set_defaults(func=lambda args, cmd=activate_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
        
        # Change password command
        change_password_parser = user_subparsers.add_parser('change-password', help='Change your password')
        change_password_cmd = UserChangePasswordCommand(self._get_api_service(), self.formatter)
        change_password_cmd.add_arguments(change_password_parser)
        change_password_parser.set_defaults(func=lambda args, cmd=change_password_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))
    
    def _add_config_commands(self, subparsers):
        """Add configuration commands."""
        config_parser = subparsers.add_parser('config', help='Manage CLI configuration')
        config_subparsers = config_parser.add_subparsers(dest='config_command', help='Configuration operations', required=False)
        
        # Show command
        show_parser = config_subparsers.add_parser('show', help='Show CLI configuration')
        show_cmd = ConfigShowCommand(self.config_service, self.formatter)
        show_cmd.add_arguments(show_parser)
        show_parser.set_defaults(func=lambda args, cmd=show_cmd: cmd.execute(args))
        
        # Effective command
        effective_parser = config_subparsers.add_parser('effective', help='Show effective CLI configuration')
        effective_cmd = ConfigEffectiveCommand(self.config_service, self.formatter)
        effective_cmd.add_arguments(effective_parser)
        effective_parser.set_defaults(func=lambda args, cmd=effective_cmd: cmd.execute(args))
        
        # Set command
        set_parser = config_subparsers.add_parser('set', help='Set CLI configuration value')
        set_cmd = ConfigSetCommand(self.config_service, self.formatter)
        set_cmd.add_arguments(set_parser)
        set_parser.set_defaults(func=lambda args, cmd=set_cmd: cmd.execute(args))
        
        # Reset command
        reset_parser = config_subparsers.add_parser('reset', help='Reset CLI configuration to defaults')
        reset_cmd = ConfigResetCommand(self.config_service, self.formatter)
        reset_cmd.add_arguments(reset_parser)
        reset_parser.set_defaults(func=lambda args, cmd=reset_cmd: cmd.execute(args))
    
    def _add_admin_commands(self, subparsers):
        """Add admin management commands."""
        admin_parser = subparsers.add_parser('admin', help='Admin operations')
        admin_subparsers = admin_parser.add_subparsers(dest='admin_command', help='Admin operations', required=False)

        # Reload adapters command
        reload_parser = admin_subparsers.add_parser('reload-adapters', help='Reload adapter configurations without server restart')
        reload_cmd = AdminReloadAdaptersCommand(self._get_api_service(), self.formatter)
        reload_cmd.add_arguments(reload_parser)
        reload_parser.set_defaults(func=lambda args, cmd=reload_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))

        # Reload templates command
        reload_templates_parser = admin_subparsers.add_parser('reload-templates', help='Reload intent templates without server restart')
        reload_templates_cmd = AdminReloadTemplatesCommand(self._get_api_service(), self.formatter)
        reload_templates_cmd.add_arguments(reload_templates_parser)
        reload_templates_parser.set_defaults(func=lambda args, cmd=reload_templates_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))

    def _add_quota_commands(self, subparsers):
        """Add quota management commands."""
        quota_parser = subparsers.add_parser('quota', help='Manage API key quotas and throttling')
        quota_subparsers = quota_parser.add_subparsers(dest='quota_command', help='Quota operations', required=False)

        # Get command
        get_parser = quota_subparsers.add_parser('get', help='Get quota and usage for an API key')
        get_cmd = QuotaGetCommand(self._get_api_service(), self.formatter)
        get_cmd.add_arguments(get_parser)
        get_parser.set_defaults(func=lambda args, cmd=get_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))

        # Set command
        set_parser = quota_subparsers.add_parser('set', help='Set quota limits for an API key')
        set_cmd = QuotaSetCommand(self._get_api_service(), self.formatter)
        set_cmd.add_arguments(set_parser)
        set_parser.set_defaults(func=lambda args, cmd=set_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))

        # Reset command
        reset_parser = quota_subparsers.add_parser('reset', help='Reset quota usage for an API key')
        reset_cmd = QuotaResetCommand(self._get_api_service(), self.formatter)
        reset_cmd.add_arguments(reset_parser)
        reset_parser.set_defaults(func=lambda args, cmd=reset_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))

        # Report command
        report_parser = quota_subparsers.add_parser('report', help='Generate quota usage report')
        report_cmd = QuotaReportCommand(self._get_api_service(), self.formatter)
        report_cmd.add_arguments(report_parser)
        report_parser.set_defaults(func=lambda args, cmd=report_cmd, cli=self: cli._update_command_services(cmd, args) or cmd.execute(args))

    def execute(self, args):
        """Execute the parsed command."""
        try:
            # Set up logging
            log_file = Path(args.log_file) if getattr(args, 'log_file', None) else None
            global logger
            logger = setup_logging(getattr(args, 'verbose', False), log_file)
            
            # Configure output formatter
            output_format = self.config_service.get_output_format(getattr(args, 'output', None))
            use_color = self.config_service.get_use_color(not getattr(args, 'no_color', False))
            self.formatter = OutputFormatter(format=output_format, color=use_color)
            
            # Update services with new server URL if provided
            # This must happen before command execution so commands get the correct URL
            server_url = getattr(args, 'server_url', None)
            if server_url:
                # Force reinitialize services with new server URL
                # Clear existing services to force recreation
                self.api_client = None
                self.auth_service = None
                self.api_service = None
                self._initialize_api_services(server_url)
            
            # Add output format to args for commands that need it
            if not hasattr(args, 'output'):
                args.output = output_format
            
            # Call the function that was mapped to the command
            if hasattr(args, 'func'):
                return args.func(args)
            
            # If no command was given, print help
            if not getattr(args, 'command', None):
                self.create_parser().print_help()
                return 1
            
            return 1
            
        except AuthenticationError as e:
            self.formatter.error(str(e))
            logger.debug(f"AuthenticationError: {e}", exc_info=True)
            return 1
        except NetworkError as e:
            self.formatter.error(f"Network error: {str(e)}")
            self.formatter.info("Please check that the server is running and accessible")
            logger.debug(f"NetworkError: {e}", exc_info=True)
            return 1
        except OrbitError as e:
            self.formatter.error(str(e))
            logger.debug(f"OrbitError: {e}", exc_info=True)
            return 1
        except KeyboardInterrupt:
            self.formatter.warning("\nOperation cancelled by user")
            return 130
        except Exception as e:
            self.formatter.error(f"Unexpected error: {str(e)}")
            logger.error(f"Unexpected error: {e}", exc_info=True)
            return 1


def main():
    """Main entry point for the ORBIT CLI."""
    cli = OrbitCLI()
    parser = cli.create_parser()
    args = parser.parse_args()
    
    exit_code = cli.execute(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

