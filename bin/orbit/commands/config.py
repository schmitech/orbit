"""
CLI configuration management commands.

Handles show, effective, set, and reset commands for CLI-local configuration only.
"""

import argparse
import json
from typing import Any
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from bin.orbit.commands import BaseCommand
from bin.orbit.services.config_service import ConfigService
from bin.orbit.utils.output import OutputFormatter

console = Console()


class ConfigShowCommand(BaseCommand):
    """Command to show CLI configuration."""
    
    def __init__(self, config_service: ConfigService, formatter: OutputFormatter):
        self.config_service = config_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "config show"
    
    @property
    def description(self) -> str:
        return "Show CLI configuration"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--key', help='Show specific configuration key')
    
    def execute(self, args: argparse.Namespace) -> int:
        if args.key:
            value = self.config_service.get(args.key)
            if value is not None:
                if self.formatter.format == 'json':
                    self.formatter.format_json({args.key: value})
                else:
                    console.print(f"{args.key}: {value}")
            else:
                self.formatter.error(f"Configuration key '{args.key}' not found")
                return 1
        else:
            config = self.config_service.load_config()
            if self.formatter.format == 'json':
                self.formatter.format_json(config)
            else:
                self._display_config(config)
        return 0
    
    def _display_config(self, config: dict, prefix: str = "") -> None:
        """Display configuration in a tree format."""
        for key, value in config.items():
            if isinstance(value, dict):
                console.print(f"{prefix}[bold]{key}:[/bold]")
                self._display_config(value, prefix + "  ")
            else:
                console.print(f"{prefix}{key}: {value}")


class ConfigEffectiveCommand(BaseCommand):
    """Command to show effective configuration."""
    
    def __init__(self, config_service: ConfigService, formatter: OutputFormatter):
        self.config_service = config_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "config effective"
    
    @property
    def description(self) -> str:
        return "Show effective CLI configuration"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--key', help='Show specific configuration key')
        parser.add_argument('--sources-only', action='store_true', help='Show only the source of each setting')
    
    def execute(self, args: argparse.Namespace) -> int:
        # For CLI config, all values come from CLI config file
        config = self.config_service.load_config()
        
        if args.key:
            value = self.config_service.get(args.key)
            if value is not None:
                if self.formatter.format == 'json':
                    self.formatter.format_json({
                        "key": args.key,
                        "value": value,
                        "source": "cli_config"
                    })
                else:
                    console.print(f"[bold]{args.key}:[/bold] {value}")
                    console.print(f"[dim]Source: cli_config[/dim]")
            else:
                self.formatter.error(f"Configuration key '{args.key}' not found")
                return 1
        else:
            if self.formatter.format == 'json':
                self.formatter.format_json({
                    "cli_config": config,
                    "note": "CLI configuration only - server config managed via API"
                })
            else:
                self._display_effective_config(config, args.sources_only)
        return 0
    
    def _display_effective_config(self, config: dict, sources_only: bool = False) -> None:
        """Display effective configuration."""
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Setting", style="bold")
        if not sources_only:
            table.add_column("Value")
        table.add_column("Source", style="dim")
        
        # Group settings by category
        categories = {
            "Server": ["server.default_url", "server.timeout", "server.retry_attempts"],
            "Authentication": ["auth.credential_storage", "auth.use_keyring", "auth.fallback_token_file", "auth.session_duration_hours"],
            "Output": ["output.format", "output.color", "output.verbose"],
            "History": ["history.enabled", "history.max_entries"]
        }
        
        for category, keys in categories.items():
            table.add_row(f"[bold blue]{category}[/bold blue]", "", "")
            
            for key in keys:
                value = self.config_service.get(key)
                if value is not None:
                    source_display = "[yellow]cli_config[/yellow]"
                    
                    if sources_only:
                        table.add_row(key, source_display)
                    else:
                        value_str = str(value)
                        if len(value_str) > 50:
                            value_str = value_str[:47] + "..."
                        table.add_row(key, value_str, source_display)
        
        console.print(table)
        console.print("\n[bold]Note:[/bold] CLI configuration only. Server configuration must be managed via API endpoints.")


class ConfigSetCommand(BaseCommand):
    """Command to set a configuration value."""
    
    def __init__(self, config_service: ConfigService, formatter: OutputFormatter):
        self.config_service = config_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "config set"
    
    @property
    def description(self) -> str:
        return "Set CLI configuration value"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('key', help='Configuration key (dot notation)')
        parser.add_argument('value', help='Configuration value')
    
    def execute(self, args: argparse.Namespace) -> int:
        # Try to parse value as JSON first
        try:
            value = json.loads(args.value)
        except json.JSONDecodeError:
            # If not JSON, treat as string
            value = args.value
        
        self.config_service.set(args.key, value)
        self.formatter.success(f"Configuration updated: {args.key} = {value}")
        return 0


class ConfigResetCommand(BaseCommand):
    """Command to reset configuration to defaults."""
    
    def __init__(self, config_service: ConfigService, formatter: OutputFormatter):
        self.config_service = config_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "config reset"
    
    @property
    def description(self) -> str:
        return "Reset CLI configuration to defaults"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--force', action='store_true', help='Skip confirmation prompt')
    
    def execute(self, args: argparse.Namespace) -> int:
        if not args.force:
            if not Confirm.ask("Are you sure you want to reset configuration to defaults?"):
                self.formatter.info("Operation cancelled")
                return 0
        
        default_config = self.config_service.get_default_config()
        self.config_service.save_config(default_config)
        self.formatter.success("Configuration reset to defaults")
        return 0

