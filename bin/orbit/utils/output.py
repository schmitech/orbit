"""
Output formatting utilities for the ORBIT CLI.
"""

import json
from typing import Any, Dict, List, Optional
from rich.console import Console
from rich.table import Table

# Initialize rich console
console = Console()


class OutputFormatter:
    """Handles output formatting for different formats and contexts."""
    
    def __init__(self, format: str = "table", color: bool = True):
        self.format = format
        self.color = color
    
    def success(self, message: str) -> None:
        """Display success message."""
        if self.color:
            console.print(f"[green]✓[/green] {message}")
        else:
            print(f"✓ {message}")
    
    def error(self, message: str) -> None:
        """Display error message."""
        if self.color:
            console.print(f"[red]✗[/red] {message}")
        else:
            print(f"✗ {message}")
    
    def warning(self, message: str) -> None:
        """Display warning message."""
        if self.color:
            console.print(f"[yellow]⚠[/yellow] {message}")
        else:
            print(f"⚠ {message}")
    
    def info(self, message: str) -> None:
        """Display info message."""
        if self.color:
            console.print(f"[blue]ℹ[/blue] {message}")
        else:
            print(f"ℹ {message}")
    
    def format_table(self, data: List[Dict[str, Any]], headers: List[str]) -> None:
        """Format data as a rich table."""
        table = Table(show_header=True, header_style="bold magenta")
        
        for header in headers:
            table.add_column(header)
        
        for row in data:
            table.add_row(*[str(row.get(h, "")) for h in headers])
        
        console.print(table)
    
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

