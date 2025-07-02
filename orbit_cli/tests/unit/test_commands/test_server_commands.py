"""Unit tests for server commands."""

import pytest
import argparse
from unittest.mock import Mock, patch, MagicMock

from orbit_cli.commands.server import (
    StartCommand,
    StopCommand,
    RestartCommand,
    StatusCommand,
    LogsCommand
)
from orbit_cli.server import HealthChecker, ServerMonitor, StartupValidator


class TestStartCommand:
    """Test cases for StartCommand."""
    
    def test_command_metadata(self):
        """Test command metadata."""
        assert StartCommand.name == "start"
        assert "Start" in StartCommand.help
        assert "Start" in StartCommand.description
    
    def test_add_arguments(self):
        """Test argument configuration."""
        cmd = StartCommand()
        parser = argparse.ArgumentParser()
        cmd.add_arguments(parser)
        
        # Parse test arguments
        args = parser.parse_args([
            '--config', 'test.yaml',
            '--host', '0.0.0.0',
            '--port', '8080',
            '--reload',
            '--delete-logs',
            '--validate',
            '--wait-healthy',
            '--timeout', '60'
        ])
        
        assert args.config == 'test.yaml'
        assert args.host == '0.0.0.0'
        assert args.port == 8080
        assert args.reload is True
        assert args.delete_logs is True
        assert args.validate is True
        assert args.wait_healthy is True
        assert args.timeout == 60
    
    def test_execute_success(self, mock_server_controller, mock_formatter):
        """Test successful server start."""
        cmd = StartCommand(
            server_controller=mock_server_controller,
            formatter=mock_formatter
        )
        
        args = argparse.Namespace(
            config=None,
            host=None,
            port=None,
            reload=False,
            delete_logs=False,
            validate=False,
            wait_healthy=False,
            timeout=30
        )
        
        exit_code = cmd.execute(args)
        
        assert exit_code == 0
        mock_server_controller.start.assert_called_once_with(
            config_path=None,
            host=None,
            port=None,
            reload=False,
            delete_logs=False
        )
        mock_formatter.success.assert_called()
    
    def test_execute_with_validation(self, mock_server_controller, mock_formatter):
        """Test server start with validation."""
        cmd = StartCommand(
            server_controller=mock_server_controller,
            formatter=mock_formatter
        )
        
        args = argparse.Namespace(
            config=None,
            host=None,
            port=3000,
            reload=False,
            delete_logs=False,
            validate=True,
            wait_healthy=False,
            timeout=30
        )
        
        with patch.object(StartupValidator, 'validate_startup_conditions') as mock_validate:
            mock_validate.return_value = {
                'valid': True,
                'port_available': True,
                'dependencies': {'uvicorn': True, 'fastapi': True}
            }
            
            exit_code = cmd.execute(args)
            
            assert exit_code == 0
            mock_validate.assert_called_once_with(3000, None)
    
    def test_execute_validation_failed(self, mock_server_controller, mock_formatter):
        """Test server start with failed validation."""
        cmd = StartCommand(
            server_controller=mock_server_controller,
            formatter=mock_formatter
        )
        
        args = argparse.Namespace(
            config=None,
            host=None,
            port=3000,
            reload=False,
            delete_logs=False,
            validate=True,
            wait_healthy=False,
            timeout=30
        )
        
        with patch.object(StartupValidator, 'validate_startup_conditions') as mock_validate:
            mock_validate.return_value = {
                'valid': False,
                'port_available': False,
                'dependencies': {'uvicorn': True, 'fastapi': True}
            }
            
            exit_code = cmd.execute(args)
            
            assert exit_code == 1
            mock_formatter.error.assert_called()
            mock_server_controller.start.assert_not_called()
    
    @patch('orbit_cli.commands.server.HealthChecker')
    def test_execute_wait_healthy(self, mock_health_checker_class, mock_server_controller, mock_formatter):
        """Test server start with health check wait."""
        mock_health_checker = Mock()
        mock_health_checker.wait_for_healthy.return_value = True
        mock_health_checker_class.return_value = mock_health_checker
        
        cmd = StartCommand(
            server_controller=mock_server_controller,
            formatter=mock_formatter
        )
        
        args = argparse.Namespace(
            config=None,
            host='localhost',
            port=3000,
            reload=False,
            delete_logs=False,
            validate=False,
            wait_healthy=True,
            timeout=30
        )
        
        exit_code = cmd.execute(args)
        
        assert exit_code == 0
        mock_health_checker.wait_for_healthy.assert_called_once()
        mock_formatter.success.assert_called()
    
    def test_execute_no_controller(self, mock_formatter):
        """Test execution without server controller."""
        cmd = StartCommand(
            server_controller=None,
            formatter=mock_formatter
        )
        
        args = argparse.Namespace(
            config=None,
            host=None,
            port=None,
            reload=False,
            delete_logs=False,
            validate=False,
            wait_healthy=False,
            timeout=30
        )
        
        exit_code = cmd.execute(args)
        
        assert exit_code == 1
        mock_formatter.error.assert_called_with("Server controller not initialized")


