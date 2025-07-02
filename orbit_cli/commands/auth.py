"""Authentication commands for ORBIT CLI."""

import argparse
import getpass
from typing import Dict, Any

from .base import BaseCommand, OutputCommand
from ..core.exceptions import AuthenticationError


class LoginCommand(OutputCommand):
    """Login to the ORBIT server."""
    
    name = "login"
    help = "Login to the ORBIT server"
    description = "Authenticate with the ORBIT server and save credentials"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add login command arguments."""
        parser.add_argument(
            '--username', '-u',
            help='Username (will prompt if not provided)'
        )
        parser.add_argument(
            '--password', '-p',
            help='Password (will prompt if not provided)'
        )
        parser.add_argument(
            '--no-save',
            action='store_true',
            help='Do not save credentials'
        )
        parser.add_argument(
            '--server-url',
            help='Server URL (overrides config)'
        )
        self.add_output_arguments(parser)
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the login command."""
        if not self.api_manager:
            self.formatter.error("API manager not initialized")
            return 1
        
        # Check if already authenticated
        auth_status = self.api_manager.check_auth_status()
        if auth_status.get('authenticated'):
            current_user = auth_status.get('user', {})
            username = current_user.get('username', 'unknown')
            self.formatter.warning(f"Already logged in as {username}")
            self.formatter.info("Please logout first if you want to login with a different account")
            return 0
        
        # Get credentials
        username = args.username
        if not username:
            username = input("Username: ")
            if not username:
                self.formatter.error("Username is required")
                return 1
        
        password = args.password
        if not password:
            password = getpass.getpass("Password: ")
            if not password:
                self.formatter.error("Password is required")
                return 1
        
        # Attempt login
        try:
            result = self.api_manager.login(username, password)
            
            if self.formatter.format == 'json':
                self.formatter.format_json(result)
            else:
                self.formatter.success(f"Logged in as {result.get('username', username)}")
                if not args.no_save:
                    storage_method = self.api_manager.auth.token_manager.storage_method
                    if storage_method == 'keyring':
                        self.formatter.info("Credentials securely stored in system keychain")
                    elif storage_method == 'file':
                        self.formatter.info("Credentials saved to file storage (~/.orbit/.env)")
                    else:
                        self.formatter.info("Credentials saved")
            
            return 0
            
        except AuthenticationError as e:
            self.formatter.error(str(e))
            return 1
        except Exception as e:
            self.formatter.error(f"Login failed: {str(e)}")
            return 1


class LogoutCommand(OutputCommand):
    """Logout from the ORBIT server."""
    
    name = "logout"
    help = "Logout from the ORBIT server"
    description = "Logout and clear saved credentials"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add logout command arguments."""
        parser.add_argument(
            '--all',
            action='store_true',
            help='Logout from all sessions'
        )
        self.add_output_arguments(parser)
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the logout command."""
        if not self.api_manager:
            self.formatter.error("API manager not initialized")
            return 1
        
        result = self.api_manager.logout()
        
        if self.formatter.format == 'json':
            self.formatter.format_json(result)
        else:
            message = result.get("message", "Logged out")
            if message.lower().startswith("logout successful"):
                self.formatter.success("Logged out successfully")
            else:
                self.formatter.info(message)
        
        return 0


class RegisterCommand(OutputCommand):
    """Register a new user."""
    
    name = "register"
    help = "Register a new user (admin only)"
    description = "Register a new user account (requires admin privileges)"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add register command arguments."""
        parser.add_argument(
            '--username', '-u',
            required=True,
            help='Username for the new user'
        )
        parser.add_argument(
            '--password', '-p',
            help='Password (will prompt if not provided)'
        )
        parser.add_argument(
            '--role', '-r',
            default='user',
            choices=['user', 'admin'],
            help='User role (default: user)'
        )
        parser.add_argument(
            '--email',
            help='Email address for the user'
        )
        self.add_output_arguments(parser)
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the register command."""
        if not self.api_manager:
            self.formatter.error("API manager not initialized")
            return 1
        
        self.ensure_authenticated()
        
        # Get password
        password = args.password
        if not password:
            password = getpass.getpass("Password for new user: ")
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                self.formatter.error("Passwords do not match")
                return 1
        
        try:
            result = self.api_manager.auth.register_user(
                username=args.username,
                password=password,
                role=args.role,
                email=args.email
            )
            
            if self.formatter.format == 'json':
                self.formatter.format_json(result)
            else:
                self.formatter.success(f"User '{args.username}' registered successfully")
            
            return 0
            
        except Exception as e:
            return self.handle_error(e, "Registration failed")


