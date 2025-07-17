"""
Health Routes

Provides a health monitoring endpoints for the fault-tolerant system.
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

def create_health_router() -> APIRouter:
    """Create health monitoring router"""
    
    router = APIRouter(prefix="/health", tags=["health"])
    
    @router.get("/")
    async def health_check():
        """Basic health check endpoint"""
        return {"status": "healthy"}
    
    @router.get("/adapters")
    async def get_adapter_health(request):
        """Get adapter health status"""
        try:
            # Try to get fault tolerant adapter manager first, then fall back to regular adapter manager
            adapter_manager = getattr(request.app.state, 'fault_tolerant_adapter_manager', None)
            if not adapter_manager:
                adapter_manager = getattr(request.app.state, 'adapter_manager', None)
            
            if not adapter_manager:
                return JSONResponse(
                    status_code=503,
                    content={"error": "Adapter manager not available"}
                )
            
            # Get health status from the adapter manager
            if hasattr(adapter_manager, 'get_health_status'):
                health_status = adapter_manager.get_health_status()
            else:
                # If no get_health_status method, try to get from parallel executor
                if hasattr(adapter_manager, 'parallel_executor') and adapter_manager.parallel_executor:
                    health_status = adapter_manager.parallel_executor.get_health_status()
                else:
                    health_status = {
                        "fault_tolerance_enabled": adapter_manager.fault_tolerance_enabled,
                        "status": "unknown - no health status method available"
                    }
            
            return health_status
            
        except Exception as e:
            logger.error(f"Error getting adapter health: {e}")
            return JSONResponse(
                status_code=500,
                content={"error": str(e)}
            )
    
    @router.post("/adapters/{adapter_name}/reset")
    async def reset_adapter_circuit(adapter_name: str, request):
        """Reset circuit breaker for a specific adapter"""
        try:
            # Try to get fault tolerant adapter manager first, then fall back to regular adapter manager
            adapter_manager = getattr(request.app.state, 'fault_tolerant_adapter_manager', None)
            if not adapter_manager:
                adapter_manager = getattr(request.app.state, 'adapter_manager', None)
            
            if not adapter_manager:
                raise HTTPException(status_code=503, detail="Adapter manager not available")
            
            # Try to reset circuit breaker through different paths
            reset_successful = False
            
            # Method 1: Direct reset method
            if hasattr(adapter_manager, 'reset_circuit_breaker'):
                adapter_manager.reset_circuit_breaker(adapter_name)
                reset_successful = True
            # Method 2: Through parallel executor
            elif hasattr(adapter_manager, 'parallel_executor') and adapter_manager.parallel_executor:
                if hasattr(adapter_manager.parallel_executor, 'reset_circuit_breaker'):
                    adapter_manager.parallel_executor.reset_circuit_breaker(adapter_name)
                    reset_successful = True
            # Method 3: Through circuit breaker service
            elif hasattr(request.app.state, 'circuit_breaker_service'):
                cb_service = request.app.state.circuit_breaker_service
                if hasattr(cb_service, 'reset_circuit_breaker'):
                    cb_service.reset_circuit_breaker(adapter_name)
                    reset_successful = True
            
            if reset_successful:
                return {
                    "message": f"Circuit breaker reset for adapter: {adapter_name}",
                    "adapter": adapter_name
                }
            else:
                raise HTTPException(status_code=501, detail="Circuit breaker reset not implemented")
            
        except Exception as e:
            logger.error(f"Error resetting circuit breaker: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get("/system")
    async def get_system_status(request):
        """Get overall system status"""
        try:
            status = {
                "status": "healthy",
                "fault_tolerance": {
                    "enabled": False,
                    "adapters": {}
                }
            }
            
            # Try to get fault tolerant adapter manager first, then fall back to regular adapter manager
            adapter_manager = getattr(request.app.state, 'fault_tolerant_adapter_manager', None)
            if not adapter_manager:
                adapter_manager = getattr(request.app.state, 'adapter_manager', None)
            
            if adapter_manager:
                # Try to get health status from the adapter manager
                if hasattr(adapter_manager, 'get_health_status'):
                    health = adapter_manager.get_health_status()
                    status["fault_tolerance"]["enabled"] = health.get("fault_tolerance_enabled", False)
                    status["fault_tolerance"]["adapters"] = health.get("circuit_breakers", {})
                elif hasattr(adapter_manager, 'fault_tolerance_enabled'):
                    status["fault_tolerance"]["enabled"] = adapter_manager.fault_tolerance_enabled
                    
                    # Try to get circuit breaker status from parallel executor
                    if hasattr(adapter_manager, 'parallel_executor') and adapter_manager.parallel_executor:
                        if hasattr(adapter_manager.parallel_executor, 'get_circuit_breaker_states'):
                            status["fault_tolerance"]["adapters"] = adapter_manager.parallel_executor.get_circuit_breaker_states()
            
            # Also try to get status from circuit breaker service
            if hasattr(request.app.state, 'circuit_breaker_service'):
                cb_service = request.app.state.circuit_breaker_service
                if hasattr(cb_service, 'get_health_status'):
                    cb_health = cb_service.get_health_status()
                    status["fault_tolerance"]["circuit_breaker_service"] = cb_health
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting system status: {e}")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": str(e)}
            )
    
    return router