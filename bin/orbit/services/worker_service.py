"""
Worker service — lifecycle management for the ORBIT message-queue (MQ) worker.

Unlike the HTTP server, the worker has no health endpoint, so status/stop are
PID-file based (logs/worker.pid) rather than HTTP-based. Supports a foreground
run (for systemd/Docker/dev) plus managed background start/stop/status/restart.
"""

import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from bin.orbit.utils.output import OutputFormatter

logger = logging.getLogger(__name__)


class WorkerService:
    """Manages the lifecycle of the standalone MQ worker process."""

    def __init__(self, project_root: Optional[Path] = None, formatter: Optional[OutputFormatter] = None):
        self.formatter = formatter or OutputFormatter()
        if project_root is None:
            # __file__ is bin/orbit/services/worker_service.py -> up 4 = project root
            project_root = Path(__file__).parent.parent.parent.parent
        self.project_root = Path(project_root)
        self.pid_file = self.project_root / "logs" / "worker.pid"
        self.log_file = self.project_root / "logs" / "worker.log"

    # ------------------------------------------------------------------
    # PID file helpers
    # ------------------------------------------------------------------
    def _read_pid(self) -> Optional[int]:
        try:
            return int(self.pid_file.read_text().strip())
        except (FileNotFoundError, ValueError):
            return None

    def _write_pid(self, pid: int) -> None:
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(str(pid))

    def _remove_pid(self) -> None:
        try:
            self.pid_file.unlink()
        except FileNotFoundError:
            pass

    def _pid_alive(self, pid: int) -> bool:
        """True if pid belongs to a live ORBIT worker process (guards against PID reuse)."""
        if PSUTIL_AVAILABLE:
            try:
                proc = psutil.Process(pid)
                if not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE:
                    return False
                return "worker_main.py" in " ".join(proc.cmdline())
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                return False
        # Fallback without psutil: liveness only (can't verify it's our worker)
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    def is_running(self) -> bool:
        """True if a tracked worker is alive. Clears a stale PID file otherwise."""
        pid = self._read_pid()
        if pid is None:
            return False
        if self._pid_alive(pid):
            return True
        self._remove_pid()
        return False

    # ------------------------------------------------------------------
    # Command construction
    # ------------------------------------------------------------------
    def _resolve_config(self, config_path: Optional[str]) -> Optional[str]:
        if config_path:
            if not os.path.isabs(config_path):
                config_path = str(self.project_root / config_path)
            return config_path
        for candidate in (
            self.project_root / "config" / "config.yaml",
            self.project_root / "server" / "config.yaml",
            self.project_root / "config.yaml",
        ):
            if candidate.exists():
                return str(candidate)
        return None

    def _build_cmd(self, config_path: Optional[str]) -> list:
        cmd = ["python", "server/worker_main.py"]
        resolved = self._resolve_config(config_path)
        if resolved:
            cmd.extend(["--config", resolved])
        return cmd

    def _maybe_delete_logs(self, delete_logs: bool) -> None:
        if delete_logs and self.log_file.exists():
            try:
                self.log_file.unlink()
            except OSError as e:
                logger.warning(f"Failed to delete worker log: {e}")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def run_foreground(self, config_path: Optional[str] = None) -> int:
        """Run the worker in the foreground (blocks until Ctrl+C). For systemd/Docker/dev."""
        cmd = self._build_cmd(config_path)
        self.formatter.info("Starting ORBIT MQ worker in foreground (Ctrl+C to stop)...")
        try:
            return subprocess.run(cmd, cwd=str(self.project_root)).returncode
        except KeyboardInterrupt:
            self.formatter.info("Worker stopped")
            return 0

    def start(self, config_path: Optional[str] = None, delete_logs: bool = False) -> bool:
        """Start the worker as a detached background process, tracked via a PID file."""
        if self.is_running():
            self.formatter.warning(f"Worker is already running (PID {self._read_pid()})")
            return True

        self._maybe_delete_logs(delete_logs)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        cmd = self._build_cmd(config_path)

        try:
            with open(self.log_file, "a") as log:
                process = subprocess.Popen(
                    cmd,
                    cwd=str(self.project_root),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,  # detach from the CLI's session
                )
        except Exception as e:
            self.formatter.error(f"Error starting worker: {e}")
            return False

        # Give it a moment and detect an immediate crash (bad config, missing aio-pika, ...)
        time.sleep(2)
        if process.poll() is not None:
            self.formatter.error(f"Worker exited immediately with code {process.returncode}")
            self.formatter.info(f"Check logs at: {self.log_file}")
            return False

        self._write_pid(process.pid)
        self.formatter.success(f"Worker started successfully with PID {process.pid}")
        self.formatter.info(f"Logs are being written to {self.log_file}")
        return True

    def stop(self, timeout: int = 30, force: bool = False, delete_logs: bool = False) -> bool:
        """Stop a running worker (SIGTERM for graceful shutdown, SIGKILL on --force/timeout)."""
        if not self.is_running():
            self.formatter.info("Worker is not running")
            self._remove_pid()
            self._maybe_delete_logs(delete_logs)
            return True

        pid = self._read_pid()
        try:
            if force:
                os.kill(pid, signal.SIGKILL)
            else:
                os.kill(pid, signal.SIGTERM)
                waited = 0.0
                while waited < timeout and self._pid_alive(pid):
                    time.sleep(0.5)
                    waited += 0.5
                if self._pid_alive(pid):
                    self.formatter.warning("Graceful shutdown timed out; force killing")
                    os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass  # already gone
        except Exception as e:
            self.formatter.error(f"Error stopping worker: {e}")
            return False

        self._remove_pid()
        self.formatter.success("Worker stopped")
        self._maybe_delete_logs(delete_logs)
        return True

    def restart(self, config_path: Optional[str] = None, delete_logs: bool = False) -> bool:
        # Abort if the running worker couldn't be stopped — otherwise start() would
        # see the still-present PID, report "already running", and mask the failure.
        if not self.stop(delete_logs=delete_logs):
            self.formatter.error("Restart aborted: failed to stop the running worker")
            return False
        time.sleep(1)
        return self.start(config_path=config_path)

    def status(self) -> bool:
        """Report worker status. Returns True if running."""
        if self.is_running():
            self.formatter.success(f"Worker is running (PID {self._read_pid()})")
            self.formatter.info(f"Logs: {self.log_file}")
            return True
        self.formatter.info("Worker is not running")
        return False