class MeCommand(OutputCommand):
    """Show current user information."""
    
    name = "me"
    help = "Show current user information"
    description = "Display information about the currently authenticated user"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add me command arguments."""
        self.add_output_arguments(parser)
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the me command."""
        if not self.api_manager:
            self.formatter.error("API manager not initialized")
            return 1
        
        self.ensure_authenticated()
        
        try:
            result = self.api_manager.get_current_user()
            
            if self.formatter.format == 'json':
                self.formatter.format_json(result)
            else:
                self._display_user_info(result)
            
            return 0
            
        except Exception as e:
            return self.handle_error(e, "Failed to get user info")
    
    def _display_user_info(self, user: Dict[str, Any]) -> None:
        """Display user information in formatted output."""
        self.formatter.print(f"[bold]Username:[/bold] {user.get('username', 'N/A')}")
        self.formatter.print(f"[bold]Role:[/bold] {user.get('role', 'N/A')}")
        self.formatter.print(f"[bold]ID:[/bold] {user.get('_id') or user.get('id', 'N/A')}")
        
        if 'email' in user:
            self.formatter.print(f"[bold]Email:[/bold] {user['email']}")
        if 'created_at' in user:
            self.formatter.print(f"[bold]Created:[/bold] {user['created_at']}")
        if 'last_login' in user:
            self.formatter.print(f"[bold]Last Login:[/bold] {user['last_login']}")
        if 'active' in user:
            status = "Active" if user['active'] else "Inactive"
            self.formatter.print(f"[bold]Status:[/bold] {status}")


class AuthStatusCommand(OutputCommand):
    """Check authentication status."""
    
    name = "auth-status"
    help = "Check authentication status"
    description = "Check if you are authenticated and token validity"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add auth-status command arguments."""
        self.add_output_arguments(parser)
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the auth-status command."""
        if not self.api_manager:
            self.formatter.error("API manager not initialized")
            return 1
        
        result = self.api_manager.check_auth_status()
        
        if self.formatter.format == 'json':
            self.formatter.format_json(result)
        else:
            self._display_auth_status(result)
        
        return 0 if result['authenticated'] else 1
    
    def _display_auth_status(self, result: Dict[str, Any]) -> None:
        """Display authentication status in formatted output."""
        if result.get('authenticated'):
            self.formatter.success("Authenticated")
            
            user = result.get('user', {})
            self.formatter.print(f"[bold]Username:[/bold] {user.get('username', 'N/A')}")
            self.formatter.print(f"[bold]Role:[/bold] {user.get('role', 'N/A')}")
            self.formatter.print(f"[bold]ID:[/bold] {user.get('id', 'N/A')}")
            
            if 'created_at' in user:
                self.formatter.print(f"[bold]Created:[/bold] {user['created_at']}")
            if 'last_login' in user:
                self.formatter.print(f"[bold]Last Login:[/bold] {user['last_login']}")
        else:
            self.formatter.warning("Not authenticated")
            message = result.get('message', 'No active session')
            self.formatter.print(f"\n[bold]Status:[/bold] {message}")
        
        # Security info
        security = result.get('security', {})
        if security:
            self.formatter.print(f"\n[bold]Security:[/bold]")
            self.formatter.print(f"  Storage method: {security.get('storage_method', 'unknown')}")
            self.formatter.print(f"  Keyring available: {security.get('keyring_available', False)}")


class ChangePasswordCommand(BaseCommand):
    """Change your password."""
    
    name = "change-password"
    help = "Change your password"
    description = "Change your account password"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add change-password command arguments."""
        parser.add_argument(
            '--current-password',
            help='Current password (will prompt if not provided)'
        )
        parser.add_argument(
            '--new-password',
            help='New password (will prompt if not provided)'
        )
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the change-password command."""
        if not self.api_manager:
            self.formatter.error("API manager not initialized")
            return 1
        
        self.ensure_authenticated()
        
        # Get passwords
        current_password = args.current_password
        if not current_password:
            current_password = getpass.getpass("Current password: ")
        
        new_password = args.new_password
        if not new_password:
            new_password = getpass.getpass("New password: ")
            confirm = getpass.getpass("Confirm new password: ")
            if new_password != confirm:
                self.formatter.error("New passwords do not match")
                return 1
        
        try:
            result = self.api_manager.auth.change_password(current_password, new_password)
            self.formatter.success("Password changed successfully")
            self.formatter.warning("All sessions have been invalidated. Please login again.")
            return 0
            
        except Exception as e:
            return self.handle_error(e, "Failed to change password")