"""Unit tests for the MQ worker lifecycle service (PID-file based start/stop/status)."""

import signal
import sys
from pathlib import Path
from unittest.mock import MagicMock

# The worker CLI lives under the repo's bin/ package, which isn't on the server
# test path (conftest scopes sys.path to server/). Add the repo root so we can
# import it here.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from bin.orbit.services import worker_service as ws_mod  # noqa: E402
from bin.orbit.services.worker_service import WorkerService  # noqa: E402


def make_service(tmp_path):
    svc = WorkerService(project_root=tmp_path, formatter=MagicMock())
    return svc


class TestPidFile:
    def test_pid_roundtrip(self, tmp_path):
        svc = make_service(tmp_path)
        assert svc._read_pid() is None
        svc._write_pid(4321)
        assert svc.pid_file.exists()
        assert svc._read_pid() == 4321
        svc._remove_pid()
        assert svc._read_pid() is None

    def test_read_pid_handles_garbage(self, tmp_path):
        svc = make_service(tmp_path)
        svc.pid_file.parent.mkdir(parents=True, exist_ok=True)
        svc.pid_file.write_text("not-a-pid")
        assert svc._read_pid() is None

    def test_remove_pid_missing_is_noop(self, tmp_path):
        make_service(tmp_path)._remove_pid()  # no exception


class TestIsRunning:
    def test_no_pid_file(self, tmp_path):
        assert make_service(tmp_path).is_running() is False

    def test_live_pid(self, tmp_path, monkeypatch):
        svc = make_service(tmp_path)
        svc._write_pid(4321)
        monkeypatch.setattr(svc, "_pid_alive", lambda pid: True)
        assert svc.is_running() is True

    def test_stale_pid_is_cleared(self, tmp_path, monkeypatch):
        svc = make_service(tmp_path)
        svc._write_pid(4321)
        monkeypatch.setattr(svc, "_pid_alive", lambda pid: False)
        assert svc.is_running() is False
        assert svc._read_pid() is None  # stale file removed


class TestStop:
    def test_stop_when_not_running(self, tmp_path):
        svc = make_service(tmp_path)
        assert svc.stop() is True
        svc.formatter.info.assert_any_call("Worker is not running")

    def test_stop_sends_sigterm_and_clears_pid(self, tmp_path, monkeypatch):
        svc = make_service(tmp_path)
        svc._write_pid(4321)
        monkeypatch.setattr(svc, "is_running", lambda: True)
        # process dies immediately after SIGTERM, so the wait loop exits at once
        monkeypatch.setattr(svc, "_pid_alive", lambda pid: False)
        kill = MagicMock()
        monkeypatch.setattr(ws_mod.os, "kill", kill)

        assert svc.stop() is True
        kill.assert_called_once_with(4321, signal.SIGTERM)
        assert svc._read_pid() is None

    def test_stop_force_uses_sigkill(self, tmp_path, monkeypatch):
        svc = make_service(tmp_path)
        svc._write_pid(4321)
        monkeypatch.setattr(svc, "is_running", lambda: True)
        kill = MagicMock()
        monkeypatch.setattr(ws_mod.os, "kill", kill)

        assert svc.stop(force=True) is True
        kill.assert_called_once_with(4321, signal.SIGKILL)
        assert svc._read_pid() is None

    def test_stop_escalates_to_sigkill_on_timeout(self, tmp_path, monkeypatch):
        svc = make_service(tmp_path)
        svc._write_pid(4321)
        monkeypatch.setattr(svc, "is_running", lambda: True)
        monkeypatch.setattr(svc, "_pid_alive", lambda pid: True)   # never dies gracefully
        monkeypatch.setattr(ws_mod.time, "sleep", lambda s: None)  # don't actually wait
        kill = MagicMock()
        monkeypatch.setattr(ws_mod.os, "kill", kill)

        assert svc.stop(timeout=1) is True
        # SIGTERM first, then SIGKILL after the timeout
        assert kill.call_args_list[0].args == (4321, signal.SIGTERM)
        assert kill.call_args_list[-1].args == (4321, signal.SIGKILL)


class TestStart:
    def test_start_when_already_running(self, tmp_path, monkeypatch):
        svc = make_service(tmp_path)
        svc._write_pid(4321)
        monkeypatch.setattr(svc, "is_running", lambda: True)
        popen = MagicMock()
        monkeypatch.setattr(ws_mod.subprocess, "Popen", popen)

        assert svc.start() is True
        popen.assert_not_called()  # didn't spawn a second worker

    def test_start_spawns_and_writes_pid(self, tmp_path, monkeypatch):
        svc = make_service(tmp_path)
        monkeypatch.setattr(svc, "is_running", lambda: False)
        monkeypatch.setattr(ws_mod.time, "sleep", lambda s: None)

        proc = MagicMock()
        proc.poll.return_value = None   # still running after the startup wait
        proc.pid = 4321
        monkeypatch.setattr(ws_mod.subprocess, "Popen", MagicMock(return_value=proc))

        assert svc.start() is True
        assert svc._read_pid() == 4321

    def test_start_detects_immediate_crash(self, tmp_path, monkeypatch):
        svc = make_service(tmp_path)
        monkeypatch.setattr(svc, "is_running", lambda: False)
        monkeypatch.setattr(ws_mod.time, "sleep", lambda s: None)

        proc = MagicMock()
        proc.poll.return_value = 1      # exited immediately
        proc.returncode = 1
        proc.pid = 4321
        monkeypatch.setattr(ws_mod.subprocess, "Popen", MagicMock(return_value=proc))

        assert svc.start() is False
        assert svc._read_pid() is None  # no PID recorded for a crashed start


class TestRestart:
    def test_restart_aborts_when_stop_fails(self, tmp_path, monkeypatch):
        svc = make_service(tmp_path)
        monkeypatch.setattr(svc, "stop", lambda **kw: False)   # stop failed (e.g. SIGTERM raised)
        start = MagicMock(return_value=True)
        monkeypatch.setattr(svc, "start", start)

        assert svc.restart() is False
        start.assert_not_called()  # must not proceed to start on a failed stop

    def test_restart_starts_when_stop_succeeds(self, tmp_path, monkeypatch):
        svc = make_service(tmp_path)
        monkeypatch.setattr(svc, "stop", lambda **kw: True)
        monkeypatch.setattr(ws_mod.time, "sleep", lambda s: None)
        start = MagicMock(return_value=True)
        monkeypatch.setattr(svc, "start", start)

        assert svc.restart() is True
        start.assert_called_once()


class TestStatus:
    def test_status_running(self, tmp_path, monkeypatch):
        svc = make_service(tmp_path)
        svc._write_pid(4321)
        monkeypatch.setattr(svc, "is_running", lambda: True)
        assert svc.status() is True

    def test_status_not_running(self, tmp_path):
        assert make_service(tmp_path).status() is False


class TestConfigResolution:
    def test_explicit_relative_config_is_absolutized(self, tmp_path):
        svc = make_service(tmp_path)
        resolved = svc._resolve_config("config.yaml")
        assert resolved == str(tmp_path / "config.yaml")

    def test_build_cmd_includes_config(self, tmp_path):
        svc = make_service(tmp_path)
        cmd = svc._build_cmd("/abs/config.yaml")
        assert cmd == ["python", "server/worker_main.py", "--config", "/abs/config.yaml"]
