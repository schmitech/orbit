"""Configuration management commands for ORBIT CLI."""

import argparse
import json
from pathlib import Path
from typing import Dict, Any, Type, Optional

from .base import CommandGroup, BaseCommand, OutputCommand
from ..config import normalize_config_key


class ConfigShowCommand(OutputCommand):
    """Show configuration."""
    
    name = "show"
    help = "Show configuration"
    description = "Display current configuration"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add show command arguments."""
        parser.add_argument(
            '--key',
            help='Show specific configuration key'
        )
        self.add_output_arguments(parser)
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the show command."""
        if not self.config_manager:
            self.formatter.error("Configuration manager not initialized")
            return 1
        
        if args.key:
            # Show specific key
            key = normalize_config_key(args.key)
            value = self.config_manager.get(key)
            
            if value is not None:
                if self.formatter.format == 'json':
                    self.formatter.format_json({key: value})
                else:
                    self.formatter.print(f"{key}: {value}")
            else:
                self.formatter.error(f"Configuration key '{args.key}' not found")
                return 1
        else:
            # Show all configuration
            config = self.config_manager.load_config()
            
            if self.formatter.format == 'json':
                self.formatter.format_json(config)
            else:
                self._display_config(config)
        
        return 0
    
    def _display_config(self, config: Dict[str, Any], prefix: str = "") -> None:
        """Display configuration in a tree format."""
        for key, value in config.items():
            if isinstance(value, dict):
                self.formatter.print(f"{prefix}[bold]{key}:[/bold]")
                self._display_config(value, prefix + "  ")
            else:
                self.formatter.print(f"{prefix}{key}: {value}")


class ConfigEffectiveCommand(OutputCommand):
    """Show effective configuration."""
    
    name = "effective"
    help = "Show effective configuration"
    description = "Display effective configuration showing which values come from CLI vs server config"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add effective command arguments."""
        parser.add_argument(
            '--key',
            help='Show specific configuration key'
        )
        parser.add_argument(
            '--sources-only',
            action='store_true',
            help='Show only the source of each setting'
        )
        self.add_output_arguments(parser)
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the effective command."""
        if not self.config_manager:
            self.formatter.error("Configuration manager not initialized")
            return 1
        
        # Get effective configuration
        effective_config = self.config_manager.get_effective_config()
        
        if args.key:
            # Show specific key
            key = normalize_config_key(args.key)
            
            if key in effective_config["effective_values"]:
                value = effective_config["effective_values"][key]
                source = effective_config["sources"][key]
                
                if self.formatter.format == 'json':
                    self.formatter.format_json({
                        "key": key,
                        "value": value,
                        "source": source
                    })
                else:
                    self.formatter.print(f"[bold]{key}:[/bold] {value}")
                    self.formatter.print(f"[dim]Source: {source}[/dim]")
            else:
                self.formatter.error(f"Configuration key '{args.key}' not found")
                return 1
        else:
            # Show all configuration
            if self.formatter.format == 'json':
                self.formatter.format_json(effective_config)
            else:
                self._display_effective_config(effective_config, args.sources_only)
        
        return 0
    
    def _display_effective_config(self, config: Dict[str, Any], sources_only: bool) -> None:
        """Display effective configuration with source information."""
        from rich.table import Table
        
        # Create a table
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Setting", style="bold")
        if not sources_only:
            table.add_column("Value")
        table.add_column("Source", style="dim")
        
        # Group settings by category
        categories = {
            "Server": ["server.default_url", "server.timeout", "server.retry_attempts"],
            "Authentication": ["auth.credential_storage", "auth.use_keyring", 
                             "auth.fallback_token_file", "auth.session_duration_hours"],
            "Output": ["output.format", "output.color", "output.verbose"],
            "History": ["history.enabled", "history.max_entries"]
        }
        
        for category, keys in categories.items():
            # Add category header
            table.add_row(f"[bold blue]{category}[/bold blue]", "", "")
            
            for key in keys:
                if key in config["effective_values"]:
                    value = config["effective_values"][key]
                    source = config["sources"][key]
                    
                    # Color code the source
                    if source == "server_config":
                        source_display = "[green]server_config[/green]"
                    elif source == "cli_config":
                        source_display = "[yellow]cli_config[/yellow]"
                    else:
                        source_display = "[dim]default[/dim]"
                    
                    if sources_only:
                        table.add_row(key, source_display)
                    else:
                        # Truncate long values
                        value_str = str(value)
                        if len(value_str) > 50:
                            value_str = value_str[:47] + "..."
                        table.add_row(key, value_str, source_display)
        
        self.formatter.console.print(table)
        
        # Add legend
        self.formatter.print("\n[bold]Legend:[/bold]")
        self.formatter.print("[green]server_config[/green] - Value from server's config.yaml")
        self.formatter.print("[yellow]cli_config[/yellow] - Value from CLI's ~/.orbit/config.json")
        self.formatter.print("[dim]default[/dim] - Default value (no config found)")
        
        # Add note
        self.formatter.print(
            "\n[bold]Note:[/bold] Server-related settings (server.*, auth.*) "
            "prioritize server config by default."
        )


