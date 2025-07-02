"""API key management commands for ORBIT CLI."""

import argparse
from datetime import datetime
from typing import Dict, Any, List, Type

from .base import CommandGroup, BaseCommand, OutputCommand, PaginatedCommand


class KeyCreateCommand(OutputCommand):
    """Create a new API key."""
    
    name = "create"
    help = "Create a new API key"
    description = "Create a new API key with optional system prompt"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add create command arguments."""
        parser.add_argument(
            '--collection',
            required=True,
            help='Collection name to associate with the key'
        )
        parser.add_argument(
            '--name',
            required=True,
            help='Client name for identification'
        )
        parser.add_argument(
            '--notes',
            help='Optional notes about this API key'
        )
        parser.add_argument(
            '--prompt-id',
            help='Existing system prompt ID to associate'
        )
        parser.add_argument(
            '--prompt-name',
            help='Name for a new system prompt'
        )
        parser.add_argument(
            '--prompt-file',
            help='Path to file containing system prompt'
        )
        parser.add_argument(
            '--expires-days',
            type=int,
            help='Number of days until key expires'
        )
        self.add_output_arguments(parser)
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the create command."""
        self.ensure_authenticated()
        
        try:
            result = self.api_manager.create_api_key_with_prompt(
                collection_name=args.collection,
                client_name=args.name,
                notes=args.notes,
                prompt_id=args.prompt_id,
                prompt_name=args.prompt_name,
                prompt_file=args.prompt_file
            )
            
            if self.formatter.format == 'json':
                self.formatter.format_json(result)
            else:
                self.formatter.success("API key created successfully")
                self.formatter.print(f"[bold]API Key:[/bold] {result.get('api_key', 'N/A')}")
                self.formatter.print(f"[bold]Client:[/bold] {result.get('client_name', 'N/A')}")
                self.formatter.print(f"[bold]Collection:[/bold] {result.get('collection', 'N/A')}")
                if result.get('system_prompt_id'):
                    self.formatter.print(f"[bold]Prompt ID:[/bold] {result['system_prompt_id']}")
            
            return 0
            
        except Exception as e:
            return self.handle_error(e, "Failed to create API key")


class KeyListCommand(PaginatedCommand):
    """List API keys."""
    
    name = "list"
    help = "List all API keys"
    description = "Display all API keys with their details and optional filtering"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add list command arguments."""
        parser.add_argument(
            '--active-only',
            action='store_true',
            help='Show only active keys'
        )
        parser.add_argument(
            '--collection',
            help='Filter by collection name'
        )
        self.add_pagination_arguments(parser)
        self.add_output_arguments(parser)
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the list command."""
        self.ensure_authenticated()
        
        try:
            pagination = self.get_pagination_params(args)
            
            if pagination['fetch_all']:
                result = self.api_manager.keys.list_all_api_keys(
                    collection=args.collection,
                    active_only=args.active_only
                )
            else:
                result = self.api_manager.keys.list_api_keys(
                    collection=args.collection,
                    active_only=args.active_only,
                    limit=pagination['limit'],
                    offset=pagination['offset']
                )
            
            if self.formatter.format == 'json':
                self.formatter.format_json(result)
            else:
                self._display_api_keys(result)
            
            return 0
            
        except Exception as e:
            return self.handle_error(e, "Failed to list API keys")
    
    def _display_api_keys(self, keys: List[Dict[str, Any]]) -> None:
        """Display API keys in table format."""
        if not keys:
            self.formatter.info("No API keys found")
            return
        
        headers = ['API Key', 'Client', 'Collection', 'Active', 'Created']
        data = []
        
        for key in keys:
            created_at = key.get('created_at', 'N/A')
            if isinstance(created_at, (int, float)):
                created_at = datetime.fromtimestamp(created_at).strftime('%Y-%m-%d')
            elif isinstance(created_at, str):
                created_at = created_at[:10]
            
            data.append({
                'API Key': key.get('api_key', 'N/A')[:20] + '...',
                'Client': key.get('client_name', 'N/A'),
                'Collection': key.get('collection', 'N/A'),
                'Active': '✓' if key.get('active', True) else '✗',
                'Created': created_at
            })
        
        self.formatter.format_table(data, headers)
        self.formatter.print(f"\nFound {len(keys)} API keys")


