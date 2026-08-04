"""
Log file discovery and tailing endpoints.
"""

import logging
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException, Query

from routes.admin._shared import (
    logs_auth,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _tail_file(path: Path, n: int) -> list:
    """Read last n lines by seeking from end of file instead of reading everything."""
    with path.open("rb") as f:
        f.seek(0, 2)
        size = f.tell()
        if size == 0:
            return []
        block_size = 8192
        blocks: list = []
        pos = size
        newline_count = 0

        while pos > 0 and newline_count < n + 1:
            read_size = min(block_size, pos)
            pos -= read_size
            f.seek(pos)
            block = f.read(read_size)
            blocks.insert(0, block)
            newline_count += block.count(b"\n")

        text = b"".join(blocks).decode("utf-8", errors="replace")
        return text.splitlines()[-n:]


def _resolve_log_dir_and_candidates(request: Request):
    config = request.app.state.config or {}
    file_config = config.get("logging", {}).get("handlers", {}).get("file", {})
    log_dir = Path(file_config.get("directory", "logs")).resolve()
    base_filename = file_config.get("filename", "orbit.log")
    candidates = sorted(
        [p for p in log_dir.glob(base_filename + "*") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return log_dir, candidates


@router.get("/logs/files", dependencies=[logs_auth])
def list_log_files(request: Request):
    """Return all available log files sorted newest-first."""
    log_dir, candidates = _resolve_log_dir_and_candidates(request)
    files = []
    for i, path in enumerate(candidates):
        stat = path.stat()
        files.append({
            "filename": path.name,
            "size": stat.st_size,
            "updated_at": datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z",
            "is_current": i == 0,
        })
    return {"files": files}


@router.get("/logs/tail", dependencies=[logs_auth])
def tail_log_file(
    request: Request,
    lines: int = Query(200, ge=10, le=500),
    file: str = Query(None),
):
    """
    Return ORBIT log file contents. With no `file` param returns the most
    recently updated file. Pass `file=<filename>` to read a specific rotated file.
    """
    log_dir, candidates = _resolve_log_dir_and_candidates(request)

    if not candidates:
        raise HTTPException(status_code=404, detail="No log files found")

    if file:
        log_path = (log_dir / Path(file).name).resolve()
        if log_path not in candidates:
            raise HTTPException(status_code=404, detail="Log file not found")
    else:
        log_path = candidates[0]

    try:
        mtime = log_path.stat().st_mtime
        tail_lines = _tail_file(log_path, lines)
    except OSError as exc:
        logger.error(f"Failed reading log file {log_path}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to read log file")

    return {
        "file": str(log_path),
        "filename": log_path.name,
        "updated_at": datetime.utcfromtimestamp(mtime).isoformat() + "Z",
        "lines": tail_lines,
    }
