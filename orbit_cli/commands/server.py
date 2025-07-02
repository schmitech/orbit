"""Server control commands for ORBIT CLI."""

import argparse
import time
from typing import Dict, Any

from .base import BaseCommand, OutputCommand
from ..server import HealthChecker, ServerMonitor, StartupValidator


class StartCommand(BaseCommand):
    """Start the ORBIT server."""
    
    name = "start"
    help = "Start the ORBIT server"
    description = "Start the ORBIT server with optional configuration"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add start command arguments."""
        parser.add_argument(
            '--config',
            type=str,
            help='Path to server configuration file'
        )
        parser.add_argument(
            '--host',
            type=str,
            help='Host to bind to (e.g., 0.0.0.0)'
        )
        parser.add_argument(
            '--port',
            type=int,
            help='Port to bind to (e.g., 3000)'
        )
        parser.add_argument(
            '--reload',
            action='store_true',
            help='Enable auto-reload for development'
        )
        parser.add_argument(
            '--delete-logs',
            action='store_true',
            help='Delete logs folder before starting'
        )
        parser.add_argument(
            '--validate',
            action='store_true',
            help='Validate startup conditions before starting'
        )
        parser.add_argument(
            '--wait-healthy',
            action='store_true',
            help='Wait for server to become healthy after starting'
        )
        parser.add_argument(
            '--timeout',
            type=int,
            default=30,
            help='Timeout for health check (default: 30s)'
        )
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the start command."""
        if not self.server_controller:
            self.formatter.error("Server controller not initialized")
            return 1
        
        # Validate startup conditions if requested
        if args.validate:
            port = args.port or 3000
            validator = StartupValidator()
            validation = validator.validate_startup_conditions(port, args.config)
            
            if not validation['valid']:
                self.formatter.error("Startup validation failed:")
                if not validation.get('port_available', True):
                    self.formatter.error(f"  - Port {port} is already in use")
                
                deps = validation.get('dependencies', {})
                missing_deps = [pkg for pkg, available in deps.items() if not available]
                if missing_deps:
                    self.formatter.error(f"  - Missing dependencies: {', '.join(missing_deps)}")
                
                if 'config' in validation and not validation['config'].get('valid', True):
                    self.formatter.error(f"  - Config error: {validation['config'].get('error')}")
                
                return 1
        
        # Start the server
        success = self.server_controller.start(
            config_path=args.config,
            host=args.host,
            port=args.port,
            reload=args.reload,
            delete_logs=args.delete_logs
        )
        
        if not success:
            return 1
        
        # Wait for server to become healthy if requested
        if args.wait_healthy:
            self.formatter.info("Waiting for server to become healthy...")
            
            # Determine server URL
            host = args.host or 'localhost'
            port = args.port or 3000
            server_url = f"http://{host}:{port}"
            
            checker = HealthChecker(server_url)
            healthy = checker.wait_for_healthy(
                max_wait=args.timeout,
                progress_callback=lambda elapsed: self.formatter.info(
                    f"  Waiting... ({elapsed:.1f}s)", end='\r'
                )
            )
            
            if healthy:
                self.formatter.success("\nServer is healthy and ready!")
            else:
                self.formatter.warning(f"\nServer did not become healthy within {args.timeout}s")
        
        return 0


class StopCommand(BaseCommand):
    """Stop the ORBIT server."""
    
    name = "stop"
    help = "Stop the ORBIT server"
    description = "Stop the running ORBIT server gracefully"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add stop command arguments."""
        parser.add_argument(
            '--timeout',
            type=int,
            default=30,
            help='Timeout for graceful shutdown (seconds)'
        )
        parser.add_argument(
            '--delete-logs',
            action='store_true',
            help='Delete logs folder after stopping'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force stop without graceful shutdown'
        )
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the stop command."""
        if not self.server_controller:
            self.formatter.error("Server controller not initialized")
            return 1
        
        success = self.server_controller.stop(
            timeout=args.timeout if not args.force else 1,
            delete_logs=args.delete_logs,
            force=args.force
        )
        
        return 0 if success else 1


