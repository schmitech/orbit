"""
Server info and config.yaml read/write endpoints.
"""

import logging
import re
import yaml
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException, Body

from routes.admin._shared import (
    config_auth, system_auth,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/info", dependencies=[system_auth])
async def get_server_info(
    request: Request,
):
    """
    Get server information including PID and status.
    
    This endpoint provides information about the running server instance,
    including process ID for process management.
    
    Returns:
        Dictionary containing server information (PID, version, etc.)
    """
    import os

    from services.pause_state import is_paused

    # Under multi-worker mode, os.getpid() is this specific worker's PID, not
    # a stable process to target for stop/status — report the supervisor's
    # PID instead (set by InferenceServer.run(), inherited by all workers).
    pid = int(os.environ.get('ORBIT_SUPERVISOR_PID', os.getpid()))

    return {
        "pid": pid,
        "version": "2.17.3",
        "status": "paused" if await is_paused(request.app.state) else "running"
    }


@router.get("/config", dependencies=[config_auth])
async def get_config(
    request: Request,
):
    """
    Read the raw config.yaml file content.

    Returns the raw file text so that comments, env var references,
    and import directives are preserved.
    """
    config_path = Path(getattr(request.app.state, 'config_path', 'config/config.yaml'))
    if not config_path.is_file():
        raise HTTPException(status_code=404, detail=f"Config file not found: {config_path}")
    content = config_path.read_text(encoding='utf-8')
    return {"content": content, "path": str(config_path.resolve())}


@router.put("/config", dependencies=[config_auth])
async def update_config(
    request: Request,
    body: dict = Body(...)
):
    """
    Validate and write new config.yaml content.

    Accepts {"content": "<yaml string>"}. Validates YAML syntax, then writes
    the new content. A server restart is required for most changes to take effect.
    """
    content = body.get("content")
    if content is None:
        raise HTTPException(status_code=422, detail="Missing 'content' field")

    # Validate YAML syntax
    try:
        yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid YAML: {exc}")

    config_path = Path(getattr(request.app.state, 'config_path', 'config/config.yaml'))
    if not config_path.is_file():
        raise HTTPException(status_code=404, detail=f"Config file not found: {config_path}")

    # Write new content
    config_path.write_text(content, encoding='utf-8')
    logger.debug("Config file updated at %s", config_path)

    # Clear loaded config singleton so next access picks up changes
    from config.config_manager import clear_config_cache
    clear_config_cache()

    return {
        "message": "Config saved. A server restart is required for changes to take effect.",
    }


_TOP_LEVEL_CONFIG_KEY_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*):(?:\s.*)?$')


def _split_config_sections(content: str):
    """Split raw config.yaml text into top-level-key sections by line range.

    Slices the raw text instead of parsing+re-dumping YAML, so comments, env
    var placeholders (${...}), and the import: directive survive untouched.
    A comment/blank-line block immediately above a key is treated as part of
    that key's section, since it documents the section below it.
    """
    lines = content.splitlines(keepends=True)
    key_line_indices = [i for i, line in enumerate(lines) if _TOP_LEVEL_CONFIG_KEY_RE.match(line)]
    if not key_line_indices:
        return None

    starts = []
    for pos, key_idx in enumerate(key_line_indices):
        lower_bound = key_line_indices[pos - 1] + 1 if pos > 0 else 0
        start = key_idx
        while start > lower_bound and (lines[start - 1].strip() == "" or lines[start - 1].lstrip().startswith("#")):
            start -= 1
        starts.append(start)

    sections = []
    for pos, key_idx in enumerate(key_line_indices):
        key = _TOP_LEVEL_CONFIG_KEY_RE.match(lines[key_idx]).group(1)
        end = starts[pos + 1] - 1 if pos + 1 < len(key_line_indices) else len(lines) - 1
        sections.append({"key": key, "start": starts[pos], "end": end})
    return sections, lines


