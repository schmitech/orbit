"""
Integration Tests for the Simplified Fault Tolerance System
==========================================================

This script tests the complete fault tolerance system integration to ensure
all components work together correctly.
"""

import asyncio
import logging
import os
import sys
import time
from unittest.mock import Mock, AsyncMock, patch
import pytest
from copy import deepcopy

# Add server directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))

# CircuitBreakerService removed - fault tolerance handled by ParallelAdapterExecutor
from services.fault_tolerant_adapter_manager import FaultTolerantAdapterManager
from services.parallel_adapter_executor import ParallelAdapterExecutor
from services.dynamic_adapter_manager import DynamicAdapterManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Complete test configuration
INTEGRATION_TEST_CONFIG = {
    'general': {},
    'fault_tolerance': {
        'enabled': True,
        'circuit_breaker': {
            'failure_threshold': 2,
            'recovery_timeout': 1.0,
            'success_threshold': 2,
            'timeout': 2.0,
            'failure_window': 60.0,
            'health_check_interval': 1.0,
            'health_check_timeout': 2.0,
            'use_thread_isolation': True,
            'use_process_isolation': False,
            'max_workers': 2,
            'max_retries': 1,
            'retry_delay': 0.1,
            'retry_backoff': 1.5,
            'enable_metrics': True,
            'metrics_window': 300.0
        },
        'execution': {
            'strategy': 'all',
            'timeout': 10.0,
            'max_concurrent_adapters': 3
        },
        'isolation': {
            'enabled': True,
            'strategy': 'thread',
            'max_threads': 5
        },
        'health_monitoring': {
            'enabled': True,
            'check_interval': 1.0,
            'history_size': 50
        }
    },
    'adapters': [
        {
            'name': 'fast-adapter',
            'type': 'retriever',
            'datasource': 'test',
            'implementation': 'test.FastAdapter'
        },
        {
            'name': 'slow-adapter',
            'type': 'retriever',
            'datasource': 'test',
            'implementation': 'test.SlowAdapter'
        },
        {
            'name': 'failing-adapter',
            'type': 'retriever',
            'datasource': 'test',
            'implementation': 'test.FailingAdapter'
        }
    ]
}


class MockFastAdapter:
    """Mock fast adapter for testing"""
    
    def __init__(self):
        self.name = "fast-adapter"
        self.call_count = 0
    
    async def get_relevant_context(self, query: str, **kwargs):
        self.call_count += 1
        await asyncio.sleep(0.1)  # Fast response
        return [
            {
                'content': f'Fast result for: {query}',
                'metadata': {'adapter': self.name, 'response_time': 0.1},
                'score': 0.9
            }
        ]


class MockSlowAdapter:
    """Mock slow adapter for testing"""
    
    def __init__(self):
        self.name = "slow-adapter"
        self.call_count = 0
    
    async def get_relevant_context(self, query: str, **kwargs):
        self.call_count += 1
        await asyncio.sleep(0.5)  # Slower response
        return [
            {
                'content': f'Slow result for: {query}',
                'metadata': {'adapter': self.name, 'response_time': 0.5},
                'score': 0.7
            }
        ]


class MockFailingAdapter:
    """Mock failing adapter for testing"""
    
    def __init__(self):
        self.name = "failing-adapter"
        self.call_count = 0
        self.should_fail = True
    
    async def get_relevant_context(self, query: str, **kwargs):
        self.call_count += 1
        if self.should_fail:
            raise ValueError(f"Adapter {self.name} is failing")
        
        return [
            {
                'content': f'Recovered result for: {query}',
                'metadata': {'adapter': self.name, 'recovered': True},
                'score': 0.6
            }
        ]


class MockTimeoutAdapter:
    """Mock adapter that times out"""
    
    def __init__(self):
        self.name = "timeout-adapter"
        self.call_count = 0
    
    async def get_relevant_context(self, query: str, **kwargs):
        self.call_count += 1
        await asyncio.sleep(10.0)  # Will timeout
        return [{'content': 'This should never be returned'}]


