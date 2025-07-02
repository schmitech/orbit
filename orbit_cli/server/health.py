"""Server health check utilities."""

import time
from typing import Dict, Any, Optional, Callable
import requests

from ..utils.logging import get_logger

logger = get_logger(__name__)


class HealthChecker:
    """Performs health checks on the server."""
    
    def __init__(
        self,
        base_url: str = "http://localhost:3000",
        timeout: int = 5,
        retry_attempts: int = 3
    ):
        """
        Initialize the health checker.
        
        Args:
            base_url: Base URL of the server
            timeout: Request timeout in seconds
            retry_attempts: Number of retry attempts
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.retry_attempts = retry_attempts
    
    def check_health(self, endpoint: str = "/health") -> Dict[str, Any]:
        """
        Perform a health check on the server.
        
        Args:
            endpoint: Health check endpoint
            
        Returns:
            Health check result
        """
        url = f"{self.base_url}{endpoint}"
        
        for attempt in range(self.retry_attempts):
            try:
                response = requests.get(url, timeout=self.timeout)
                
                if response.status_code == 200:
                    try:
                        return {
                            "status": "healthy",
                            "response_time_ms": round(response.elapsed.total_seconds() * 1000, 2),
                            "data": response.json()
                        }
                    except:
                        return {
                            "status": "healthy",
                            "response_time_ms": round(response.elapsed.total_seconds() * 1000, 2),
                            "data": response.text
                        }
                else:
                    return {
                        "status": "unhealthy",
                        "status_code": response.status_code,
                        "error": f"HTTP {response.status_code}"
                    }
                    
            except requests.exceptions.ConnectionError:
                if attempt < self.retry_attempts - 1:
                    time.sleep(1)
                    continue
                return {
                    "status": "unhealthy",
                    "error": "Connection failed"
                }
            except requests.exceptions.Timeout:
                return {
                    "status": "unhealthy",
                    "error": f"Timeout after {self.timeout}s"
                }
            except Exception as e:
                return {
                    "status": "unhealthy",
                    "error": str(e)
                }
        
        return {
            "status": "unhealthy",
            "error": "All retry attempts failed"
        }
    
    def wait_for_healthy(
        self,
        max_wait: float = 30.0,
        check_interval: float = 1.0,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> bool:
        """
        Wait for the server to become healthy.
        
        Args:
            max_wait: Maximum time to wait in seconds
            check_interval: Interval between checks
            progress_callback: Optional callback for progress updates
            
        Returns:
            True if server became healthy, False if timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            elapsed = time.time() - start_time
            
            if progress_callback:
                progress_callback(elapsed)
            
            result = self.check_health()
            if result["status"] == "healthy":
                return True
            
            time.sleep(check_interval)
        
        return False
    
    def check_endpoints(self, endpoints: list) -> Dict[str, Dict[str, Any]]:
        """
        Check multiple endpoints.
        
        Args:
            endpoints: List of endpoints to check
            
        Returns:
            Dictionary mapping endpoints to their health status
        """
        results = {}
        
        for endpoint in endpoints:
            results[endpoint] = self.check_health(endpoint)
        
        return results
    
    def get_server_info(self) -> Dict[str, Any]:
        """
        Get server information from the info endpoint.
        
        Returns:
            Server information or error
        """
        try:
            response = requests.get(
                f"{self.base_url}/info",
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            return {"error": str(e)}


class StartupValidator:
    """Validates server startup conditions."""
    
    @staticmethod
    def check_port_available(port: int) -> bool:
        """
        Check if a port is available for binding.
        
        Args:
            port: Port number to check
            
        Returns:
            True if available, False if in use
        """
        import socket
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(('', port))
            sock.close()
            return True
        except OSError:
            return False
    
    @staticmethod
    def check_dependencies() -> Dict[str, bool]:
        """
        Check if required dependencies are available.
        
        Returns:
            Dictionary of dependency check results
        """
        dependencies = {}
        
        # Check Python packages
        required_packages = [
            "uvicorn",
            "fastapi",
            "pydantic",
            "chromadb"
        ]
        
        for package in required_packages:
            try:
                __import__(package)
                dependencies[package] = True
            except ImportError:
                dependencies[package] = False
        
        return dependencies
    
    @staticmethod
    def check_config_file(config_path: str) -> Dict[str, Any]:
        """
        Validate configuration file.
        
        Args:
            config_path: Path to config file
            
        Returns:
            Validation result
        """
        from pathlib import Path
        
        path = Path(config_path)
        
        if not path.exists():
            return {
                "valid": False,
                "error": "Configuration file not found"
            }
        
        if not path.is_file():
            return {
                "valid": False,
                "error": "Path is not a file"
            }
        
        # Try to parse as YAML
        try:
            import yaml
            with open(path, 'r') as f:
                config = yaml.safe_load(f)
            
            return {
                "valid": True,
                "config": config
            }
        except Exception as e:
            return {
                "valid": False,
                "error": f"Failed to parse config: {e}"
            }
    
    @staticmethod
    def validate_startup_conditions(
        port: int = 3000,
        config_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate all startup conditions.
        
        Args:
            port: Port to bind to
            config_path: Optional config file path
            
        Returns:
            Validation results
        """
        results = {
            "port_available": StartupValidator.check_port_available(port),
            "dependencies": StartupValidator.check_dependencies()
        }
        
        if config_path:
            results["config"] = StartupValidator.check_config_file(config_path)
        
        # Overall validation
        results["valid"] = (
            results["port_available"] and
            all(results["dependencies"].values()) and
            (not config_path or results.get("config", {}).get("valid", True))
        )
        
        return results