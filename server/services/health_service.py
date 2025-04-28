"""
Health service for checking the status of components
"""

import asyncio
import logging
import sqlite3
from typing import Dict, Any, Optional

from utils.text_utils import sanitize_error_message
from models.schema import HealthStatus

# Configure logging
logger = logging.getLogger(__name__)


class HealthService:
    """Handles health check functionality"""
    
    def __init__(self, config: Dict[str, Any], datasource_client: Optional[Any] = None, llm_client: Optional[Any] = None):
        self.config = config
        self.datasource_client = datasource_client
        self.llm_client = llm_client
        self._last_status = None
        self._last_check_time = 0
        self._cache_ttl = 30  # Cache health status for 30 seconds
        
        # Identify the datasource type from config
        self.datasource_type = config['general'].get('datasource_provider', 'chroma')
        logger.info(f"Health service initialized with datasource type: {self.datasource_type}")
    
    async def get_health_status(self, use_cache: bool = True) -> HealthStatus:
        """Get health status of all components"""
        current_time = asyncio.get_event_loop().time()
        
        # Return cached status if available and not expired
        if use_cache and self._last_status and (current_time - self._last_check_time) < self._cache_ttl:
            return self._last_status
        
        status = {
            "status": "ok",
            "components": {
                "server": {
                    "status": "ok"
                },
                "datasource": {
                    "status": "unknown",
                    "type": self.datasource_type
                },
                "llm": {
                    "status": "unknown"
                }
            }
        }
        
        # Check datasource based on type
        if self.datasource_type == 'chroma':
            await self._check_chroma_health(status)
        elif self.datasource_type == 'sqlite':
            await self._check_sqlite_health(status)
        else:
            status["components"]["datasource"]["status"] = "unknown"
            status["components"]["datasource"]["error"] = f"Unsupported datasource type: {self.datasource_type}"
        
        # Check LLM
        try:
            if self.llm_client:
                llm_ok = await self.llm_client.verify_connection()
                status["components"]["llm"]["status"] = "ok" if llm_ok else "error"
                if not llm_ok:
                    provider = self.config['general'].get('inference_provider', 'ollama')
                    status["components"]["llm"]["error"] = f"Failed to connect to {provider}"
            else:
                status["components"]["llm"]["status"] = "error"
                status["components"]["llm"]["error"] = "LLM client not initialized"
        except Exception as e:
            status["components"]["llm"]["status"] = "error"
            status["components"]["llm"]["error"] = sanitize_error_message(str(e))
        
        # Overall status
        if any(component["status"] != "ok" for component in status["components"].values()):
            status["status"] = "error"
        
        # Cache the result
        self._last_status = HealthStatus(**status)
        self._last_check_time = current_time
        
        return self._last_status
    
    async def _check_chroma_health(self, status: Dict) -> None:
        """Check ChromaDB health"""
        try:
            if self.datasource_client:
                # Simple heartbeat check in thread pool
                await asyncio.get_event_loop().run_in_executor(
                    None, 
                    self.datasource_client.heartbeat
                )
                status["components"]["datasource"]["status"] = "ok"
            else:
                status["components"]["datasource"]["status"] = "error"
                status["components"]["datasource"]["error"] = "ChromaDB client not initialized"
        except Exception as e:
            status["components"]["datasource"]["status"] = "error"
            status["components"]["datasource"]["error"] = sanitize_error_message(str(e))
            
    async def _check_sqlite_health(self, status: Dict) -> None:
        """Check SQLite health"""
        try:
            if self.datasource_client:
                # Run a simple query to check connection
                def check_sqlite():
                    try:
                        cursor = self.datasource_client.cursor()
                        cursor.execute("SELECT 1")
                        cursor.fetchone()
                        return True
                    except sqlite3.Error:
                        return False
                
                is_ok = await asyncio.get_event_loop().run_in_executor(None, check_sqlite)
                
                if is_ok:
                    status["components"]["datasource"]["status"] = "ok"
                else:
                    status["components"]["datasource"]["status"] = "error"
                    status["components"]["datasource"]["error"] = "SQLite database error"
            else:
                status["components"]["datasource"]["status"] = "error"
                status["components"]["datasource"]["error"] = "SQLite connection not initialized"
        except Exception as e:
            status["components"]["datasource"]["status"] = "error"
            status["components"]["datasource"]["error"] = sanitize_error_message(str(e))
    
    def is_healthy(self, health: HealthStatus) -> bool:
        """Check if the system is healthy based on health status"""
        return health.status == "ok"