"""
Health Routes

Provides a health monitoring endpoints for the fault-tolerant system.
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Request
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
    async def get_adapter_health(request: Request):
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
                        "fault_tolerance_enabled": True,
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
    async def reset_adapter_circuit(adapter_name: str, request: Request):
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
    
    @router.get("/ready")
    async def readiness_check(request: Request):
        """Simple readiness check for load balancers - returns UP/DOWN status"""
        try:
            # Try to get fault tolerant adapter manager first, then fall back to regular adapter manager
            adapter_manager = getattr(request.app.state, 'fault_tolerant_adapter_manager', None)
            if not adapter_manager:
                adapter_manager = getattr(request.app.state, 'adapter_manager', None)
            
            if not adapter_manager:
                return JSONResponse(
                    status_code=503,
                    content={"ready": False, "reason": "Adapter manager not available"}
                )
            
            # Get health status from the adapter manager
            health_status = None
            if hasattr(adapter_manager, 'get_health_status'):
                health_status = adapter_manager.get_health_status()
            elif hasattr(adapter_manager, 'parallel_executor') and adapter_manager.parallel_executor:
                if hasattr(adapter_manager.parallel_executor, 'get_health_status'):
                    health_status = adapter_manager.parallel_executor.get_health_status()
            
            # Get adapter counts from multiple sources
            total_adapters = 0
            healthy_adapters = 0
            
            if health_status:
                # Try main health status first
                total_adapters = health_status.get("total_adapters", 0)
                healthy_adapters = health_status.get("healthy_adapters", 0)
                
                # If no adapters found in main status, check available_adapters list
                if total_adapters == 0 and "available_adapters" in health_status:
                    available = health_status.get("available_adapters", [])
                    total_adapters = len(available)
                    # If circuit_breakers dict is empty, assume all available adapters are healthy
                    circuit_breakers = health_status.get("circuit_breakers", {})
                    if not circuit_breakers:
                        healthy_adapters = total_adapters
                    else:
                        # Count healthy adapters (closed circuits)
                        healthy_adapters = sum(1 for cb in circuit_breakers.values() if cb.get("state") == "closed")
            
            # Also check circuit breaker service if available
            if hasattr(request.app.state, 'circuit_breaker_service'):
                cb_service = request.app.state.circuit_breaker_service
                if hasattr(cb_service, 'get_health_status'):
                    cb_health = cb_service.get_health_status()
                    cb_total = cb_health.get("total_adapters", 0)
                    cb_healthy = cb_health.get("healthy_adapters", 0)
                    # Use circuit breaker service data if it has more adapters
                    if cb_total > total_adapters:
                        total_adapters = cb_total
                        healthy_adapters = cb_healthy
            
            if total_adapters == 0:
                # No adapters configured, consider ready
                return {"ready": True, "reason": "No adapters configured"}
            
            healthy_ratio = healthy_adapters / total_adapters
            is_ready = healthy_ratio > 0.5
            
            return {
                "ready": is_ready,
                "healthy_ratio": round(healthy_ratio, 2),
                "healthy_adapters": healthy_adapters,
                "total_adapters": total_adapters
            }
            
        except Exception as e:
            logger.error(f"Error in readiness check: {e}")
            return JSONResponse(
                status_code=503,
                content={"ready": False, "reason": f"Error: {str(e)}"}
            )
    
    @router.get("/system")
    async def get_system_status(request: Request):
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
                    status["fault_tolerance"]["enabled"] = health.get("fault_tolerance_enabled", True)
                    status["fault_tolerance"]["adapters"] = health.get("circuit_breakers", {})
                else:
                    status["fault_tolerance"]["enabled"] = True
                    
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