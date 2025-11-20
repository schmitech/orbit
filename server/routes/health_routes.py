"""
Health Routes

Provides a health monitoring endpoints for the fault-tolerant system.
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from utils import is_true_value

logger = logging.getLogger(__name__)

def get_adapter_manager(request: Request):
    """
    Dependency to get the adapter manager from the application state.
    
    First tries to get the fault tolerant adapter manager, then falls back to regular adapter manager.
    
    Returns:
        The adapter manager instance
        
    Raises:
        HTTPException: If no adapter manager is available (503 Service Unavailable)
    """
    manager = getattr(request.app.state, 'fault_tolerant_adapter_manager', None)
    if not manager:
        manager = getattr(request.app.state, 'adapter_manager', None)
    if not manager:
        raise HTTPException(status_code=503, detail="Adapter manager not available")
    return manager

def get_adapter_manager_optional(request: Request):
    """
    Optional dependency to get the adapter manager from the application state.
    
    Returns None if no adapter manager is available instead of raising an exception.
    Used for health check endpoints that need to handle the case gracefully.
    
    Returns:
        The adapter manager instance or None
    """
    manager = getattr(request.app.state, 'fault_tolerant_adapter_manager', None)
    if not manager:
        manager = getattr(request.app.state, 'adapter_manager', None)
    return manager

def create_health_router() -> APIRouter:
    """Create health monitoring router"""
    
    router = APIRouter(prefix="/health", tags=["health"])
    
    @router.get("/")
    async def health_check():
        """Basic health check endpoint"""
        return {"status": "healthy"}
    
    @router.get("/adapters")
    async def get_adapter_health(adapter_manager = Depends(get_adapter_manager)):
        """Get adapter health status"""
        try:
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
    async def reset_adapter_circuit(adapter_name: str, adapter_manager = Depends(get_adapter_manager)):
        """Reset circuit breaker for a specific adapter"""
        try:
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
            # Circuit breaker service removed - fault tolerance handled by ParallelAdapterExecutor
            
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
    
    @router.get("/embedding-services")
    async def get_embedding_service_stats():
        """Get statistics about cached embedding services"""
        try:
            from embeddings.base import EmbeddingServiceFactory
            stats = EmbeddingServiceFactory.get_cache_stats()
            return stats
        except Exception as e:
            logger.error(f"Error getting embedding service stats: {e}")
            return JSONResponse(
                status_code=500,
                content={"error": str(e)}
            )
    
    @router.get("/mongodb-services")
    async def get_mongodb_service_stats():
        """Get statistics about cached MongoDB services"""
        try:
            from services.mongodb_service import MongoDBService
            stats = MongoDBService.get_cache_stats()
            return stats
        except Exception as e:
            logger.error(f"Error getting MongoDB service stats: {e}")
            return JSONResponse(
                status_code=500,
                content={"error": str(e)}
            )
    
    @router.get("/ready")
    async def readiness_check(adapter_manager = Depends(get_adapter_manager_optional)):
        """Simple readiness check for load balancers - returns UP/DOWN status"""
        try:
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
            
            # Circuit breaker service removed - all health data comes from ParallelAdapterExecutor
            
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
    async def get_system_status(adapter_manager = Depends(get_adapter_manager_optional)):
        """Get overall system status"""
        try:
            status = {
                "status": "healthy",
                "fault_tolerance": {
                    "enabled": False,
                    "adapters": {}
                }
            }
            
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
            
            # Circuit breaker service removed - all fault tolerance data comes from ParallelAdapterExecutor
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting system status: {e}")
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": str(e)}
            )
    
    @router.get("/adapters/{adapter_name}/history")
    async def get_adapter_history(adapter_name: str, adapter_manager = Depends(get_adapter_manager)):
        """
        Get detailed circuit breaker history for a specific adapter.
        
        This endpoint provides detailed observability data including:
        - Call history with timestamps, outcomes, and execution times
        - State transitions with reasons and timestamps
        - Statistical summaries for debugging intermittent issues
        
        Args:
            adapter_name: Name of the adapter to get history for
            adapter_manager: Adapter manager dependency
            
        Returns:
            Detailed history and metrics for the specified adapter
            
        Raises:
            HTTPException: If adapter not found or no circuit breaker data available
        """
        try:
            # Try to get the parallel executor from the adapter manager
            parallel_executor = None
            if hasattr(adapter_manager, 'parallel_executor') and adapter_manager.parallel_executor:
                parallel_executor = adapter_manager.parallel_executor
            else:
                raise HTTPException(
                    status_code=503, 
                    detail="Parallel executor not available for history retrieval"
                )
            
            # Get the circuit breaker for the specific adapter
            if not hasattr(parallel_executor, 'circuit_breakers') or adapter_name not in parallel_executor.circuit_breakers:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Circuit breaker not found for adapter: {adapter_name}"
                )
            
            circuit_breaker = parallel_executor.circuit_breakers[adapter_name]
            
            # Extract detailed history and statistics
            history_data = {
                "adapter_name": adapter_name,
                "current_state": circuit_breaker.state.value,
                "statistics": {
                    "total_calls": circuit_breaker.stats.total_calls,
                    "total_successes": circuit_breaker.stats.total_successes,
                    "total_failures": circuit_breaker.stats.total_failures,
                    "timeout_calls": circuit_breaker.stats.timeout_calls,
                    "success_rate": circuit_breaker.stats.total_successes / circuit_breaker.stats.total_calls if circuit_breaker.stats.total_calls > 0 else 0.0,
                    "consecutive_failures": circuit_breaker.stats.consecutive_failures,
                    "consecutive_successes": circuit_breaker.stats.consecutive_successes,
                    "last_success_time": circuit_breaker.stats.last_success_time,
                    "last_failure_time": circuit_breaker.stats.last_failure_time
                },
                "call_history": circuit_breaker.stats.call_history[-50:],  # Last 50 calls to prevent huge responses
                "state_transitions": circuit_breaker.stats.state_transitions[-20:],  # Last 20 state changes
                "configuration": {
                    "failure_threshold": circuit_breaker.failure_threshold,
                    "recovery_timeout": circuit_breaker.base_recovery_timeout,
                    "success_threshold": circuit_breaker.success_threshold,
                    "max_recovery_timeout": circuit_breaker.max_recovery_timeout
                }
            }
            
            return history_data
            
        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.error(f"Error getting adapter history for {adapter_name}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error while retrieving adapter history: {str(e)}"
            )
    
    @router.get("/adapters/{adapter_name}/history/full")
    async def get_adapter_full_history(adapter_name: str, adapter_manager = Depends(get_adapter_manager)):
        """
        Get complete circuit breaker history for a specific adapter (admin/debug use).
        
        WARNING: This endpoint can return large amounts of data and should be used carefully.
        Use the regular /history endpoint for most debugging purposes.
        
        Args:
            adapter_name: Name of the adapter to get full history for
            adapter_manager: Adapter manager dependency
            
        Returns:
            Complete history and metrics for the specified adapter
        """
        try:
            # Try to get the parallel executor from the adapter manager
            parallel_executor = None
            if hasattr(adapter_manager, 'parallel_executor') and adapter_manager.parallel_executor:
                parallel_executor = adapter_manager.parallel_executor
            else:
                raise HTTPException(
                    status_code=503, 
                    detail="Parallel executor not available for history retrieval"
                )
            
            # Get the circuit breaker for the specific adapter
            if not hasattr(parallel_executor, 'circuit_breakers') or adapter_name not in parallel_executor.circuit_breakers:
                raise HTTPException(
                    status_code=404, 
                    detail=f"Circuit breaker not found for adapter: {adapter_name}"
                )
            
            circuit_breaker = parallel_executor.circuit_breakers[adapter_name]
            
            # Extract complete history (be careful with size)
            history_data = {
                "adapter_name": adapter_name,
                "current_state": circuit_breaker.state.value,
                "statistics": {
                    "total_calls": circuit_breaker.stats.total_calls,
                    "total_successes": circuit_breaker.stats.total_successes,
                    "total_failures": circuit_breaker.stats.total_failures,
                    "timeout_calls": circuit_breaker.stats.timeout_calls,
                    "success_rate": circuit_breaker.stats.total_successes / circuit_breaker.stats.total_calls if circuit_breaker.stats.total_calls > 0 else 0.0,
                    "consecutive_failures": circuit_breaker.stats.consecutive_failures,
                    "consecutive_successes": circuit_breaker.stats.consecutive_successes,
                    "last_success_time": circuit_breaker.stats.last_success_time,
                    "last_failure_time": circuit_breaker.stats.last_failure_time
                },
                "call_history": circuit_breaker.stats.call_history,  # Complete history
                "state_transitions": circuit_breaker.stats.state_transitions,  # Complete history
                "configuration": {
                    "failure_threshold": circuit_breaker.failure_threshold,
                    "recovery_timeout": circuit_breaker.base_recovery_timeout,
                    "success_threshold": circuit_breaker.success_threshold,
                    "max_recovery_timeout": circuit_breaker.max_recovery_timeout
                },
                "warning": "This is the complete history and may contain large amounts of data"
            }
            
            return history_data
            
        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.error(f"Error getting full adapter history for {adapter_name}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error while retrieving full adapter history: {str(e)}"
            )
    
    @router.get("/thread-pools")
    async def get_thread_pool_stats(request: Request):
        """Get thread pool statistics"""
        # Get thread pool manager from application state
        thread_pool_manager = getattr(request.app.state, 'thread_pool_manager', None)
        if not thread_pool_manager:
            raise HTTPException(
                status_code=503,
                detail="Thread pool manager not available"
            )
        
        try:
            # Get current stats
            stats = thread_pool_manager.get_pool_stats()
            
            # Add summary information
            total_workers = sum(pool['max_workers'] for pool in stats.values())
            total_active = sum(pool['active_threads'] for pool in stats.values() if isinstance(pool['active_threads'], int))
            total_queued = sum(pool['queued_tasks'] for pool in stats.values() if pool['queued_tasks'] != 'N/A' and isinstance(pool['queued_tasks'], int))
            
            return {
                "timestamp": request.app.state.config.get('server_start_time', 'unknown'),
                "summary": {
                    "total_workers": total_workers,
                    "total_active": total_active,
                    "total_queued": total_queued,
                    "utilization_percent": round((total_active / total_workers * 100) if total_workers > 0 else 0, 1)
                },
                "pools": stats
            }
            
        except Exception as e:
            logger.error(f"Error getting thread pool stats: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.post("/thread-pools/log-status")
    async def log_thread_pool_status(request: Request):
        """Trigger logging of current thread pool status"""
        # Get thread pool manager from application state
        thread_pool_manager = getattr(request.app.state, 'thread_pool_manager', None)
        if not thread_pool_manager:
            raise HTTPException(
                status_code=503,
                detail="Thread pool manager not available"
            )
        
        try:
            # Trigger status logging
            thread_pool_manager.log_current_status()
            return {
                "message": "Thread pool status logged successfully",
                "check_logs": "See server logs for detailed thread pool status"
            }
            
        except Exception as e:
            logger.error(f"Error logging thread pool status: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    return router