class KeyTestCommand(OutputCommand):
    """Test an API key."""
    
    name = "test"
    help = "Test an API key"
    description = "Test if an API key is valid and active"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add test command arguments."""
        parser.add_argument(
            '--key',
            required=True,
            help='API key to test'
        )
        self.add_output_arguments(parser)
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the test command."""
        try:
            result = self.api_manager.keys.test_api_key(args.key)
            
            if self.formatter.format == 'json':
                self.formatter.format_json(result)
            else:
                if result.get('status') == 'error':
                    self.formatter.error(f"API key test failed: {result.get('error', 'Unknown error')}")
                    return 1
                else:
                    self.formatter.success("API key is valid and active")
                    if 'key_info' in result:
                        info = result['key_info']
                        self.formatter.print(f"[bold]Client:[/bold] {info.get('client_name', 'N/A')}")
                        self.formatter.print(f"[bold]Collection:[/bold] {info.get('collection', 'N/A')}")
            
            return 0 if result.get('status') != 'error' else 1
            
        except Exception as e:
            return self.handle_error(e, "Failed to test API key")


class KeyStatusCommand(OutputCommand):
    """Get API key status."""
    
    name = "status"
    help = "Get API key status"
    description = "Get detailed status of an API key"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add status command arguments."""
        parser.add_argument(
            '--key',
            required=True,
            help='API key to check'
        )
        self.add_output_arguments(parser)
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the status command."""
        self.ensure_authenticated()
        
        try:
            result = self.api_manager.keys.get_api_key_status(args.key)
            
            if self.formatter.format == 'json':
                self.formatter.format_json(result)
            else:
                self._display_api_key_status(result)
            
            return 0
            
        except Exception as e:
            return self.handle_error(e, "Failed to get API key status")
    
    def _display_api_key_status(self, status: Dict[str, Any]) -> None:
        """Display API key status in formatted output."""
        if status.get('active'):
            self.formatter.success("API key is active")
        else:
            self.formatter.warning("API key is inactive")
        
        self.formatter.print(f"[bold]Client:[/bold] {status.get('client_name', 'N/A')}")
        self.formatter.print(f"[bold]Collection:[/bold] {status.get('collection', 'N/A')}")
        
        if 'created_at' in status:
            self.formatter.print(f"[bold]Created:[/bold] {status['created_at']}")
        if 'last_used' in status:
            self.formatter.print(f"[bold]Last Used:[/bold] {status['last_used']}")
        if 'system_prompt_id' in status:
            self.formatter.print(f"[bold]System Prompt:[/bold] {status['system_prompt_id']}")
        if 'notes' in status:
            self.formatter.print(f"[bold]Notes:[/bold] {status['notes']}")


class KeyDeactivateCommand(BaseCommand):
    """Deactivate an API key."""
    
    name = "deactivate"
    help = "Deactivate an API key"
    description = "Temporarily deactivate an API key"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add deactivate command arguments."""
        parser.add_argument(
            '--key',
            required=True,
            help='API key to deactivate'
        )
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the deactivate command."""
        self.ensure_authenticated()
        
        try:
            result = self.api_manager.keys.deactivate_api_key(args.key)
            self.formatter.success("API key deactivated successfully")
            return 0
            
        except Exception as e:
            return self.handle_error(e, "Failed to deactivate API key")


class KeyDeleteCommand(BaseCommand):
    """Delete an API key."""
    
    name = "delete"
    help = "Delete an API key"
    description = "Permanently delete an API key"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add delete command arguments."""
        parser.add_argument(
            '--key',
            required=True,
            help='API key to delete'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompt'
        )
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the delete command."""
        self.ensure_authenticated()
        
        if not self.require_confirmation(
            f"Are you sure you want to delete API key {args.key[:20]}...?",
            skip_flag='force'
        ):
            self.formatter.info("Operation cancelled")
            return 0
        
        try:
            result = self.api_manager.keys.delete_api_key(args.key)
            self.formatter.success("API key deleted successfully")
            return 0
            
        except Exception as e:
            return self.handle_error(e, "Failed to delete API key")


class ApiKeyCommandGroup(CommandGroup):
    """API key management command group."""
    
    name = "key"
    help = "Manage API keys"
    description = "Create, list, and manage API keys"
    
    def get_subcommands(self) -> Dict[str, Type[BaseCommand]]:
        """Get API key subcommands."""
        return {
            'create': KeyCreateCommand,
            'list': KeyListCommand,
            'test': KeyTestCommand,
            'status': KeyStatusCommand,
            'deactivate': KeyDeactivateCommand,
            'delete': KeyDeleteCommand
        }