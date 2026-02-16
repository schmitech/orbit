"""
Authentication commands.

Handles login, logout, register, me, and auth-status commands.
"""

import argparse
import getpass
from rich.console import Console

from bin.orbit.commands import BaseCommand
from bin.orbit.services.api_service import ApiService
from bin.orbit.services.auth_service import AuthService
from bin.orbit.utils.output import OutputFormatter

console = Console()

# Import keyring availability check
try:
    import keyring  # noqa: F401
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False


class LoginCommand(BaseCommand):
    """Command to login to the ORBIT server."""
    
    def __init__(self, api_service: ApiService, auth_service: AuthService, formatter: OutputFormatter):
        self.api_service = api_service
        self.auth_service = auth_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "login"
    
    @property
    def description(self) -> str:
        return "Login to the ORBIT server"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--username', '-u', help='Username (will prompt if not provided)')
        parser.add_argument('--password', '-p', help='Password (will prompt if not provided)')
        parser.add_argument('--no-save', action='store_true', help='Do not save credentials')
    
    def execute(self, args: argparse.Namespace) -> int:
        # Check if already authenticated
        auth_status = self.api_service.check_auth_status()
        if auth_status.get('authenticated'):
            current_user = auth_status.get('user', {})
            username = current_user.get('username', 'unknown')
            self.formatter.warning(f"Already logged in as {username}")
            self.formatter.info("Please logout first if you want to login with a different account")
            return 0
        
        # Prompt for username if not provided
        username = args.username
        if not username:
            from rich.prompt import Prompt
            username = Prompt.ask("Username")
            if not username:
                self.formatter.error("Username is required")
                return 1
        
        # Prompt for password if not provided
        password = args.password
        if not password:
            password = getpass.getpass("Password: ")
            if not password:
                self.formatter.error("Password is required")
                return 1
        
        result = self.api_service.login(username, password)
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            self.formatter.success(f"Logged in as {result.get('username', username)}")
            if not args.no_save:
                storage_method = self.auth_service.config_service.get_auth_storage_method()
                if storage_method == 'keyring':
                    self.formatter.info("Credentials securely stored in system keychain")
                elif storage_method == 'file':
                    self.formatter.info("Credentials saved to file storage (~/.orbit/.env)")
                else:
                    self.formatter.info("Credentials saved to secure file storage")
                    if not KEYRING_AVAILABLE:
                        self.formatter.warning("For enhanced security, consider installing keyring: pip install keyring")
        return 0


class LogoutCommand(BaseCommand):
    """Command to logout from the ORBIT server."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "logout"
    
    @property
    def description(self) -> str:
        return "Logout from the ORBIT server"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--all', action='store_true', help='Logout from all sessions')
    
    def execute(self, args: argparse.Namespace) -> int:
        result = self.api_service.logout()
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            if result.get("message", "").lower().startswith("logout successful"):
                self.formatter.success("Logged out successfully")
            else:
                self.formatter.info(result.get("message", "Logged out"))
        return 0


class RegisterCommand(BaseCommand):
    """Command to register a new user."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "register"
    
    @property
    def description(self) -> str:
        return "Register a new user (admin only)"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--username', '-u', required=True, help='Username for the new user')
        parser.add_argument('--password', '-p', help='Password (will prompt if not provided)')
        parser.add_argument('--role', '-r', default='user', choices=['user', 'admin'], help='User role')
        parser.add_argument('--email', help='Email address for the user')
    
    def execute(self, args: argparse.Namespace) -> int:
        password = args.password
        if not password:
            password = getpass.getpass("Password for new user: ")
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                self.formatter.error("Passwords do not match")
                return 1
        
        result = self.api_service.register_user(args.username, password, args.role)
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            self.formatter.success(f"User '{args.username}' registered successfully")
        return 0


class MeCommand(BaseCommand):
    """Command to show current user information."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "me"
    
    @property
    def description(self) -> str:
        return "Show current user information"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        pass
    
    def execute(self, args: argparse.Namespace) -> int:
        result = self.api_service.get_current_user()
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            self._display_user_info(result)
        return 0
    
    def _display_user_info(self, user: dict) -> None:
        """Display user information."""
        console.print(f"[bold]Username:[/bold] {user.get('username', 'N/A')}")
        console.print(f"[bold]Role:[/bold] {user.get('role', 'N/A')}")
        console.print(f"[bold]ID:[/bold] {user.get('_id') or user.get('id', 'N/A')}")
        if 'created_at' in user:
            console.print(f"[bold]Created:[/bold] {user['created_at']}")
        if 'last_login' in user:
            console.print(f"[bold]Last Login:[/bold] {user['last_login']}")


class AuthStatusCommand(BaseCommand):
    """Command to check authentication status."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "auth-status"
    
    @property
    def description(self) -> str:
        return "Check authentication status"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        pass
    
    def execute(self, args: argparse.Namespace) -> int:
        result = self.api_service.check_auth_status()
        
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            self._display_auth_status(result)
        return 0 if result['authenticated'] else 1
    
    def _display_auth_status(self, result: dict) -> None:
        """Display authentication status."""
        console.print("[bold]Server Authentication:[/bold] [green]ENABLED[/green]")
        
        if result.get('authenticated'):
            self.formatter.success("authenticated")
            user = result.get('user', {})
            console.print(f"[bold]Username:[/bold] {user.get('username', 'N/A')}")
            console.print(f"[bold]Role:[/bold] {user.get('role', 'N/A')}")
            console.print(f"[bold]ID:[/bold] {user.get('id', 'N/A')}")
            console.print(f"[bold]Created:[/bold] {user.get('created_at', 'N/A')}")
            console.print(f"[bold]Last Login:[/bold] {user.get('last_login', 'N/A')}")
        else:
            self.formatter.warning("not authenticated")
            message = result.get('message', 'No active session')
            console.print(f"\n[bold]Status:[/bold] {message}")

