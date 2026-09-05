#!/usr/bin/env python3
"""Generate a base64-encoded 32-byte key for `ORBIT_MFA_ENCRYPTION_KEY`.

Required once `auth.two_factor.enabled: true` is set - TOTP secrets are
encrypted at rest (AES-256-GCM) using this key (see
`server/services/file_storage/encryption.py`,
`server/services/mfa_service.py`). Without it set, enrollment fails loudly
rather than silently storing a secret in plaintext.

Usage
-----
  python utils/scripts/generate_mfa_encryption_key.py

  # Write directly into .env instead of printing to stdout
  python utils/scripts/generate_mfa_encryption_key.py --write-env
"""

import argparse
import base64
import secrets
import sys
from pathlib import Path
from typing import Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_VAR = "ORBIT_MFA_ENCRYPTION_KEY"


def generate_key() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode()


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-env",
        action="store_true",
        help=f"Append {ENV_VAR}=<key> to .env in the project root instead of "
        "printing it (refuses to overwrite an existing entry).",
    )
    parser.add_argument(
        "--env-file",
        default=str(PROJECT_ROOT / ".env"),
        metavar="PATH",
        help="Path to the .env file to write to with --write-env (default: project root .env)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    key = generate_key()

    if not args.write_env:
        print(key)
        return 0

    env_path = Path(args.env_file)
    existing = env_path.read_text() if env_path.exists() else ""
    if any(line.strip().startswith(f"{ENV_VAR}=") for line in existing.splitlines()):
        print(
            f"ERROR: {ENV_VAR} is already set in {env_path} - remove it first "
            "if you intend to rotate the key (existing enrolled TOTP secrets "
            "will stop decrypting).",
            file=sys.stderr,
        )
        return 1

    with env_path.open("a") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write(f"{ENV_VAR}={key}\n")
    print(f"Wrote {ENV_VAR} to {env_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
