"""Process management utilities for server control."""

import os
import signal
import time
from pathlib import Path
from typing import Optional
import psutil

from ..utils.logging import get_logger
from ..core.exceptions import ServerError

logger = get_logger(__name__)


class ProcessManager:
    """Manages server process lifecycle and PID file operations."""
    
    def __init__(self, pid_file: Path):
        """
        Initialize the process manager.
        
        Args:
            pid_file: Path to the PID file
        """
        self.pid_file = Path(pid_file)
    
    def get_pid(self) -> Optional[int]:
        """
        Read the PID from the PID file.
        
        Returns:
            The PID if the file exists and is valid, None otherwise
        """
        if not self.pid_file.exists():
            return None
        
        try:
            with open(self.pid_file, 'r') as f:
                content = f.read().strip()
                if content:
                    return int(content)
                return None
        except (ValueError, IOError) as e:
            logger.debug(f"Failed to read PID file: {e}")
            return None
    
    def save_pid(self, pid: int) -> None:
        """
        Write the PID to the PID file.
        
        Args:
            pid: The process ID to write
            
        Raises:
            ServerError: If the PID file cannot be written
        """
        try:
            # Ensure directory exists
            self.pid_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.pid_file, 'w') as f:
                f.write(str(pid))
            
            # Set secure permissions
            self.pid_file.chmod(0o600)
            
            logger.debug(f"Wrote PID {pid} to {self.pid_file}")
        except IOError as e:
            raise ServerError(f"Failed to write PID file: {e}")
    
    def remove_pid_file(self) -> None:
        """Remove the PID file if it exists."""
        if self.pid_file.exists():
            try:
                self.pid_file.unlink()
                logger.debug(f"Removed PID file {self.pid_file}")
            except IOError as e:
                logger.warning(f"Failed to remove PID file: {e}")
    
    def is_process_running(self, pid: int) -> bool:
        """
        Check if a process with the given PID is running.
        
        Args:
            pid: The process ID to check
            
        Returns:
            True if the process is running, False otherwise
        """
        try:
            process = psutil.Process(pid)
            
            # Additional check to ensure it's our server process
            cmdline = ' '.join(process.cmdline())
            is_server = any(
                marker in cmdline 
                for marker in ['server.py', 'main.py', 'uvicorn', 'server:app']
            )
            
            return process.is_running() and is_server
            
        except psutil.NoSuchProcess:
            return False
        except psutil.AccessDenied:
            logger.warning(f"Access denied when checking process {pid}")
            # If we can't access it, assume it's running
            return True
        except Exception as e:
            logger.error(f"Error checking process {pid}: {e}")
            return False
    
    def is_running(self) -> bool:
        """
        Check if the server is currently running.
        
        Returns:
            True if running, False otherwise
        """
        pid = self.get_pid()
        if pid is None:
            return False
        
        return self.is_process_running(pid)
    
    def stop_process(self, timeout: int = 30, force: bool = False) -> bool:
        """
        Stop the server process.
        
        Args:
            timeout: Maximum time to wait for graceful shutdown
            force: Whether to force kill immediately
            
        Returns:
            True if stopped successfully, False otherwise
        """
        pid = self.get_pid()
        if not pid:
            logger.warning("No PID file found")
            return False
        
        if not self.is_process_running(pid):
            logger.info(f"Process {pid} is not running")
            self.cleanup()
            return True
        
        try:
            if force:
                # Force kill immediately
                os.kill(pid, signal.SIGKILL)
                time.sleep(1)
            else:
                # Try graceful shutdown first
                os.kill(pid, signal.SIGTERM)
                
                # Wait for process to terminate
                start_time = time.time()
                while time.time() - start_time < timeout:
                    if not self.is_process_running(pid):
                        self.cleanup()
                        return True
                    time.sleep(0.5)
                
                # If still running, force kill
                logger.warning(f"Process {pid} did not stop gracefully, force killing...")
                os.kill(pid, signal.SIGKILL)
                time.sleep(1)
            
            # Final check
            if not self.is_process_running(pid):
                self.cleanup()
                return True
            else:
                logger.error(f"Failed to stop process {pid}")
                return False
                
        except ProcessLookupError:
            logger.info("Process already stopped")
            self.cleanup()
            return True
        except PermissionError:
            logger.error(f"Permission denied to stop process {pid}")
            return False
        except Exception as e:
            logger.error(f"Error stopping process: {e}")
            return False
    
    def cleanup(self) -> None:
        """Clean up PID file and any stale resources."""
        self.remove_pid_file()
    
    def get_process_info(self, pid: int) -> Optional[psutil.Process]:
        """
        Get psutil Process object for the given PID.
        
        Args:
            pid: Process ID
            
        Returns:
            psutil.Process object or None if not found
        """
        try:
            process = psutil.Process(pid)
            if process.is_running():
                return process
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        return None
    
    def wait_for_port(self, port: int, timeout: float = 10.0) -> bool:
        """
        Wait for a port to become available.
        
        Args:
            port: Port number to check
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if port is available, False if timeout
        """
        import socket
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                result = sock.connect_ex(('localhost', port))
                sock.close()
                
                if result == 0:
                    return True
            except:
                pass
            
            time.sleep(0.5)
        
        return False
    
    def find_process_by_port(self, port: int) -> Optional[int]:
        """
        Find process ID listening on a specific port.
        
        Args:
            port: Port number
            
        Returns:
            Process ID or None
        """
        for conn in psutil.net_connections():
            if conn.laddr.port == port and conn.status == 'LISTEN':
                return conn.pid
        return None