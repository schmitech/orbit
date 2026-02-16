"""
User management commands.

Handles list, reset-password, delete, deactivate, activate, and change-password commands.
"""

import argparse
import getpass
import secrets
import string
from datetime import datetime
from rich.console import Console
from rich.prompt import Confirm

from bin.orbit.commands import BaseCommand
from bin.orbit.services.api_service import ApiService
from bin.orbit.utils.output import OutputFormatter

console = Console()


class UserListCommand(BaseCommand):
    """Command to list all users."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "user list"
    
    @property
    def description(self) -> str:
        return "List all users"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--role', choices=['user', 'admin'], help='Filter by role')
        parser.add_argument('--active-only', action='store_true', help='Show only active users')
        parser.add_argument('--limit', type=int, default=100, help='Maximum number of users to return')
        parser.add_argument('--offset', type=int, default=0, help='Number of users to skip for pagination')
    
    def execute(self, args: argparse.Namespace) -> int:
        result = self.api_service.list_users(
            role=args.role,
            active_only=args.active_only,
            limit=args.limit,
            offset=args.offset
        )
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            if result:
                headers = ['ID', 'Username', 'Role', 'Active', 'Created']
                data = []
                for user in result:
                    created_at = user.get('created_at', 'N/A')
                    if isinstance(created_at, (int, float)):
                        created_at = datetime.fromtimestamp(created_at).strftime('%Y-%m-%d')
                    elif isinstance(created_at, str):
                        created_at = created_at[:10]
                    
                    data.append({
                        'ID': (user.get('_id') or user.get('id', 'N/A'))[:12] + '...',
                        'Username': user.get('username', 'N/A'),
                        'Role': user.get('role', 'N/A'),
                        'Active': '✓' if user.get('active', True) else '✗',
                        'Created': created_at
                    })
                self.formatter.format_table(data, headers)
                console.print(f"Found {len(result)} users")
            else:
                console.print("No users found")
        return 0


class UserResetPasswordCommand(BaseCommand):
    """Command to reset a user's password."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "user reset-password"
    
    @property
    def description(self) -> str:
        return "Reset user password"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        reset_group = parser.add_mutually_exclusive_group(required=True)
        reset_group.add_argument('--user-id', help='User ID')
        reset_group.add_argument('--username', help='Username')
        parser.add_argument('--password', help='New password (will generate if not provided)')
    
    def execute(self, args: argparse.Namespace) -> int:
        # Determine user ID from either --user-id or --username
        user_id = args.user_id
        if args.username:
            user_id = self.api_service.find_user_id_by_username(args.username)
        
        password = args.password
        if not password:
            # Generate a random password
            alphabet = string.ascii_letters + string.digits
            password = ''.join(secrets.choice(alphabet) for i in range(16))
            console.print(f"[bold]Generated password:[/bold] {password}")
        
        result = self.api_service.reset_user_password(user_id, password)
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            self.formatter.success("User password reset successfully")
        return 0


class UserDeleteCommand(BaseCommand):
    """Command to delete a user."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "user delete"
    
    @property
    def description(self) -> str:
        return "Delete a user"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--user-id', required=True, help='User ID to delete')
        parser.add_argument('--force', action='store_true', help='Skip confirmation prompt')
    
    def execute(self, args: argparse.Namespace) -> int:
        if not args.force:
            if not Confirm.ask(f"Are you sure you want to delete user {args.user_id[:12]}...?"):
                self.formatter.info("Operation cancelled")
                return 0
        
        result = self.api_service.delete_user(args.user_id)
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            self.formatter.success("User deleted successfully")
        return 0


class UserDeactivateCommand(BaseCommand):
    """Command to deactivate a user."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "user deactivate"
    
    @property
    def description(self) -> str:
        return "Deactivate a user"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--user-id', required=True, help='User ID to deactivate')
        parser.add_argument('--force', action='store_true', help='Skip confirmation prompt')
    
    def execute(self, args: argparse.Namespace) -> int:
        if not args.force:
            if not Confirm.ask(f"Are you sure you want to deactivate user {args.user_id[:12]}...?"):
                self.formatter.info("Operation cancelled")
                return 0
        
        result = self.api_service.deactivate_user(args.user_id)
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            self.formatter.success("User deactivated successfully")
        return 0


class UserActivateCommand(BaseCommand):
    """Command to activate a user."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "user activate"
    
    @property
    def description(self) -> str:
        return "Activate a user"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--user-id', required=True, help='User ID to activate')
        parser.add_argument('--force', action='store_true', help='Skip confirmation prompt')
    
    def execute(self, args: argparse.Namespace) -> int:
        if not args.force:
            if not Confirm.ask(f"Are you sure you want to activate user {args.user_id[:12]}...?"):
                self.formatter.info("Operation cancelled")
                return 0
        
        result = self.api_service.activate_user(args.user_id)
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            self.formatter.success("User activated successfully")
        return 0


class UserChangePasswordCommand(BaseCommand):
    """Command to change your password."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "user change-password"
    
    @property
    def description(self) -> str:
        return "Change your password"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--current-password', help='Current password (will prompt if not provided)')
        parser.add_argument('--new-password', help='New password (will prompt if not provided)')
    
    def execute(self, args: argparse.Namespace) -> int:
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
        
        result = self.api_service.change_password(current_password, new_password)
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            self.formatter.success("Password changed successfully")
            self.formatter.warning("All sessions have been invalidated. Please login again.")
        
        # Clear the local token since it's now invalid
        self.api_service.auth_service.clear_token()
        return 0