def _load_config_sections(request: Request):
    config_path = Path(getattr(request.app.state, 'config_path', 'config/config.yaml'))
    if not config_path.is_file():
        raise HTTPException(status_code=404, detail=f"Config file not found: {config_path}")
    content = config_path.read_text(encoding='utf-8')
    result = _split_config_sections(content)
    if result is None:
        raise HTTPException(status_code=404, detail="No top-level sections found in config file")
    sections, lines = result
    return config_path, sections, lines


@router.get("/config/sections", dependencies=[config_auth])
async def list_config_sections(request: Request):
    """List config.yaml's top-level keys, for the split settings editor."""
    _config_path, sections, _lines = _load_config_sections(request)
    return {
        "sections": [
            {"key": s["key"], "line_count": s["end"] - s["start"] + 1}
            for s in sections
        ]
    }


@router.get("/config/sections/{key}", dependencies=[config_auth])
async def get_config_section(request: Request, key: str):
    """Read the raw text of a single top-level config.yaml section."""
    _config_path, sections, lines = _load_config_sections(request)
    match = next((s for s in sections if s["key"] == key), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"Section '{key}' not found")
    return {"content": "".join(lines[match["start"]:match["end"] + 1])}


@router.put("/config/sections/{key}", dependencies=[config_auth])
async def update_config_section(request: Request, key: str, body: dict = Body(...)):
    """Validate and splice one section's edited text back into config.yaml."""
    new_section_content = body.get("content")
    if new_section_content is None:
        raise HTTPException(status_code=422, detail="Missing 'content' field")
    if not new_section_content.endswith("\n"):
        new_section_content += "\n"

    config_path, sections, lines = _load_config_sections(request)
    match = next((s for s in sections if s["key"] == key), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"Section '{key}' not found")

    # Count raw top-level key headers by regex rather than trusting yaml.safe_load's
    # parsed keys — PyYAML silently collapses duplicate mapping keys (last one wins),
    # so a pasted-in second "auth:" header would parse clean but still be a structural
    # change we don't want to allow from the per-section editor.
    section_key_headers = [
        m.group(1) for line in new_section_content.splitlines()
        if (m := _TOP_LEVEL_CONFIG_KEY_RE.match(line + "\n"))
    ]
    if section_key_headers != [key]:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Section '{key}' must remain a single top-level key named '{key}'. "
                "Renaming, removing, adding, or duplicating a top-level key here isn't "
                "supported — use the Raw File editor for structural changes."
            ),
        )

    try:
        parsed_section = yaml.safe_load(new_section_content)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid YAML in section '{key}': {exc}")

    # Belt-and-suspenders: the raw header count catches duplicate/renamed/injected
    # headers even when PyYAML would silently collapse them, while this parsed-key
    # check catches any exotic syntax (e.g. multi-line flow mappings) that could
    # confuse the regex-based header count.
    if not isinstance(parsed_section, dict) or list(parsed_section.keys()) != [key]:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Section '{key}' must remain a single top-level key named '{key}'. "
                "Renaming, removing, adding, or duplicating a top-level key here isn't "
                "supported — use the Raw File editor for structural changes."
            ),
        )

    new_content = "".join(lines[:match["start"]] + [new_section_content] + lines[match["end"] + 1:])

    full_key_headers = [
        m.group(1) for line in new_content.splitlines()
        if (m := _TOP_LEVEL_CONFIG_KEY_RE.match(line + "\n"))
    ]
    if full_key_headers != [s["key"] for s in sections]:
        raise HTTPException(
            status_code=422,
            detail=f"Saving section '{key}' would change the config file's top-level structure.",
        )

    try:
        parsed_full = yaml.safe_load(new_content)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid YAML after merging section '{key}': {exc}")

    if not isinstance(parsed_full, dict) or list(parsed_full.keys()) != [s["key"] for s in sections]:
        raise HTTPException(
            status_code=422,
            detail=f"Saving section '{key}' would change the config file's top-level structure.",
        )

    config_path.write_text(new_content, encoding='utf-8')
    logger.debug("Config section '%s' updated at %s", key, config_path)

    from config.config_manager import clear_config_cache
    clear_config_cache()

    return {
        "message": f"'{key}' section saved. A server restart is required for changes to take effect.",
    }
