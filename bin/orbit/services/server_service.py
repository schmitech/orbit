"""
Server process management service.

This service manages the ORBIT server process using HTTP-based communication
instead of PID files. It uses the server's API endpoints for graceful shutdown
and status checking.
"""

import os
import signal
import subprocess
import time
import logging
import shutil
import yaml
from pathlib import Path
from typing import Any, Dict, Optional
import psutil
import requests
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.console import Console

from bin.orbit.services.api_client import ApiClient
from bin.orbit.services.auth_service import AuthService
from bin.orbit.utils.exceptions import ServerError, NetworkError
from bin.orbit.utils.output import OutputFormatter

logger = logging.getLogger(__name__)
console = Console()


class ServerService:
    """
    Service for managing the ORBIT server process.
    
    Uses HTTP-based communication instead of PID files:
    - Checks server status via /health endpoint
    - Gets server info (PID) via /admin/info endpoint
    - Stops server via /admin/shutdown endpoint
    - Falls back to signal-based shutdown if HTTP unavailable
    """
    
    def __init__(
        self,
        api_client: ApiClient,
        auth_service: AuthService,
        project_root: Optional[Path] = None,
        formatter: Optional[OutputFormatter] = None
    ):
        """
        Initialize the server service.
        
        Args:
            api_client: API client for HTTP communication
            auth_service: Auth service for authentication
            project_root: Root directory of the project (auto-detected if None)
            formatter: Output formatter for messages
        """
        self.api_client = api_client
        self.auth_service = auth_service
        self.formatter = formatter or OutputFormatter()
        
        # Auto-detect project root
        if project_root is None:
            # Get the directory where this script is located and find project root
            # __file__ is bin/orbit/services/server_service.py
            # We need to go up 4 levels: services -> orbit -> bin -> project root
            script_dir = Path(__file__).parent.parent.parent.parent
            self.project_root = script_dir
        else:
            self.project_root = project_root
        
        self.log_file = self.project_root / "logs" / "orbit.log"
        self._cpu_initialized = False
    
    def is_running(self) -> bool:
        """
        Check if the server is running by attempting HTTP health check.
        
        Returns:
            True if server is responding, False otherwise
        """
        try:
            response = self.api_client.get("/health", retry=False)
            return response.status_code == 200
        except (NetworkError, requests.exceptions.RequestException):
            return False
    
    def get_server_info(self) -> Optional[Dict[str, Any]]:
        """
        Get server information including PID via /admin/info endpoint.
        
        Returns:
            Dictionary with server info (pid, version, status) or None if unavailable
        """
        try:
            self.auth_service.ensure_authenticated()
            headers = {"Authorization": f"Bearer {self.auth_service.token}"}
            response = self.api_client.get("/admin/info", headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.debug(f"Failed to get server info via API: {e}")
            return None
    
    def start(
        self,
        config_path: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        reload: bool = False,
        delete_logs: bool = False
    ) -> bool:
        """
        Start the server if it's not already running.
        
        Args:
            config_path: Optional path to the configuration file
            host: Optional host to bind to
            port: Optional port to bind to
            reload: Whether to enable auto-reload for development
            delete_logs: Whether to delete the logs folder before starting
            
        Returns:
            True if the server was started successfully, False otherwise
        """
        # Update API client URL based on config or provided port
        # This ensures we check the correct port when determining if server is running
        config_port = port if port else self._get_port_from_config(config_path)
        if config_port:
            self._update_api_client_url(config_port)
        
        # Check if server is already running via HTTP
        if self.is_running():
            info = self.get_server_info()
            if info:
                pid = info.get('pid', 'unknown')
                self.formatter.warning(f"Server is already running with PID {pid}")
            else:
                self.formatter.warning("Server is already running")
            return False
        
        # Delete logs if requested
        if delete_logs and self.log_file.parent.exists():
            try:
                shutil.rmtree(self.log_file.parent)
                self.formatter.info("Logs folder deleted")
            except Exception as e:
                logger.warning(f"Failed to delete logs: {e}")
        
        # Build the command to start the server
        os.chdir(self.project_root)
        cmd = ["python", "server/main.py"]
        
        if config_path:
            # Resolve config path relative to project root
            if not os.path.isabs(config_path):
                config_path = str(self.project_root / config_path)
            cmd.extend(["--config", config_path])
        else:
            # Try to find config file in common locations
            possible_configs = [
                self.project_root / "config" / "config.yaml",
                self.project_root / "server" / "config.yaml",
                self.project_root / "config.yaml"
            ]
            for config in possible_configs:
                if config.exists():
                    cmd.extend(["--config", str(config)])
                    logger.debug(f"Using config file: {config}")
                    break
        
        # Set environment variables if host/port specified
        env = os.environ.copy()
        if host:
            env["OIS_HOST"] = host
        if port:
            env["OIS_PORT"] = str(port)
        
        # Add reload flag if requested
        if reload:
            # For reload mode, use uvicorn directly from server directory
            cmd = ["uvicorn", "server:app", "--reload"]
            if host:
                cmd.extend(["--host", host])
            if port:
                cmd.extend(["--port", str(port)])
            # Change to server directory for reload mode
            os.chdir(self.project_root / "server")
        
        logger.debug(f"Starting server with command: {' '.join(cmd)}")
        
        # Start the server process
        try:
            # Ensure logs directory exists
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            self.log_file.parent.chmod(0o700)
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True,
            ) as progress:
                task = progress.add_task("Starting server...", total=None)
                
                # Open log file for output
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
                    
                    # Wait a moment to check if the process started successfully
                    time.sleep(2)
                    
                    # Check if process crashed immediately
                    exit_code = process.poll()
                    if exit_code is not None:
                        progress.update(task, completed=True)
                        self.formatter.error(f"Server process exited immediately with code {exit_code}")
                        self.formatter.info(f"Check logs at: {self.log_file}")
                        return False
                    
                    # Wait a bit more and check if server is responding
                    # Server might need more time to fully start, especially when loading adapters
                    max_wait = 30  # Wait up to 30 seconds for server to fully initialize
                    waited = 2
                    server_responding = False
                    
                    while waited < max_wait:
                        if self.is_running():
                            server_responding = True
                            break
                        time.sleep(1)
                        waited += 1
                    
                    # If process is still running but not responding yet, give it one more check
                    # Sometimes the server needs a few extra seconds to fully initialize
                    if process.poll() is None and not server_responding:
                        # Wait a bit more and do a final check
                        time.sleep(3)
                        server_responding = self.is_running()
                    
                    # Check if process is still running and server is responding
                    if process.poll() is None and server_responding:
                        progress.update(task, completed=True)
                        info = self.get_server_info()
                        pid = info.get('pid', process.pid) if info else process.pid
                        self.formatter.success(f"Server started successfully with PID {pid}")
                        self.formatter.info(f"Logs are being written to {self.log_file}")
                        return True
                    else:
                        progress.update(task, completed=True)
                        if process.poll() is not None:
                            exit_code = process.poll()
                            self.formatter.error(f"Server process exited with code {exit_code}")
                        else:
                            # Process is running but not responding - might still be starting
                            # Check one more time after a brief wait
                            time.sleep(2)
                            if self.is_running():
                                info = self.get_server_info()
                                pid = info.get('pid', process.pid) if info else process.pid
                                self.formatter.success(f"Server started successfully with PID {pid}")
                                self.formatter.info(f"Logs are being written to {self.log_file}")
                                return True
                            else:
                                self.formatter.warning("Server process is running but not yet responding to HTTP requests")
                                self.formatter.info("The server may still be initializing. Check logs at: " + str(self.log_file))
                                self.formatter.info("You can check server status with: orbit status")
                                # Don't return False - the server is running, just not ready yet
                                return True
                        self.formatter.info(f"Check logs at: {self.log_file}")
                        return False
                        
        except Exception as e:
            self.formatter.error(f"Error starting server: {e}")
            return False
    
    def stop(self, timeout: int = 30, force: bool = False, delete_logs: bool = False) -> bool:
        """
        Stop the server if it's running.
        
        Args:
            timeout: Maximum time to wait for graceful shutdown (seconds)
            force: If True, force kill without graceful shutdown
            delete_logs: Whether to delete the logs folder after stopping
            
        Returns:
            True if the server was stopped successfully, False otherwise
        """
        # Update API client URL based on config to ensure we check the correct port
        config_port = self._get_port_from_config()
        if config_port:
            self._update_api_client_url(config_port)
        
        # Check if server is running via HTTP
        if not self.is_running():
            self.formatter.info("Server is not running")
            return True
        
        # Get server info to get PID for fallback
        info = self.get_server_info()
        pid = info.get('pid') if info else None
        
        # If we don't have PID from API, try to find it by port
        if not pid:
            pid = self._find_process_by_port()
            if pid:
                logger.debug(f"Found server process by port: PID {pid}")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            task_description = "Stopping server..." if not force else "Force stopping server..."
            task = progress.add_task(task_description, total=None)
            
            try:
                if force:
                    # Force kill immediately
                    if pid:
                        try:
                            os.kill(pid, signal.SIGKILL)
                            time.sleep(1)
                            progress.update(task, completed=True)
                            self.formatter.success("Server force stopped")
                            return True
                        except ProcessLookupError:
                            # Process already gone
                            pass
                    
                    # If we don't have PID or kill failed, try HTTP shutdown
                    # but don't wait for it
                    try:
                        self.auth_service.ensure_authenticated()
                        headers = {"Authorization": f"Bearer {self.auth_service.token}"}
                        self.api_client.post("/admin/shutdown", headers=headers, retry=False)
                    except Exception:
                        pass  # Ignore errors in force mode
                    
                    progress.update(task, completed=True)
                    self.formatter.success("Server force stopped")
                    return True
                
                # Try graceful shutdown via HTTP first
                http_shutdown_attempted = False
                try:
                    # Try to authenticate, but don't fail if not authenticated
                    try:
                        self.auth_service.ensure_authenticated()
                        headers = {"Authorization": f"Bearer {self.auth_service.token}"}
                        self.api_client.post("/admin/shutdown", headers=headers, retry=False)
                        http_shutdown_attempted = True
                        
                        # Wait for the server to stop
                        start_time = time.time()
                        while time.time() - start_time < timeout:
                            if not self.is_running():
                                progress.update(task, completed=True)
                                self.formatter.success("Server stopped successfully")
                                
                                # Delete logs if requested
                                if delete_logs and self.log_file.parent.exists():
                                    shutil.rmtree(self.log_file.parent)
                                    self.formatter.info("Logs folder deleted")
                                
                                return True
                            time.sleep(0.5)
                    except AuthenticationError:
                        # Not authenticated, will try signal-based shutdown
                        logger.debug("Not authenticated, using signal-based shutdown")
                        http_shutdown_attempted = False
                    
                    # If HTTP shutdown was attempted but timed out, or if we couldn't authenticate
                    # Try to find PID if we don't have it
                    if not pid:
                        pid = self._find_process_by_port()
                        if pid:
                            logger.debug(f"Found server process by port: PID {pid}")
                    
                    if http_shutdown_attempted:
                        # HTTP shutdown timed out, try signal-based shutdown as fallback
                        if pid:
                            self.formatter.warning(f"HTTP shutdown timed out. Trying signal-based shutdown for PID {pid}...")
                        else:
                            self.formatter.warning("HTTP shutdown timed out, but no PID available for signal-based shutdown")
                    else:
                        # HTTP shutdown not attempted (auth failed), use signal-based shutdown
                        if pid:
                            self.formatter.info(f"Using signal-based shutdown for PID {pid}...")
                        else:
                            self.formatter.warning("No PID available. Trying to find server process by port...")
                            pid = self._find_process_by_port()
                            if pid:
                                logger.debug(f"Found server process by port: PID {pid}")
                                self.formatter.info(f"Found server process (PID {pid}), attempting signal-based shutdown...")
                    
                    # Try signal-based shutdown
                    if pid:
                        try:
                            os.kill(pid, signal.SIGTERM)
                            
                            # Wait a bit more
                            start_time = time.time()
                            while time.time() - start_time < 10:  # 10 second timeout for signal
                                if not self.is_running():
                                    progress.update(task, completed=True)
                                    self.formatter.success("Server stopped successfully")
                                    
                                    # Delete logs if requested
                                    if delete_logs and self.log_file.parent.exists():
                                        shutil.rmtree(self.log_file.parent)
                                        self.formatter.info("Logs folder deleted")
                                    
                                    return True
                                time.sleep(0.5)
                            
                            # Force kill if still running
                            self.formatter.warning("Server did not stop gracefully. Force killing...")
                            os.kill(pid, signal.SIGKILL)
                            time.sleep(1)
                            
                            if not self.is_running():
                                progress.update(task, completed=True)
                                self.formatter.success("Server force stopped")
                                
                                # Delete logs if requested
                                if delete_logs and self.log_file.parent.exists():
                                    shutil.rmtree(self.log_file.parent)
                                    self.formatter.info("Logs folder deleted")
                                
                                return True
                        except ProcessLookupError:
                            # Process already gone
                            if not self.is_running():
                                progress.update(task, completed=True)
                                self.formatter.success("Server already stopped")
                                return True
                        except PermissionError:
                            self.formatter.error(f"Permission denied: Cannot stop process {pid}. Try running with sudo or as the process owner.")
                            return False
                    
                    progress.update(task, completed=True)
                    if pid:
                        self.formatter.error(f"Failed to stop server (PID: {pid}). Server may still be running.")
                    else:
                        self.formatter.error("Failed to stop server: No process ID available and server is not responding to HTTP shutdown.")
                    return False
                    
                except Exception as e:
                    # Fallback to signal-based shutdown if HTTP fails
                    if pid:
                        logger.debug(f"HTTP shutdown failed, using signal-based shutdown: {e}")
                        try:
                            os.kill(pid, signal.SIGTERM)
                            
                            start_time = time.time()
                            while time.time() - start_time < timeout:
                                if not self.is_running():
                                    progress.update(task, completed=True)
                                    self.formatter.success("Server stopped successfully")
                                    
                                    # Delete logs if requested
                                    if delete_logs and self.log_file.parent.exists():
                                        shutil.rmtree(self.log_file.parent)
                                        self.formatter.info("Logs folder deleted")
                                    
                                    return True
                                time.sleep(0.5)
                            
                            # Force kill if still running
                            os.kill(pid, signal.SIGKILL)
                            time.sleep(1)
                            
                            if not self.is_running():
                                progress.update(task, completed=True)
                                self.formatter.success("Server force stopped")
                                
                                # Delete logs if requested
                                if delete_logs and self.log_file.parent.exists():
                                    shutil.rmtree(self.log_file.parent)
                                    self.formatter.info("Logs folder deleted")
                                
                                return True
                        except ProcessLookupError:
                            if not self.is_running():
                                progress.update(task, completed=True)
                                self.formatter.success("Server already stopped")
                                return True
                        except PermissionError:
                            self.formatter.error(f"Permission denied: Cannot stop process {pid}. Try running with sudo or as the process owner.")
                            return False
                    else:
                        # Try to find process by port
                        pid = self._find_process_by_port()
                        if pid:
                            try:
                                os.kill(pid, signal.SIGTERM)
                                time.sleep(2)
                                if not self.is_running():
                                    progress.update(task, completed=True)
                                    self.formatter.success("Server stopped successfully")
                                    return True
                            except Exception:
                                pass
                    
                    progress.update(task, completed=True)
                    self.formatter.error(f"Error stopping server: {e}")
                    if not pid:
                        self.formatter.info("Tip: Try 'orbit stop --force' or manually kill the process")
                    return False
                    
            except ProcessLookupError:
                progress.update(task, completed=True)
                self.formatter.info("Server process not found")
                return True
            except Exception as e:
                progress.update(task, completed=True)
                self.formatter.error(f"Error stopping server: {e}")
                return False
    
    def _get_port_from_config(self, config_path: Optional[str] = None) -> Optional[int]:
        """
        Read the port from the server's config.yaml file.
        
        Args:
            config_path: Optional path to the configuration file
            
        Returns:
            Port number if found, None otherwise
        """
        # Determine config file path
        if config_path:
            if not os.path.isabs(config_path):
                config_path = str(self.project_root / config_path)
        else:
            # Try to find config file in common locations
            possible_configs = [
                self.project_root / "config" / "config.yaml",
                self.project_root / "server" / "config.yaml",
                self.project_root / "config.yaml"
            ]
            for config in possible_configs:
                if config.exists():
                    config_path = str(config)
                    break
        
        if not config_path or not os.path.exists(config_path):
            return None
        
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            # Check for port in general.port
            port = config.get('general', {}).get('port')
            if port:
                return int(port)
            
            # Check for HTTPS port if HTTPS is enabled
            https_config = config.get('general', {}).get('https', {})
            if https_config.get('enabled'):
                https_port = https_config.get('port')
                if https_port:
                    return int(https_port)
            
        except Exception as e:
            logger.debug(f"Failed to read port from config: {e}")
        
        return None
    
    def _update_api_client_url(self, port: Optional[int] = None) -> None:
        """
        Update the API client URL to use the correct port.
        
        Args:
            port: Port number to use (if None, tries to read from config)
        """
        if port is None:
            port = self._get_port_from_config()
        
        if port:
            # Extract host from current URL
            current_url = self.api_client.server_url
            try:
                # Parse the URL to extract protocol and host
                if '://' in current_url:
                    parts = current_url.split('://', 1)
                    protocol = parts[0]
                    # Remove any path and get just the host:port part
                    host_port = parts[1].split('/')[0]
                    # Extract host (remove port if present)
                    if ':' in host_port:
                        host = host_port.split(':')[0]
                    else:
                        host = host_port
                    new_url = f"{protocol}://{host}:{port}"
                else:
                    # Fallback if URL format is unexpected
                    new_url = f"http://localhost:{port}"
            except Exception as e:
                logger.debug(f"Error parsing URL, using default: {e}")
                new_url = f"http://localhost:{port}"
            
            # Update API client URL
            self.api_client.server_url = new_url
            logger.debug(f"Updated API client URL to: {new_url}")
    
    def restart(
        self,
        config_path: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        delete_logs: bool = False
    ) -> bool:
        """
        Restart the server.
        
        Args:
            config_path: Optional path to the configuration file
            host: Optional host to bind to
            port: Optional port to bind to
            delete_logs: Whether to delete the logs folder during restart
            
        Returns:
            True if the server was restarted successfully, False otherwise
        """
        self.formatter.info("Restarting server...")
        
        # Update API client URL based on config or provided port
        # This ensures we check the correct port when determining if server is running
        config_port = self._get_port_from_config(config_path) if not port else port
        if config_port:
            self._update_api_client_url(config_port)
        
        # Stop the server if it's running
        if self.is_running():
            if not self.stop(delete_logs=delete_logs):
                self.formatter.error("Failed to stop server for restart")
                return False
            
            # Wait a moment before starting again
            time.sleep(2)
        
        # Start the server with new configuration
        return self.start(config_path=config_path, host=host, port=port, delete_logs=delete_logs)
    
    def status(self) -> Dict[str, Any]:
        """
        Get the status of the server.
        
        Returns:
            A dictionary containing status information
        """
        # Update API client URL based on config to ensure we check the correct port
        config_port = self._get_port_from_config()
        if config_port:
            self._update_api_client_url(config_port)
        
        if not self.is_running():
            return {
                "status": "stopped",
                "message": "Server is not running"
            }
        
        # Try to get server info via API
        info = self.get_server_info()
        pid = info.get('pid') if info else None
        
        # If we don't have PID from API, try to find it by port
        if not pid:
            pid = self._find_process_by_port()
            if pid:
                logger.debug(f"Found server process by port: PID {pid}")
        
        if not pid:
            # Server is running but we can't get PID
            return {
                "status": "running",
                "message": "Server is running (unable to get detailed info - try 'orbit login' for full details)"
            }
        
        try:
            process = psutil.Process(pid)
            uptime_seconds = time.time() - process.create_time()
            uptime_str = self._format_uptime(uptime_seconds)
            
            # Get CPU percentage with proper initialization
            cpu_percent = self._get_cpu_percent(process)
            
            return {
                "status": "running",
                "pid": pid,
                "uptime": uptime_str,
                "uptime_seconds": uptime_seconds,
                "memory_mb": round(process.memory_info().rss / 1024 / 1024, 2),
                "cpu_percent": cpu_percent,
                "message": f"Server is running with PID {pid}"
            }
        except psutil.NoSuchProcess:
            return {
                "status": "stopped",
                "pid": pid,
                "message": f"Server is not running (PID {pid} not found)"
            }
        except Exception as e:
            return {
                "status": "unknown",
                "pid": pid,
                "error": str(e),
                "message": f"Error checking server status: {e}"
            }
    
    def get_enhanced_status(self, interval: float = 1.0) -> Dict[str, Any]:
        """
        Get enhanced status with more accurate CPU measurement.
        
        Args:
            interval: Time interval for CPU measurement (default: 1.0 second)
            
        Returns:
            A dictionary containing enhanced status information
        """
        if not self.is_running():
            return {
                "status": "stopped",
                "message": "Server is not running"
            }
        
        info = self.get_server_info()
        pid = info.get('pid') if info else None
        
        if not pid:
            return {
                "status": "running",
                "message": "Server is running (unable to get detailed info)"
            }
        
        try:
            process = psutil.Process(pid)
            uptime_seconds = time.time() - process.create_time()
            uptime_str = self._format_uptime(uptime_seconds)
            
            # Get more accurate CPU measurement with interval
            cpu_percent = process.cpu_percent(interval=interval)
            
            # Get additional system information
            memory_info = process.memory_info()
            memory_percent = process.memory_percent()
            
            # Get number of threads
            num_threads = process.num_threads()
            
            # Get I/O counters if available
            try:
                io_counters = process.io_counters()
                io_read_mb = round(io_counters.read_bytes / 1024 / 1024, 2)
                io_write_mb = round(io_counters.write_bytes / 1024 / 1024, 2)
            except (psutil.AccessDenied, AttributeError):
                io_read_mb = io_write_mb = 0.0
            
            return {
                "status": "running",
                "pid": pid,
                "uptime": uptime_str,
                "uptime_seconds": uptime_seconds,
                "memory_mb": round(memory_info.rss / 1024 / 1024, 2),
                "memory_percent": round(memory_percent, 2),
                "cpu_percent": round(cpu_percent, 2),
                "num_threads": num_threads,
                "io_read_mb": io_read_mb,
                "io_write_mb": io_write_mb,
                "message": f"Server is running with PID {pid}"
            }
        except psutil.NoSuchProcess:
            return {
                "status": "stopped",
                "pid": pid,
                "message": f"Server is not running (PID {pid} not found)"
            }
        except Exception as e:
            return {
                "status": "unknown",
                "pid": pid,
                "error": str(e),
                "message": f"Error checking server status: {e}"
            }
    
    def _get_cpu_percent(self, process: psutil.Process) -> float:
        """
        Get CPU percentage for a process with proper initialization.
        
        Args:
            process: The psutil Process object
            
        Returns:
            CPU percentage as float
        """
        try:
            # For the first call, we need to initialize the CPU monitoring
            if not self._cpu_initialized:
                # Call cpu_percent() once to initialize the baseline
                process.cpu_percent()
                self._cpu_initialized = True
                # Return 0.0 for the first call since we don't have a baseline yet
                return 0.0
            
            # For subsequent calls, get the actual CPU percentage
            return process.cpu_percent()
        except Exception as e:
            logger.debug(f"Error getting CPU percentage: {e}")
            return 0.0
    
    def _format_uptime(self, seconds: float) -> str:
        """Format uptime in human-readable format."""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        
        return " ".join(parts) if parts else "< 1m"
    
    def _find_process_by_port(self) -> Optional[int]:
        """
        Try to find the server process by checking which process is using the server port.
        
        Returns:
            Process ID if found, None otherwise
        """
        try:
            # Try to get port from server URL
            url = self.api_client.server_url
            if ':' in url:
                port_str = url.split(':')[-1].split('/')[0]
                try:
                    port = int(port_str)
                except ValueError:
                    # Default port
                    port = 3000
            else:
                port = 3000
            
            logger.debug(f"Looking for process listening on port {port}")
            
            # Method 1: Use psutil to find process by port
            try:
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        # Get connections for this process
                        conns = proc.connections()
                        for conn in conns:
                            if conn.status == psutil.CONN_LISTEN:
                                if conn.laddr.port == port:
                                    logger.debug(f"Found process {proc.info['pid']} listening on port {port}")
                                    return proc.info['pid']
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, AttributeError):
                        continue
            except Exception as e:
                logger.debug(f"Error iterating processes: {e}")
            
            # Method 2: Try using netstat/lsof as fallback (Unix-like systems)
            try:
                import subprocess
                # Try lsof first (more common on macOS)
                result = subprocess.run(
                    ['lsof', '-ti', f':{port}'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0 and result.stdout.strip():
                    pid = int(result.stdout.strip().split('\n')[0])
                    logger.debug(f"Found process {pid} on port {port} using lsof")
                    return pid
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, ValueError, FileNotFoundError) as e:
                logger.debug(f"lsof method failed: {e}")
            
            # Method 3: Try netstat as fallback
            try:
                import subprocess
                result = subprocess.run(
                    ['netstat', '-tuln'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if f':{port}' in line and 'LISTEN' in line:
                            # Try to extract PID (format varies by OS)
                            parts = line.split()
                            if len(parts) > 0:
                                # On some systems, PID is in the last column
                                try:
                                    pid = int(parts[-1])
                                    logger.debug(f"Found process {pid} on port {port} using netstat")
                                    return pid
                                except ValueError:
                                    pass
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError) as e:
                logger.debug(f"netstat method failed: {e}")
            
        except Exception as e:
            logger.debug(f"Failed to find process by port: {e}")
        
        return None

