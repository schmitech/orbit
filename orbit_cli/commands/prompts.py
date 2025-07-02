"""
System prompt commands
"""

import argparse
from orbit_cli.commands.base import BaseCommand
from orbit_cli.api.client import ApiManager
from orbit_cli.api.endpoints.prompts import PromptEndpoints


class PromptsCommand(BaseCommand):
    """System prompt commands"""
    
    def __init__(self, config, formatter):
        super().__init__(config, formatter)
        self.api = ApiManager()
        self.prompt_endpoints = PromptEndpoints(self.api)
    
    def add_arguments(self, parser: argparse.ArgumentParser):
        """Add prompt command arguments"""
        subparsers = parser.add_subparsers(dest="prompt_action", help="System prompt actions")
        
        # List command
        list_parser = subparsers.add_parser("list", help="List system prompts")
        list_parser.add_argument("--page", type=int, default=1, help="Page number")
        list_parser.add_argument("--limit", type=int, default=10, help="Items per page")
        
        # Create command
        create_parser = subparsers.add_parser("create", help="Create system prompt")
        create_parser.add_argument("name", help="Prompt name")
        create_parser.add_argument("content", help="Prompt content")
        create_parser.add_argument("--description", help="Prompt description")
        
        # Get command
        get_parser = subparsers.add_parser("get", help="Get system prompt")
        get_parser.add_argument("prompt_id", help="Prompt ID")
        
        # Update command
        update_parser = subparsers.add_parser("update", help="Update system prompt")
        update_parser.add_argument("prompt_id", help="Prompt ID")
        update_parser.add_argument("--name", help="New prompt name")
        update_parser.add_argument("--content", help="New prompt content")
        update_parser.add_argument("--description", help="New prompt description")
        
        # Delete command
        delete_parser = subparsers.add_parser("delete", help="Delete system prompt")
        delete_parser.add_argument("prompt_id", help="Prompt ID")
        
        # Activate command
        activate_parser = subparsers.add_parser("activate", help="Activate system prompt")
        activate_parser.add_argument("prompt_id", help="Prompt ID")
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute prompt command"""
        if args.prompt_action == "list":
            return self._list_prompts(args)
        elif args.prompt_action == "create":
            return self._create_prompt(args)
        elif args.prompt_action == "get":
            return self._get_prompt(args)
        elif args.prompt_action == "update":
            return self._update_prompt(args)
        elif args.prompt_action == "delete":
            return self._delete_prompt(args)
        elif args.prompt_action == "activate":
            return self._activate_prompt(args)
        else:
            self.print_error("No prompt action specified")
            return 1
    
    def _list_prompts(self, args) -> int:
        """List system prompts"""
        try:
            response = self.prompt_endpoints.list_prompts(args.page, args.limit)
            if response and response.data:
                self.print_result(response.data)
                return 0
            else:
                self.print_error("Failed to list system prompts")
                return 1
        except Exception as e:
            self.print_error(f"Error listing system prompts: {e}")
            return 1
    
    def _create_prompt(self, args) -> int:
        """Create system prompt"""
        try:
            response = self.prompt_endpoints.create_prompt(args.name, args.content, args.description)
            if response and response.data:
                self.print_result(response.data)
                self.print_success("System prompt created successfully")
                return 0
            else:
                self.print_error("Failed to create system prompt")
                return 1
        except Exception as e:
            self.print_error(f"Error creating system prompt: {e}")
            return 1
    
    def _get_prompt(self, args) -> int:
        """Get system prompt"""
        try:
            response = self.prompt_endpoints.get_prompt(args.prompt_id)
            if response and response.data:
                self.print_result(response.data)
                return 0
            else:
                self.print_error("Failed to get system prompt")
                return 1
        except Exception as e:
            self.print_error(f"Error getting system prompt: {e}")
            return 1
    
    def _update_prompt(self, args) -> int:
        """Update system prompt"""
        try:
            update_data = {}
            if args.name:
                update_data["name"] = args.name
            if args.content:
                update_data["content"] = args.content
            if args.description:
                update_data["description"] = args.description
            
            response = self.prompt_endpoints.update_prompt(args.prompt_id, **update_data)
            if response and response.data:
                self.print_result(response.data)
                self.print_success("System prompt updated successfully")
                return 0
            else:
                self.print_error("Failed to update system prompt")
                return 1
        except Exception as e:
            self.print_error(f"Error updating system prompt: {e}")
            return 1
    
    def _delete_prompt(self, args) -> int:
        """Delete system prompt"""
        try:
            response = self.prompt_endpoints.delete_prompt(args.prompt_id)
            if response:
                self.print_success("System prompt deleted successfully")
                return 0
            else:
                self.print_error("Failed to delete system prompt")
                return 1
        except Exception as e:
            self.print_error(f"Error deleting system prompt: {e}")
            return 1
    
    def _activate_prompt(self, args) -> int:
        """Activate system prompt"""
        try:
            response = self.prompt_endpoints.activate_prompt(args.prompt_id)
            if response:
                self.print_success("System prompt activated successfully")
                return 0
            else:
                self.print_error("Failed to activate system prompt")
                return 1
        except Exception as e:
            self.print_error(f"Error activating system prompt: {e}")
 