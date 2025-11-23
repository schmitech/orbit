"""
System prompt management commands.

Handles create, list, get, update, delete, and associate commands.
"""

import argparse
from datetime import datetime
from typing import Any
from rich.console import Console
from rich.prompt import Confirm

from bin.orbit.commands import BaseCommand
from bin.orbit.services.api_service import ApiService
from bin.orbit.utils.output import OutputFormatter

console = Console()


class PromptCreateCommand(BaseCommand):
    """Command to create a new system prompt."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "prompt create"
    
    @property
    def description(self) -> str:
        return "Create a new system prompt"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--name', required=True, help='Unique name for the prompt')
        parser.add_argument('--file', help='Path to file containing prompt text')
        parser.add_argument('--prompt-text', help='Prompt text as a string (alternative to --file)')
        parser.add_argument('--version', default='1.0', help='Version string (default: 1.0)')
    
    def execute(self, args: argparse.Namespace) -> int:
        # Validate that either file or prompt-text is provided
        if not args.file and not args.prompt_text:
            self.formatter.error("Either --file or --prompt-text must be provided")
            return 1
        
        if args.file and args.prompt_text:
            self.formatter.error("Cannot specify both --file and --prompt-text. Use only one.")
            return 1
        
        # Get prompt text from either source
        if args.prompt_text:
            prompt_text = args.prompt_text
        else:
            prompt_text = self.api_service.api_client.read_file_content(args.file)
        
        result = self.api_service.create_prompt(args.name, prompt_text, args.version)
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            self.formatter.success("System prompt created successfully")
            console.print(f"[bold]ID:[/bold] {result.get('_id') or result.get('id', 'N/A')}")
            console.print(f"[bold]Name:[/bold] {result.get('name', 'N/A')}")
            console.print(f"[bold]Version:[/bold] {result.get('version', 'N/A')}")
        return 0


class PromptListCommand(BaseCommand):
    """Command to list all system prompts."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "prompt list"
    
    @property
    def description(self) -> str:
        return "List all system prompts"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--name-filter', help='Filter by prompt name')
        parser.add_argument('--limit', type=int, default=100, help='Maximum number of prompts to return')
        parser.add_argument('--offset', type=int, default=0, help='Number of prompts to skip for pagination')
    
    def execute(self, args: argparse.Namespace) -> int:
        result = self.api_service.list_prompts(
            name_filter=args.name_filter,
            limit=args.limit,
            offset=args.offset
        )
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            if result:
                headers = ['ID', 'Name', 'Version', 'Created', 'Updated']
                data = []
                for prompt in result:
                    created_at = prompt.get('created_at', 'N/A')
                    updated_at = prompt.get('updated_at', 'N/A')
                    
                    if isinstance(created_at, (int, float)):
                        created_at = datetime.fromtimestamp(created_at).strftime('%Y-%m-%d')
                    elif isinstance(created_at, str):
                        created_at = created_at[:10]
                    
                    if isinstance(updated_at, (int, float)):
                        updated_at = datetime.fromtimestamp(updated_at).strftime('%Y-%m-%d')
                    elif isinstance(updated_at, str):
                        updated_at = updated_at[:10]
                    
                    data.append({
                        'ID': (prompt.get('_id') or prompt.get('id', 'N/A'))[:12] + '...',
                        'Name': prompt.get('name', 'N/A'),
                        'Version': prompt.get('version', 'N/A'),
                        'Created': created_at,
                        'Updated': updated_at
                    })
                self.formatter.format_table(data, headers)
                console.print(f"Found {len(result)} prompts")
            else:
                console.print("No prompts found")
        return 0


class PromptGetCommand(BaseCommand):
    """Command to get a system prompt."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "prompt get"
    
    @property
    def description(self) -> str:
        return "Get a system prompt"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--id', required=True, help='Prompt ID')
        parser.add_argument('--save', help='Save prompt to file')
    
    def execute(self, args: argparse.Namespace) -> int:
        result = self.api_service.get_prompt(args.id)
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            self._display_prompt_details(result)
            if args.save:
                with open(args.save, 'w') as f:
                    f.write(result.get('prompt', ''))
                self.formatter.success(f"Prompt saved to {args.save}")
        return 0
    
    def _display_prompt_details(self, prompt: dict) -> None:
        """Display prompt details."""
        console.print(f"[bold]ID:[/bold] {prompt.get('_id') or prompt.get('id', 'N/A')}")
        console.print(f"[bold]Name:[/bold] {prompt.get('name', 'N/A')}")
        console.print(f"[bold]Version:[/bold] {prompt.get('version', 'N/A')}")
        if 'created_at' in prompt:
            console.print(f"[bold]Created:[/bold] {prompt['created_at']}")
        if 'updated_at' in prompt:
            console.print(f"[bold]Updated:[/bold] {prompt['updated_at']}")
        console.print("\n[bold]Prompt Text:[/bold]")
        console.print("─" * 60)
        console.print(prompt.get('prompt', 'N/A'))
        console.print("─" * 60)


class PromptUpdateCommand(BaseCommand):
    """Command to update a system prompt."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "prompt update"
    
    @property
    def description(self) -> str:
        return "Update a system prompt"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--id', required=True, help='Prompt ID to update')
        parser.add_argument('--file', help='Path to file with updated prompt text')
        parser.add_argument('--prompt-text', help='Prompt text as a string (alternative to --file)')
        parser.add_argument('--version', help='New version string')
    
    def execute(self, args: argparse.Namespace) -> int:
        # Validate that either file or prompt-text is provided
        if not args.file and not args.prompt_text:
            self.formatter.error("Either --file or --prompt-text must be provided")
            return 1
        
        if args.file and args.prompt_text:
            self.formatter.error("Cannot specify both --file and --prompt-text. Use only one.")
            return 1
        
        # Get prompt text from either source
        if args.prompt_text:
            prompt_text = args.prompt_text
        else:
            prompt_text = self.api_service.api_client.read_file_content(args.file)
        
        result = self.api_service.update_prompt(args.id, prompt_text, args.version)
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            self.formatter.success("System prompt updated successfully")
        return 0


class PromptDeleteCommand(BaseCommand):
    """Command to delete a system prompt."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "prompt delete"
    
    @property
    def description(self) -> str:
        return "Delete a system prompt"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--id', required=True, help='Prompt ID to delete')
        parser.add_argument('--force', action='store_true', help='Skip confirmation prompt')
    
    def execute(self, args: argparse.Namespace) -> int:
        if not args.force:
            if not Confirm.ask(f"Are you sure you want to delete prompt {args.id[:12]}...?"):
                self.formatter.info("Operation cancelled")
                return 0
        
        result = self.api_service.delete_prompt(args.id)
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            self.formatter.success("System prompt deleted successfully")
        return 0


class PromptAssociateCommand(BaseCommand):
    """Command to associate a prompt with an API key."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "prompt associate"
    
    @property
    def description(self) -> str:
        return "Associate prompt with API key"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--key', required=True, help='API key')
        parser.add_argument('--prompt-id', required=True, help='Prompt ID to associate')
    
    def execute(self, args: argparse.Namespace) -> int:
        result = self.api_service.associate_prompt_with_api_key(args.key, args.prompt_id)
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            self.formatter.success("System prompt associated with API key successfully")
        return 0

