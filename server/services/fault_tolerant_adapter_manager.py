"""
Fault-Tolerant Adapter Manager

This module provides a fault-tolerant adapter manager that integrates
parallel execution and circuit breaker protection without complex layering.
"""

import logging
from typing import Dict, Any, List, Optional

from .dynamic_adapter_manager import DynamicAdapterManager
from .parallel_adapter_executor import ParallelAdapterExecutor

logger = logging.getLogger(__name__)

class FaultTolerantAdapterManager:
    """
    A fault-tolerant adapter manager that provides:
    - Parallel adapter execution
    - Circuit breaker protection
    - Easy debugging and monitoring
    - Backward compatibility with existing API
    """
    
    def __init__(self, config: Dict[str, Any], app_state: Any):
        self.config = config
        self.app_state = app_state
        
        # Fault tolerance is always enabled as core functionality
        self.fault_tolerance_enabled = True
        
        # Initialize base adapter manager
        self.base_adapter_manager = DynamicAdapterManager(config, app_state)
        
        # Initialize parallel executor (always enabled)
        self.parallel_executor = ParallelAdapterExecutor(
            self.base_adapter_manager, 
            config
        )
        logger.info("Fault tolerance enabled with parallel execution")
    
    def _is_enabled(self, value) -> bool:
        """Check if a config value is true"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', 'yes', '1', 'on')
        return bool(value)
    
    @property
    def config_manager(self):
        """Delegate to base adapter manager's config_manager for backward compatibility."""
        return self.base_adapter_manager.config_manager

    async def get_adapter(self, adapter_name: str) -> Any:
        """Get a single adapter - backward compatibility method"""
        return await self.base_adapter_manager.get_adapter(adapter_name)
    
    def get_available_adapters(self) -> List[str]:
        """Get list of available adapters"""
        return self.base_adapter_manager.get_available_adapters()

    def get_adapter_config(self, adapter_name: str) -> Optional[Dict[str, Any]]:
        """Get adapter configuration - delegates to base adapter manager"""
        return self.base_adapter_manager.get_adapter_config(adapter_name)

    async def get_relevant_context(self, query: str, adapter_names: List[str] = None,
                                 adapter_name: str = None, api_key: Optional[str] = None,
                                 **kwargs) -> List[Dict[str, Any]]:
        """
        Get relevant context from adapters with fault tolerance.
        
        This is the main entry point that provides parallel execution
        and circuit breaker protection when enabled.
        """
        # Determine which adapters to use
        if adapter_names:
            target_adapters = adapter_names
        elif adapter_name:
            target_adapters = [adapter_name]
        else:
            target_adapters = self.get_available_adapters()
        
        if not target_adapters:
            logger.warning("No adapters specified")
            return []
        
        # Fault tolerance is always enabled - use parallel executor
        if not self.parallel_executor:
            logger.error("Parallel executor not initialized!")
            return await self._sequential_execution(query, target_adapters[0], api_key, **kwargs)
        
        # Use parallel executor for fault-tolerant execution
        logger.debug(f"Executing {len(target_adapters)} adapters in parallel")
        results = await self.parallel_executor.execute_adapters(
            query, target_adapters, api_key, **kwargs
        )
        
        # Combine results from successful adapters
        combined_context = []
        for result in results:
            if result.success and result.data:
                # Add adapter source information
                for item in result.data:
                    item_with_source = item.copy() if isinstance(item, dict) else {"content": item}
                    item_with_source["source_adapter"] = result.adapter_name
                    combined_context.append(item_with_source)
        
        logger.info(f"Retrieved {len(combined_context)} context items from "
                   f"{sum(1 for r in results if r.success)} successful adapters")
        
        return combined_context
    
    async def _sequential_execution(self, query: str, adapter_name: str,
                                  api_key: Optional[str] = None, **kwargs) -> List[Dict[str, Any]]:
        """Fallback to sequential execution when fault tolerance is disabled"""
        try:
            adapter = await self.get_adapter(adapter_name)
            return await adapter.get_relevant_context(query=query, api_key=api_key, **kwargs)
        except Exception as e:
            logger.error(f"Error in sequential execution for adapter {adapter_name}: {e}")
            return []
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health status of the adapter system"""
        health = {
            "fault_tolerance_enabled": self.fault_tolerance_enabled,
            "available_adapters": self.get_available_adapters(),
            "cached_adapters": self.base_adapter_manager.get_cached_adapters()
        }
        
        if self.parallel_executor:
            health["circuit_breakers"] = self.parallel_executor.get_circuit_breaker_status()
        
        return health
    
    def reset_circuit_breaker(self, adapter_name: str):
        """Reset circuit breaker for a specific adapter"""
        if self.parallel_executor:
            self.parallel_executor.reset_circuit_breaker(adapter_name)
        else:
            logger.warning("Parallel executor not available, cannot reset circuit breaker")
    
    async def preload_all_adapters(self, timeout_per_adapter: float = 30.0) -> Dict[str, Any]:
        """Preload all adapters"""
        return await self.base_adapter_manager.preload_all_adapters(timeout_per_adapter)
    
    async def reload_adapters(self, config: Dict[str, Any], adapter_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Reload adapters via base adapter manager.

        Args:
            config: The new configuration dictionary containing adapter configs
            adapter_name: Optional name of specific adapter to reload. If None, reloads all adapters.

        Returns:
            Summary dict with reload results
        """
        return await self.base_adapter_manager.reload_adapter_configs(config, adapter_name)

    async def reload_templates(self, adapter_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Reload templates for intent adapters via base adapter manager.

        Args:
            adapter_name: Optional name of specific adapter to reload templates for.
                         If None, reloads templates for all cached intent adapters.

        Returns:
            Summary dict with reload results
        """
        return await self.base_adapter_manager.reload_templates(adapter_name)

    async def cleanup(self):
        """Cleanup resources"""
        if self.parallel_executor:
            await self.parallel_executor.cleanup()

        # Cleanup base adapter manager
        await self.base_adapter_manager.close()

# Proxy class for backward compatibility
class FaultTolerantAdapterProxy:
    """
    Proxy that provides the retriever interface for backward compatibility.
    """
    
    def __init__(self, fault_tolerant_manager: FaultTolerantAdapterManager):
        self.manager = fault_tolerant_manager
    
    async def get_relevant_context(self, query: str, adapter_name: str = None,
                                 adapter_names: List[str] = None,
                                 api_key: Optional[str] = None,
                                 **kwargs) -> List[Dict[str, Any]]:
        """Get relevant context through the fault-tolerant manager"""
        return await self.manager.get_relevant_context(
            query=query,
            adapter_names=adapter_names,
            adapter_name=adapter_name,
            api_key=api_key,
            **kwargs
        )
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health status"""
        return self.manager.get_health_status()