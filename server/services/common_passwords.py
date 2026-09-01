"""Offline common-password blocklist used by the local password policy."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def load_common_passwords() -> frozenset[str]:
    """Load the bundled blocklist once, normalized for case-insensitive checks."""
    path = Path(__file__).parent.parent / "resources" / "common_passwords.txt"
    try:
        return frozenset(
            line.strip().casefold()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        )
    except OSError:
        # A missing package resource must not silently weaken an opted-in policy.
        return frozenset({"password"})
