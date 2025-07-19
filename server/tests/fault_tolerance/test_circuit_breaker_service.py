"""
Tests for the Circuit Breaker Service
=====================================

This script tests the circuit breaker functionality to ensure fault tolerance
works correctly in the simplified fault tolerance system.
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
import pytest

# Get the directory of this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Add server directory to Python path (go up two levels: fault_tolerance -> tests -> server)
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.circuit_breaker import (
    CircuitBreakerService, 
    CircuitBreakerConfig, 
    CircuitBreakerManager,
    AdapterCircuitBreaker,
    CircuitState,
    CircuitOpenError,
    OperationTimeoutError
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Test configuration
TEST_CONFIG = {
    'general': {'verbose': True},
    'fault_tolerance': {
        'enabled': True,
        'circuit_breaker': {
            'failure_threshold': 3,
            'recovery_timeout': 5.0,
            'success_threshold': 2,
            'timeout': 10.0,
            'failure_window': 60.0,
            'health_check_interval': 1.0,
            'health_check_timeout': 2.0,
            'use_thread_isolation': True,
            'use_process_isolation': False,
            'max_workers': 2,
            'max_retries': 1,
            'retry_delay': 0.1,
            'retry_backoff': 1.5,
            'enable_metrics': False, # Disable metrics to avoid async issues in tests
            'metrics_window': 300.0
        }
    }
}


@pytest.fixture
def circuit_breaker_config():
    """Create a CircuitBreakerConfig for testing"""
    return CircuitBreakerConfig(
        operation_timeout=2.0,
        failure_threshold=3,
        recovery_timeout=1.0,
        success_threshold=2,
        failure_window=60.0,
        health_check_interval=1.0,
        max_workers=2,
        max_retries=1,
        retry_delay=0.1,
        enable_metrics=False # Disable metrics to avoid async issues
    )


@pytest.fixture
def circuit_breaker_service():
    """Create a CircuitBreakerService for testing"""
    return CircuitBreakerService(TEST_CONFIG)


@pytest.fixture
def adapter_circuit_breaker(circuit_breaker_config):
    """Create an AdapterCircuitBreaker for testing"""
    return AdapterCircuitBreaker("test-adapter", circuit_breaker_config)


class TestCircuitBreakerConfig:
    """Test CircuitBreakerConfig class"""
    
    def test_default_values(self):
        """Test that default configuration values are set correctly"""
        config = CircuitBreakerConfig()
        
        assert config.operation_timeout == 30.0
        assert config.failure_threshold == 5
        assert config.recovery_timeout == 60.0
        assert config.success_threshold == 3
        assert config.use_thread_isolation is True
        assert config.enable_metrics is True
    
    def test_custom_values(self):
        """Test that custom configuration values are applied correctly"""
        config = CircuitBreakerConfig(
            operation_timeout=10.0,
            failure_threshold=2,
            recovery_timeout=30.0
        )
        
        assert config.operation_timeout == 10.0
        assert config.failure_threshold == 2
        assert config.recovery_timeout == 30.0


class TestAdapterCircuitBreaker:
    """Test AdapterCircuitBreaker class"""
    
    def test_initialization(self, adapter_circuit_breaker):
        """Test circuit breaker initialization"""
        assert adapter_circuit_breaker.adapter_name == "test-adapter"
        assert adapter_circuit_breaker.state.state == CircuitState.CLOSED
        assert adapter_circuit_breaker.metrics.total_calls == 0
    
    @pytest.mark.asyncio
    async def test_successful_operation(self, adapter_circuit_breaker):
        """Test successful operation execution"""
        async def successful_operation():
            await asyncio.sleep(0.1)
            return "success"
        
        result = await adapter_circuit_breaker.execute_operation(successful_operation)
        
        assert result == "success"
        assert adapter_circuit_breaker.state.state == CircuitState.CLOSED
        assert adapter_circuit_breaker.metrics.total_calls == 1
        assert adapter_circuit_breaker.metrics.successful_calls == 1
        assert adapter_circuit_breaker.metrics.failed_calls == 0
    
    @pytest.mark.asyncio
    async def test_failed_operation(self, adapter_circuit_breaker):
        """Test failed operation execution"""
        async def failing_operation():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            await adapter_circuit_breaker.execute_operation(failing_operation)
        
        assert adapter_circuit_breaker.state.state == CircuitState.CLOSED
        assert adapter_circuit_breaker.metrics.total_calls == 1
        assert adapter_circuit_breaker.metrics.successful_calls == 0
        assert adapter_circuit_breaker.metrics.failed_calls == 1
        assert adapter_circuit_breaker.metrics.consecutive_failures == 1
    
    @pytest.mark.asyncio
    async def test_circuit_opens_after_failures(self, adapter_circuit_breaker):
        """Test that circuit opens after threshold failures"""
        async def failing_operation():
            raise ValueError("Test error")
        
        # Execute failing operations up to threshold
        for i in range(3):
            with pytest.raises(ValueError):
                await adapter_circuit_breaker.execute_operation(failing_operation)
        
        # Circuit should now be open
        assert adapter_circuit_breaker.state.state == CircuitState.OPEN
        assert adapter_circuit_breaker.metrics.failed_calls == 3
        
        # Next operation should fail fast
        with pytest.raises(CircuitOpenError):
            await adapter_circuit_breaker.execute_operation(failing_operation)
    
    @pytest.mark.asyncio
    async def test_timeout_operation(self, adapter_circuit_breaker):
        """Test operation timeout"""
        async def slow_operation():
            await asyncio.sleep(5.0)  # Longer than timeout
            return "too_slow"
        
        with pytest.raises(OperationTimeoutError):
            await adapter_circuit_breaker.execute_operation(slow_operation)
        
        assert adapter_circuit_breaker.metrics.timeout_calls == 1
        assert adapter_circuit_breaker.metrics.failed_calls == 0
    
    @pytest.mark.asyncio
    async def test_circuit_recovery(self, adapter_circuit_breaker):
        """Test circuit recovery from open to closed state"""
        async def failing_operation():
            raise ValueError("Test error")
        
        async def successful_operation():
            return "success"
        
        # Open the circuit
        for i in range(3):
            with pytest.raises(ValueError):
                await adapter_circuit_breaker.execute_operation(failing_operation)
        
        assert adapter_circuit_breaker.state.state == CircuitState.OPEN
        
        # Wait for recovery timeout
        await asyncio.sleep(1.1)
        
        # Next operation should transition to half-open
        result = await adapter_circuit_breaker.execute_operation(successful_operation)
        assert result == "success"
        assert adapter_circuit_breaker.state.state == CircuitState.HALF_OPEN
        
        # Another success should close the circuit
        result = await adapter_circuit_breaker.execute_operation(successful_operation)
        assert result == "success"
        assert adapter_circuit_breaker.state.state == CircuitState.CLOSED
    
    def test_get_health_status(self, adapter_circuit_breaker):
        """Test health status reporting"""
        health_status = adapter_circuit_breaker.get_health_status()
        
        assert health_status["adapter_name"] == "test-adapter"
        assert health_status["circuit_state"] == "closed"
        assert health_status["success_rate"] == 0.0
        assert health_status["total_calls"] == 0
    
    def test_force_open_close(self, adapter_circuit_breaker):
        """Test manual circuit control"""
        # Force open
        adapter_circuit_breaker.force_open()
        assert adapter_circuit_breaker.state.state == CircuitState.OPEN
        
        # Force close
        adapter_circuit_breaker.force_close()
        assert adapter_circuit_breaker.state.state == CircuitState.CLOSED


class TestCircuitBreakerManager:
    """Test CircuitBreakerManager class"""
    
    def test_initialization(self, circuit_breaker_config):
        """Test manager initialization"""
        manager = CircuitBreakerManager(circuit_breaker_config)
        
        assert len(manager.circuit_breakers) == 0
        assert manager.config == circuit_breaker_config
    
    def test_get_circuit_breaker(self, circuit_breaker_config):
        """Test getting/creating circuit breakers"""
        manager = CircuitBreakerManager(circuit_breaker_config)
        
        # Get first circuit breaker
        cb1 = manager.get_circuit_breaker("adapter1")
        assert cb1.adapter_name == "adapter1"
        assert len(manager.circuit_breakers) == 1
        
        # Get same circuit breaker again
        cb2 = manager.get_circuit_breaker("adapter1")
        assert cb1 is cb2
        
        # Get different circuit breaker
        cb3 = manager.get_circuit_breaker("adapter2")
        assert cb3.adapter_name == "adapter2"
        assert len(manager.circuit_breakers) == 2
    
    def test_get_all_health_status(self, circuit_breaker_config):
        """Test getting health status for all adapters"""
        manager = CircuitBreakerManager(circuit_breaker_config)
        
        # Create some circuit breakers
        manager.get_circuit_breaker("adapter1")
        manager.get_circuit_breaker("adapter2")
        
        health_status = manager.get_all_health_status()
        
        assert "adapter1" in health_status
        assert "adapter2" in health_status
        assert health_status["adapter1"]["adapter_name"] == "adapter1"
        assert health_status["adapter2"]["adapter_name"] == "adapter2"
    
    def test_get_system_health_summary(self, circuit_breaker_config):
        """Test system health summary"""
        manager = CircuitBreakerManager(circuit_breaker_config)
        
        # Empty system
        summary = manager.get_system_health_summary()
        assert summary["total_adapters"] == 0
        assert summary["system_health"] == "unknown"
        
        # Add healthy adapters
        manager.get_circuit_breaker("adapter1")
        manager.get_circuit_breaker("adapter2")
        
        summary = manager.get_system_health_summary()
        assert summary["total_adapters"] == 2
        assert summary["healthy_adapters"] == 2
        assert summary["unhealthy_adapters"] == 0
        assert summary["system_health"] == "healthy"


class TestCircuitBreakerService:
    """Test CircuitBreakerService class"""
    
    def test_initialization(self, circuit_breaker_service):
        """Test service initialization"""
        assert circuit_breaker_service.config == TEST_CONFIG
        assert circuit_breaker_service.circuit_breaker_manager is not None
    
    def test_get_circuit_breaker(self, circuit_breaker_service):
        """Test getting circuit breakers through service"""
        cb = circuit_breaker_service.get_circuit_breaker("test-adapter")
        
        assert cb.adapter_name == "test-adapter"
        assert cb.state.state == CircuitState.CLOSED
    
    def test_get_circuit_breaker_states(self, circuit_breaker_service):
        """Test getting circuit breaker states"""
        # Create some circuit breakers
        circuit_breaker_service.get_circuit_breaker("adapter1")
        circuit_breaker_service.get_circuit_breaker("adapter2")
        
        states = circuit_breaker_service.get_circuit_breaker_states()
        
        assert "adapter1" in states
        assert "adapter2" in states
        assert states["adapter1"]["circuit_state"] == "closed"
        assert states["adapter2"]["circuit_state"] == "closed"
    
    def test_reset_circuit_breaker(self, circuit_breaker_service):
        """Test resetting individual circuit breakers"""
        cb = circuit_breaker_service.get_circuit_breaker("test-adapter")
        
        # Force open the circuit
        cb.force_open()
        assert cb.state.state == CircuitState.OPEN
        
        # Reset through service
        circuit_breaker_service.reset_circuit_breaker("test-adapter")
        assert cb.state.state == CircuitState.CLOSED
    
    def test_reset_all_circuit_breakers(self, circuit_breaker_service):
        """Test resetting all circuit breakers"""
        # Create and open some circuit breakers
        cb1 = circuit_breaker_service.get_circuit_breaker("adapter1")
        cb2 = circuit_breaker_service.get_circuit_breaker("adapter2")
        
        cb1.force_open()
        cb2.force_open()
        
        assert cb1.state.state == CircuitState.OPEN
        assert cb2.state.state == CircuitState.OPEN
        
        # Reset all
        circuit_breaker_service.reset_all_circuit_breakers()
        
        assert cb1.state.state == CircuitState.CLOSED
        assert cb2.state.state == CircuitState.CLOSED
    
    def test_get_health_status(self, circuit_breaker_service):
        """Test getting overall health status"""
        # Create some circuit breakers
        circuit_breaker_service.get_circuit_breaker("adapter1")
        circuit_breaker_service.get_circuit_breaker("adapter2")
        
        health_status = circuit_breaker_service.get_health_status()
        
        assert "total_adapters" in health_status
        assert "healthy_adapters" in health_status
        assert "unhealthy_adapters" in health_status
        assert "system_health" in health_status
        assert health_status["total_adapters"] == 2
        assert health_status["system_health"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_cleanup(self, circuit_breaker_service):
        """Test service cleanup"""
        # Create some circuit breakers
        circuit_breaker_service.get_circuit_breaker("adapter1")
        circuit_breaker_service.get_circuit_breaker("adapter2")
        
        # Cleanup should not raise errors
        await circuit_breaker_service.cleanup()


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 