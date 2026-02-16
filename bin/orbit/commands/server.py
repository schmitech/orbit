"""
Server control commands.

Handles start, stop, restart, and status commands for the ORBIT server.
"""

import time
import argparse
import logging
from datetime import datetime
from rich.console import Console
from rich.table import Table

from bin.orbit.commands import BaseCommand
from bin.orbit.services.server_service import ServerService
from bin.orbit.utils.output import OutputFormatter

logger = logging.getLogger(__name__)
console = Console()


class ServerStartCommand(BaseCommand):
    """Command to start the ORBIT server."""
    
    def __init__(self, server_service: ServerService, formatter: OutputFormatter):
        self.server_service = server_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "start"
    
    @property
    def description(self) -> str:
        return "Start the ORBIT server"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--config', type=str, help='Path to server configuration file')
        parser.add_argument('--host', type=str, help='Host to bind to (e.g., 0.0.0.0)')
        parser.add_argument('--port', type=int, help='Port to bind to (e.g., 3000)')
        parser.add_argument('--reload', action='store_true', help='Enable auto-reload for development')
        parser.add_argument('--delete-logs', action='store_true', help='Delete logs folder before starting')
    
    def execute(self, args: argparse.Namespace) -> int:
        success = self.server_service.start(
            config_path=args.config,
            host=args.host,
            port=args.port,
            reload=args.reload,
            delete_logs=args.delete_logs
        )
        return 0 if success else 1


class ServerStopCommand(BaseCommand):
    """Command to stop the ORBIT server."""
    
    def __init__(self, server_service: ServerService, formatter: OutputFormatter):
        self.server_service = server_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "stop"
    
    @property
    def description(self) -> str:
        return "Stop the ORBIT server"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--timeout', type=int, default=30, help='Timeout for graceful shutdown (seconds)')
        parser.add_argument('--delete-logs', action='store_true', help='Delete logs folder after stopping')
        parser.add_argument('--force', action='store_true', help='Force stop without graceful shutdown')
    
    def execute(self, args: argparse.Namespace) -> int:
        timeout = 1 if args.force else args.timeout
        success = self.server_service.stop(timeout=timeout, force=args.force, delete_logs=args.delete_logs)
        return 0 if success else 1


class ServerRestartCommand(BaseCommand):
    """Command to restart the ORBIT server."""
    
    def __init__(self, server_service: ServerService, formatter: OutputFormatter):
        self.server_service = server_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "restart"
    
    @property
    def description(self) -> str:
        return "Restart the ORBIT server"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--config', type=str, help='Path to server configuration file')
        parser.add_argument('--host', type=str, help='Host to bind to')
        parser.add_argument('--port', type=int, help='Port to bind to')
        parser.add_argument('--delete-logs', action='store_true', help='Delete logs folder during restart')
    
    def execute(self, args: argparse.Namespace) -> int:
        success = self.server_service.restart(
            config_path=args.config,
            host=args.host,
            port=args.port,
            delete_logs=args.delete_logs
        )
        return 0 if success else 1


class ServerStatusCommand(BaseCommand):
    """Command to check ORBIT server status."""
    
    def __init__(self, server_service: ServerService, formatter: OutputFormatter):
        self.server_service = server_service
        self.formatter = formatter
    
    @property
    def name(self) -> str:
        return "status"
    
    @property
    def description(self) -> str:
        return "Check ORBIT server status"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--watch', action='store_true', help='Continuously monitor status')
        parser.add_argument('--interval', type=int, default=5, help='Watch interval in seconds')
    
    def execute(self, args: argparse.Namespace) -> int:
        if args.watch:
            try:
                # Initialize CPU monitoring for watch mode
                self.server_service._cpu_initialized = False
                
                while True:
                    console.clear()
                    # Use enhanced status for watch mode with better CPU measurement
                    status = self.server_service.get_enhanced_status(interval=0.5)
                    self._display_enhanced_status(status)
                    time.sleep(args.interval)
            except KeyboardInterrupt:
                self.formatter.info("Status monitoring stopped")
                return 0
        else:
            status = self.server_service.status()
            self._display_status(status)
            return 0 if status['status'] == 'running' else 1
    
    def _display_status(self, status: dict) -> None:
        """Display server status in a formatted way."""
        if status['status'] == 'running':
            self.formatter.success(status['message'])
            if 'pid' in status:
                console.print(f"[bold]PID:[/bold] {status['pid']}")
            if 'uptime' in status:
                console.print(f"[bold]Uptime:[/bold] {status['uptime']}")
            if 'memory_mb' in status:
                console.print(f"[bold]Memory:[/bold] {status['memory_mb']} MB")
            if 'cpu_percent' in status:
                console.print(f"[bold]CPU:[/bold] {status['cpu_percent']}%")
        elif status['status'] == 'stopped':
            self.formatter.warning(status['message'])
        else:
            self.formatter.error(status['message'])
            if 'error' in status:
                console.print(f"[bold]Error:[/bold] {status['error']}")
    
    def _display_enhanced_status(self, status: dict) -> None:
        """Display enhanced server status with additional metrics."""
        if status['status'] == 'running':
            self.formatter.success(status['message'])
            
            # Create a table for better organization
            table = Table(show_header=False, box=None, padding=(0, 2))
            table.add_column("Metric", style="bold")
            table.add_column("Value")
            
            # Basic info
            if 'pid' in status:
                table.add_row("PID", str(status['pid']))
            if 'uptime' in status:
                table.add_row("Uptime", status['uptime'])
            
            # Performance metrics
            if 'memory_mb' in status:
                memory_str = f"{status['memory_mb']} MB"
                if 'memory_percent' in status:
                    memory_str += f" ({status['memory_percent']}%)"
                table.add_row("Memory", memory_str)
            if 'cpu_percent' in status:
                table.add_row("CPU", f"{status['cpu_percent']}%")
            
            # Additional metrics if available
            if 'num_threads' in status:
                table.add_row("Threads", str(status['num_threads']))
            
            if 'io_read_mb' in status and 'io_write_mb' in status:
                table.add_row("I/O", f"R: {status['io_read_mb']} MB, W: {status['io_write_mb']} MB")
            
            console.print(table)
            
            # Add timestamp
            console.print(f"\n[dim]Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
            
        elif status['status'] == 'stopped':
            self.formatter.warning(status['message'])
        else:
            self.formatter.error(status['message'])
            if 'error' in status:
                console.print(f"[bold]Error:[/bold] {status['error']}")

