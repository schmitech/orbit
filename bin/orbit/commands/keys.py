"""
API key management commands.

Handles create, list, test, status, rename, deactivate, delete, and list-adapters commands.
"""

import argparse
from datetime import datetime
from rich.console import Console
from rich.prompt import Confirm

from bin.orbit.commands import BaseCommand
from bin.orbit.services.api_service import ApiService
from bin.orbit.services.config_service import ConfigService
from bin.orbit.utils.output import OutputFormatter

console = Console()


class KeyCreateCommand(BaseCommand):
    """Command to create a new API key."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "key create"
    
    @property
    def description(self) -> str:
        return "Create a new API key"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--adapter', required=True, help='Adapter name to associate with the key')
        parser.add_argument('--name', required=True, help='Client name for identification')
        parser.add_argument('--notes', help='Optional notes about this API key')
        parser.add_argument('--notes-file', help='Path to file containing notes text')
        parser.add_argument('--prompt-id', help='Existing system prompt ID to associate')
        parser.add_argument('--prompt-name', help='Name for a new system prompt')
        parser.add_argument('--prompt-file', help='Path to file containing system prompt')
        parser.add_argument('--prompt-text', help='Prompt text as a string (alternative to --prompt-file)')
        parser.add_argument('--expires-in-days', type=int, help='Days until the key expires (default: server default_lifetime_days)')
        parser.add_argument('--non-expiring', action='store_true', help='Request a non-expiring key (requires --justification and admin policy approval)')
        parser.add_argument('--justification', help='Justification required when using --non-expiring')

    def execute(self, args: argparse.Namespace) -> int:
        try:
            # Validate that both notes and notes-file are not provided
            if args.notes and args.notes_file:
                self.formatter.error("Cannot specify both --notes and --notes-file. Use only one.")
                return 1

            # Validate that both prompt-text and prompt-file are not provided
            if args.prompt_text and args.prompt_file:
                self.formatter.error("Cannot specify both --prompt-text and --prompt-file. Use only one.")
                return 1

            if args.non_expiring and not args.justification:
                self.formatter.error("--non-expiring requires --justification.")
                return 1

            if args.non_expiring and args.expires_in_days is not None:
                self.formatter.error("Cannot specify both --non-expiring and --expires-in-days. Use only one.")
                return 1

            result = self.api_service.create_api_key(
                client_name=args.name,
                notes=args.notes,
                prompt_id=args.prompt_id,
                prompt_name=args.prompt_name,
                prompt_file=args.prompt_file,
                adapter_name=args.adapter,
                prompt_text=args.prompt_text,
                notes_file=args.notes_file,
                expires_in_days=args.expires_in_days,
                non_expiring=args.non_expiring,
                expiration_justification=args.justification,
            )
            if getattr(args, 'output', None) == 'json':
                self.formatter.format_json(result)
            else:
                self.formatter.success("API key created successfully")
                console.print(f"[bold]API Key:[/bold] {result.get('api_key', 'N/A')}")
                console.print(f"[bold]Client:[/bold] {result.get('client_name', 'N/A')}")
                if result.get('adapter_name'):
                    console.print(f"[bold]Adapter:[/bold] {result['adapter_name']}")
                if result.get('system_prompt_id'):
                    console.print(f"[bold]Prompt ID:[/bold] {result['system_prompt_id']}")
                if result.get('expiration_policy') == 'non_expiring_exception':
                    console.print("[bold]Expiration:[/bold] non-expiring (exception)")
                elif result.get('expires_at'):
                    console.print(f"[bold]Expires:[/bold] {datetime.fromtimestamp(result['expires_at']).strftime('%Y-%m-%d')}")
            return 0
        except Exception as e:
            self.formatter.error(f"Failed to create API key: {e!s}")
            return 1


class KeyListCommand(BaseCommand):
    """Command to list all API keys."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "key list"
    
    @property
    def description(self) -> str:
        return "List all API keys"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--active-only', action='store_true', help='Show only active keys')
        parser.add_argument('--limit', type=int, default=100, help='Maximum number of keys to return')
        parser.add_argument('--offset', type=int, default=0, help='Number of keys to skip for pagination')
        parser.add_argument('--expired', action='store_true', help='Show only expired keys')
        parser.add_argument('--expiring-within-days', type=int, help='Show only keys expiring within this many days')
        parser.add_argument('--output', choices=['table', 'json'], default='table', help='Output format (default: table)')

    def execute(self, args: argparse.Namespace) -> int:
        result = self.api_service.list_api_keys(
            active_only=args.active_only,
            limit=args.limit,
            offset=args.offset,
            expired_only=args.expired,
            expiring_within_days=args.expiring_within_days,
        )
        # Check for output format (from subcommand arg or parent parser)
        output_format = getattr(args, 'output', 'table')
        if output_format == 'json':
            self.formatter.format_json(result)
        else:
            if result:
                headers = ['API Key', 'Client', 'Adapter', 'Active', 'Created', 'Expires']
                data = []
                for key in result:
                    created_at = key.get('created_at', 'N/A')
                    if isinstance(created_at, (int, float)):
                        created_at = datetime.fromtimestamp(created_at).strftime('%Y-%m-%d')
                    elif isinstance(created_at, str):
                        created_at = created_at[:10]

                    if key.get('expiration_policy') == 'non_expiring_exception':
                        expires = 'never'
                    elif key.get('expires_at'):
                        expires_str = datetime.fromtimestamp(key['expires_at']).strftime('%Y-%m-%d')
                        expires = f"{expires_str} (expired)" if key.get('expired') else expires_str
                    else:
                        expires = 'N/A'

                    data.append({
                        'API Key': key.get('api_key', 'N/A')[:20] + '...',
                        'Client': key.get('client_name', 'N/A'),
                        'Adapter': key.get('adapter_name', 'N/A'),
                        'Active': '✓' if key.get('active', True) else '✗',
                        'Created': created_at,
                        'Expires': expires,
                    })
                self.formatter.format_table(data, headers)
                console.print(f"Found {len(result)} api keys")
            else:
                console.print("No api keys found")
        return 0


