"""Output formatting utilities for ORBIT CLI."""

import json
from typing import Any, List, Dict, Optional
from rich.console import Console
from rich.table import Table


class OutputFormatter:
    """Handles output formatting for different formats and contexts."""
    
    def __init__(self, format: str = "table", color: bool = True, console: Optional[Console] = None):
        """
        Initialize the output formatter.
        
        Args:
            format: Output format ("table" or "json")
            color: Whether to use colored output
            console: Optional Rich console instance
        """
        self.format = format
        self.color = color
        self.console = console or Console()
    
    def success(self, message: str) -> None:
        """Display success message."""
        if self.color:
            self.console.print(f"[green]✓[/green] {message}")
        else:
            print(f"✓ {message}")
    
    def error(self, message: str) -> None:
        """Display error message."""
        if self.color:
            self.console.print(f"[red]✗[/red] {message}")
        else:
            print(f"✗ {message}")
    
    def warning(self, message: str) -> None:
        """Display warning message."""
        if self.color:
            self.console.print(f"[yellow]⚠[/yellow] {message}")
        else:
            print(f"⚠ {message}")
    
    def info(self, message: str) -> None:
        """Display info message."""
        if self.color:
            self.console.print(f"[blue]ℹ[/blue] {message}")
        else:
            print(f"ℹ {message}")
    
    def format_table(self, data: List[Dict[str, Any]], headers: List[str]) -> None:
        """Format data as a rich table."""
        table = Table(show_header=True, header_style="bold magenta")
        
        for header in headers:
            table.add_column(header)
        
        for row in data:
            table.add_row(*[str(row.get(h, "")) for h in headers])
        
        self.console.print(table)
    
    def format_json(self, data: Any) -> None:
        """Format data as JSON."""
        print(json.dumps(data, indent=2))
    
    def format_output(self, data: Any, headers: Optional[List[str]] = None) -> None:
        """Format output based on configured format."""
        if self.format == "json":
            self.format_json(data)
        elif self.format == "table" and isinstance(data, list) and headers:
            self.format_table(data, headers)
        else:
            # Default to JSON for complex data
            self.format_json(data)
    
    def print(self, message: str, style: Optional[str] = None) -> None:
        """Print a message with optional style."""
        if self.color and style:
            self.console.print(f"[{style}]{message}[/{style}]")
        else:
            print(message)
    
    def print_dict(self, data: Dict[str, Any], title: Optional[str] = None) -> None:
        """Print a dictionary in a formatted way."""
        if title:
            self.console.print(f"[bold]{title}[/bold]")
        
        for key, value in data.items():
            self.console.print(f"[bold]{key}:[/bold] {value}")