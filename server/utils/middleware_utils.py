"""Shared middleware helpers."""

from typing import Sequence


def path_is_excluded(path: str, excluded: Sequence[str]) -> bool:
    """Return True when path exactly matches or is under an excluded path."""
    return any(path == item or path.startswith(item + "/") for item in excluded)