class KeyTestCommand(BaseCommand):
    """Command to test an API key."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "key test"
    
    @property
    def description(self) -> str:
        return "Test an API key"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--key', required=True, help='API key to test')
    
    def execute(self, args: argparse.Namespace) -> int:
        result = self.api_service.test_api_key(args.key)
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            if result.get('status') == 'error':
                self.formatter.error(f"API key test failed: {result.get('error', 'Unknown error')}")
                return 1
            else:
                self.formatter.success("API key is valid and active")
        return 0 if result.get('status') != 'error' else 1


class KeyStatusCommand(BaseCommand):
    """Command to get API key status."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "key status"
    
    @property
    def description(self) -> str:
        return "Get API key status"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--key', required=True, help='API key to check')
    
    def execute(self, args: argparse.Namespace) -> int:
        result = self.api_service.get_api_key_status(args.key)
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            self._display_api_key_status(result)
        return 0
    
    def _display_api_key_status(self, status: dict) -> None:
        """Display API key status."""
        if status.get('active'):
            self.formatter.success("API key is active")
        else:
            self.formatter.warning("API key is inactive")
        
        console.print(f"[bold]Client:[/bold] {status.get('client_name', 'N/A')}")
        if status.get('adapter_name'):
            console.print(f"[bold]Adapter:[/bold] {status['adapter_name']}")
        if 'created_at' in status:
            console.print(f"[bold]Created:[/bold] {status['created_at']}")
        if 'last_used' in status:
            console.print(f"[bold]Last Used:[/bold] {status['last_used']}")
        if 'system_prompt_id' in status:
            console.print(f"[bold]System Prompt:[/bold] {status['system_prompt_id']}")
        if status.get('expiration_policy') == 'non_expiring_exception':
            console.print("[bold]Expiration:[/bold] non-expiring (exception)")
        elif status.get('expires_at'):
            expires_at = status['expires_at']
            if isinstance(expires_at, (int, float)):
                expires_at = datetime.fromtimestamp(expires_at).strftime('%Y-%m-%d')
            console.print(f"[bold]Expires:[/bold] {expires_at}{' (expired)' if status.get('expired') else ''}")


