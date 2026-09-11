"""
Server control commands.

Handles start, stop, restart, and status commands for the ORBIT server.
"""

import time
import argparse
import logging
from datetime import datetime
from typing import ClassVar
from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from bin.orbit.commands import BaseCommand
from bin.orbit.services.server_service import ServerService
from bin.orbit.services.worker_service import WorkerService
from bin.orbit.utils.invocation import cli_command
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


class ServerPauseCommand(BaseCommand):
    """Command to pause the ORBIT server (reject new requests without stopping it)."""

    def __init__(self, server_service: ServerService, formatter: OutputFormatter):
        self.server_service = server_service
        self.formatter = formatter

    @property
    def name(self) -> str:
        return "pause"

    @property
    def description(self) -> str:
        return "Pause the ORBIT server (reject new requests without stopping it)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        pass

    def execute(self, args: argparse.Namespace) -> int:
        success = self.server_service.pause()
        return 0 if success else 1


class ServerResumeCommand(BaseCommand):
    """Command to resume a paused ORBIT server."""

    def __init__(self, server_service: ServerService, formatter: OutputFormatter):
        self.server_service = server_service
        self.formatter = formatter

    @property
    def name(self) -> str:
        return "resume"

    @property
    def description(self) -> str:
        return "Resume a paused ORBIT server"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        pass

    def execute(self, args: argparse.Namespace) -> int:
        success = self.server_service.resume()
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


class WorkerRunCommand(BaseCommand):
    """Run the ORBIT MQ worker in the foreground (for systemd/Docker/dev)."""

    def __init__(self, worker_service: WorkerService, formatter: OutputFormatter):
        self.worker_service = worker_service
        self.formatter = formatter

    @property
    def name(self) -> str:
        return "run"

    @property
    def description(self) -> str:
        return "Run the MQ worker in the foreground (Ctrl+C to stop)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--config', type=str, help='Path to configuration file')

    def execute(self, args: argparse.Namespace) -> int:
        return self.worker_service.run_foreground(config_path=args.config)


class WorkerStartCommand(BaseCommand):
    """Start the ORBIT MQ worker as a background process."""

    def __init__(self, worker_service: WorkerService, formatter: OutputFormatter):
        self.worker_service = worker_service
        self.formatter = formatter

    @property
    def name(self) -> str:
        return "start"

    @property
    def description(self) -> str:
        return "Start the MQ worker in the background"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--config', type=str, help='Path to configuration file')
        parser.add_argument('--delete-logs', action='store_true', help='Delete the worker log before starting')

    def execute(self, args: argparse.Namespace) -> int:
        success = self.worker_service.start(config_path=args.config, delete_logs=args.delete_logs)
        return 0 if success else 1


class WorkerStopCommand(BaseCommand):
    """Stop the background ORBIT MQ worker."""

    def __init__(self, worker_service: WorkerService, formatter: OutputFormatter):
        self.worker_service = worker_service
        self.formatter = formatter

    @property
    def name(self) -> str:
        return "stop"

    @property
    def description(self) -> str:
        return "Stop the background MQ worker"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--timeout', type=int, default=30, help='Timeout for graceful shutdown (seconds)')
        parser.add_argument('--force', action='store_true', help='Force stop (SIGKILL) without graceful shutdown')
        parser.add_argument('--delete-logs', action='store_true', help='Delete the worker log after stopping')

    def execute(self, args: argparse.Namespace) -> int:
        success = self.worker_service.stop(timeout=args.timeout, force=args.force, delete_logs=args.delete_logs)
        return 0 if success else 1


class WorkerRestartCommand(BaseCommand):
    """Restart the background ORBIT MQ worker."""

    def __init__(self, worker_service: WorkerService, formatter: OutputFormatter):
        self.worker_service = worker_service
        self.formatter = formatter

    @property
    def name(self) -> str:
        return "restart"

    @property
    def description(self) -> str:
        return "Restart the background MQ worker"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--config', type=str, help='Path to configuration file')
        parser.add_argument('--delete-logs', action='store_true', help='Delete the worker log during restart')

    def execute(self, args: argparse.Namespace) -> int:
        success = self.worker_service.restart(config_path=args.config, delete_logs=args.delete_logs)
        return 0 if success else 1


class WorkerStatusCommand(BaseCommand):
    """Check whether the background ORBIT MQ worker is running."""

    def __init__(self, worker_service: WorkerService, formatter: OutputFormatter):
        self.worker_service = worker_service
        self.formatter = formatter

    @property
    def name(self) -> str:
        return "status"

    @property
    def description(self) -> str:
        return "Check MQ worker status"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        pass

    def execute(self, args: argparse.Namespace) -> int:
        return 0 if self.worker_service.status() else 1


