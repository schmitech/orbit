"""
Comment-preserving YAML helpers for the adapter and MCP config files.

MCP servers and adapters both live in heavily commented YAML files whose
commented-out entries form a catalogue. Writes therefore patch individual
lines in place rather than round-tripping through yaml.dump.
"""

import logging
from pathlib import Path

import yaml
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


def _get_adapters_dir(request: Request) -> Path:
    """Resolve the adapters config directory from app state."""
    config_path = Path(getattr(request.app.state, 'config_path', 'config/config.yaml'))
    return config_path.parent / "adapters"


def _validate_adapter_filename(filename: str) -> None:
    """Reject path-traversal attempts."""
    if "/" in filename or "\\" in filename or ".." in filename or not filename.endswith(".yaml"):
        raise HTTPException(status_code=400, detail="Invalid adapter filename")


def _find_adapter_block(lines: list[str], adapter_name: str) -> tuple[int, int]:
    """Find start/end line indices of a single adapter entry in YAML content.

    Returns (start, end) where lines[start:end] is the adapter block.
    """
    start = None
    start_indent = 0
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped.startswith("- name:"):
            continue
        name_val = stripped[len("- name:"):].strip().strip('"').strip("'")
        if name_val == adapter_name:
            start = i
            start_indent = len(line) - len(stripped)
            break

    if start is None:
        return -1, -1

    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].lstrip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        current_indent = len(lines[i]) - len(stripped)
        if stripped.startswith("- ") and current_indent <= start_indent:
            end = i
            break
        if current_indent < start_indent:
            end = i
            break

    while end > start + 1 and lines[end - 1].strip() == "":
        end -= 1

    return start, end


def _find_adapter_file(adapters_dir: Path, adapter_name: str):
    """Locate which .yaml file contains an adapter by name. Returns (path, content)."""
    for yaml_file in sorted(adapters_dir.glob("*.yaml")):
        content = yaml_file.read_text(encoding="utf-8")
        try:
            parsed = yaml.safe_load(content) or {}
            for a in parsed.get("adapters", []):
                if isinstance(a, dict) and a.get("name") == adapter_name:
                    return yaml_file, content
        except yaml.YAMLError:
            continue
    return None, ""


def _write_adapter_config(file_path: Path, new_content: str) -> None:
    """Write new adapter config content to disk."""
    file_path.write_text(new_content, encoding="utf-8")
    logger.info("Adapter config updated: %s", file_path)
    from config.config_manager import clear_config_cache
    clear_config_cache()