class KeyRenameCommand(BaseCommand):
    """Command to rename an API key."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "key rename"
    
    @property
    def description(self) -> str:
        return "Rename an API key"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--old-key', required=True, help='Current API key to rename')
        parser.add_argument('--new-key', required=True, help='New API key value')
    
    def execute(self, args: argparse.Namespace) -> int:
        result = self.api_service.rename_api_key(args.old_key, args.new_key)
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            self.formatter.success("API key renamed successfully")
            masked_old = f"***{args.old_key[-4:]}" if len(args.old_key) > 4 else "***"
            masked_new = f"***{args.new_key[-4:]}" if len(args.new_key) > 4 else "***"
            console.print(f"Old key: {masked_old}")
            console.print(f"New key: {masked_new}")
        return 0


class KeyRenewCommand(BaseCommand):
    """Command to renew an API key's expiration."""

    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter

    @property
    def name(self) -> str:
        return "key renew"

    @property
    def description(self) -> str:
        return "Renew an API key's expiration, or grant a non-expiring exception"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--key', required=True, help='API key or record ID to renew')
        parser.add_argument('--expires-in-days', type=int, help='Days from now until the key expires')
        parser.add_argument('--non-expiring', action='store_true', help='Grant a non-expiring exception (requires --justification and admin policy approval)')
        parser.add_argument('--justification', help='Justification required when using --non-expiring')

    def execute(self, args: argparse.Namespace) -> int:
        if args.non_expiring and not args.justification:
            self.formatter.error("--non-expiring requires --justification.")
            return 1
        if not args.non_expiring and args.expires_in_days is None:
            self.formatter.error("Specify --expires-in-days or --non-expiring.")
            return 1
        if args.non_expiring and args.expires_in_days is not None:
            self.formatter.error("Cannot specify both --non-expiring and --expires-in-days. Use only one.")
            return 1

        result = self.api_service.renew_api_key(
            args.key,
            expires_in_days=args.expires_in_days,
            non_expiring=args.non_expiring,
            expiration_justification=args.justification,
        )
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            self.formatter.success("API key renewed successfully")
            if result.get('expiration_policy') == 'non_expiring_exception':
                console.print("[bold]Expiration:[/bold] non-expiring (exception)")
            elif result.get('expires_at'):
                console.print(f"[bold]Expires:[/bold] {datetime.fromtimestamp(result['expires_at']).strftime('%Y-%m-%d')}")
        return 0


class KeyDeactivateCommand(BaseCommand):
    """Command to deactivate an API key."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "key deactivate"
    
    @property
    def description(self) -> str:
        return "Deactivate an API key"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--key', required=True, help='API key to deactivate')
    
    def execute(self, args: argparse.Namespace) -> int:
        result = self.api_service.deactivate_api_key(args.key)
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            self.formatter.success("API key deactivated successfully")
        return 0


class KeyDeleteCommand(BaseCommand):
    """Command to delete an API key."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "key delete"
    
    @property
    def description(self) -> str:
        return "Delete an API key"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--key', required=True, help='API key to delete')
        parser.add_argument('--force', action='store_true', help='Skip confirmation prompt')
    
    def execute(self, args: argparse.Namespace) -> int:
        if not args.force:
            if not Confirm.ask(f"Are you sure you want to delete API key {args.key[:20]}...?"):
                self.formatter.info("Operation cancelled")
                return 0
        
        result = self.api_service.delete_api_key(args.key)
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            self.formatter.success("API key deleted successfully")
        return 0


class KeyListAdaptersCommand(BaseCommand):
    """Command to list available adapters."""
    
    def __init__(self, config_service: ConfigService, formatter: OutputFormatter):
        self.config_service = config_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "key list-adapters"
    
    @property
    def description(self) -> str:
        return "List available adapters"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        pass
    
    def execute(self, args: argparse.Namespace) -> int:
        # Note: This should read from server config via API, but for now we'll read local config
        # In a full implementation, this would call a server endpoint
        import yaml
        from pathlib import Path
        
        # Try to find config file
        script_dir = Path(__file__).parent.parent.parent
        config_paths = [
            script_dir / "config" / "config.yaml",
            script_dir / "config.yaml"
        ]
        
        adapters = []
        for config_path in config_paths:
            if config_path.exists():
                try:
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f)
                        adapters = config.get('adapters', [])
                        break
                except Exception:
                    pass
        
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(adapters)
        else:
            if adapters:
                headers = ['Name', 'Type', 'Datasource', 'Adapter', 'Implementation']
                data = []
                for adapter in adapters:
                    data.append({
                        'Name': adapter.get('name', 'N/A'),
                        'Type': adapter.get('type', 'N/A'),
                        'Datasource': adapter.get('datasource', 'N/A'),
                        'Adapter': adapter.get('adapter', 'N/A'),
                        'Implementation': (adapter.get('implementation', 'N/A')[:40] + '...' 
                                         if len(adapter.get('implementation', '')) > 40 
                                         else adapter.get('implementation', 'N/A'))
                    })
                self.formatter.format_table(data, headers)
                console.print(f"Found {len(adapters)} configured adapters")
                console.print("\n[bold]Usage:[/bold] orbit key create --adapter <name> --name \"Client Name\"")
            else:
                console.print("No adapters configured")
                console.print("Check config/adapters.yaml for adapter configuration")
        return 0