class TestStopCommand:
    """Test cases for StopCommand."""
    
    def test_add_arguments(self):
        """Test argument configuration."""
        cmd = StopCommand()
        parser = argparse.ArgumentParser()
        cmd.add_arguments(parser)
        
        args = parser.parse_args([
            '--timeout', '60',
            '--delete-logs',
            '--force'
        ])
        
        assert args.timeout == 60
        assert args.delete_logs is True
        assert args.force is True
    
    def test_execute_success(self, mock_server_controller, mock_formatter):
        """Test successful server stop."""
        cmd = StopCommand(
            server_controller=mock_server_controller,
            formatter=mock_formatter
        )
        
        args = argparse.Namespace(
            timeout=30,
            delete_logs=False,
            force=False
        )
        
        exit_code = cmd.execute(args)
        
        assert exit_code == 0
        mock_server_controller.stop.assert_called_once_with(
            timeout=30,
            delete_logs=False,
            force=False
        )
    
    def test_execute_force_stop(self, mock_server_controller, mock_formatter):
        """Test force stop."""
        cmd = StopCommand(
            server_controller=mock_server_controller,
            formatter=mock_formatter
        )
        
        args = argparse.Namespace(
            timeout=30,
            delete_logs=False,
            force=True
        )
        
        exit_code = cmd.execute(args)
        
        assert exit_code == 0
        mock_server_controller.stop.assert_called_once_with(
            timeout=1,  # Force uses timeout=1
            delete_logs=False,
            force=True
        )
    
    def test_execute_failed(self, mock_server_controller, mock_formatter):
        """Test failed server stop."""
        mock_server_controller.stop.return_value = False
        
        cmd = StopCommand(
            server_controller=mock_server_controller,
            formatter=mock_formatter
        )
        
        args = argparse.Namespace(
            timeout=30,
            delete_logs=False,
            force=False
        )
        
        exit_code = cmd.execute(args)
        
        assert exit_code == 1


class TestRestartCommand:
    """Test cases for RestartCommand."""
    
    def test_execute_success(self, mock_server_controller, mock_formatter):
        """Test successful server restart."""
        cmd = RestartCommand(
            server_controller=mock_server_controller,
            formatter=mock_formatter
        )
        
        args = argparse.Namespace(
            config='test.yaml',
            host='0.0.0.0',
            port=8080,
            delete_logs=True,
            delay=2.0
        )
        
        exit_code = cmd.execute(args)
        
        assert exit_code == 0
        mock_server_controller.restart.assert_called_once_with(
            config_path='test.yaml',
            host='0.0.0.0',
            port=8080,
            delete_logs=True,
            restart_delay=2.0
        )


