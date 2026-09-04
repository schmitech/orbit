"""
Admin IP allowlist commands.

Manages the CIDR ranges permitted to reach `/admin/*` and the admin-scoped
`/auth/*` routes, on top of `auth.admin_ip_allowlist.default_ranges` in
config.yaml. See docs/roadmap/authentication/complete/phase-6-auth-admin-ip-allowlist.md.
"""

import argparse

from rich.console import Console

from bin.orbit.commands import BaseCommand
from bin.orbit.services.api_service import ApiService
from bin.orbit.utils.output import OutputFormatter

console = Console()


class AdminIpListCommand(BaseCommand):
    """Command to list admin IP allowlist rules."""

    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter

    @property
    def name(self) -> str:
        return "admin-ip list"

    @property
    def description(self) -> str:
        return "List admin IP allowlist rules"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        pass

    def execute(self, args: argparse.Namespace) -> int:
        rules = self.api_service.list_admin_ip_rules()
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(rules)
            return 0

        if not rules:
            self.formatter.warning(
                "No admin IP rules. Under auth.admin_ip_allowlist.enabled with "
                "mode: allowlist, only default_ranges (and loopback) can reach "
                "the admin interface."
            )
            return 0

        headers = ['ID', 'CIDR', 'Reason', 'Added by']
        data = [
            {
                'ID': str(r.get('id', '')),
                'CIDR': r.get('cidr', ''),
                'Reason': r.get('reason') or '-',
                'Added by': r.get('created_by') or '-',
            }
            for r in rules
        ]
        self.formatter.format_table(data, headers)
        return 0


class AdminIpAddCommand(BaseCommand):
    """Command to add an admin IP allowlist rule."""

    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter

    @property
    def name(self) -> str:
        return "admin-ip add"

    @property
    def description(self) -> str:
        return "Allow an IP/CIDR range to reach the admin interface"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '--cidr', required=True,
            help="IP address or CIDR range, e.g. '10.0.0.0/8' or '203.0.113.4/32'"
        )
        parser.add_argument('--reason', help='Why this range is allowed')

    def execute(self, args: argparse.Namespace) -> int:
        rule = self.api_service.add_admin_ip_rule(cidr=args.cidr, reason=args.reason)
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(rule)
        else:
            self.formatter.success(f"Admin IP rule added: {rule['cidr']}")
        return 0


class AdminIpRemoveCommand(BaseCommand):
    """Command to remove an admin IP allowlist rule."""

    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter

    @property
    def name(self) -> str:
        return "admin-ip remove"

    @property
    def description(self) -> str:
        return "Remove an admin IP allowlist rule"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--rule-id', required=True, help='Admin IP rule ID')
        parser.add_argument(
            '--i-am-sure', action='store_true', dest='i_am_sure',
            help='Confirm removal even if it would exclude your own current IP'
        )

    def execute(self, args: argparse.Namespace) -> int:
        # The server refuses (400) without --i-am-sure if this rule is the only
        # thing covering the caller's own current IP while enforcement is
        # active - self-lockout guard. Its message names the IP explicitly, so
        # it's surfaced as-is rather than retried automatically.
        result = self.api_service.delete_admin_ip_rule(args.rule_id, force=args.i_am_sure)
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            self.formatter.success(f"Admin IP rule removed: {args.rule_id}")
        return 0
