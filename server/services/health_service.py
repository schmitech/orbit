"""
Health service for checking the status of components
"""

import asyncio
import logging
from typing import Dict, Any, Optional

from utils.text_utils import sanitize_error_message
from models.schema import HealthStatus

# Configure logging
logger = logging.getLogger(__name__)


class HealthService:
    """Handles health check functionality"""
    
    def __init__(self, config: Dict[str, Any], datasource_client: Optional[Any] = None, llm_client: Optional[Any] = None):
        self.config = config
        self._last_status = None
        self._last_check_time = 0
        self._cache_ttl = 30  # Cache health status for 30 seconds
    
    async def get_health_status(self, use_cache: bool = True) -> HealthStatus:
        """Get health status of the server"""
        current_time = asyncio.get_event_loop().time()
        
        # Return cached status if available and not expired
        if use_cache and self._last_status and (current_time - self._last_check_time) < self._cache_ttl:
            return self._last_status
        
        # Server is always considered healthy if it's responding
        status = {
            "status": "ok"
        }
        
        # Cache the result
        self._last_status = HealthStatus(**status)
        self._last_check_time = current_time
        
        return self._last_status
    
    def is_healthy(self, health: HealthStatus) -> bool:
        """Check if the system is healthy based on health status"""
        return health.status == "ok"