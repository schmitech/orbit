"""
Test for ParallelAdapterExecutor with adapter-specific circuit breaker configuration
"""

import pytest
import asyncio
import inspect
from unittest.mock import Mock
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))

from services.parallel_adapter_executor import (
    ParallelAdapterExecutor, 
    SimpleCircuitBreaker, 
    AdapterExecutionContext
)


class TestParallelAdapterExecutor:
    
    @pytest.fixture
    def mock_adapter_manager(self):
        """Mock adapter manager"""
        manager = Mock()
        manager.get_adapter = Mock(return_value=Mock())
        return manager
    
    @pytest.fixture
    def config_with_adapter_specific_settings(self):
        """Configuration with adapter-specific fault tolerance settings"""
        return {
            'adapters': [
                {
                    'name': 'qa-sql',
                    'fault_tolerance': {
                        'operation_timeout': 15.0,
                        'failure_threshold': 10,
                        'recovery_timeout': 45.0,
                        'success_threshold': 5
                    }
                },
                {
                    'name': 'qa-vector-chroma',
                    'fault_tolerance': {
                        'operation_timeout': 25.0,
                        'failure_threshold': 3,
                        'recovery_timeout': 60.0,
                        'success_threshold': 2
                    }
                },
                {
                    'name': 'file-vector',
                    'fault_tolerance': {
                        'operation_timeout': 35.0,
                        'failure_threshold': 5,
                        'recovery_timeout': 90.0,
                        'success_threshold': 3
                    }
                }
            ],
            'fault_tolerance': {
                'failure_threshold': 5,
                'recovery_timeout': 30.0,
                'success_threshold': 3,
                'operation_timeout': 30.0,
                'execution': {
                    'timeout': 35.0,
                    'max_concurrent_adapters': 10
                }
            }
        }
    
    @pytest.fixture
    def executor(self, mock_adapter_manager, config_with_adapter_specific_settings):
        """Create executor instance with adapter-specific config"""
        return ParallelAdapterExecutor(mock_adapter_manager, config_with_adapter_specific_settings)
    
    def test_get_adapter_config(self, executor):
        """Test getting adapter-specific configuration"""
        # Test existing adapter
        config = executor._get_adapter_config('qa-sql')
        assert config['name'] == 'qa-sql'
        assert config['fault_tolerance']['operation_timeout'] == 15.0
        
        # Test non-existing adapter
        config = executor._get_adapter_config('non-existing')
        assert config == {}
    
    def test_get_adapter_fault_tolerance_config(self, executor):
        """Test getting adapter-specific fault tolerance configuration"""
        # Test existing adapter
        ft_config = executor._get_adapter_fault_tolerance_config('qa-sql')
        assert ft_config['operation_timeout'] == 15.0
        assert ft_config['failure_threshold'] == 10
        assert ft_config['recovery_timeout'] == 45.0
        assert ft_config['success_threshold'] == 5
        
        # Test non-existing adapter (should return empty dict)
        ft_config = executor._get_adapter_fault_tolerance_config('non-existing')
        assert ft_config == {}
    
    def test_circuit_breaker_creation_with_adapter_specific_settings(self, executor):
        """Test that circuit breakers are created with adapter-specific settings"""
        # Create circuit breaker for qa-sql
        cb = executor._get_circuit_breaker('qa-sql')
        assert isinstance(cb, SimpleCircuitBreaker)
        assert cb.adapter_name == 'qa-sql'
        assert cb.failure_threshold == 10  # Adapter-specific
        assert cb.base_recovery_timeout == 45.0  # Adapter-specific
        assert cb.success_threshold == 5  # Adapter-specific
        
        # Create circuit breaker for qa-vector-chroma
        cb = executor._get_circuit_breaker('qa-vector-chroma')
        assert cb.failure_threshold == 3  # Adapter-specific
        assert cb.base_recovery_timeout == 60.0  # Adapter-specific
        assert cb.success_threshold == 2  # Adapter-specific
        
        # Create circuit breaker for non-existing adapter (should use global defaults)
        cb = executor._get_circuit_breaker('non-existing')
        assert cb.failure_threshold == 5  # Global default
        assert cb.base_recovery_timeout == 30.0  # Global default
        assert cb.success_threshold == 3  # Global default
    
    def test_circuit_breaker_reuse(self, executor):
        """Test that circuit breakers are reused and not recreated"""
        cb1 = executor._get_circuit_breaker('qa-sql')
        cb2 = executor._get_circuit_breaker('qa-sql')
        assert cb1 is cb2  # Same instance
    
    def test_get_adapter_configuration_info(self, executor):
        """Test getting adapter configuration information"""
        # Create circuit breakers first
        executor._get_circuit_breaker('qa-sql')
        executor._get_circuit_breaker('qa-vector-chroma')
        
        config_info = executor.get_adapter_configuration_info()
        
        assert 'qa-sql' in config_info
        assert 'qa-vector-chroma' in config_info
        
        # Check qa-sql configuration
        qa_sql_config = config_info['qa-sql']['fault_tolerance']
        assert qa_sql_config['operation_timeout'] == 15.0
        assert qa_sql_config['failure_threshold'] == 10
        assert qa_sql_config['recovery_timeout'] == 45.0
        assert qa_sql_config['success_threshold'] == 5
        
        # Check qa-vector-chroma configuration
        chroma_config = config_info['qa-vector-chroma']['fault_tolerance']
        assert chroma_config['operation_timeout'] == 25.0
        assert chroma_config['failure_threshold'] == 3
        assert chroma_config['recovery_timeout'] == 60.0
        assert chroma_config['success_threshold'] == 2
    
    def test_get_health_status_includes_adapter_configurations(self, executor):
        """Test that health status includes adapter configuration information"""
        # Create circuit breakers first
        executor._get_circuit_breaker('qa-sql')
        executor._get_circuit_breaker('qa-vector-chroma')
        
        health_status = executor.get_health_status()
        
        assert 'adapter_configurations' in health_status
        assert 'qa-sql' in health_status['adapter_configurations']
        assert 'qa-vector-chroma' in health_status['adapter_configurations']
        assert health_status['total_adapters'] == 2
        assert health_status['healthy_adapters'] == 2  # All circuits should be closed initially
    
    @pytest.mark.asyncio
    async def test_execute_single_adapter_uses_adapter_specific_timeout(self, executor):
        """Test that _execute_single_adapter uses adapter-specific timeout"""
        # Mock the adapter to return successfully
        mock_adapter = Mock()
        mock_adapter.get_relevant_context = Mock(return_value=[{"test": "data"}])
        executor.adapter_manager.get_adapter = Mock(return_value=mock_adapter)
        
        # Create context for testing
        context = AdapterExecutionContext(request_id="test-request")
        
        # Test with qa-sql (15s timeout)
        result = await executor._execute_single_adapter('qa-sql', 'test query', context)
        assert result.success
        assert result.adapter_name == 'qa-sql'
        
        # Test with qa-vector-chroma (25s timeout)
        result = await executor._execute_single_adapter('qa-vector-chroma', 'test query', context)
        assert result.success
        assert result.adapter_name == 'qa-vector-chroma'
    
    def test_circuit_breaker_stats_tracking(self, executor):
        """Test that circuit breaker stats are tracked correctly"""
        cb = executor._get_circuit_breaker('qa-sql')
        
        # Initial state
        status = cb.get_status()
        assert status['total_calls'] == 0
        assert status['consecutive_failures'] == 0
        assert status['consecutive_successes'] == 0
        
        # Record some successes
        cb.record_success()
        cb.record_success()
        cb.record_success()
        
        status = cb.get_status()
        assert status['total_calls'] == 3
        assert status['success_rate'] == 1.0  # 3 successes / 3 total calls
        assert status['consecutive_successes'] == 3
        assert status['consecutive_failures'] == 0
        
        # Record a failure
        cb.record_failure()
        
        status = cb.get_status()
        assert status['total_calls'] == 4
        assert status['success_rate'] == 0.75  # 3 successes / 4 total calls
        assert status['consecutive_failures'] == 1
        assert status['consecutive_successes'] == 0

    def test_reset_circuit_breaker_clears_stats_and_backoff(self, executor):
        """reset_circuit_breaker must clear stats/history and reset backoff, not just close."""
        from services.parallel_adapter_executor import CircuitState

        cb = executor._get_circuit_breaker('qa-sql')

        # Open the circuit by recording enough failures
        for _ in range(10):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.stats.total_failures > 0
        assert cb.recovery_attempts > 0

        # Reset via the executor public API
        executor.reset_circuit_breaker('qa-sql')

        assert cb.state == CircuitState.CLOSED
        assert cb.stats.total_failures == 0
        assert cb.stats.total_calls == 0
        assert cb.recovery_attempts == 0
        assert cb.current_recovery_timeout == cb.base_recovery_timeout

    def test_half_open_probe_limit_via_executor(self, executor):
        """Only max_half_open_calls probes may pass when the circuit is half-open."""
        from services.parallel_adapter_executor import CircuitState

        cb = executor._get_circuit_breaker('qa-sql')
        cb.max_half_open_calls = 1

        # Force the circuit to HALF_OPEN
        for _ in range(10):
            cb.record_failure()
        cb.state = CircuitState.HALF_OPEN
        cb._half_open_probes = 0

        # First probe should be allowed
        assert cb._claim_half_open_slot() is True
        # Second probe must be rejected
        assert cb._claim_half_open_slot() is False

    @pytest.mark.asyncio
    async def test_timeout_split_proportions(self, executor):
        """Adapter lookup gets 30% of the timeout, query execution gets 70%."""
        from unittest.mock import patch

        adapter_timeout = 10.0  # override for a round number

        lookup_timeout_seen = []
        query_timeout_seen = []

        async def fake_wait_for(coro, timeout):
            if inspect.iscoroutine(coro):
                coro.close()
            if not lookup_timeout_seen:
                lookup_timeout_seen.append(timeout)
                mock_adapter = Mock()
                mock_adapter.get_relevant_context = Mock(return_value=[])
                return mock_adapter
            else:
                query_timeout_seen.append(timeout)
                return []

        context = AdapterExecutionContext(request_id="timeout-test")
        with patch.object(executor, '_get_adapter_fault_tolerance_config',
                          return_value={'operation_timeout': adapter_timeout}):
            with patch('services.parallel_adapter_executor.asyncio.wait_for',
                       side_effect=fake_wait_for):
                await executor._execute_single_adapter('qa-sql', 'q', context)

        assert lookup_timeout_seen, "lookup wait_for was never called"
        assert query_timeout_seen, "query wait_for was never called"
        assert abs(lookup_timeout_seen[0] - adapter_timeout * 0.3) < 0.001
        assert abs(query_timeout_seen[0] - adapter_timeout * 0.7) < 0.001

    @pytest.mark.asyncio
    async def test_execute_single_adapter_fast_fails_saturated_half_open(self, executor):
        """_execute_single_adapter must return 'probe limit reached' when HALF_OPEN is saturated."""
        from services.parallel_adapter_executor import CircuitState

        cb = executor._get_circuit_breaker('qa-sql')
        cb.max_half_open_calls = 1

        # Drive to OPEN via public behavior, then manually advance to HALF_OPEN
        for _ in range(10):
            cb.record_failure()
        cb.state = CircuitState.HALF_OPEN
        cb._half_open_probes = 1  # slot already taken

        context = AdapterExecutionContext(request_id="saturated-probe-test")
        result = await executor._execute_single_adapter('qa-sql', 'q', context)

        assert not result.success
        assert "probe limit reached" in str(result.error).lower()

    @pytest.mark.asyncio
    async def test_timeout_during_adapter_lookup_records_failure(self, executor):
        """A TimeoutError in the lookup phase records a failure and increments timeout_calls."""
        from unittest.mock import patch

        cb = executor._get_circuit_breaker('qa-sql')
        context = AdapterExecutionContext(request_id="lookup-timeout-test")

        call_count = [0]

        async def fake_wait_for(coro, timeout):
            if asyncio.iscoroutine(coro):
                coro.close()
            call_count[0] += 1
            raise asyncio.TimeoutError()  # always fail — simulates lookup timeout

        with patch('services.parallel_adapter_executor.asyncio.wait_for', side_effect=fake_wait_for):
            result = await executor._execute_single_adapter('qa-sql', 'q', context)

        assert not result.success
        assert "timeout" in str(result.error).lower()
        assert call_count[0] == 1, "only the lookup wait_for should have been called"
        assert cb.stats.total_failures == 1
        assert cb.stats.timeout_calls == 1

    @pytest.mark.asyncio
    async def test_timeout_during_query_execution_records_failure(self, executor):
        """A TimeoutError in the query phase records a failure and increments timeout_calls."""
        from unittest.mock import patch

        cb = executor._get_circuit_breaker('qa-sql')
        context = AdapterExecutionContext(request_id="query-timeout-test")

        call_count = [0]

        async def fake_wait_for(coro, timeout):
            if asyncio.iscoroutine(coro):
                coro.close()
            call_count[0] += 1
            if call_count[0] == 1:
                # Lookup succeeds
                mock_adapter = Mock()
                mock_adapter.get_relevant_context = Mock(return_value=[])
                return mock_adapter
            raise asyncio.TimeoutError()  # query times out

        with patch('services.parallel_adapter_executor.asyncio.wait_for', side_effect=fake_wait_for):
            result = await executor._execute_single_adapter('qa-sql', 'q', context)

        assert not result.success
        assert "timeout" in str(result.error).lower()
        assert call_count[0] == 2, "both lookup and query wait_for should have been called"
        assert cb.stats.total_failures == 1
        assert cb.stats.timeout_calls == 1

    @pytest.mark.asyncio
    async def test_timeout_calls_consistent_with_failure_stats(self, executor):
        """timeout_calls must increment with each timeout and stay <= total_failures."""
        from unittest.mock import patch

        cb = executor._get_circuit_breaker('qa-vector-chroma')
        context = AdapterExecutionContext(request_id="timeout-consistency-test")

        async def always_timeout(coro, timeout):
            if asyncio.iscoroutine(coro):
                coro.close()
            raise asyncio.TimeoutError()

        with patch('services.parallel_adapter_executor.asyncio.wait_for', side_effect=always_timeout):
            for _ in range(3):
                await executor._execute_single_adapter('qa-vector-chroma', 'q', context)

        assert cb.stats.timeout_calls == 3
        assert cb.stats.total_failures == 3
        assert cb.stats.timeout_calls <= cb.stats.total_failures

    def test_max_half_open_calls_read_from_adapter_config(self, executor):
        """max_half_open_calls is read from adapter-level fault_tolerance config."""
        config = {
            'adapters': [
                {
                    'name': 'probe-limited',
                    'fault_tolerance': {
                        'max_half_open_calls': 3,
                    }
                }
            ],
            'fault_tolerance': {}
        }
        mgr = Mock()
        ex = ParallelAdapterExecutor(mgr, config)
        cb = ex._get_circuit_breaker('probe-limited')
        assert cb.max_half_open_calls == 3

    @pytest.mark.asyncio
    async def test_cancelled_half_open_probe_releases_slot(self, executor):
        """Cancelled adapter tasks must not leak half-open probe slots."""
        from services.parallel_adapter_executor import CircuitState
        from unittest.mock import patch

        cb = executor._get_circuit_breaker('qa-sql')
        cb.max_half_open_calls = 1
        cb.state = CircuitState.HALF_OPEN
        cb._half_open_probes = 0

        async def slow_lookup(adapter_name):
            await asyncio.sleep(10)

        context = AdapterExecutionContext(request_id="cancel-test")
        with patch.object(executor, '_get_adapter_with_timeout', side_effect=slow_lookup):
            task = asyncio.create_task(executor._execute_single_adapter('qa-sql', 'q', context))
            await asyncio.sleep(0.05)
            assert cb._half_open_probes == 1

            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert cb._half_open_probes == 0


if __name__ == "__main__":
    pytest.main([__file__])
