"""
Identity allowlist commands.

Manages the rules that pre-clear external (Entra ID / Auth0) identities before
ORBIT will provision them an account. See docs/authentication.md.

``seed-from-existing`` exists for one job: turning enforcement on in a
deployment that already has external users. It grandfathers the current
population in one command so the operator doesn't have to hand-write a rule per
user — but it prints every identity first and asks, because "already signed in
once" is not an approval decision and this is the one place that could quietly
bless an account that shouldn't have had one.
"""

import argparse
from typing import Any, Dict, List

from rich.console import Console
from rich.prompt import Confirm

from bin.orbit.commands import BaseCommand
from bin.orbit.services.api_service import ApiService
from bin.orbit.utils.output import OutputFormatter

console = Console()

ENTRY_TYPES = ("email", "user_id", "username")


class AllowlistListCommand(BaseCommand):
    """Command to list identity allowlist rules."""

    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter

    @property
    def name(self) -> str:
        return "user allowlist list"

    @property
    def description(self) -> str:
        return "List identity allowlist rules"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        pass

    def execute(self, args: argparse.Namespace) -> int:
        rules = self.api_service.list_allowlist_rules()
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(rules)
            return 0

        if not rules:
            self.formatter.warning(
                "No allowlist rules. Under access_control: allowlist this means no "
                "external identity can sign in (apart from admin_users entries)."
            )
            return 0

        headers = ['ID', 'Type', 'Pattern', 'Reason', 'Added by']
        data = [
            {
                'ID': str(r.get('id', '')),
                'Type': r.get('entry_type', ''),
                'Pattern': r.get('pattern', ''),
                'Reason': r.get('reason') or '-',
                'Added by': r.get('created_by') or '-',
            }
            for r in rules
        ]
        self.formatter.format_table(data, headers)
        return 0


class AllowlistAddCommand(BaseCommand):
    """Command to add an identity allowlist rule."""

    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter

    @property
    def name(self) -> str:
        return "user allowlist add"

    @property
    def description(self) -> str:
        return "Pre-clear an identity pattern for external login"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '--pattern', required=True,
            help="Identity pattern; * and ? are wildcards, e.g. '*@corp.example.com'"
        )
        parser.add_argument(
            '--entry-type', default='email', choices=list(ENTRY_TYPES),
            help="Identity field to match (default: email). Use 'username' for "
                 "'{provider}:{subject}' values."
        )
        parser.add_argument('--reason', help='Why this identity is approved')

    def execute(self, args: argparse.Namespace) -> int:
        rule = self.api_service.add_allowlist_rule(
            pattern=args.pattern, entry_type=args.entry_type, reason=args.reason
        )
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(rule)
        else:
            self.formatter.success(
                f"Allowlist rule added: {rule['entry_type']}={rule['pattern']}"
            )
        return 0


class AllowlistRemoveCommand(BaseCommand):
    """Command to remove an identity allowlist rule."""

    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter

    @property
    def name(self) -> str:
        return "user allowlist remove"

    @property
    def description(self) -> str:
        return "Remove an allowlist rule and revoke the sessions it was clearing"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument('--rule-id', required=True, help='Allowlist rule ID')

    def execute(self, args: argparse.Namespace) -> int:
        result = self.api_service.delete_allowlist_rule(args.rule_id)
        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json(result)
        else:
            self.formatter.success(f"Allowlist rule removed: {args.rule_id}")
            revoked = result.get('revoked_sessions')
            if revoked:
                self.formatter.warning(
                    f"Revoked {revoked} session(s) for {result.get('matched_users')} "
                    f"user(s) this rule was clearing"
                )
        return 0


class AllowlistSeedCommand(BaseCommand):
    """Command to grandfather existing external users into the allowlist."""

    def __init__(self, api_service: ApiService, formatter: OutputFormatter):
        self.api_service = api_service
        self.formatter = formatter

    @property
    def name(self) -> str:
        return "user allowlist seed-from-existing"

    @property
    def description(self) -> str:
        return "Add an allowlist rule for each existing external user"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            '--yes', action='store_true',
            help='Skip the confirmation prompt (for scripted rollouts)'
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show the rules that would be added and exit'
        )

    def _external_users(self) -> List[Dict[str, Any]]:
        """Existing users provisioned by an external provider.

        Identified by the stored '{provider}:{subject}' username, which is the
        shape AuthService gives every JIT-provisioned external account.
        """
        users = self.api_service.list_users(limit=10000)
        return [
            u for u in users
            if str(u.get('username', '')).split(':', 1)[0] in ('entra', 'auth0')
            and ':' in str(u.get('username', ''))
        ]

    def execute(self, args: argparse.Namespace) -> int:
        users = self._external_users()
        if not users:
            self.formatter.warning("No external users found; nothing to seed.")
            return 0

        existing = {
            (r.get('entry_type'), r.get('pattern'))
            for r in self.api_service.list_allowlist_rules()
        }
        pending = [
            u for u in users
            if ('username', str(u['username']).lower()) not in existing
        ]

        if getattr(args, 'output', None) == 'json':
            self.formatter.format_json({
                'external_users': len(users),
                'already_cleared': len(users) - len(pending),
                'to_add': [u['username'] for u in pending],
            })
            if args.dry_run:
                return 0
        else:
            self.formatter.warning(
                f"About to pre-clear {len(pending)} of {len(users)} existing external "
                f"identities. Review this list — signing in once is not an approval:"
            )
            for u in pending:
                console.print(f"  - {u['username']}  ({u.get('email') or 'no email'})")
            if len(pending) < len(users):
                console.print(
                    f"({len(users) - len(pending)} already have a rule and are skipped.)"
                )

        if not pending:
            self.formatter.success("Every external user already has a rule.")
            return 0

        if args.dry_run:
            self.formatter.warning("Dry run — nothing was written.")
            return 0

        if not args.yes and not Confirm.ask(
            f"Add {len(pending)} allowlist rule(s)?", default=False
        ):
            self.formatter.warning("Aborted; nothing was written.")
            return 1

        added, failed = 0, 0
        for user in pending:
            try:
                self.api_service.add_allowlist_rule(
                    pattern=str(user['username']),
                    entry_type='username',
                    reason='Seeded from existing external user',
                )
                added += 1
            except Exception as e:
                failed += 1
                self.formatter.error(f"Failed for {user['username']}: {e}")

        self.formatter.success(f"Added {added} allowlist rule(s).")
        if failed:
            self.formatter.error(f"{failed} rule(s) could not be added.")
            return 1
        return 0