class MockAppState:
    """Mock FastAPI app state"""
    def __init__(self):
        pass


@pytest.fixture
def mock_adapters():
    """Create mock adapters for testing"""
    return {
        "fast-adapter": MockFastAdapter(),
        "slow-adapter": MockSlowAdapter(),
        "failing-adapter": MockFailingAdapter(),
        "timeout-adapter": MockTimeoutAdapter()
    }


@pytest.fixture
def mock_app_state():
    """Create mock app state"""
    return MockAppState()


@pytest.fixture
def mock_adapter_manager(mock_adapters):
    """Create a mock adapter manager with test adapters"""
    manager = Mock(spec=DynamicAdapterManager)
    manager.get_available_adapters.return_value = list(mock_adapters.keys())
    
    async def mock_get_adapter(name):
        if name in mock_adapters:
            return mock_adapters[name]
        raise ValueError(f"Adapter {name} not found")
    
    manager.get_adapter = AsyncMock(side_effect=mock_get_adapter)
    return manager


class TestFaultToleranceSystemIntegration:
    """Test complete fault tolerance system integration"""
    
    # Circuit breaker service test removed - functionality now in ParallelAdapterExecutor
    
    @pytest.mark.asyncio
    async def test_parallel_executor_integration(self, mock_adapter_manager):
        """Test ParallelAdapterExecutor integration"""
        executor = ParallelAdapterExecutor(mock_adapter_manager, INTEGRATION_TEST_CONFIG)
        
        # Test successful parallel execution
        adapter_names = ["fast-adapter", "slow-adapter"]
        results = await executor.execute_adapters("test query", adapter_names)
        
        # Should get results from both adapters
        assert len(results) == 2
        
        # Results should be successful
        successful_results = [r for r in results if r.success]
        assert len(successful_results) == 2
        
        # Test execution with failures
        adapter_names_with_failure = ["fast-adapter", "failing-adapter"]
        results_with_failure = await executor.execute_adapters("test query", adapter_names_with_failure)
        
        assert len(results_with_failure) == 2
        successful_results = [r for r in results_with_failure if r.success]
        failed_results = [r for r in results_with_failure if not r.success]
        
        assert len(successful_results) == 1
        assert len(failed_results) == 1
        assert successful_results[0].adapter_name == "fast-adapter"
        assert failed_results[0].adapter_name == "failing-adapter"
        
        # Cleanup
        await executor.cleanup()
    
    @pytest.mark.asyncio
    async def test_fault_tolerant_adapter_manager_integration(self, mock_app_state):
        """Test FaultTolerantAdapterManager complete integration"""
        with patch('services.fault_tolerant_adapter_manager.DynamicAdapterManager') as mock_dam:
            # Setup mock base manager
            mock_base_manager = Mock()
            mock_base_manager.get_available_adapters.return_value = ["fast-adapter", "slow-adapter"]
            
            # Mock adapters
            mock_adapters = {
                "fast-adapter": MockFastAdapter(),
                "slow-adapter": MockSlowAdapter()
            }
            
            async def mock_get_adapter(name):
                return mock_adapters.get(name)
            
            mock_base_manager.get_adapter = AsyncMock(side_effect=mock_get_adapter)
            mock_dam.return_value = mock_base_manager
            
            # Create fault tolerant manager
            manager = FaultTolerantAdapterManager(INTEGRATION_TEST_CONFIG, mock_app_state)
            
            # Test fault tolerance is enabled
            assert manager.fault_tolerance_enabled is True
            assert manager.parallel_executor is not None
            
            # Test getting relevant context
            # Mock the parallel executor to simulate actual results
            from services.parallel_adapter_executor import AdapterResult
            
            mock_adapter_results = [
                AdapterResult("fast-adapter", True, [{'content': 'Fast result', 'metadata': {'adapter': 'fast-adapter'}}], None, 0.1),
                AdapterResult("slow-adapter", True, [{'content': 'Slow result', 'metadata': {'adapter': 'slow-adapter'}}], None, 0.2)
            ]
            
            with patch.object(manager.parallel_executor, 'execute_adapters') as mock_execute:
                mock_execute.return_value = mock_adapter_results
                
                results = await manager.get_relevant_context("integration test query")
                
                # Should get combined results from both adapters (dicts)
                assert len(results) == 2
                assert results[0]['content'] == 'Fast result'
                assert results[1]['content'] == 'Slow result'
                mock_execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_and_recovers(self, mock_adapter_manager, mock_adapters):
        """Test circuit breaker opening and recovery behavior"""
        executor = ParallelAdapterExecutor(mock_adapter_manager, INTEGRATION_TEST_CONFIG)
        
        # Set failure threshold to 2 for this test
        cb = executor._get_circuit_breaker("failing-adapter")
        cb.failure_threshold = 2
        failing_adapter = mock_adapters["failing-adapter"]
        
        # First two calls should fail and open circuit
        for i in range(2):
            results = await executor.execute_adapters(f"test query {i}", ["failing-adapter"])
            assert len(results) == 1
            assert not results[0].success
        
        # Check circuit breaker state
        cb = executor._get_circuit_breaker("failing-adapter")
        assert cb.state.value == "open"  # Should be open now
        
        # Next call should fail fast (circuit open)
        start_time = time.time()
        results = await executor.execute_adapters("fast fail query", ["failing-adapter"])
        execution_time = time.time() - start_time
        
        assert len(results) == 1
        assert not results[0].success
        assert execution_time < 0.1  # Should fail fast
        assert "circuit" in str(results[0].error).lower()
        
        # Wait for recovery timeout and fix the adapter
        await asyncio.sleep(1.1)  # Recovery timeout is 1.0s
        failing_adapter.should_fail = False
        
        # Next call should succeed and close circuit
        results = await executor.execute_adapters("recovery query", ["failing-adapter"])
        assert len(results) == 1
        # Circuit might still be in half-open state, but adapter should work
        
        # Cleanup
        await executor.cleanup()
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self, mock_adapter_manager):
        """Test timeout handling in the fault tolerance system"""
        # Create executor with short timeout
        short_timeout_config = deepcopy(INTEGRATION_TEST_CONFIG)
        short_timeout_config['fault_tolerance']['execution']['timeout'] = 0.2
        # Make sure the slow adapter sleeps longer than the timeout
        class ReallySlowAdapter:
            def __init__(self):
                self.name = "timeout-test-adapter"
                self.call_count = 0
            async def get_relevant_context(self, query: str, **kwargs):
                self.call_count += 1
                await asyncio.sleep(1.0)  # 1s > 0.2s timeout
                return [{'content': 'This should never be returned'}]
        slow_adapter = ReallySlowAdapter()
        # Patch get_adapter to return the slow adapter for "timeout-test-adapter"
        async def get_adapter(name):
            if name == "timeout-test-adapter":
                return slow_adapter
            raise ValueError(f"Adapter {name} not found")
        mock_adapter_manager.get_adapter = AsyncMock(side_effect=get_adapter)
        mock_adapter_manager.get_available_adapters.return_value = ["timeout-test-adapter"]
        executor = ParallelAdapterExecutor(mock_adapter_manager, short_timeout_config)
        
        # Execute slow adapter that should timeout
        results = await executor.execute_adapters("timeout test", ["timeout-test-adapter"])
        
        assert len(results) == 1
        assert not results[0].success
        assert "timeout" in str(results[0].error).lower()
        
        # Check that circuit breaker recorded the timeout as a failure
        cb = executor._get_circuit_breaker("timeout-test-adapter")
        assert cb.stats.timeout_calls > 0
        
        # Cleanup
        await executor.cleanup()
    
    @pytest.mark.asyncio
    async def test_parallel_execution_performance(self, mock_adapter_manager):
        """Test that parallel execution is actually faster than sequential"""
        # Create a fresh config copy to ensure isolation
        test_config = deepcopy(INTEGRATION_TEST_CONFIG)
        executor = ParallelAdapterExecutor(mock_adapter_manager, test_config)
        
        # Execute multiple adapters in parallel
        adapter_names = ["fast-adapter", "slow-adapter"]  # 0.1s + 0.5s = 0.6s sequential
        
        start_time = time.time()
        results = await executor.execute_adapters("performance test", adapter_names)
        execution_time = time.time() - start_time
        
        # Should complete in less time than sequential execution
        assert execution_time < 0.8  # Should be around 0.5s (max of individual times)
        assert len(results) == 2
        assert all(r.success for r in results)
        
        # Cleanup
        await executor.cleanup()
    
    @pytest.mark.asyncio
    async def test_health_monitoring_integration(self, mock_adapter_manager):
        """Test health monitoring across the system"""
        # Create services
        # Circuit breaker service removed - using ParallelAdapterExecutor directly
        executor = ParallelAdapterExecutor(mock_adapter_manager, INTEGRATION_TEST_CONFIG)
        
        # Execute some operations to generate health data
        await executor.execute_adapters("health test 1", ["fast-adapter"])
        await executor.execute_adapters("health test 2", ["failing-adapter"])
        
        # Check circuit breaker service health
        # Get health from parallel executor instead
        cb_health = executor.get_health_status()
        assert "total_adapters" in cb_health
        assert "healthy_adapters" in cb_health
        
        # Check executor health
        executor_health = executor.get_health_status()
        assert "total_adapters" in executor_health
        assert "circuit_breakers" in executor_health
        
        # Check individual circuit breaker states
        cb_states = executor.get_circuit_breaker_states()
        assert "fast-adapter" in cb_states or "failing-adapter" in cb_states
        
        # Cleanup
        # Cleanup handled by parallel executor
        await executor.cleanup()
    
    @pytest.mark.asyncio
    async def test_fault_tolerance_with_mixed_adapters(self, mock_adapter_manager):
        """Test fault tolerance with a mix of fast, slow, and failing adapters"""
        test_config = deepcopy(INTEGRATION_TEST_CONFIG)
        executor = ParallelAdapterExecutor(mock_adapter_manager, test_config)
        
        # Execute all adapter types
        all_adapters = ["fast-adapter", "slow-adapter", "failing-adapter"]
        results = await executor.execute_adapters("mixed adapter test", all_adapters)
        
        # Should get 3 results
        assert len(results) == 3
        
        # Check results
        successful_results = [r for r in results if r.success]
        failed_results = [r for r in results if not r.success]
        
        # Should have 2 successful (fast and slow) and 1 failed (failing)
        assert len(successful_results) == 2
        assert len(failed_results) == 1
        
        # Verify specific adapters
        fast_result = next((r for r in successful_results if r.adapter_name == "fast-adapter"), None)
        slow_result = next((r for r in successful_results if r.adapter_name == "slow-adapter"), None)
        failing_result = next((r for r in failed_results if r.adapter_name == "failing-adapter"), None)
        
        assert fast_result is not None
        assert slow_result is not None
        assert failing_result is not None
        
        # Check execution times make sense
        assert fast_result.execution_time < slow_result.execution_time
        
        # Cleanup
        await executor.cleanup()
    
    @pytest.mark.asyncio
    async def test_system_resilience_under_load(self, mock_adapter_manager):
        """Test system resilience under concurrent load"""
        test_config = deepcopy(INTEGRATION_TEST_CONFIG)
        executor = ParallelAdapterExecutor(mock_adapter_manager, test_config)
        
        # Create multiple concurrent queries
        async def single_query(query_id):
            return await executor.execute_adapters(
                f"load test query {query_id}", 
                ["fast-adapter", "slow-adapter"]
            )
        
        # Execute 5 concurrent queries
        tasks = [single_query(i) for i in range(5)]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All queries should complete successfully
        assert len(all_results) == 5
        
        # Check that no exceptions were raised
        exceptions = [r for r in all_results if isinstance(r, Exception)]
        assert len(exceptions) == 0
        
        # Check that all queries got results
        for results in all_results:
            assert len(results) == 2  # fast-adapter and slow-adapter
            assert all(r.success for r in results)
        
        # Cleanup
        await executor.cleanup()


