"""
Writer — persists a generated adapter file and registers it so ORBIT loads it.

Fills the gap no current admin endpoint covers: create a new adapter file AND add
it to the import list in config/adapters.yaml (registration = activation).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = _PROJECT_ROOT / "config"
ADAPTERS_DIR = CONFIG_DIR / "adapters"
ADAPTERS_YAML = CONFIG_DIR / "adapters.yaml"

# Matches an import list entry, capturing its leading indent, e.g.  '  - "adapters/fetch.yaml"'
_IMPORT_ENTRY = re.compile(r'^(\s*)-\s*["\']?adapters/.+?["\']?\s*$')

# A safe adapter identifier: letters/digits to start, then letters/digits/_/-. No dots, no
# path separators, no "..", no absolute paths — so the name can never escape config/adapters/.
_VALID_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def validate_adapter_name(name: str) -> str:
    """Return the name if it is a safe filename identifier, else raise ValueError."""
    if not isinstance(name, str) or not _VALID_NAME.match(name):
        raise ValueError(
            f"invalid adapter name {name!r}: use only letters, digits, '_' and '-' "
            "(no path separators, dots, or '..')"
        )
    return name


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def is_registered(import_path: str, adapters_yaml: Path = ADAPTERS_YAML) -> bool:
    """True if `adapters/<file>.yaml` already appears (uncommented) in the import list."""
    text = adapters_yaml.read_text(encoding="utf-8")
    pattern = re.compile(r'^\s*-\s*["\']?' + re.escape(import_path) + r'["\']?\s*$', re.MULTILINE)
    return bool(pattern.search(text))


def register_import(import_path: str, adapters_yaml: Path = ADAPTERS_YAML) -> bool:
    """
    Add `adapters/<file>.yaml` to the import list, preserving comments/formatting via
    text insertion. Returns True if added, False if already present. Idempotent.
    """
    if is_registered(import_path, adapters_yaml):
        return False

    lines = adapters_yaml.read_text(encoding="utf-8").splitlines(keepends=True)

    last_entry_idx: Optional[int] = None
    indent = "  "
    for i, line in enumerate(lines):
        m = _IMPORT_ENTRY.match(line.rstrip("\n"))
        if m:
            last_entry_idx = i
            indent = m.group(1)

    if last_entry_idx is None:
        raise ValueError(f"Could not find an import list to append to in {adapters_yaml}")

    new_line = f'{indent}- "{import_path}"\n'
    if not lines[last_entry_idx].endswith("\n"):
        lines[last_entry_idx] += "\n"
    lines.insert(last_entry_idx + 1, new_line)

    _atomic_write(adapters_yaml, "".join(lines))
    return True


def write_adapter(
    name: str,
    yaml_text: str,
    *,
    register: bool = True,
    overwrite: bool = False,
    adapters_dir: Path = ADAPTERS_DIR,
    adapters_yaml: Path = ADAPTERS_YAML,
) -> Path:
    """
    Write config/adapters/<name>.yaml and (optionally) register it in adapters.yaml.
    Returns the path written. Raises FileExistsError if the file exists and overwrite is False,
    or ValueError if the name is not a safe filename identifier.
    """
    validate_adapter_name(name)
    target = adapters_dir / f"{name}.yaml"
    if target.exists() and not overwrite:
        raise FileExistsError(f"{target} already exists (pass overwrite=True to replace)")

    _atomic_write(target, yaml_text)

    if register:
        register_import(f"adapters/{name}.yaml", adapters_yaml)

    return target