class ConfigSetCommand(BaseCommand):
    """Set configuration value."""
    
    name = "set"
    help = "Set configuration value"
    description = "Set a configuration value"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add set command arguments."""
        parser.add_argument(
            'key',
            help='Configuration key (dot notation)'
        )
        parser.add_argument(
            'value',
            help='Configuration value'
        )
        parser.add_argument(
            '--type',
            choices=['string', 'int', 'float', 'bool', 'json'],
            help='Value type (auto-detected if not specified)'
        )
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the set command."""
        if not self.config_manager:
            self.formatter.error("Configuration manager not initialized")
            return 1
        
        # Normalize key
        key = normalize_config_key(args.key)
        
        # Parse value based on type
        value = self._parse_value(args.value, args.type)
        
        try:
            self.config_manager.set(key, value)
            self.formatter.success(f"Configuration updated: {key} = {value}")
            return 0
            
        except Exception as e:
            return self.handle_error(e, "Failed to set configuration")
    
    def _parse_value(self, value_str: str, value_type: Optional[str]) -> Any:
        """Parse value based on type."""
        if value_type == 'int':
            return int(value_str)
        elif value_type == 'float':
            return float(value_str)
        elif value_type == 'bool':
            return value_str.lower() in ('true', 'yes', '1', 'on')
        elif value_type == 'json':
            return json.loads(value_str)
        elif value_type == 'string':
            return value_str
        else:
            # Auto-detect type
            try:
                return json.loads(value_str)
            except json.JSONDecodeError:
                # Not JSON, treat as string
                return value_str


class ConfigResetCommand(BaseCommand):
    """Reset configuration."""
    
    name = "reset"
    help = "Reset configuration"
    description = "Reset configuration to defaults"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add reset command arguments."""
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompt'
        )
        parser.add_argument(
            '--keys',
            nargs='+',
            help='Specific keys to reset (default: all)'
        )
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the reset command."""
        if not self.config_manager:
            self.formatter.error("Configuration manager not initialized")
            return 1
        
        # Determine what to reset
        if args.keys:
            message = f"Are you sure you want to reset {len(args.keys)} configuration keys?"
        else:
            message = "Are you sure you want to reset configuration to defaults?"
        
        if not self.require_confirmation(message, skip_flag='force'):
            self.formatter.info("Operation cancelled")
            return 0
        
        try:
            if args.keys:
                # Reset specific keys
                normalized_keys = [normalize_config_key(k) for k in args.keys]
                self.config_manager.reset_to_defaults(normalized_keys)
                self.formatter.success(f"Reset {len(normalized_keys)} configuration keys to defaults")
            else:
                # Reset all
                self.config_manager.reset_to_defaults()
                self.formatter.success("Configuration reset to defaults")
            
            return 0
            
        except Exception as e:
            return self.handle_error(e, "Failed to reset configuration")


class ConfigExportCommand(BaseCommand):
    """Export configuration."""
    
    name = "export"
    help = "Export configuration"
    description = "Export configuration to a file"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add export command arguments."""
        parser.add_argument(
            'file',
            help='File to export to'
        )
        parser.add_argument(
            '--include-defaults',
            action='store_true',
            help='Include default values in export'
        )
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the export command."""
        if not self.config_manager:
            self.formatter.error("Configuration manager not initialized")
            return 1
        
        try:
            path = Path(args.file)
            self.config_manager.export_config(path, args.include_defaults)
            self.formatter.success(f"Configuration exported to {path}")
            return 0
            
        except Exception as e:
            return self.handle_error(e, "Failed to export configuration")


class ConfigImportCommand(BaseCommand):
    """Import configuration."""
    
    name = "import"
    help = "Import configuration"
    description = "Import configuration from a file"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add import command arguments."""
        parser.add_argument(
            'file',
            help='File to import from'
        )
        parser.add_argument(
            '--merge',
            action='store_true',
            default=True,
            help='Merge with existing config (default)'
        )
        parser.add_argument(
            '--replace',
            action='store_true',
            help='Replace existing config entirely'
        )
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the import command."""
        if not self.config_manager:
            self.formatter.error("Configuration manager not initialized")
            return 1
        
        try:
            path = Path(args.file)
            if not path.exists():
                self.formatter.error(f"File not found: {path}")
                return 1
            
            merge = not args.replace
            self.config_manager.import_config(path, merge=merge)
            
            if merge:
                self.formatter.success(f"Configuration merged from {path}")
            else:
                self.formatter.success(f"Configuration replaced from {path}")
            
            return 0
            
        except Exception as e:
            return self.handle_error(e, "Failed to import configuration")


class ConfigCommandGroup(CommandGroup):
    """Configuration management command group."""
    
    name = "config"
    help = "Manage CLI configuration"
    description = "View and modify CLI configuration"
    
    def get_subcommands(self) -> Dict[str, Type[BaseCommand]]:
        """Get configuration subcommands."""
        return {
            'show': ConfigShowCommand,
            'effective': ConfigEffectiveCommand,
            'set': ConfigSetCommand,
            'reset': ConfigResetCommand,
            'export': ConfigExportCommand,
            'import': ConfigImportCommand
        }