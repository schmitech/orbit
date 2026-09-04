#!/usr/bin/env python3
"""Offline recovery tool: reset a local user's password directly in the
database, bypassing the authenticated admin API.

`orbit user reset-password` (bin/orbit.py) calls the running server's API,
which itself requires an authenticated session - if you're locked out
(forgotten password, or a tripped account lockout under
`auth.account_lockout`), that command cannot help you back in. This script
talks to the configured database backend directly, using the same
AuthService.validate_password/_hash_and_encode the server uses, so the
result is indistinguishable from a normal in-app password change. It also
clears any active account lockout on the target user, since a forgotten
password and a lockout are often discovered together.

**Stop the server first** if you're on SQLite - a running server holds the
database file open, and this script does not coordinate with it.

Usage
-----
Run with the project venv activated, from the project root (it loads
config/config.yaml, the same one the server uses).

  # Reset the default admin's password (prompts for the new password)
  python utils/scripts/reset_admin_password.py --username admin

  # Non-interactive
  python utils/scripts/reset_admin_password.py --username admin --password 'NewPassword123!'

  # Only clear a lockout, without changing the password
  python utils/scripts/reset_admin_password.py --username admin --unlock-only

  # Point at a different config file
  python utils/scripts/reset_admin_password.py --username admin --config /path/to/config.yaml
"""

import argparse
import asyncio
import getpass
import sys
from pathlib import Path
from typing import Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SERVER_DIR = PROJECT_ROOT / "server"
sys.path.insert(0, str(SERVER_DIR))

import yaml

from services.auth_service import AuthService
from services.database_service import create_database_service


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline password reset / lockout clear for a local Orbit user."
    )
    parser.add_argument("--username", required=True, help="Username to reset")
    parser.add_argument(
        "--password",
        default=None,
        help="New password. If omitted (and --unlock-only is not set), you will be prompted.",
    )
    parser.add_argument(
        "--unlock-only",
        action="store_true",
        help="Clear failed-login/lockout state without changing the password",
    )
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "config" / "config.yaml"),
        metavar="PATH",
        help="Path to config.yaml (default: config/config.yaml)",
    )
    return parser.parse_args(argv)


async def reset(username: str, password: Optional[str], unlock_only: bool, config_path: str) -> int:
    with open(config_path) as f:
        config = yaml.safe_load(f)

    db = create_database_service(config)
    await db.initialize()
    auth = AuthService(config, database_service=db)
    await auth.initialize()

    try:
        user = await db.find_one(auth.users_collection_name, {"username": username})
        if not user:
            print(f"ERROR: no user named {username!r}", file=sys.stderr)
            return 1

        if user.get("provider"):
            print(
                f"ERROR: {username!r} is an external ({user['provider']}) identity - "
                "it has no local password to reset. Use the identity provider's own "
                "recovery flow instead.",
                file=sys.stderr,
            )
            return 1

        update = {
            "failed_login_attempts": 0,
            "last_failed_login_at": None,
            "locked_until": None,
        }

        if not unlock_only:
            error = AuthService.validate_password(password, auth.password_policy)
            if error:
                print(f"ERROR: password rejected: {error}", file=sys.stderr)
                return 1
            update["password"] = auth._hash_and_encode(password)

        result = await db.update_one(
            auth.users_collection_name,
            {"_id": user["_id"]},
            {"$set": update},
        )
        if not result:
            print("ERROR: update failed", file=sys.stderr)
            return 1

        if unlock_only:
            print(f"Cleared lockout state for {username!r}.")
        else:
            print(f"Password reset for {username!r}.")
        return 0
    finally:
        db.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    password = args.password
    if not args.unlock_only and password is None:
        password = getpass.getpass("New password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("ERROR: passwords do not match", file=sys.stderr)
            return 1

    return asyncio.run(reset(args.username, password, args.unlock_only, args.config))


if __name__ == "__main__":
    sys.exit(main())
