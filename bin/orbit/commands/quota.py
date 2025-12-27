"""
Quota management commands.

Handles quota get, set, reset, and report commands for API key throttling.
"""

import argparse
from datetime import datetime
from typing import Any
from rich.console import Console
from rich.table import Table

from bin.orbit.commands import BaseCommand
from bin.orbit.services.api_service import ApiService
from bin.orbit.utils.output import OutputFormatter

console = Console()


class QuotaGetCommand(BaseCommand):
    """Command to get quota and usage for an API key."""

    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter

    @property
    def name(self) -> str:
        return "quota get"

    @property
    def description(self) -> str:
        return "Get quota and usage for an API key"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--key', required=True, help='API key to get quota for')
        parser.add_argument('--output', choices=['table', 'json'], default='table', help='Output format')

    def execute(self, args: argparse.Namespace) -> int:
        try:
            result = self.api_service.get_quota(args.key)

            if getattr(args, 'output', None) == 'json':
                self.formatter.format_json(result)
            else:
                self.formatter.success("Quota information retrieved")

                # Display quota configuration
                quota = result.get('quota', {})
                usage = result.get('usage', {})

                console.print("\n[bold]Quota Configuration:[/bold]")
                daily_limit = quota.get('daily_limit')
                monthly_limit = quota.get('monthly_limit')
                console.print(f"  Daily Limit: {daily_limit if daily_limit else 'Unlimited'}")
                console.print(f"  Monthly Limit: {monthly_limit if monthly_limit else 'Unlimited'}")
                console.print(f"  Throttle Enabled: {quota.get('throttle_enabled', True)}")
                console.print(f"  Throttle Priority: {quota.get('throttle_priority', 5)}")

                console.print("\n[bold]Current Usage:[/bold]")
                console.print(f"  Daily Used: {usage.get('daily_used', 0)}")
                console.print(f"  Monthly Used: {usage.get('monthly_used', 0)}")

                daily_remaining = result.get('daily_remaining')
                monthly_remaining = result.get('monthly_remaining')
                console.print(f"  Daily Remaining: {daily_remaining if daily_remaining is not None else 'Unlimited'}")
                console.print(f"  Monthly Remaining: {monthly_remaining if monthly_remaining is not None else 'Unlimited'}")

                # Display reset times
                daily_reset = usage.get('daily_reset_at', 0)
                monthly_reset = usage.get('monthly_reset_at', 0)
                if daily_reset:
                    console.print(f"  Daily Reset: {datetime.fromtimestamp(daily_reset).strftime('%Y-%m-%d %H:%M:%S UTC')}")
                if monthly_reset:
                    console.print(f"  Monthly Reset: {datetime.fromtimestamp(monthly_reset).strftime('%Y-%m-%d %H:%M:%S UTC')}")

                # Current throttle delay
                throttle_delay = result.get('throttle_delay_ms', 0)
                if throttle_delay > 0:
                    console.print(f"\n[yellow]Current Throttle Delay: {throttle_delay}ms[/yellow]")

            return 0
        except Exception as e:
            self.formatter.error(f"Failed to get quota: {str(e)}")
            return 1


class QuotaSetCommand(BaseCommand):
    """Command to set quota limits for an API key."""

    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter

    @property
    def name(self) -> str:
        return "quota set"

    @property
    def description(self) -> str:
        return "Set quota limits for an API key"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--key', required=True, help='API key to set quota for')
        parser.add_argument('--daily-limit', type=int, help='Daily request limit (use 0 for unlimited)')
        parser.add_argument('--monthly-limit', type=int, help='Monthly request limit (use 0 for unlimited)')
        parser.add_argument('--throttle-enabled', type=lambda x: x.lower() == 'true', help='Enable/disable throttling (true/false)')
        parser.add_argument('--priority', type=int, choices=range(1, 11), metavar='1-10', help='Throttle priority (1=premium, 10=low)')

    def execute(self, args: argparse.Namespace) -> int:
        try:
            # Build quota update payload
            quota_data = {}
            if args.daily_limit is not None:
                quota_data['daily_limit'] = args.daily_limit if args.daily_limit > 0 else None
            if args.monthly_limit is not None:
                quota_data['monthly_limit'] = args.monthly_limit if args.monthly_limit > 0 else None
            if args.throttle_enabled is not None:
                quota_data['throttle_enabled'] = args.throttle_enabled
            if args.priority is not None:
                quota_data['throttle_priority'] = args.priority

            if not quota_data:
                self.formatter.error("No quota settings specified. Use --daily-limit, --monthly-limit, --throttle-enabled, or --priority")
                return 1

            result = self.api_service.update_quota(args.key, quota_data)

            self.formatter.success("Quota updated successfully")

            # Show what was updated
            if args.daily_limit is not None:
                limit_str = str(args.daily_limit) if args.daily_limit > 0 else "Unlimited"
                console.print(f"  Daily Limit: {limit_str}")
            if args.monthly_limit is not None:
                limit_str = str(args.monthly_limit) if args.monthly_limit > 0 else "Unlimited"
                console.print(f"  Monthly Limit: {limit_str}")
            if args.throttle_enabled is not None:
                console.print(f"  Throttle Enabled: {args.throttle_enabled}")
            if args.priority is not None:
                console.print(f"  Priority: {args.priority}")

            return 0
        except Exception as e:
            self.formatter.error(f"Failed to update quota: {str(e)}")
            return 1


