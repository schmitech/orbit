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
from typing import Any, Optional
import psutil
import requests
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.console import Console

from bin.orbit.services.api_client import ApiClient
from bin.orbit.services.auth_service import AuthService
from bin.orbit.utils.exceptions import AuthenticationError, NetworkError
from bin.orbit.utils.invocation import cli_command
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
    
    @staticmethod
    def _is_orbit_server_process(proc: "psutil.Process") -> bool:
        """Identify an ORBIT server process by its command line, not by OS
        process-group membership — see `_force_kill`."""
        try:
            cmdline = " ".join(proc.cmdline())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False
        return "server/main.py" in cmdline or "main:app" in cmdline or "main:create_app" in cmdline

    @staticmethod
    def _force_kill(pid: int) -> None:
        """
        SIGKILL the server, taking any multi-worker children down with it,
        without ever risking a signal to processes outside ORBIT's own tree
        (e.g. the operator's shell).

        `start()` launches the server with start_new_session=True, so in the
        normal detached case `pid`'s process group ID equals `pid` itself,
        and workers it spawns stay in that same group (they never call
        setsid()). SIGKILL can't be caught, so killing only one process's
        PID would orphan the rest of the group holding the listening
        socket — killpg() on that group takes them all down safely.

        But `pid` isn't always that supervisor: a port-based fallback
        lookup can return a worker's PID instead, and `orbit start --reload`
        (or a manually foreground-started server) never calls
        start_new_session=True at all, so `pid`'s process group is
        whatever shared it — potentially the invoking terminal's group. In
        those cases getpgid(pid) != pid, and killpg() must NOT be used: it
        would signal every process in that group, shell included. Instead,
        walk pid's ancestry to find the actual ORBIT server process
        (verified by command line, not by group membership) and kill
        exactly that verified tree.
        """
        try:
            if os.getpgid(pid) == pid:
                os.killpg(pid, signal.SIGKILL)
                return
        except (ProcessLookupError, PermissionError):
            raise
        except OSError:
            pass

        root = None
        try:
            proc = psutil.Process(pid)
            for candidate in [proc, *proc.parents()]:
                if ServerService._is_orbit_server_process(candidate):
                    root = candidate
                    break
        except psutil.Error:
            root = None

        if root is not None:
            # The supervisor's health loop can spawn a replacement worker
            # the instant it observes one of its children die — if it's
            # still running while we enumerate+kill children below, a
            # worker started between the snapshot and the kill loop would
            # be missed and survive as an orphan holding the listening
            # socket. Freeze the supervisor first so it can't react to
            # anything we do to its children, then it's safe to enumerate.
            try:
                root.suspend()
            except psutil.NoSuchProcess:
                return
            try:
                for child in root.children(recursive=True):
                    try:
                        child.kill()
                    except psutil.NoSuchProcess:
                        pass
            finally:
                # A stopped process still dies instantly on SIGKILL — no
                # need to resume it first.
                try:
                    root.kill()
                except psutil.NoSuchProcess:
                    pass
            return

        # Couldn't verify this belongs to an ORBIT server tree — kill only
        # the single process rather than risk touching anything else.
        os.kill(pid, signal.SIGKILL)

    def get_server_info(self) -> Optional[dict[str, Any]]:
        """
        Get server information including PID via /admin/info endpoint.
        
        Returns:
            Dictionary with server info (pid, version, status) or None if unavailable
        """
        # Skip the call when no token is stored. The endpoint requires
        # system.manage, and a 401 is recorded as a server-side error - which
        # would inflate the error rate that `status` goes on to report -
        # while telling us nothing the PID fallbacks don't already cover.
        if not self.auth_service.token:
            logger.debug("Skipping /admin/info: no stored credentials")
            return None

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
                    config_path = str(config)
                    cmd.extend(["--config", config_path])
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
            cmd = ["uvicorn", "main:app", "--reload"]
            if host:
                cmd.extend(["--host", host])
            if port:
                cmd.extend(["--port", str(port)])
            # uvicorn calls create_app(), which reads the config from this env var
            if config_path:
                env["OIS_CONFIG_PATH"] = config_path
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
                                self.formatter.info(f"Tip: Run '{cli_command('status')}' to check when it is ready")
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
                            self._force_kill(pid)
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
                            self._force_kill(pid)
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
                            self._force_kill(pid)
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
                        self.formatter.info(f"Tip: Try '{cli_command('stop', '--force')}' or manually kill the process")
                    return False
                    
            except ProcessLookupError:
                progress.update(task, completed=True)
                self.formatter.info("Server process not found")
                return True
            except Exception as e:
                progress.update(task, completed=True)
                self.formatter.error(f"Error stopping server: {e}")
                return False

    def pause(self) -> bool:
        """
        Pause the server: reject new chat requests without stopping the process.

        Returns:
            True if the pause request succeeded, False otherwise
        """
        return self._toggle_pause("/admin/pause", "pause", "Server paused")

    def resume(self) -> bool:
        """
        Resume a paused server.

        Returns:
            True if the resume request succeeded, False otherwise
        """
        return self._toggle_pause("/admin/resume", "resume", "Server resumed")

    def _toggle_pause(self, endpoint: str, action: str, success_message: str) -> bool:
        """Shared implementation for pause()/resume() — both are pure HTTP admin calls."""
        if not self.is_running():
            self.formatter.error("Server is not running")
            return False

        try:
            self.auth_service.ensure_authenticated()
            headers = {"Authorization": f"Bearer {self.auth_service.token}"}
            response = self.api_client.post(endpoint, headers=headers, retry=False)
            response.raise_for_status()
            self.formatter.success(success_message)
            return True
        except AuthenticationError as e:
            self.formatter.error(f"Authentication required: {e}")
            return False
        except Exception as e:
            self.formatter.error(f"Error requesting server {action}: {e}")
            return False

    def _find_config_path(self, config_path: Optional[str] = None) -> Optional[str]:
        """
        Resolve the server's config.yaml path.

        Args:
            config_path: Optional explicit path (resolved against project root)

        Returns:
            Path to an existing config file, or None if none was found
        """
        if config_path:
            if not os.path.isabs(config_path):
                config_path = str(self.project_root / config_path)
            return config_path if os.path.exists(config_path) else None

        # Try to find config file in common locations
        possible_configs = [
            self.project_root / "config" / "config.yaml",
            self.project_root / "server" / "config.yaml",
            self.project_root / "config.yaml"
        ]
        for config in possible_configs:
            if config.exists():
                return str(config)
        return None

    def _get_port_from_config(self, config_path: Optional[str] = None) -> Optional[int]:
        """
        Read the port from the server's config.yaml file.
        
        Args:
            config_path: Optional path to the configuration file
            
        Returns:
            Port number if found, None otherwise
        """
        config_path = self._find_config_path(config_path)
        if not config_path:
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
    
    def _probe(
        self,
        endpoint: str,
        authenticated: bool = False,
        accept_codes: tuple = (200,)
    ) -> Optional[dict[str, Any]]:
        """
        Fetch an optional status endpoint, returning None when unavailable.

        Status reporting must never fail because a section is disabled or the
        caller is not logged in, so every error is swallowed and logged at
        debug level. Retries are disabled to keep `status` responsive.

        Args:
            endpoint: API endpoint path
            authenticated: Whether to attach an admin bearer token
            accept_codes: HTTP status codes whose body should be parsed

        Returns:
            Parsed JSON body, or None if the section is unavailable
        """
        try:
            headers = None
            if authenticated:
                self.auth_service.ensure_authenticated()
                headers = {"Authorization": f"Bearer {self.auth_service.token}"}
            response = self.api_client.get(endpoint, headers=headers, retry=False)
            if response.status_code not in accept_codes:
                logger.debug(f"Probe {endpoint} returned {response.status_code}")
                return None
            return response.json()
        except Exception as e:
            logger.debug(f"Probe {endpoint} failed: {e}")
            return None

    def status(self, cpu_interval: float = 0.15) -> dict[str, Any]:
        """
        Get a full status report for the server.

        Combines process facts (from psutil), server identity (/admin/info),
        traffic and latency (/metrics/json), adapter readiness (/health/ready)
        and circuit breaker state (/health/system) into a single report, then
        rolls those up into an overall health verdict using the thresholds the
        server itself declares.

        Sections that are unavailable - monitoring disabled, not logged in,
        endpoint missing - are omitted and named in `unavailable` rather than
        raising.

        Args:
            cpu_interval: Seconds to sample CPU over (blocking)

        Returns:
            A dictionary containing status information
        """
        # Update API client URL based on config to ensure we check the correct port
        config_port = self._get_port_from_config()
        if config_port:
            self._update_api_client_url(config_port)

        config_path = self._find_config_path()
        result: dict[str, Any] = {
            "server_url": self.api_client.server_url,
            "config_path": str(config_path) if config_path else None,
            "log_file": str(self.log_file),
            "unavailable": [],
        }

        if not self.is_running():
            result.update({
                "status": "stopped",
                "health": "stopped",
                "health_reasons": [],
                "message": "Server is not running"
            })
            return result

        # Server identity. Requires system.manage, so it may legitimately fail.
        info = self.get_server_info()
        if info is None:
            result["unavailable"].append("info")
        else:
            result["version"] = info.get("version")
        reported_status = (info.get('status') if info else None) or "running"
        result["status"] = reported_status

        pid = info.get('pid') if info else None
        if not pid:
            pid = self._find_process_by_port()
            if pid:
                logger.debug(f"Found server process by port: PID {pid}")
        result["pid"] = pid

        if pid:
            try:
                self._add_process_metrics(result, pid, cpu_interval)
            except psutil.NoSuchProcess:
                result.update({
                    "status": "stopped",
                    "health": "stopped",
                    "health_reasons": [],
                    "message": f"Server is not running (PID {pid} not found)"
                })
                return result
            except Exception as e:
                result.update({
                    "status": "unknown",
                    "health": "unknown",
                    "health_reasons": [],
                    "error": str(e),
                    "message": f"Error checking server status: {e}"
                })
                return result
        else:
            result["unavailable"].append("process")

        self._add_service_metrics(result)

        health, reasons = self._roll_up_health(result)
        result["health"] = health
        result["health_reasons"] = reasons

        if pid:
            result["message"] = f"Server is {reported_status} with PID {pid}"
        else:
            result["message"] = (
                f"Server is {reported_status} (unable to get detailed info - "
                f"try '{cli_command('login')}' for full details)"
            )
        return result

    def _add_process_metrics(self, result: dict[str, Any], pid: int, cpu_interval: float) -> None:
        """Add psutil-derived process facts to a status report, in place."""
        process = psutil.Process(pid)
        uptime_seconds = time.time() - process.create_time()
        result["uptime_seconds"] = uptime_seconds
        result["uptime"] = self._format_uptime(uptime_seconds)

        memory_info = process.memory_info()
        try:
            io_counters = process.io_counters()
            io_read_mb = round(io_counters.read_bytes / 1024 / 1024, 2)
            io_write_mb = round(io_counters.write_bytes / 1024 / 1024, 2)
        except (psutil.AccessDenied, AttributeError):
            io_read_mb = io_write_mb = 0.0

        result["process"] = {
            "memory_mb": round(memory_info.rss / 1024 / 1024, 2),
            "memory_percent": round(process.memory_percent(), 2),
            "cpu_percent": self._get_cpu_percent(process, cpu_interval),
            "num_threads": process.num_threads(),
            "io_read_mb": io_read_mb,
            "io_write_mb": io_write_mb,
        }

    def _add_service_metrics(self, result: dict[str, Any]) -> None:
        """Add traffic, readiness and adapter sections to a report, in place."""
        metrics = self._probe("/metrics/json")
        if metrics is None:
            result["unavailable"].append("metrics")
        else:
            result["traffic"] = metrics.get("requests") or {}
            result["thresholds"] = metrics.get("thresholds") or {}
            result["resources"] = metrics.get("system") or {}
            result["endpoints"] = metrics.get("endpoint_stats") or []
            result["cpu_series"] = (metrics.get("time_series") or {}).get("cpu") or []

        # 503 carries a meaningful "not ready" body, so accept it too.
        readiness = self._probe("/health/ready", accept_codes=(200, 503))
        if readiness is None:
            result["unavailable"].append("readiness")
        else:
            result["readiness"] = readiness

        system = self._probe("/health/system")
        if system is None:
            result["unavailable"].append("adapters")
        else:
            fault_tolerance = system.get("fault_tolerance") or {}
            result["fault_tolerance_enabled"] = fault_tolerance.get("enabled", False)
            result["adapters"] = fault_tolerance.get("adapters") or {}

    def _roll_up_health(self, result: dict[str, Any]) -> tuple[str, list[str]]:
        """
        Derive an overall health verdict from a status report.

        Uses the thresholds the server reports for itself rather than limits
        invented here, so the CLI verdict matches the server's own alerting.

        Returns:
            (verdict, reasons) where verdict is healthy/degraded/unhealthy
        """
        severity = {"healthy": 0, "degraded": 1, "unhealthy": 2}
        level = "healthy"
        reasons: list[str] = []

        def degrade(new_level: str, reason: str) -> None:
            nonlocal level
            reasons.append(reason)
            if severity[new_level] > severity[level]:
                level = new_level

        if result.get("status") == "paused":
            degrade("degraded", "server is paused")

        readiness = result.get("readiness") or {}
        if readiness.get("ready") is False:
            reason = readiness.get("reason")
            if not reason:
                reason = (
                    f"only {readiness.get('healthy_adapters', 0)}/"
                    f"{readiness.get('total_adapters', 0)} adapters healthy"
                )
            degrade("unhealthy", reason)

        adapters = result.get("adapters") or {}
        states: dict[str, list[str]] = {}
        for name, adapter in adapters.items():
            state = str((adapter or {}).get("state", "")).lower().replace("_", "-")
            states.setdefault(state, []).append(name)
        if states.get("open"):
            degrade("unhealthy", f"circuit open: {', '.join(sorted(states['open']))}")
        if states.get("half-open"):
            degrade("degraded", f"circuit recovering: {', '.join(sorted(states['half-open']))}")

        thresholds = result.get("thresholds") or {}
        traffic = result.get("traffic") or {}
        resources = result.get("resources") or {}
        checks = [
            (traffic.get("error_rate"), thresholds.get("error_rate"), "error rate {value}% (limit {limit}%)"),
            (traffic.get("p95_response_time"), thresholds.get("response_time_ms"), "p95 latency {value} ms (limit {limit} ms)"),
            (resources.get("cpu_percent"), thresholds.get("cpu"), "CPU {value}% (limit {limit}%)"),
            (resources.get("memory_percent"), thresholds.get("memory"), "memory {value}% (limit {limit}%)"),
        ]
        for value, limit, template in checks:
            if value is None or limit is None:
                continue
            if value > limit:
                degrade("degraded", template.format(value=value, limit=limit))

        return level, reasons

    def _get_cpu_percent(self, process: psutil.Process, interval: float = 0.15) -> float:
        """
        Get CPU percentage for a process.

        psutil computes CPU as a delta between two samples, so a blocking
        interval is required - a single non-blocking call would always return
        0.0 in a short-lived CLI process.

        Args:
            process: The psutil Process object
            interval: Seconds to sample over; must be > 0

        Returns:
            CPU percentage as float
        """
        try:
            return round(process.cpu_percent(interval=max(interval, 0.05)), 2)
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