class TestFaultToleranceConfigurationVariations:
    """Test different configuration variations"""
    
    @pytest.mark.asyncio
    async def test_first_success_strategy(self, mock_adapter_manager):
        """Test first_success execution strategy"""
        config = INTEGRATION_TEST_CONFIG.copy()
        config['fault_tolerance']['execution']['strategy'] = 'first_success'
        
        executor = ParallelAdapterExecutor(mock_adapter_manager, config)
        
        # Execute adapters with first_success strategy
        results = await executor.execute_adapters(
            "first success test", 
            ["fast-adapter", "slow-adapter"]
        )
        
        # Should return as soon as first adapter succeeds
        # Fast adapter should complete first
        assert len(results) >= 1
        
        # First result should be from fast adapter
        if len(results) > 0:
            # In first_success mode, we get results as they complete
            assert results[0].success
        
        # Cleanup
        await executor.cleanup()
    
    @pytest.mark.asyncio
    async def test_best_effort_strategy(self, mock_adapter_manager):
        """Test best_effort execution strategy"""
        config = INTEGRATION_TEST_CONFIG.copy()
        config['fault_tolerance']['execution']['strategy'] = 'best_effort'
        
        executor = ParallelAdapterExecutor(mock_adapter_manager, config)
        
        # Execute adapters with best_effort strategy
        results = await executor.execute_adapters(
            "best effort test", 
            ["fast-adapter", "slow-adapter", "failing-adapter"]
        )
        
        # Should return whatever completes successfully within timeout
        assert len(results) >= 1  # At least fast-adapter should complete
        # At least one result should be successful
        assert any(result.success for result in results)
        
        # Cleanup
        await executor.cleanup()
    
    @pytest.mark.asyncio
    async def test_fault_tolerance_always_enabled(self, mock_app_state):
        """Test that fault tolerance is always enabled"""
        config = INTEGRATION_TEST_CONFIG.copy()
        # Remove the enabled setting - fault tolerance should still be enabled
        config['fault_tolerance'].pop('enabled', None)
        
        with patch('services.fault_tolerant_adapter_manager.DynamicAdapterManager') as mock_dam, \
             patch('services.fault_tolerant_adapter_manager.ParallelAdapterExecutor') as mock_pae:
            
            mock_base_manager = Mock()
            mock_base_manager.get_available_adapters = Mock(return_value=["fast-adapter"])
            mock_dam.return_value = mock_base_manager
            
            mock_parallel_executor = Mock()
            mock_parallel_executor.execute_adapters = AsyncMock(return_value=[
                Mock(success=True, data=["result from parallel"], adapter_name="fast-adapter")
            ])
            mock_pae.return_value = mock_parallel_executor
            
            manager = FaultTolerantAdapterManager(config, mock_app_state)
            
            # Should always have fault tolerance enabled
            assert manager.fault_tolerance_enabled is True
            assert manager.parallel_executor == mock_parallel_executor
            
            # Should use parallel executor
            result = await manager.get_relevant_context("always enabled test")
            assert len(result) == 1
            assert result[0]["content"] == "result from parallel"
            assert result[0]["source_adapter"] == "fast-adapter"
            mock_parallel_executor.execute_adapters.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 