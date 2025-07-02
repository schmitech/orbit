"""
Unit tests for process manager.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from orbit_cli.server.process_manager import ProcessManager
from orbit_cli.core.exceptions import ProcessError


class TestProcessManager:
    """Test cases for ProcessManager class."""

    @pytest.mark.unit
    def test_init(self):
        """Test ProcessManager initialization."""
        manager = ProcessManager()
        assert manager.processes == {}

    @pytest.mark.unit
    def test_start_process_success(self, mock_subprocess):
        """Test successful process start."""
        process_instance = Mock()
        process_instance.pid = 12345
        mock_subprocess.return_value = process_instance
        
        manager = ProcessManager()
        result = manager.start_process("test_process", ["python", "test.py"])
        
        assert result["status"] == "started"
        assert result["pid"] == 12345
        assert "test_process" in manager.processes
        mock_subprocess.assert_called_once()

    @pytest.mark.unit
    def test_start_process_already_running(self, mock_subprocess):
        """Test process start when already running."""
        process_instance = Mock()
        process_instance.pid = 12345
        mock_subprocess.return_value = process_instance
        
        manager = ProcessManager()
        manager.start_process("test_process", ["python", "test.py"])
        
        with pytest.raises(ProcessError, match="Process test_process is already running"):
            manager.start_process("test_process", ["python", "test.py"])

    @pytest.mark.unit
    def test_stop_process_success(self, mock_subprocess):
        """Test successful process stop."""
        process_instance = Mock()
        process_instance.pid = 12345
        process_instance.terminate.return_value = None
        process_instance.wait.return_value = 0
        mock_subprocess.return_value = process_instance
        
        manager = ProcessManager()
        manager.start_process("test_process", ["python", "test.py"])
        result = manager.stop_process("test_process")
        
        assert result["status"] == "stopped"
        assert "test_process" not in manager.processes
        process_instance.terminate.assert_called_once()

    @pytest.mark.unit
    def test_stop_process_not_running(self):
        """Test process stop when not running."""
        manager = ProcessManager()
        
        with pytest.raises(ProcessError, match="Process test_process is not running"):
            manager.stop_process("test_process")

    @pytest.mark.unit
    def test_restart_process_success(self, mock_subprocess):
        """Test successful process restart."""
        process_instance = Mock()
        process_instance.pid = 12345
        process_instance.terminate.return_value = None
        process_instance.wait.return_value = 0
        mock_subprocess.return_value = process_instance
        
        manager = ProcessManager()
        manager.start_process("test_process", ["python", "test.py"])
        result = manager.restart_process("test_process")
        
        assert result["status"] == "restarted"
        assert result["pid"] == 12345

    @pytest.mark.unit
    def test_is_process_running_true(self, mock_subprocess):
        """Test process running status when running."""
        process_instance = Mock()
        process_instance.pid = 12345
        process_instance.is_running.return_value = True
        mock_subprocess.return_value = process_instance
        
        manager = ProcessManager()
        manager.start_process("test_process", ["python", "test.py"])
        result = manager.is_process_running("test_process")
        
        assert result is True

    @pytest.mark.unit
    def test_is_process_running_false(self):
        """Test process running status when not running."""
        manager = ProcessManager()
        result = manager.is_process_running("test_process")
        
        assert result is False

    @pytest.mark.unit
    def test_get_process_status_running(self, mock_subprocess):
        """Test process status when running."""
        process_instance = Mock()
        process_instance.pid = 12345
        process_instance.is_running.return_value = True
        process_instance.cpu_percent.return_value = 2.5
        process_instance.memory_percent.return_value = 1.2
        mock_subprocess.return_value = process_instance
        
        manager = ProcessManager()
        manager.start_process("test_process", ["python", "test.py"])
        result = manager.get_process_status("test_process")
        
        assert result["status"] == "running"
        assert result["pid"] == 12345
        assert result["cpu_percent"] == 2.5
        assert result["memory_percent"] == 1.2

    @pytest.mark.unit
    def test_get_process_status_stopped(self):
        """Test process status when stopped."""
        manager = ProcessManager()
        result = manager.get_process_status("test_process")
        
        assert result["status"] == "stopped"
        assert result["pid"] is None

    @pytest.mark.unit
    def test_list_processes(self, mock_subprocess):
        """Test listing all processes."""
        process_instance = Mock()
        process_instance.pid = 12345
        process_instance.is_running.return_value = True
        mock_subprocess.return_value = process_instance
        
        manager = ProcessManager()
        manager.start_process("process1", ["python", "test1.py"])
        manager.start_process("process2", ["python", "test2.py"])
        
        processes = manager.list_processes()
        
        assert len(processes) == 2
        assert "process1" in processes
        assert "process2" in processes

    @pytest.mark.unit
    def test_force_stop_process(self, mock_subprocess):
        """Test force stopping process."""
        process_instance = Mock()
        process_instance.pid = 12345
        process_instance.terminate.return_value = None
        process_instance.wait.return_value = 0
        mock_subprocess.return_value = process_instance
        
        manager = ProcessManager()
        manager.start_process("test_process", ["python", "test.py"])
        result = manager.force_stop_process("test_process")
        
        assert result["status"] == "force_stopped"
        process_instance.kill.assert_called_once()

    @pytest.mark.unit
    def test_cleanup_dead_processes(self, mock_subprocess):
        """Test cleanup of dead processes."""
        process_instance = Mock()
        process_instance.pid = 12345
        process_instance.is_running.return_value = False
        mock_subprocess.return_value = process_instance
        
        manager = ProcessManager()
        manager.start_process("test_process", ["python", "test.py"])
        
        # Process should be automatically removed when checked
        result = manager.is_process_running("test_process")
        assert result is False
        assert "test_process" not in manager.processes

    @pytest.mark.unit
    def test_get_process_info(self, mock_subprocess):
        """Test getting process information."""
        process_instance = Mock()
        process_instance.pid = 12345
        process_instance.cmdline.return_value = ["python", "test.py"]
        process_instance.create_time.return_value = 1640995200.0
        mock_subprocess.return_value = process_instance
        
        manager = ProcessManager()
        manager.start_process("test_process", ["python", "test.py"])
        info = manager.get_process_info("test_process")
        
        assert info["pid"] == 12345
        assert info["command"] == ["python", "test.py"]
        assert "create_time" in info

    @pytest.mark.unit
    def test_start_process_with_env(self, mock_subprocess):
        """Test starting process with environment variables."""
        process_instance = Mock()
        process_instance.pid = 12345
        mock_subprocess.return_value = process_instance
        
        manager = ProcessManager()
        env = {"DEBUG": "1", "PORT": "8000"}
        result = manager.start_process("test_process", ["python", "test.py"], env=env)
        
        assert result["status"] == "started"
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args
        assert call_args[1]["env"] == env

    @pytest.mark.unit
    def test_start_process_with_cwd(self, mock_subprocess):
        """Test starting process with working directory."""
        process_instance = Mock()
        process_instance.pid = 12345
        mock_subprocess.return_value = process_instance
        
        manager = ProcessManager()
        result = manager.start_process("test_process", ["python", "test.py"], cwd="/tmp")
        
        assert result["status"] == "started"
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args
        assert call_args[1]["cwd"] == "/tmp"

    @pytest.mark.unit
    def test_start_process_with_stdout_redirect(self, mock_subprocess):
        """Test starting process with stdout redirection."""
        process_instance = Mock()
        process_instance.pid = 12345
        mock_subprocess.return_value = process_instance
        
        with patch('builtins.open', mock_open()) as mock_file:
            manager = ProcessManager()
            result = manager.start_process(
                "test_process", 
                ["python", "test.py"], 
                stdout_file="/tmp/output.log"
            )
            
            assert result["status"] == "started"
            mock_subprocess.assert_called_once()
            call_args = mock_subprocess.call_args
            assert call_args[1]["stdout"] is not None

    @pytest.mark.unit
    def test_start_process_with_stderr_redirect(self, mock_subprocess):
        """Test starting process with stderr redirection."""
        process_instance = Mock()
        process_instance.pid = 12345
        mock_subprocess.return_value = process_instance
        
        with patch('builtins.open', mock_open()) as mock_file:
            manager = ProcessManager()
            result = manager.start_process(
                "test_process", 
                ["python", "test.py"], 
                stderr_file="/tmp/error.log"
            )
            
            assert result["status"] == "started"
            mock_subprocess.assert_called_once()
            call_args = mock_subprocess.call_args
            assert call_args[1]["stderr"] is not None

    @pytest.mark.unit
    def test_get_process_logs(self, mock_subprocess):
        """Test getting process logs."""
        process_instance = Mock()
        process_instance.pid = 12345
        mock_subprocess.return_value = process_instance
        
        with patch('pathlib.Path.read_text') as mock_read:
            mock_read.return_value = "Process log content"
            
            manager = ProcessManager()
            manager.start_process("test_process", ["python", "test.py"], stdout_file="/tmp/output.log")
            logs = manager.get_process_logs("test_process")
            
            assert logs["stdout"] == "Process log content"
            mock_read.assert_called_once()

    @pytest.mark.unit
    def test_get_process_logs_file_not_found(self, mock_subprocess):
        """Test getting process logs when log file doesn't exist."""
        process_instance = Mock()
        process_instance.pid = 12345
        mock_subprocess.return_value = process_instance
        
        with patch('pathlib.Path.read_text', side_effect=FileNotFoundError):
            manager = ProcessManager()
            manager.start_process("test_process", ["python", "test.py"], stdout_file="/tmp/output.log")
            logs = manager.get_process_logs("test_process")
            
            assert logs["stdout"] == "No logs available" 