class TestStatusCommand:
    """Test cases for StatusCommand."""
    
    def test_execute_one_time_status(self, mock_server_controller, mock_formatter):
        """Test one-time status check."""
        cmd = StatusCommand(
            server_controller=mock_server_controller,
            formatter=mock_formatter
        )
        
        args = argparse.Namespace(
            watch=False,
            interval=5,
            detailed=False,
            health=False,
            output='table',
            no_color=False
        )
        
        exit_code = cmd.execute(args)
        
        assert exit_code == 0
        mock_server_controller.status.assert_called_once_with(detailed=False)
    
    @patch('orbit_cli.commands.server.ServerMonitor')
    def test_execute_watch_mode(self, mock_monitor_class, mock_server_controller, mock_formatter):
        """Test watch mode."""
        mock_monitor = Mock()
        mock_monitor_class.return_value = mock_monitor
        
        # Simulate KeyboardInterrupt to stop watching
        mock_monitor.start.side_effect = KeyboardInterrupt()
        
        cmd = StatusCommand(
            server_controller=mock_server_controller,
            formatter=mock_formatter
        )
        
        args = argparse.Namespace(
            watch=True,
            interval=2,
            detailed=False,
            health=False,
            output='table',
            no_color=False
        )
        
        exit_code = cmd.execute(args)
        
        assert exit_code == 0
        mock_monitor_class.assert_called_once_with(mock_server_controller, interval=2)
        mock_monitor.start.assert_called_once()
    
    @patch('orbit_cli.commands.server.HealthChecker')
    def test_execute_with_health_check(self, mock_health_checker_class, mock_server_controller, mock_formatter):
        """Test status with health check."""
        mock_health_checker = Mock()
        mock_health_checker.check_health.return_value = {
            'status': 'healthy',
            'response_time_ms': 50
        }
        mock_health_checker_class.return_value = mock_health_checker
        
        cmd = StatusCommand(
            server_controller=mock_server_controller,
            formatter=mock_formatter
        )
        
        args = argparse.Namespace(
            watch=False,
            interval=5,
            detailed=True,
            health=True,
            output='table',
            no_color=False,
            server_url='http://localhost:3000'
        )
        
        exit_code = cmd.execute(args)
        
        assert exit_code == 0
        mock_server_controller.status.assert_called_once_with(detailed=True)
        mock_health_checker.check_health.assert_called_once()
    
    def test_execute_json_output(self, mock_server_controller, mock_formatter):
        """Test JSON output format."""
        mock_formatter.format = 'json'
        
        cmd = StatusCommand(
            server_controller=mock_server_controller,
            formatter=mock_formatter
        )
        
        args = argparse.Namespace(
            watch=False,
            interval=5,
            detailed=False,
            health=False,
            output='json',
            no_color=False
        )
        
        exit_code = cmd.execute(args)
        
        assert exit_code == 0
        mock_formatter.format_json.assert_called_once()
    
    def test_display_status_running(self, mock_formatter):
        """Test status display for running server."""
        cmd = StatusCommand(formatter=mock_formatter)
        
        status = {
            'status': 'running',
            'message': 'Server is running',
            'pid': 12345,
            'uptime': '2h 30m',
            'memory_mb': 256.5,
            'memory_percent': 12.5,
            'cpu_percent': 2.5,
            'num_threads': 4,
            'io_read_mb': 100,
            'io_write_mb': 50,
            'health': {
                'status': 'healthy',
                'response_time_ms': 50
            }
        }
        
        cmd._display_status(status)
        
        mock_formatter.success.assert_called()
        # Should display all metrics
        assert mock_formatter.print.call_count >= 6
    
    def test_display_status_stopped(self, mock_formatter):
        """Test status display for stopped server."""
        cmd = StatusCommand(formatter=mock_formatter)
        
        status = {
            'status': 'stopped',
            'message': 'Server is not running'
        }
        
        cmd._display_status(status)
        
        mock_formatter.warning.assert_called_once()


class TestLogsCommand:
    """Test cases for LogsCommand."""
    
    def test_add_arguments(self):
        """Test argument configuration."""
        cmd = LogsCommand()
        parser = argparse.ArgumentParser()
        cmd.add_arguments(parser)
        
        args = parser.parse_args(['-n', '100', '-f'])
        
        assert args.lines == 100
        assert args.follow is True
    
    def test_execute_show_logs(self, mock_server_controller, mock_formatter):
        """Test showing logs."""
        cmd = LogsCommand(
            server_controller=mock_server_controller,
            formatter=mock_formatter
        )
        
        args = argparse.Namespace(
            lines=50,
            follow=False
        )
        
        exit_code = cmd.execute(args)
        
        assert exit_code == 0
        mock_server_controller.get_logs.assert_called_once_with(
            lines=50,
            follow=False
        )
    
    def test_execute_follow_logs(self, mock_server_controller, mock_formatter):
        """Test following logs."""
        cmd = LogsCommand(
            server_controller=mock_server_controller,
            formatter=mock_formatter
        )
        
        args = argparse.Namespace(
            lines=None,
            follow=True
        )
        
        exit_code = cmd.execute(args)
        
        assert exit_code == 0
        mock_server_controller.get_logs.assert_called_once_with(
            lines=None,
            follow=True
        )