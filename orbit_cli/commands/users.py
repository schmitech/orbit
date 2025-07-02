"""
User management commands
"""

import argparse
from orbit_cli.commands.base import BaseCommand
from orbit_cli.api.client import ApiManager
from orbit_cli.api.endpoints.users import UserEndpoints


class UsersCommand(BaseCommand):
    """User management commands"""
    
    def __init__(self, config, formatter):
        super().__init__(config, formatter)
        self.api = ApiManager()
        self.user_endpoints = UserEndpoints(self.api)
    
    def add_arguments(self, parser: argparse.ArgumentParser):
        """Add user command arguments"""
        subparsers = parser.add_subparsers(dest="user_action", help="User management actions")
        
        # List command
        list_parser = subparsers.add_parser("list", help="List users")
        list_parser.add_argument("--page", type=int, default=1, help="Page number")
        list_parser.add_argument("--limit", type=int, default=10, help="Items per page")
        
        # Create command
        create_parser = subparsers.add_parser("create", help="Create user")
        create_parser.add_argument("username", help="Username")
        create_parser.add_argument("email", help="Email")
        create_parser.add_argument("password", help="Password")
        
        # Get command
        get_parser = subparsers.add_parser("get", help="Get user")
        get_parser.add_argument("user_id", help="User ID")
        
        # Update command
        update_parser = subparsers.add_parser("update", help="Update user")
        update_parser.add_argument("user_id", help="User ID")
        update_parser.add_argument("--username", help="New username")
        update_parser.add_argument("--email", help="New email")
        update_parser.add_argument("--password", help="New password")
        
        # Delete command
        delete_parser = subparsers.add_parser("delete", help="Delete user")
        delete_parser.add_argument("user_id", help="User ID")
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute user command"""
        if args.user_action == "list":
            return self._list_users(args)
        elif args.user_action == "create":
            return self._create_user(args)
        elif args.user_action == "get":
            return self._get_user(args)
        elif args.user_action == "update":
            return self._update_user(args)
        elif args.user_action == "delete":
            return self._delete_user(args)
        else:
            self.print_error("No user action specified")
            return 1
    
    def _list_users(self, args) -> int:
        """List users"""
        try:
            response = self.user_endpoints.list_users(args.page, args.limit)
            if response and response.data:
                self.print_result(response.data)
                return 0
            else:
                self.print_error("Failed to list users")
                return 1
        except Exception as e:
            self.print_error(f"Error listing users: {e}")
            return 1
    
    def _create_user(self, args) -> int:
        """Create user"""
        try:
            response = self.user_endpoints.create_user(args.username, args.email, args.password)
            if response and response.data:
                self.print_result(response.data)
                self.print_success("User created successfully")
                return 0
            else:
                self.print_error("Failed to create user")
                return 1
        except Exception as e:
            self.print_error(f"Error creating user: {e}")
            return 1
    
    def _get_user(self, args) -> int:
        """Get user"""
        try:
            response = self.user_endpoints.get_user(args.user_id)
            if response and response.data:
                self.print_result(response.data)
                return 0
            else:
                self.print_error("Failed to get user")
                return 1
        except Exception as e:
            self.print_error(f"Error getting user: {e}")
            return 1
    
    def _update_user(self, args) -> int:
        """Update user"""
        try:
            update_data = {}
            if args.username:
                update_data["username"] = args.username
            if args.email:
                update_data["email"] = args.email
            if args.password:
                update_data["password"] = args.password
            
            response = self.user_endpoints.update_user(args.user_id, **update_data)
            if response and response.data:
                self.print_result(response.data)
                self.print_success("User updated successfully")
                return 0
            else:
                self.print_error("Failed to update user")
                return 1
        except Exception as e:
            self.print_error(f"Error updating user: {e}")
            return 1
    
    def _delete_user(self, args) -> int:
        """Delete user"""
        try:
            response = self.user_endpoints.delete_user(args.user_id)
            if response:
                self.print_success("User deleted successfully")
                return 0
            else:
                self.print_error("Failed to delete user")
                return 1
        except Exception as e:
            self.print_error(f"Error deleting user: {e}")
            return 1 