class QuotaResetCommand(BaseCommand):
    """Command to reset quota usage for an API key."""

    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter

    @property
    def name(self) -> str:
        return "quota reset"

    @property
    def description(self) -> str:
        return "Reset quota usage for an API key"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--key', required=True, help='API key to reset quota for')
        parser.add_argument('--period', choices=['daily', 'monthly', 'all'], default='daily', help='Period to reset (default: daily)')

    def execute(self, args: argparse.Namespace) -> int:
        try:
            result = self.api_service.reset_quota(args.key, args.period)

            self.formatter.success(f"Quota usage ({args.period}) reset successfully")

            return 0
        except Exception as e:
            self.formatter.error(f"Failed to reset quota: {str(e)}")
            return 1


class QuotaReportCommand(BaseCommand):
    """Command to generate a quota usage report."""

    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter

    @property
    def name(self) -> str:
        return "quota report"

    @property
    def description(self) -> str:
        return "Generate quota usage report for all API keys"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--period', choices=['daily', 'monthly'], default='daily', help='Report period (default: daily)')
        parser.add_argument('--limit', type=int, default=50, help='Maximum number of keys to include (default: 50)')
        parser.add_argument('--output', choices=['table', 'json'], default='table', help='Output format')

    def execute(self, args: argparse.Namespace) -> int:
        try:
            result = self.api_service.get_quota_report(args.period, args.limit)

            if getattr(args, 'output', None) == 'json':
                self.formatter.format_json(result)
            else:
                usage_data = result.get('usage', [])

                if not usage_data:
                    self.formatter.info("No API keys found with quota data")
                    return 0

                # Create table
                table = Table(title=f"Quota Usage Report ({args.period.capitalize()})")
                table.add_column("API Key", style="cyan")
                table.add_column("Client", style="green")
                table.add_column("Adapter", style="blue")
                table.add_column("Used", justify="right")
                table.add_column("Limit", justify="right")
                table.add_column("% Used", justify="right")
                table.add_column("Throttle", justify="center")
                table.add_column("Priority", justify="center")

                for item in usage_data:
                    used = item.get('used', 0)
                    limit = item.get('limit')
                    limit_str = str(limit) if limit else "Unlimited"

                    # Calculate percentage
                    if limit and limit > 0:
                        pct = (used / limit) * 100
                        pct_str = f"{pct:.1f}%"
                        if pct >= 90:
                            pct_str = f"[red]{pct_str}[/red]"
                        elif pct >= 70:
                            pct_str = f"[yellow]{pct_str}[/yellow]"
                    else:
                        pct_str = "-"

                    throttle_str = "Yes" if item.get('throttle_enabled', True) else "No"
                    priority = item.get('throttle_priority', 5)

                    table.add_row(
                        item.get('api_key_masked', '***'),
                        item.get('client_name', 'Unknown'),
                        item.get('adapter_name', '-') or '-',
                        str(used),
                        limit_str,
                        pct_str,
                        throttle_str,
                        str(priority)
                    )

                console.print(table)
                console.print(f"\nTotal keys: {result.get('total_keys', len(usage_data))}")

            return 0
        except Exception as e:
            self.formatter.error(f"Failed to generate report: {str(e)}")
            return 1
