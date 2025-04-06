"""
Health service for checking the status of components
"""

import asyncio
import logging
from typing import Dict, Any

from utils.text_utils import sanitize_error_message
from models.schema import HealthStatus

# Configure logging
logger = logging.getLogger(__name__)


class HealthService:
    """Handles health check functionality"""
    
    def __init__(self, config: Dict[str, Any], chroma_client, llm_client):
        self.config = config
        self.chroma_client = chroma_client
        self.llm_client = llm_client
        self._last_status = None
        self._last_check_time = 0
        self._cache_ttl = 30  # Cache health status for 30 seconds
    
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
                "chroma": {
                    "status": "unknown"
                },
                "llm": {
                    "status": "unknown"
                }
            }
        }
        
        # Check Chroma
        try:
            # Simple heartbeat check in thread pool
            await asyncio.get_event_loop().run_in_executor(
                None, 
                self.chroma_client.heartbeat
            )
            status["components"]["chroma"]["status"] = "ok"
        except Exception as e:
            status["components"]["chroma"]["status"] = "error"
            status["components"]["chroma"]["error"] = sanitize_error_message(str(e))
        
        # Check LLM (Ollama)
        try:
            llm_ok = await self.llm_client.verify_connection()
            status["components"]["llm"]["status"] = "ok" if llm_ok else "error"
            if not llm_ok:
                status["components"]["llm"]["error"] = "Failed to connect to Ollama"
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
    
    def is_healthy(self, health: HealthStatus) -> bool:
        """Check if the system is healthy based on health status"""
        return health.status == "ok"