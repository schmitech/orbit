"""
Admin operations commands.

Handles reload-adapters command.
"""

import argparse
from typing import Any
from rich.console import Console
from rich.table import Table

from bin.orbit.commands import BaseCommand
from bin.orbit.services.api_service import ApiService
from bin.orbit.utils.output import OutputFormatter

console = Console()


class AdminReloadAdaptersCommand(BaseCommand):
    """Command to reload adapter configurations."""
    
    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "admin reload-adapters"
    
    @property
    def description(self) -> str:
        return "Reload adapter configurations without server restart"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--adapter', type=str, help='Optional name of specific adapter to reload')
    
    def execute(self, args: argparse.Namespace) -> int:
        result = self.api_service.reload_adapters(adapter_name=args.adapter)
        summary = result.get('summary', {})
        
        if self.formatter.format == 'json':
            self.formatter.format_json(result)
        else:
            self.formatter.success(result.get('message', 'Adapters reloaded successfully'))
            
            if args.adapter:
                # Single adapter reload
                action = summary.get('action', 'reloaded')
                console.print(f"\n[bold]Adapter:[/bold] {summary.get('adapter_name', args.adapter)}")
                
                if action == 'disabled':
                    console.print(f"[bold]Action:[/bold] [red]{action}[/red] (adapter removed from active pool)")
                elif action == 'enabled':
                    console.print(f"[bold]Action:[/bold] [green]{action}[/green] (adapter added to active pool)")
                elif action == 'added':
                    console.print(f"[bold]Action:[/bold] [green]{action}[/green]")
                elif action == 'updated':
                    console.print(f"[bold]Action:[/bold] [yellow]{action}[/yellow]")
                else:
                    console.print(f"[bold]Action:[/bold] {action}")
            else:
                # Multiple adapters reload
                table = Table(title="Adapter Reload Summary")
                table.add_column("Metric", style="cyan")
                table.add_column("Count", style="green")
                
                table.add_row("Added", str(summary.get('added', 0)))
                table.add_row("Removed", str(summary.get('removed', 0)))
                table.add_row("Updated", str(summary.get('updated', 0)))
                table.add_row("Unchanged", str(summary.get('unchanged', 0)))
                table.add_row("Total", str(summary.get('total', 0)))
                
                console.print(table)
                
                # Show details if verbose
                if getattr(args, 'verbose', False):
                    if summary.get('added_names'):
                        console.print(f"\n[green]Added:[/green] {', '.join(summary['added_names'])}")
                    if summary.get('removed_names'):
                        console.print(f"[red]Removed:[/red] {', '.join(summary['removed_names'])}")
                    if summary.get('updated_names'):
                        console.print(f"[yellow]Updated:[/yellow] {', '.join(summary['updated_names'])}")
        
        return 0


class AdminReloadTemplatesCommand(BaseCommand):
    """Command to reload intent templates."""

    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter

    @property
    def name(self) -> str:
        return "admin reload-templates"

    @property
    def description(self) -> str:
        return "Reload intent templates without server restart"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--adapter', type=str, help='Optional name of specific adapter to reload templates for')

    def execute(self, args: argparse.Namespace) -> int:
        result = self.api_service.reload_templates(adapter_name=args.adapter)
        summary = result.get('summary', {})

        if self.formatter.format == 'json':
            self.formatter.format_json(result)
        else:
            self.formatter.success(result.get('message', 'Templates reloaded successfully'))

            if args.adapter:
                # Single adapter template reload
                console.print(f"\n[bold]Adapter:[/bold] {args.adapter}")
                console.print(f"[bold]Templates Loaded:[/bold] {summary.get('templates_loaded', 0)}")

                if 'details' in summary:
                    details = summary['details']
                    if details.get('collection_name'):
                        console.print(f"[bold]Collection:[/bold] {details['collection_name']}")
                    if details.get('template_library_path'):
                        console.print(f"[bold]Template Library:[/bold] {details['template_library_path']}")
            else:
                # Multiple adapters template reload
                table = Table(title="Template Reload Summary")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="green")

                table.add_row("Total Templates", str(summary.get('templates_loaded', 0)))
                table.add_row("Adapters Updated", str(len(summary.get('adapters_updated', []))))

                console.print(table)

                if summary.get('adapters_updated'):
                    console.print(f"\n[green]Updated:[/green] {', '.join(summary['adapters_updated'])}")
                if summary.get('errors'):
                    console.print(f"[red]Errors:[/red] {', '.join(summary['errors'])}")

        return 0

