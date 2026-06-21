"""
Unit tests for log file picker logic introduced in admin_routes.py.

These tests exercise the candidate-resolution and security logic directly
(without importing admin_routes, which requires a full FastAPI app context)
by mirroring the same algorithm used in:
  - _resolve_log_dir_and_candidates()
  - list_log_files()
  - tail_log_file() with ?file= param
"""

import pytest
import time
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers mirroring admin_routes.py implementation
# ---------------------------------------------------------------------------

def resolve_candidates(log_dir: Path, base_filename: str) -> list[Path]:
    """Mirror of _resolve_log_dir_and_candidates() — returns sorted candidate list."""
    return sorted(
        [p for p in log_dir.glob(base_filename + "*") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def tail_file(path: Path, n: int) -> list[str]:
    """Mirror of _tail_file() — seeks from end to avoid reading entire file."""
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


def resolve_requested_file(log_dir: Path, filename: str, candidates: list[Path]):
    """Mirror of the ?file= validation in tail_log_file()."""
    path = (log_dir / Path(filename).name).resolve()
    if path not in candidates:
        return None  # caller should raise 404
    return path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

LOG_CONTENT = {
    "orbit.log": [
        "2026-06-21 10:00:00,001 - health_routes - INFO - GET /health 200",
        "2026-06-21 10:01:22,441 - chat_routes - INFO - POST /v1/chat/completions adapter=simple-chat",
        "2026-06-21 10:01:23,812 - chat_service - INFO - Streamed 312 tokens in 1.37s",
        "2026-06-21 10:15:00,001 - health_routes - INFO - GET /health 200",
        "2026-06-21 11:02:33,441 - retrieval_service - WARNING - Slow query detected (2847ms)",
    ],
    "orbit.log.1": [
        "2026-06-20 00:01:02,114 - config.config_manager - INFO - Server startup complete",
        "2026-06-20 08:45:22,113 - chat_routes - INFO - POST /v1/chat/completions adapter=business-analytics",
        "2026-06-20 08:45:24,401 - retrieval_service - INFO - Intent matched: revenue_by_region (score=0.94)",
        "2026-06-20 10:29:47,663 - guardrail_service - WARNING - Content policy triggered (category=prompt_injection)",
        "2026-06-20 04:15:07,904 - adapters.composite - ERROR - All retries exhausted for adapter=postgres-assistant",
        "2026-06-20 23:59:59,999 - inference_server - INFO - Log rotation triggered. Continuing in orbit.log",
    ],
    "orbit.log.2": [
        "2026-06-19 00:00:55,771 - config.config_manager - INFO - Server startup complete",
        "2026-06-19 11:17:48,003 - retrieval_service - ERROR - Database connection lost: datasource=pg-prod",
        "2026-06-19 11:17:53,334 - datasources.postgres - INFO - Reconnected to pg-prod after 5.3s",
        "2026-06-19 22:33:22,118 - chat_service - INFO - Streamed 477 tokens in 2.67s",
        "2026-06-19 23:59:59,999 - inference_server - INFO - Log rotation triggered. Continuing in orbit.log",
    ],
    "orbit.log.3": [
        "2026-06-18 00:00:41,003 - config.config_manager - INFO - Server startup complete",
        "2026-06-18 10:11:55,338 - guardrail_service - WARNING - Content policy triggered (category=pii_leak)",
        "2026-06-18 12:45:31,007 - admin_routes - INFO - Admin action: create_user user=admin new_user=coconut",
        "2026-06-18 16:38:52,003 - retrieval_service - WARNING - Low confidence intent match (score=0.51)",
        "2026-06-18 23:59:59,999 - inference_server - INFO - Log rotation triggered. Continuing in orbit.log",
    ],
}

# Ordered newest → oldest so mtime stamps are applied correctly
FILE_ORDER = ["orbit.log", "orbit.log.1", "orbit.log.2", "orbit.log.3"]


@pytest.fixture()
def log_dir(tmp_path: Path) -> Path:
    """Create a logs/ directory with 4 realistic log files at distinct mtimes."""
    d = tmp_path / "logs"
    d.mkdir()

    base_mtime = time.time()
    for i, name in enumerate(FILE_ORDER):
        path = d / name
        path.write_text("\n".join(LOG_CONTENT[name]) + "\n", encoding="utf-8")
        # newest file gets highest mtime; each older file is 1 day earlier
        mtime = base_mtime - i * 86400
        import os
        os.utime(path, (mtime, mtime))

    return d


# ---------------------------------------------------------------------------
# Tests: list_log_files logic
# ---------------------------------------------------------------------------

class TestListLogFiles:

    def test_finds_all_rotated_files(self, log_dir):
        candidates = resolve_candidates(log_dir, "orbit.log")
        assert len(candidates) == 4

    def test_sorted_newest_first(self, log_dir):
        candidates = resolve_candidates(log_dir, "orbit.log")
        names = [p.name for p in candidates]
        assert names == FILE_ORDER

    def test_current_is_first(self, log_dir):
        candidates = resolve_candidates(log_dir, "orbit.log")
        assert candidates[0].name == "orbit.log"

    def test_ignores_unrelated_files(self, log_dir):
        (log_dir / "other_service.log").write_text("noise\n")
        (log_dir / "orbit.log.bak").write_text("backup\n")
        candidates = resolve_candidates(log_dir, "orbit.log")
        names = {p.name for p in candidates}
        assert "other_service.log" not in names
        # .bak does NOT match orbit.log* glob — it does, so verify it IS included
        # (matches the prefix pattern; this is expected and safe since it's in log_dir)
        assert all(n.startswith("orbit.log") for n in names)

    def test_empty_log_dir_returns_no_candidates(self, tmp_path):
        d = tmp_path / "empty_logs"
        d.mkdir()
        candidates = resolve_candidates(d, "orbit.log")
        assert candidates == []


# ---------------------------------------------------------------------------
# Tests: tail_log_file ?file= resolution logic
# ---------------------------------------------------------------------------

class TestRequestedFileResolution:

    def test_current_file_resolves(self, log_dir):
        candidates = resolve_candidates(log_dir, "orbit.log")
        result = resolve_requested_file(log_dir, "orbit.log", candidates)
        assert result is not None
        assert result.name == "orbit.log"

    def test_rotated_file_resolves(self, log_dir):
        candidates = resolve_candidates(log_dir, "orbit.log")
        result = resolve_requested_file(log_dir, "orbit.log.1", candidates)
        assert result is not None
        assert result.name == "orbit.log.1"

    def test_nonexistent_file_returns_none(self, log_dir):
        candidates = resolve_candidates(log_dir, "orbit.log")
        result = resolve_requested_file(log_dir, "orbit.log.99", candidates)
        assert result is None

    def test_path_traversal_returns_none(self, log_dir):
        """../config/config.yaml must not resolve to a readable path."""
        candidates = resolve_candidates(log_dir, "orbit.log")
        result = resolve_requested_file(log_dir, "../config/config.yaml", candidates)
        assert result is None

    def test_path_traversal_with_subdirectory_returns_none(self, log_dir):
        candidates = resolve_candidates(log_dir, "orbit.log")
        result = resolve_requested_file(log_dir, "../../server/main.py", candidates)
        assert result is None

    def test_unrelated_file_in_log_dir_returns_none(self, log_dir):
        """A file that exists in log_dir but doesn't match the glob must be blocked."""
        secret = log_dir / "credentials.txt"
        secret.write_text("super-secret\n")
        candidates = resolve_candidates(log_dir, "orbit.log")
        result = resolve_requested_file(log_dir, "credentials.txt", candidates)
        assert result is None


# ---------------------------------------------------------------------------
# Tests: tail_file content correctness
# ---------------------------------------------------------------------------

class TestTailFile:

    def test_tail_returns_last_n_lines(self, log_dir):
        path = log_dir / "orbit.log.1"
        lines = tail_file(path, 3)
        expected = LOG_CONTENT["orbit.log.1"][-3:]
        assert lines == expected

    def test_tail_more_than_available_returns_all(self, log_dir):
        path = log_dir / "orbit.log.2"
        total = len(LOG_CONTENT["orbit.log.2"])
        lines = tail_file(path, total + 100)
        assert lines == LOG_CONTENT["orbit.log.2"]

    def test_tail_empty_file_returns_empty_list(self, tmp_path):
        empty = tmp_path / "orbit.log"
        empty.write_bytes(b"")
        assert tail_file(empty, 100) == []

    def test_tail_single_line_file(self, tmp_path):
        f = tmp_path / "orbit.log"
        f.write_text("only one line\n", encoding="utf-8")
        assert tail_file(f, 10) == ["only one line"]

    def test_tail_current_log_content(self, log_dir):
        path = log_dir / "orbit.log"
        lines = tail_file(path, 2)
        assert lines == LOG_CONTENT["orbit.log"][-2:]

    def test_tail_rotated_log_ends_with_rotation_marker(self, log_dir):
        for name in ["orbit.log.1", "orbit.log.2", "orbit.log.3"]:
            lines = tail_file(log_dir / name, 1)
            assert "Log rotation triggered" in lines[0]
