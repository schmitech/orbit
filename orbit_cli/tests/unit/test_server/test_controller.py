"""
Unit tests for server controller.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from orbit_cli.server.controller import ServerController
from orbit_cli.core.exceptions import ServerError


class TestServerController:
    """Test cases for ServerController class."""

    @pytest.mark.unit
    def test_init(self, mock_config_manager):
        """Test ServerController initialization."""
        controller = ServerController(mock_config_manager)
        assert controller.config_manager == mock_config_manager

    @pytest.mark.unit
    def test_start_server_success(self, mock_config_manager, mock_subprocess):
        """Test successful server start."""
        process_instance = Mock()
        process_instance.pid = 12345
        mock_subprocess.return_value = process_instance
        
        with patch('orbit_cli.server.controller.ServerController._get_server_command') as mock_cmd:
            mock_cmd.return_value = ["python", "-m", "orbit.server"]
            
            controller = ServerController(mock_config_manager)
            result = controller.start_server()
            
            assert result["status"] == "started"
            assert result["pid"] == 12345
            mock_subprocess.assert_called_once()

    @pytest.mark.unit
    def test_start_server_already_running(self, mock_config_manager):
        """Test server start when already running."""
        with patch('orbit_cli.server.controller.ServerController.is_running', return_value=True):
            controller = ServerController(mock_config_manager)
            
            with pytest.raises(ServerError, match="Server is already running"):
                controller.start_server()

    @pytest.mark.unit
    def test_stop_server_success(self, mock_config_manager, mock_server_process):
        """Test successful server stop."""
        with patch('orbit_cli.server.controller.ServerController._get_process') as mock_get:
            mock_get.return_value = mock_server_process
            
            controller = ServerController(mock_config_manager)
            result = controller.stop_server()
            
            assert result["status"] == "stopped"
            mock_server_process.terminate.assert_called_once()
            mock_server_process.wait.assert_called_once()

    @pytest.mark.unit
    def test_stop_server_not_running(self, mock_config_manager):
        """Test server stop when not running."""
        with patch('orbit_cli.server.controller.ServerController.is_running', return_value=False):
            controller = ServerController(mock_config_manager)
            
            with pytest.raises(ServerError, match="Server is not running"):
                controller.stop_server()

    @pytest.mark.unit
    def test_restart_server_success(self, mock_config_manager, mock_subprocess, mock_server_process):
        """Test successful server restart."""
        process_instance = Mock()
        process_instance.pid = 12345
        mock_subprocess.return_value = process_instance
        
        with patch('orbit_cli.server.controller.ServerController._get_process') as mock_get, \
             patch('orbit_cli.server.controller.ServerController._get_server_command') as mock_cmd:
            mock_get.return_value = mock_server_process
            mock_cmd.return_value = ["python", "-m", "orbit.server"]
            
            controller = ServerController(mock_config_manager)
            result = controller.restart_server()
            
            assert result["status"] == "restarted"
            assert result["pid"] == 12345
            mock_server_process.terminate.assert_called_once()

    @pytest.mark.unit
    def test_is_running_true(self, mock_config_manager, mock_psutil_process):
        """Test server running status when running."""
        with patch('psutil.process_iter') as mock_iter:
            mock_iter.return_value = [mock_psutil_process]
            
            controller = ServerController(mock_config_manager)
            result = controller.is_running()
            
            assert result is True

    @pytest.mark.unit
    def test_is_running_false(self, mock_config_manager):
        """Test server running status when not running."""
        with patch('psutil.process_iter') as mock_iter:
            mock_iter.return_value = []
            
            controller = ServerController(mock_config_manager)
            result = controller.is_running()
            
            assert result is False

    @pytest.mark.unit
    def test_get_status_running(self, mock_config_manager, mock_psutil_process):
        """Test server status when running."""
        with patch('psutil.process_iter') as mock_iter:
            mock_iter.return_value = [mock_psutil_process]
            
            controller = ServerController(mock_config_manager)
            result = controller.get_status()
            
            assert result["status"] == "running"
            assert result["pid"] == 12345
            assert result["cpu_percent"] == 2.5
            assert result["memory_percent"] == 1.2

    @pytest.mark.unit
    def test_get_status_stopped(self, mock_config_manager):
        """Test server status when stopped."""
        with patch('psutil.process_iter') as mock_iter:
            mock_iter.return_value = []
            
            controller = ServerController(mock_config_manager)
            result = controller.get_status()
            
            assert result["status"] == "stopped"
            assert result["pid"] is None

    @pytest.mark.unit
    def test_get_logs_success(self, mock_config_manager):
        """Test successful log retrieval."""
        with patch('pathlib.Path.read_text') as mock_read:
            mock_read.return_value = "Server log content"
            
            controller = ServerController(mock_config_manager)
            result = controller.get_logs()
            
            assert result["logs"] == "Server log content"
            mock_read.assert_called_once()

    @pytest.mark.unit
    def test_get_logs_file_not_found(self, mock_config_manager):
        """Test log retrieval when log file doesn't exist."""
        with patch('pathlib.Path.read_text', side_effect=FileNotFoundError):
            controller = ServerController(mock_config_manager)
            result = controller.get_logs()
            
            assert result["logs"] == "No logs available"

    @pytest.mark.unit
    def test_get_server_command(self, mock_config_manager):
        """Test server command generation."""
        mock_config_manager.get.side_effect = lambda key, default=None: {
            "server.host": "localhost",
            "server.port": 8000,
            "server.debug": False
        }.get(key, default)
        
        controller = ServerController(mock_config_manager)
        command = controller._get_server_command()
        
        assert "python" in command
        assert "-m" in command
        assert "orbit.server" in command

    @pytest.mark.unit
    def test_get_server_command_with_debug(self, mock_config_manager):
        """Test server command generation with debug mode."""
        mock_config_manager.get.side_effect = lambda key, default=None: {
            "server.host": "localhost",
            "server.port": 8000,
            "server.debug": True
        }.get(key, default)
        
        controller = ServerController(mock_config_manager)
        command = controller._get_server_command()
        
        assert "--debug" in command

    @pytest.mark.unit
    def test_get_process_success(self, mock_config_manager, mock_psutil_process):
        """Test successful process retrieval."""
        with patch('psutil.process_iter') as mock_iter:
            mock_iter.return_value = [mock_psutil_process]
            
            controller = ServerController(mock_config_manager)
            process = controller._get_process()
            
            assert process == mock_psutil_process

    @pytest.mark.unit
    def test_get_process_not_found(self, mock_config_manager):
        """Test process retrieval when not found."""
        with patch('psutil.process_iter') as mock_iter:
            mock_iter.return_value = []
            
            controller = ServerController(mock_config_manager)
            
            with pytest.raises(ServerError, match="Server process not found"):
                controller._get_process()

    @pytest.mark.unit
    def test_force_stop_server(self, mock_config_manager, mock_server_process):
        """Test force stopping server."""
        with patch('orbit_cli.server.controller.ServerController._get_process') as mock_get:
            mock_get.return_value = mock_server_process
            
            controller = ServerController(mock_config_manager)
            result = controller.force_stop_server()
            
            assert result["status"] == "force_stopped"
            mock_server_process.kill.assert_called_once()

    @pytest.mark.unit
    def test_get_server_info(self, mock_config_manager):
        """Test server information retrieval."""
        mock_config_manager.get.side_effect = lambda key, default=None: {
            "server.host": "localhost",
            "server.port": 8000,
            "server.debug": False
        }.get(key, default)
        
        controller = ServerController(mock_config_manager)
        info = controller.get_server_info()
        
        assert info["host"] == "localhost"
        assert info["port"] == 8000
        assert info["debug"] is False

    @pytest.mark.unit
    def test_validate_server_config(self, mock_config_manager):
        """Test server configuration validation."""
        controller = ServerController(mock_config_manager)
        
        # Should not raise an exception
        controller.validate_server_config()

    @pytest.mark.unit
    def test_validate_server_config_invalid(self, temp_config_dir):
        """Test server configuration validation with invalid config."""
        with patch('orbit_cli.config.manager.ConfigManager._get_config_path') as mock_path:
            mock_path.return_value = temp_config_dir / "config.yaml"
            
            controller = ServerController(Mock())
            controller.config_manager._config = {"invalid": "config"}
            
            with pytest.raises(ServerError, match="Invalid server configuration"):
                controller.validate_server_config() 