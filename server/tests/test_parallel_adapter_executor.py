"""
Tests for the Parallel Adapter Executor
=======================================

This script tests the parallel adapter execution functionality to ensure
proper parallel execution and circuit breaker integration.
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import pytest
import pytest_asyncio

# Get the directory of this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Add server directory to Python path
SERVER_DIR = SCRIPT_DIR.parent
sys.path.append(str(SERVER_DIR))

from services.parallel_adapter_executor import (
    ParallelAdapterExecutor,
    SimpleCircuitBreaker,
    AdapterResult,
    CircuitState
)
from services.dynamic_adapter_manager import DynamicAdapterManager

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
            'recovery_timeout': 1.0,
            'success_threshold': 2,
            'timeout': 2.0
        },
        'execution': {
            'strategy': 'all',
            'timeout': 5.0,
            'max_concurrent_adapters': 3
        }
    },
    'adapters': [
        {
            'name': 'adapter1',
            'type': 'retriever',
            'datasource': 'test',
            'implementation': 'test.MockRetriever'
        },
        {
            'name': 'adapter2',
            'type': 'retriever',
            'datasource': 'test',
            'implementation': 'test.MockRetriever'
        }
    ]
}


class MockAdapter:
    """Mock adapter for testing"""
    
    def __init__(self, name: str, delay: float = 0.1, should_fail: bool = False):
        self.name = name
        self.delay = delay
        self.should_fail = should_fail
        self.call_count = 0
    
    async def get_relevant_context(self, query: str, **kwargs):
        """Mock get_relevant_context method"""
        self.call_count += 1
        
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        
        if self.should_fail:
            raise ValueError(f"Mock adapter {self.name} failure")
        
        return [
            {
                'content': f'Result from {self.name}',
                'metadata': {'adapter': self.name, 'query': query},
                'score': 0.8
            }
        ]


class MockAdapterManager:
    """Mock adapter manager for testing"""
    
    def __init__(self):
        self.adapters = {}
    
    def add_adapter(self, name: str, adapter: MockAdapter):
        """Add a mock adapter"""
        self.adapters[name] = adapter
    
    async def get_adapter(self, name: str):
        """Get a mock adapter"""
        if name not in self.adapters:
            raise ValueError(f"Adapter {name} not found")
        return self.adapters[name]
    
    def get_available_adapters(self):
        """Get list of available adapters"""
        return list(self.adapters.keys())


@pytest.fixture
def mock_adapter_manager():
    """Create a mock adapter manager for testing"""
    manager = MockAdapterManager()
    manager.add_adapter("adapter1", MockAdapter("adapter1", delay=0.1))
    manager.add_adapter("adapter2", MockAdapter("adapter2", delay=0.2))
    manager.add_adapter("adapter3", MockAdapter("adapter3", delay=0.1))
    return manager


@pytest.fixture
def parallel_executor(mock_adapter_manager):
    """Create a ParallelAdapterExecutor for testing"""
    return ParallelAdapterExecutor(mock_adapter_manager, TEST_CONFIG)


class TestSimpleCircuitBreaker:
    """Test SimpleCircuitBreaker class"""
    
    def test_initialization(self):
        """Test circuit breaker initialization"""
        cb = SimpleCircuitBreaker("test-adapter")
        
        assert cb.adapter_name == "test-adapter"
        assert cb.state == CircuitState.CLOSED
        assert cb.stats.failure_count == 0
        assert cb.stats.success_count == 0
    
    def test_record_success(self):
        """Test recording successful operations"""
        cb = SimpleCircuitBreaker("test-adapter")
        
        cb.record_success(0.5)
        
        assert cb.stats.success_count == 1
        assert cb.stats.consecutive_successes == 1
        assert cb.stats.consecutive_failures == 0
        assert cb.state == CircuitState.CLOSED
    
    def test_record_failure(self):
        """Test recording failed operations"""
        cb = SimpleCircuitBreaker("test-adapter", failure_threshold=2)
        
        # First failure
        cb.record_failure(Exception("test error"))
        assert cb.stats.failure_count == 1
        assert cb.stats.consecutive_failures == 1
        assert cb.state == CircuitState.CLOSED
        
        # Second failure should open circuit
        cb.record_failure(Exception("test error"))
        assert cb.stats.failure_count == 2
        assert cb.stats.consecutive_failures == 2
        assert cb.state == CircuitState.OPEN
    
    def test_circuit_recovery(self):
        """Test circuit recovery after timeout"""
        cb = SimpleCircuitBreaker("test-adapter", failure_threshold=1, recovery_timeout=0.1, success_threshold=1)
        
        # Open the circuit
        cb.record_failure(Exception("test error"))
        assert cb.state == CircuitState.OPEN
        
        # Should still be open immediately
        assert not cb.can_execute()
        
        # Wait for recovery timeout
        time.sleep(0.2)
        
        # Should transition to half-open
        assert cb.can_execute()
        assert cb.state == CircuitState.HALF_OPEN
        
        # Success should close circuit (with success_threshold=1)
        cb.record_success(0.1)
        assert cb.state == CircuitState.CLOSED
    
    def test_can_execute(self):
        """Test can_execute logic"""
        cb = SimpleCircuitBreaker("test-adapter", failure_threshold=1)
        
        # Initially should be executable
        assert cb.can_execute()
        
        # After failure, should open
        cb.record_failure(Exception("test error"))
        assert not cb.can_execute()
    
    def test_reset(self):
        """Test circuit breaker reset"""
        cb = SimpleCircuitBreaker("test-adapter", failure_threshold=1)
        
        # Open the circuit
        cb.record_failure(Exception("test error"))
        assert cb.state == CircuitState.OPEN
        
        # Reset
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.stats.failure_count == 0
        assert cb.stats.success_count == 0


class TestAdapterResult:
    """Test AdapterResult class"""
    
    def test_initialization(self):
        """Test adapter result initialization"""
        result = AdapterResult(
            adapter_name="test-adapter",
            success=True,
            data=["test data"],
            execution_time=0.5
        )
        
        assert result.adapter_name == "test-adapter"
        assert result.success is True
        assert result.data == ["test data"]
        assert result.error is None
        assert result.execution_time == 0.5
    
    def test_failure_result(self):
        """Test adapter result for failures"""
        error = ValueError("test error")
        result = AdapterResult(
            adapter_name="test-adapter",
            success=False,
            error=error,
            execution_time=0.2
        )
        
        assert result.adapter_name == "test-adapter"
        assert result.success is False
        assert result.data is None
        assert result.error == error
        assert result.execution_time == 0.2


class TestParallelAdapterExecutor:
    """Test ParallelAdapterExecutor class"""
    
    def test_initialization(self, parallel_executor):
        """Test executor initialization"""
        assert parallel_executor.adapter_manager is not None
        assert parallel_executor.config == TEST_CONFIG
        assert parallel_executor.timeout == 5.0
        assert parallel_executor.max_concurrent == 3
        assert parallel_executor.strategy == "all"
        assert len(parallel_executor.circuit_breakers) == 0
    
    def test_get_circuit_breaker(self, parallel_executor):
        """Test getting circuit breakers"""
        cb1 = parallel_executor._get_circuit_breaker("adapter1")
        cb2 = parallel_executor._get_circuit_breaker("adapter1")
        cb3 = parallel_executor._get_circuit_breaker("adapter2")
        
        # Same adapter should return same circuit breaker
        assert cb1 is cb2
        assert cb1.adapter_name == "adapter1"
        
        # Different adapter should return different circuit breaker
        assert cb1 is not cb3
        assert cb3.adapter_name == "adapter2"
        
        # Should be stored in dict
        assert len(parallel_executor.circuit_breakers) == 2
    
    @pytest.mark.asyncio
    async def test_execute_single_adapter_success(self, parallel_executor):
        """Test executing a single adapter successfully"""
        result = await parallel_executor._execute_single_adapter("adapter1", "test query")
        
        assert result.adapter_name == "adapter1"
        assert result.success is True
        assert result.data is not None
        assert len(result.data) == 1
        assert result.data[0]['content'] == "Result from adapter1"
        assert result.error is None
        assert result.execution_time > 0
    
    @pytest.mark.asyncio
    async def test_execute_single_adapter_failure(self, parallel_executor, mock_adapter_manager):
        """Test executing a single adapter that fails"""
        # Add a failing adapter
        mock_adapter_manager.add_adapter("failing_adapter", MockAdapter("failing_adapter", should_fail=True))
        
        result = await parallel_executor._execute_single_adapter("failing_adapter", "test query")
        
        assert result.adapter_name == "failing_adapter"
        assert result.success is False
        assert result.data is None
        assert result.error is not None
        assert isinstance(result.error, ValueError)
        assert result.execution_time > 0
    
    @pytest.mark.asyncio
    async def test_execute_single_adapter_timeout(self, parallel_executor, mock_adapter_manager):
        """Test executing a single adapter that times out"""
        # Add a slow adapter that should timeout
        mock_adapter_manager.add_adapter("slow_adapter", MockAdapter("slow_adapter", delay=10.0))
        
        result = await parallel_executor._execute_single_adapter("slow_adapter", "test query")
        
        assert result.adapter_name == "slow_adapter"
        assert result.success is False
        assert result.data is None
        assert result.error is not None
        assert "timeout" in str(result.error).lower()
    
    @pytest.mark.asyncio
    async def test_execute_single_adapter_circuit_open(self, parallel_executor, mock_adapter_manager):
        """Test executing an adapter with open circuit"""
        # Add a failing adapter
        mock_adapter_manager.add_adapter("failing_adapter", MockAdapter("failing_adapter", should_fail=True))
        
        # Create a circuit breaker with lower failure threshold for testing
        cb = parallel_executor._get_circuit_breaker("failing_adapter")
        cb.failure_threshold = 3 # Override to 3 for this test
        
        # Execute failures to open circuit (3 failures with threshold=3)
        for _ in range(3):
            result = await parallel_executor._execute_single_adapter("failing_adapter", "test query")
            assert not result.success
        
        # Circuit should now be open, next call should fail fast
        result = await parallel_executor._execute_single_adapter("failing_adapter", "test query")
        
        assert result.adapter_name == "failing_adapter"
        assert result.success is False
        assert result.data is None
        assert "circuit" in str(result.error).lower()
        assert result.execution_time < 0.1 # Should fail fast
    
    @pytest.mark.asyncio
    async def test_execute_adapters_all_strategy(self, parallel_executor):
        """Test executing multiple adapters with 'all' strategy"""
        adapter_names = ["adapter1", "adapter2", "adapter3"]
        
        start_time = time.time()
        results = await parallel_executor.execute_adapters("test query", adapter_names)
        execution_time = time.time() - start_time
        
        # Should execute all adapters
        assert len(results) == 3
        
        # All should be successful
        successful_results = [r for r in results if r.success]
        assert len(successful_results) == 3
        
        # Should execute in parallel (total time < sum of individual times)
        assert execution_time < 0.5  # All adapters run in parallel
        
        # Each result should have correct data
        for result in results:
            assert result.success
            assert result.data is not None
            assert len(result.data) == 1
            assert result.adapter_name in adapter_names
    
    @pytest.mark.asyncio
    async def test_execute_adapters_first_success_strategy(self, parallel_executor):
        """Test executing adapters with 'first_success' strategy"""
        parallel_executor.strategy = "first_success"
        adapter_names = ["adapter1", "adapter2", "adapter3"]
        
        results = await parallel_executor.execute_adapters("test query", adapter_names)
        
        # Should return as soon as first adapter succeeds
        # Since adapter1 is fastest (0.1s delay), it should be the only result
        assert len(results) >= 1
        
        # First result should be successful
        assert results[0].success
        assert results[0].data is not None
    
    @pytest.mark.asyncio
    async def test_execute_adapters_best_effort_strategy(self, parallel_executor):
        """Test executing adapters with 'best_effort' strategy"""
        parallel_executor.strategy = "best_effort"
        adapter_names = ["adapter1", "adapter2", "adapter3"]
        
        results = await parallel_executor.execute_adapters("test query", adapter_names)
        
        # Should return whatever completes within timeout
        assert len(results) >= 1
        assert len(results) <= 3
        
        # All returned results should be successful
        for result in results:
            assert result.success
    
    @pytest.mark.asyncio
    async def test_execute_adapters_with_failures(self, parallel_executor, mock_adapter_manager):
        """Test executing adapters with some failures"""
        # Add a failing adapter
        mock_adapter_manager.add_adapter("failing_adapter", MockAdapter("failing_adapter", should_fail=True))
        
        adapter_names = ["adapter1", "failing_adapter", "adapter2"]
        results = await parallel_executor.execute_adapters("test query", adapter_names)
        
        assert len(results) == 3
        
        # Check results
        successful_results = [r for r in results if r.success]
        failed_results = [r for r in results if not r.success]
        
        assert len(successful_results) == 2
        assert len(failed_results) == 1
        assert failed_results[0].adapter_name == "failing_adapter"
    
    @pytest.mark.asyncio
    async def test_combine_results(self, parallel_executor):
        """Test result combination"""
        # Create test results
        results = [
            AdapterResult("adapter1", True, [{"content": "result1", "score": 0.9}], 0.1),
            AdapterResult("adapter2", True, [{"content": "result2", "score": 0.8}], 0.2),
            AdapterResult("adapter3", False, None, ValueError("error"), 0.1)
        ]
        
        combined = parallel_executor._combine_results(results)
        
        # Should only include successful results
        assert len(combined) == 2
        assert combined[0]["content"] == "result1"
        assert combined[1]["content"] == "result2"
        
        # Should preserve metadata
        assert "adapter_name" in combined[0]
        assert "execution_time" in combined[0]
    
    def test_get_circuit_breaker_states(self, parallel_executor):
        """Test getting circuit breaker states"""
        # Create some circuit breakers
        parallel_executor._get_circuit_breaker("adapter1")
        parallel_executor._get_circuit_breaker("adapter2")
        
        states = parallel_executor.get_circuit_breaker_states()
        
        assert "adapter1" in states
        assert "adapter2" in states
        assert states["adapter1"]["state"] == "closed"
        assert states["adapter2"]["state"] == "closed"
    
    def test_reset_circuit_breaker(self, parallel_executor):
        """Test resetting circuit breakers"""
        cb = parallel_executor._get_circuit_breaker("adapter1")
        
        # Override failure threshold to 3 for this test
        cb.failure_threshold = 3        
        # Open the circuit (3 failures with threshold=3)
        cb.record_failure(Exception("test"))
        cb.record_failure(Exception("test"))
        cb.record_failure(Exception("test"))
        assert cb.state == CircuitState.OPEN
        
        # Reset through executor
        parallel_executor.reset_circuit_breaker("adapter1")
        assert cb.state == CircuitState.CLOSED
    
    def test_get_health_status(self, parallel_executor):
        """Test getting health status"""
        # Create some circuit breakers
        parallel_executor._get_circuit_breaker("adapter1")
        parallel_executor._get_circuit_breaker("adapter2")
        
        health_status = parallel_executor.get_health_status()
        
        assert "total_adapters" in health_status
        assert "healthy_adapters" in health_status
        assert "circuit_breakers" in health_status
        assert health_status["total_adapters"] == 2
        assert health_status["healthy_adapters"] == 2
    
    @pytest.mark.asyncio
    async def test_cleanup(self, parallel_executor):
        """Test executor cleanup"""
        # Create some circuit breakers
        parallel_executor._get_circuit_breaker("adapter1")
        parallel_executor._get_circuit_breaker("adapter2")
        
        # Cleanup should not raise errors
        await parallel_executor.cleanup()
    
    @pytest.mark.asyncio
    async def test_concurrent_execution_limit(self, parallel_executor, mock_adapter_manager):
        """Test that concurrent execution respects limits"""
        # Set low concurrent limit
        parallel_executor.max_concurrent = 2
        
        # Add more adapters than the limit
        for i in range(5):
            mock_adapter_manager.add_adapter(f"adapter{i+10}", MockAdapter(f"adapter{i+10}", delay=0.2))
        
        adapter_names = [f"adapter{i+10}" for i in range(5)]
        
        start_time = time.time()
        results = await parallel_executor.execute_adapters("test query", adapter_names)
        execution_time = time.time() - start_time
        
        # Should execute all adapters
        assert len(results) == 5
        
        # Should take longer due to batching (not all at once)
        # With limit 2 and 5 adapters, should take at least 2 batches
        assert execution_time > 0.3  # Should take time for batching


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 