"""Server controller for managing the ORBIT server process."""

import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
import psutil

from ..core.exceptions import ServerError
from ..core.constants import DEFAULT_PID_FILE, DEFAULT_SERVER_LOG_FILE
from ..output.formatter import OutputFormatter
from ..utils.logging import get_logger
from .process_manager import ProcessManager
from .status import ServerStatus, ServerMetrics

logger = get_logger(__name__)


class ServerController:
    """Controller class for managing the Open Inference Server process."""
    
    def __init__(
        self,
        project_root: Optional[Path] = None,
        pid_file: str = DEFAULT_PID_FILE,
        log_file: str = DEFAULT_SERVER_LOG_FILE,
        formatter: Optional[OutputFormatter] = None
    ):
        """
        Initialize the server controller.
        
        Args:
            project_root: Root directory of the project (auto-detected if not provided)
            pid_file: Name of the PID file for tracking the server process
            log_file: Name of the log file for server output
            formatter: Output formatter instance
        """
        # Auto-detect project root if not provided
        if project_root is None:
            # Assuming this module is in orbit_cli/server/controller.py
            module_path = Path(__file__)
            # Go up to orbit_cli, then to project root
            project_root = module_path.parent.parent.parent
        
        self.project_root = Path(project_root)
        self.pid_file = self.project_root / pid_file
        self.log_file = self.project_root / "logs" / log_file
        self.formatter = formatter or OutputFormatter()
        
        # Initialize process manager
        self.process_manager = ProcessManager(self.pid_file)
        
        # Server status tracker
        self.status_tracker = ServerStatus()
    
    def start(
        self,
        config_path: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        reload: bool = False,
        delete_logs: bool = False,
        env_vars: Optional[Dict[str, str]] = None,
        additional_args: Optional[List[str]] = None
    ) -> bool:
        """
        Start the server if it's not already running.
        
        Args:
            config_path: Optional path to the configuration file
            host: Optional host to bind to
            port: Optional port to bind to
            reload: Whether to enable auto-reload for development
            delete_logs: Whether to delete the logs folder before starting
            env_vars: Additional environment variables
            additional_args: Additional command line arguments
            
        Returns:
            True if the server was started successfully, False otherwise
        """
        # Check if server is already running
        if self.process_manager.is_running():
            pid = self.process_manager.get_pid()
            self.formatter.warning(f"Server is already running with PID {pid}")
            return False
        
        # Clean up stale PID file
        self.process_manager.cleanup()
        
        # Delete logs if requested
        if delete_logs:
            self._delete_logs()
        
        # Prepare and start the server
        try:
            # Ensure logs directory exists
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            self.log_file.parent.chmod(0o700)
            
            # Build command and environment
            cmd, env = self._build_start_command(
                config_path, host, port, reload, env_vars, additional_args
            )
            
            # Start the server
            logger.debug(f"Starting server with command: {' '.join(cmd)}")
            process = self._start_server_process(cmd, env, reload)
            
            # Verify the server started successfully
            if self._verify_server_started(process.pid):
                self.formatter.success(f"Server started successfully with PID {process.pid}")
                self.formatter.info(f"Logs are being written to {self.log_file}")
                return True
            else:
                self.formatter.error("Server failed to start. Check the logs for details.")
                self.process_manager.cleanup()
                return False
                
        except Exception as e:
            self.formatter.error(f"Error starting server: {e}")
            logger.error(f"Server start failed: {e}", exc_info=True)
            self.process_manager.cleanup()
            return False
    
    def stop(self, timeout: int = 30, delete_logs: bool = False, force: bool = False) -> bool:
        """
        Stop the server if it's running.
        
        Args:
            timeout: Maximum time to wait for graceful shutdown (seconds)
            delete_logs: Whether to delete the logs folder after stopping
            force: Whether to force kill without graceful shutdown
            
        Returns:
            True if the server was stopped successfully, False otherwise
        """
        if not self.process_manager.is_running():
            self.formatter.info("Server is not running")
            self.process_manager.cleanup()
            return True
        
        pid = self.process_manager.get_pid()
        
        # Use force timeout if force flag is set
        if force:
            timeout = 1
        
        # Stop the process
        success = self.process_manager.stop_process(timeout, force)
        
        if success:
            self.formatter.success("Server stopped successfully")
            if delete_logs:
                self._delete_logs()
            return True
        else:
            self.formatter.error("Failed to stop server")
            return False
    
    def restart(
        self,
        config_path: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        delete_logs: bool = False,
        restart_delay: float = 2.0
    ) -> bool:
        """
        Restart the server.
        
        Args:
            config_path: Optional path to the configuration file
            host: Optional host to bind to
            port: Optional port to bind to
            delete_logs: Whether to delete the logs folder during restart
            restart_delay: Delay in seconds between stop and start
            
        Returns:
            True if the server was restarted successfully, False otherwise
        """
        self.formatter.info("Restarting server...")
        
        # Stop the server if it's running
        if self.process_manager.is_running():
            if not self.stop(delete_logs=delete_logs):
                self.formatter.error("Failed to stop server for restart")
                return False
            
            # Wait before starting again
            time.sleep(restart_delay)
        
        # Start the server with new configuration
        return self.start(
            config_path=config_path,
            host=host,
            port=port,
            delete_logs=delete_logs
        )
    
    def status(self, detailed: bool = False) -> Dict[str, Any]:
        """
        Get the status of the server.
        
        Args:
            detailed: Whether to include detailed metrics
            
        Returns:
            A dictionary containing status information
        """
        if not self.process_manager.is_running():
            return self.status_tracker.get_stopped_status()
        
        pid = self.process_manager.get_pid()
        
        try:
            process = psutil.Process(pid)
            
            if detailed:
                metrics = ServerMetrics.collect_detailed(process)
                return self.status_tracker.get_running_status(pid, metrics)
            else:
                metrics = ServerMetrics.collect_basic(process)
                return self.status_tracker.get_running_status(pid, metrics)
                
        except Exception as e:
            return self.status_tracker.get_error_status(pid, str(e))
    
    def get_logs(self, lines: Optional[int] = None, follow: bool = False) -> None:
        """
        Display server logs.
        
        Args:
            lines: Number of lines to show (None = all)
            follow: Whether to follow the log file (like tail -f)
        """
        if not self.log_file.exists():
            self.formatter.warning("No log file found")
            return
        
        if follow:
            self._follow_logs()
        else:
            self._show_logs(lines)
    
    def _build_start_command(
        self,
        config_path: Optional[str],
        host: Optional[str],
        port: Optional[int],
        reload: bool,
        env_vars: Optional[Dict[str, str]],
        additional_args: Optional[List[str]]
    ) -> tuple[List[str], Dict[str, str]]:
        """Build the command and environment for starting the server."""
        # Change to project root
        os.chdir(self.project_root)
        
        # Base command
        cmd = ["python", "server/main.py"]
        
        # Add config path if provided
        if config_path:
            if not os.path.isabs(config_path):
                config_path = str(self.project_root / config_path)
            cmd.extend(["--config", config_path])
        else:
            # Try to find config file
            config_file = self._find_config_file()
            if config_file:
                cmd.extend(["--config", str(config_file)])
        
        # Set up environment
        env = os.environ.copy()
        if host:
            env["OIS_HOST"] = host
        if port:
            env["OIS_PORT"] = str(port)
        if env_vars:
            env.update(env_vars)
        
        # Handle reload mode
        if reload:
            # Use uvicorn directly for reload
            cmd = ["uvicorn", "server:app", "--reload"]
            if host:
                cmd.extend(["--host", host])
            if port:
                cmd.extend(["--port", str(port)])
            # Change to server directory for reload mode
            os.chdir(self.project_root / "server")
        
        # Add any additional arguments
        if additional_args:
            cmd.extend(additional_args)
        
        return cmd, env
    
    def _start_server_process(
        self,
        cmd: List[str],
        env: Dict[str, str],
        reload: bool
    ) -> subprocess.Popen:
        """Start the server process."""
        with open(self.log_file, 'a') as log:
            if reload:
                # For reload mode, run in foreground
                process = subprocess.Popen(
                    cmd,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env=env
                )
            else:
                # For production mode, run in background
                process = subprocess.Popen(
                    cmd,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env=env,
                    start_new_session=True  # Detach from current session
                )
            
            # Save the PID
            self.process_manager.save_pid(process.pid)
            
            return process
    
    def _verify_server_started(self, pid: int, wait_time: float = 2.0) -> bool:
        """Verify that the server process started successfully."""
        time.sleep(wait_time)
        return self.process_manager.is_process_running(pid)
    
    def _find_config_file(self) -> Optional[Path]:
        """Find configuration file in common locations."""
        possible_configs = [
            self.project_root / "server" / "config.yaml",
            self.project_root / "config.yaml",
            self.project_root / "config" / "config.yaml"
        ]
        
        for config in possible_configs:
            if config.exists():
                logger.debug(f"Using config file: {config}")
                return config
        
        return None
    
    def _delete_logs(self) -> None:
        """Delete the logs folder."""
        if self.log_file.parent.exists():
            import shutil
            try:
                shutil.rmtree(self.log_file.parent)
                self.formatter.info("Logs folder deleted")
            except Exception as e:
                logger.warning(f"Failed to delete logs: {e}")
    
    def _show_logs(self, lines: Optional[int]) -> None:
        """Display log file contents."""
        try:
            with open(self.log_file, 'r') as f:
                if lines:
                    # Read last N lines
                    all_lines = f.readlines()
                    for line in all_lines[-lines:]:
                        print(line.rstrip())
                else:
                    # Read all
                    print(f.read())
        except Exception as e:
            self.formatter.error(f"Error reading logs: {e}")
    
    def _follow_logs(self) -> None:
        """Follow log file (like tail -f)."""
        try:
            import time
            with open(self.log_file, 'r') as f:
                # Go to end of file
                f.seek(0, 2)
                
                while True:
                    line = f.readline()
                    if line:
                        print(line.rstrip())
                    else:
                        time.sleep(0.1)
        except KeyboardInterrupt:
            self.formatter.info("\nStopped following logs")
        except Exception as e:
            self.formatter.error(f"Error following logs: {e}")