class RestartCommand(BaseCommand):
    """Restart the ORBIT server."""
    
    name = "restart"
    help = "Restart the ORBIT server"
    description = "Restart the ORBIT server with optional new configuration"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add restart command arguments."""
        parser.add_argument(
            '--config',
            type=str,
            help='Path to server configuration file'
        )
        parser.add_argument(
            '--host',
            type=str,
            help='Host to bind to'
        )
        parser.add_argument(
            '--port',
            type=int,
            help='Port to bind to'
        )
        parser.add_argument(
            '--delete-logs',
            action='store_true',
            help='Delete logs folder during restart'
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=2.0,
            help='Delay between stop and start (default: 2.0s)'
        )
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the restart command."""
        if not self.server_controller:
            self.formatter.error("Server controller not initialized")
            return 1
        
        success = self.server_controller.restart(
            config_path=args.config,
            host=args.host,
            port=args.port,
            delete_logs=args.delete_logs,
            restart_delay=args.delay
        )
        
        return 0 if success else 1


class StatusCommand(OutputCommand):
    """Check ORBIT server status."""
    
    name = "status"
    help = "Check ORBIT server status"
    description = "Display current status of the ORBIT server"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add status command arguments."""
        parser.add_argument(
            '--watch',
            action='store_true',
            help='Continuously monitor status'
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=5,
            help='Watch interval in seconds (default: 5)'
        )
        parser.add_argument(
            '--detailed',
            action='store_true',
            help='Show detailed metrics'
        )
        parser.add_argument(
            '--health',
            action='store_true',
            help='Include health check'
        )
        self.add_output_arguments(parser)
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the status command."""
        if not self.server_controller:
            self.formatter.error("Server controller not initialized")
            return 1
        
        if args.watch:
            # Continuous monitoring
            try:
                monitor = ServerMonitor(
                    self.server_controller,
                    interval=args.interval
                )
                monitor.start()
            except KeyboardInterrupt:
                self.formatter.info("\nStatus monitoring stopped")
            return 0
        
        # One-time status check
        status = self.server_controller.status(detailed=args.detailed)
        
        # Add health check if requested
        if args.health and status['status'] == 'running':
            server_url = self.get_server_url(args)
            checker = HealthChecker(server_url)
            health = checker.check_health()
            status['health'] = health
        
        # Display status
        if self.formatter.format == 'json':
            self.formatter.format_json(status)
        else:
            self._display_status(status)
        
        return 0 if status['status'] == 'running' else 1
    
    def _display_status(self, status: Dict[str, Any]) -> None:
        """Display status in formatted output."""
        if status['status'] == 'running':
            self.formatter.success(status['message'])
            
            # Basic info
            self.formatter.print(f"[bold]PID:[/bold] {status.get('pid', 'N/A')}")
            self.formatter.print(f"[bold]Uptime:[/bold] {status.get('uptime', 'N/A')}")
            
            # Metrics
            if 'memory_mb' in status:
                memory_str = f"{status['memory_mb']} MB"
                if 'memory_percent' in status:
                    memory_str += f" ({status['memory_percent']}%)"
                self.formatter.print(f"[bold]Memory:[/bold] {memory_str}")
            
            if 'cpu_percent' in status:
                self.formatter.print(f"[bold]CPU:[/bold] {status['cpu_percent']}%")
            
            # Additional metrics for detailed view
            if 'num_threads' in status:
                self.formatter.print(f"[bold]Threads:[/bold] {status['num_threads']}")
            
            if 'io_read_mb' in status and 'io_write_mb' in status:
                self.formatter.print(
                    f"[bold]I/O:[/bold] R: {status['io_read_mb']} MB, "
                    f"W: {status['io_write_mb']} MB"
                )
            
            # Health status
            if 'health' in status:
                health = status['health']
                if health['status'] == 'healthy':
                    self.formatter.success(
                        f"[bold]Health:[/bold] Healthy "
                        f"(response time: {health.get('response_time_ms', 'N/A')}ms)"
                    )
                else:
                    self.formatter.error(
                        f"[bold]Health:[/bold] Unhealthy - {health.get('error', 'Unknown error')}"
                    )
        
        elif status['status'] == 'stopped':
            self.formatter.warning(status['message'])
        else:
            self.formatter.error(status['message'])
            if 'error' in status:
                self.formatter.print(f"[bold]Error:[/bold] {status['error']}")


class LogsCommand(BaseCommand):
    """View server logs."""
    
    name = "logs"
    help = "View server logs"
    description = "Display server log output"
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add logs command arguments."""
        parser.add_argument(
            '-n', '--lines',
            type=int,
            help='Number of lines to show (default: all)'
        )
        parser.add_argument(
            '-f', '--follow',
            action='store_true',
            help='Follow log output (like tail -f)'
        )
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute the logs command."""
        if not self.server_controller:
            self.formatter.error("Server controller not initialized")
            return 1
        
        self.server_controller.get_logs(
            lines=args.lines,
            follow=args.follow
        )
        
        return 0