class ServerStatusCommand(BaseCommand):
    """Command to check ORBIT server status."""

    # Overall health verdict -> (glyph colour, label)
    HEALTH_STYLES: ClassVar[dict[str, tuple[str, str]]] = {
        "healthy": ("green", "HEALTHY"),
        "degraded": ("yellow", "DEGRADED"),
        "unhealthy": ("red", "UNHEALTHY"),
        "stopped": ("red", "STOPPED"),
        "unknown": ("yellow", "UNKNOWN"),
    }

    # Process state -> colour
    STATE_COLORS: ClassVar[dict[str, str]] = {"running": "green", "paused": "yellow", "stopped": "red"}

    SPARK_CHARS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"

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
        parser.add_argument('--detailed', action='store_true',
                            help='Include per-endpoint traffic and process detail')
    
    def execute(self, args: argparse.Namespace) -> int:
        detailed = getattr(args, 'detailed', False)

        if getattr(args, 'output', None) == 'json':
            status = self.server_service.status()
            self.formatter.format_json(status)
            return 0 if status['status'] in ('running', 'paused') else 1

        if args.watch:
            # The alternate screen only makes sense on a real terminal; when
            # piped, fall through to appending each snapshot instead.
            interactive = console.is_terminal
            try:
                with Live(console=console, screen=interactive,
                          auto_refresh=False, transient=not interactive) as live:
                    while True:
                        status = self.server_service.status(cpu_interval=0.5)
                        view = self._render(status, detailed)
                        if interactive:
                            live.update(view, refresh=True)
                        else:
                            console.print(view)
                        time.sleep(args.interval)
            except KeyboardInterrupt:
                self.formatter.info("Status monitoring stopped")
                return 0

        status = self.server_service.status()
        console.print(self._render(status, detailed))
        return 0 if status['status'] in ('running', 'paused') else 1

    def _render(self, status: dict, detailed: bool = False) -> Group:
        """Build the full status view as a single Rich renderable."""
        if status['status'] not in ('running', 'paused'):
            return Group(self._render_header(status), *self._render_notes(status))

        sections = [self._render_header(status), "", self._render_summary(status)]

        if detailed:
            endpoints = status.get('endpoints') or []
            if endpoints:
                sections.extend(["", self._render_endpoints(endpoints)])
            sections.extend(["", self._render_process(status)])

        sections.extend(self._render_notes(status))
        return Group(*sections)

    def _render_header(self, status: dict) -> Panel:
        """Identity panel with the overall health badge in the border title."""
        health = status.get('health', 'unknown')
        color, label = self.HEALTH_STYLES.get(health, self.HEALTH_STYLES['unknown'])

        grid = Table.grid(padding=(0, 3))
        grid.add_column(style="bold")
        grid.add_column()

        version = status.get('version')
        grid.add_row("Version", f"v{version}" if version else "[dim]unknown[/dim]")
        grid.add_row("Endpoint", status.get('server_url') or "[dim]unknown[/dim]")
        state_color = self.STATE_COLORS.get(status['status'], "yellow")
        grid.add_row("State", f"[{state_color}]{status['status']}[/{state_color}]")
        if status.get('pid'):
            grid.add_row("PID", str(status['pid']))
        if status.get('uptime'):
            grid.add_row("Uptime", status['uptime'])
        if status.get('config_path'):
            grid.add_row("Config", status['config_path'])

        return Panel(
            grid,
            title="[bold]ORBIT[/bold]",
            subtitle=f"[{color}]\u25cf {label}[/{color}]",
            border_style=color,
            padding=(0, 1),
        )

    def _render_summary(self, status: dict) -> Table:
        """Readiness, traffic, latency and resource lines."""
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold", width=11)
        table.add_column()

        readiness = status.get('readiness')
        if readiness is not None:
            ready = readiness.get('ready')
            glyph = "[green]\u25cf ready[/green]" if ready else "[red]\u25cb not ready[/red]"
            detail = ""
            if readiness.get('total_adapters') is not None:
                detail = (f"   adapters {readiness.get('healthy_adapters', 0)}"
                          f"/{readiness.get('total_adapters', 0)} healthy")
            elif readiness.get('reason'):
                detail = f"   {readiness['reason']}"
            table.add_row("Readiness", glyph + detail)

        traffic = status.get('traffic') or {}
        thresholds = status.get('thresholds') or {}
        if traffic:
            error_rate = self._threshold_text(
                traffic.get('error_rate'), thresholds.get('error_rate'), "{:.2f}%")
            table.add_row("Traffic", (
                f"{traffic.get('per_second', 0)} req/s"
                f"   errors {error_rate}"
                f"   {traffic.get('total', 0):,} total"
            ))
            p95 = self._threshold_text(
                traffic.get('p95_response_time'), thresholds.get('response_time_ms'), "{:.0f} ms")
            table.add_row("Latency", (
                f"p50 {traffic.get('p50_response_time', 0):.0f} ms"
                f"   p95 {p95}"
                f"   p99 {traffic.get('p99_response_time', 0):.0f} ms"
            ))

        resources = status.get('resources') or {}
        process = status.get('process') or {}
        parts = []
        cpu = resources.get('cpu_percent', process.get('cpu_percent'))
        if cpu is not None:
            spark = self._sparkline(status.get('cpu_series') or [])
            parts.append(f"CPU {self._threshold_text(cpu, thresholds.get('cpu'), '{:.1f}%')}"
                         + (f" {spark}" if spark else ""))
        if process.get('memory_mb') is not None:
            parts.append(f"MEM {process['memory_mb']:.0f} MB ({process.get('memory_percent', 0):.1f}%)")
        elif resources.get('memory_gb') is not None:
            parts.append(f"MEM {resources['memory_gb']} GB ({resources.get('memory_percent', 0)}%)")
        if resources.get('disk_usage_percent') is not None:
            parts.append(f"DISK {resources['disk_usage_percent']}%")
        if parts:
            table.add_row("Resources", "   ".join(parts))

        return table

    def _render_endpoints(self, endpoints: list) -> Group:
        """Busiest endpoints by request count."""
        table = Table(box=box.SIMPLE, padding=(0, 1), header_style="dim")
        table.add_column("Endpoint")
        table.add_column("Method")
        table.add_column("Requests", justify="right")
        table.add_column("Avg", justify="right")
        table.add_column("Errors", justify="right")

        for endpoint in endpoints[:10]:
            table.add_row(
                endpoint.get('endpoint', '?'),
                endpoint.get('method', 'GET'),
                f"{endpoint.get('total_requests', 0):,}",
                f"{endpoint.get('avg_latency_ms', 0)} ms",
                f"{endpoint.get('error_rate', 0)}%",
            )

        return Group("[bold]Top endpoints[/bold]", table)

    def _render_process(self, status: dict) -> Group:
        """Process-level detail, shown only with --detailed."""
        process = status.get('process') or {}
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold", width=11)
        table.add_column()
        table.add_row("Threads", str(process.get('num_threads', '-')))
        table.add_row("I/O", f"read {process.get('io_read_mb', 0)} MB"
                             f"   write {process.get('io_write_mb', 0)} MB")
        table.add_row("Logs", status.get('log_file') or "-")
        return Group("[bold]Process[/bold]", table)

    def _render_notes(self, status: dict) -> list:
        """Reasons for the verdict, missing sections, and a timestamp."""
        notes = []

        def note(markup: str) -> None:
            notes.append(Text.from_markup(markup))

        if status['status'] == 'stopped':
            note(f"[yellow]{status['message']}[/yellow]")
        elif status['status'] not in ('running', 'paused'):
            note(f"[red]{status['message']}[/red]")
            if status.get('error'):
                note(f"[bold]Error:[/bold] {status['error']}")

        reasons = status.get('health_reasons') or []
        if reasons:
            color = self.HEALTH_STYLES.get(status.get('health'), ("yellow", ""))[0]
            notes.append("")
            for reason in reasons:
                note(f"[{color}]\u2022[/{color}] {reason}")

        unavailable = status.get('unavailable') or []
        if unavailable:
            notes.append("")
            note(f"[dim]No data for: {', '.join(unavailable)} "
                 f"(monitoring disabled, or run '{cli_command('login')}' for admin detail)[/dim]")

        if status['status'] in ('running', 'paused'):
            notes.append("")
            note(f"[dim]Updated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]")

        return notes

    def _threshold_text(self, value, limit, fmt: str) -> str:
        """Format a metric, coloured red when it exceeds the server's threshold."""
        if value is None:
            return "[dim]-[/dim]"
        text = fmt.format(value)
        if limit is not None and value > limit:
            return f"[red]{text}[/red]"
        return text

    def _sparkline(self, series: list, headroom: float = 10.0) -> str:
        """
        Render a percentage series as a compact inline sparkline.

        Scales from zero rather than from the series minimum, so an idle
        server reads as flat and low instead of having its noise stretched
        to full height. `headroom` is the minimum top of the scale, which
        keeps a busy server using the full ramp.
        """
        points = [v for v in series[-20:] if isinstance(v, (int, float))]
        if len(points) < 2:
            return ""
        top = max(max(points), headroom)
        scale = len(self.SPARK_CHARS) - 1
        return "".join(
            self.SPARK_CHARS[min(int(v / top * scale), scale)] for v in points
        )
