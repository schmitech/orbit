"""
Test for memory leak prevention in SimpleCircuitBreaker
"""

import pytest
import asyncio
import time
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))

from services.parallel_adapter_executor import (
    SimpleCircuitBreaker,
    CircuitBreakerStats,
    CircuitState
)


class TestMemoryLeakPrevention:
    
    def test_circuit_breaker_stats_initialization(self):
        """Test that CircuitBreakerStats initializes with empty history"""
        stats = CircuitBreakerStats()
        
        assert stats.call_history == []
        assert stats.state_transitions == []
        assert stats.total_calls == 0
        assert stats.total_successes == 0
        assert stats.total_failures == 0
    
    def test_add_call_record(self):
        """Test adding call records to history"""
        stats = CircuitBreakerStats()
        timestamp = time.time()
        
        # Add success record
        stats.add_call_record(timestamp, True, 0.5)
        assert len(stats.call_history) == 1
        assert stats.call_history[0]['timestamp'] == timestamp
        assert stats.call_history[0]['success'] is True
        assert stats.call_history[0]['execution_time'] == 0.5
        
        # Add failure record
        stats.add_call_record(timestamp + 1, False, 1.2)
        assert len(stats.call_history) == 2
        assert stats.call_history[1]['timestamp'] == timestamp + 1
        assert stats.call_history[1]['success'] is False
        assert stats.call_history[1]['execution_time'] == 1.2
    
    def test_add_state_transition(self):
        """Test adding state transition records"""
        stats = CircuitBreakerStats()
        timestamp = time.time()
        
        # Add state transition
        stats.add_state_transition(timestamp, "closed", "open", "failure_threshold")
        assert len(stats.state_transitions) == 1
        assert stats.state_transitions[0]['timestamp'] == timestamp
        assert stats.state_transitions[0]['from_state'] == "closed"
        assert stats.state_transitions[0]['to_state'] == "open"
        assert stats.state_transitions[0]['reason'] == "failure_threshold"
    
    def test_cleanup_old_records(self):
        """Test cleanup of old records"""
        stats = CircuitBreakerStats()
        current_time = time.time()
        
        # Add records with different timestamps
        stats.add_call_record(current_time - 100, True, 0.1)      # Old record
        stats.add_call_record(current_time - 50, False, 0.2)      # Old record
        stats.add_call_record(current_time - 10, True, 0.3)       # Recent record
        stats.add_call_record(current_time, False, 0.4)           # Current record
        
        stats.add_state_transition(current_time - 100, "closed", "open", "old")
        stats.add_state_transition(current_time - 10, "open", "half_open", "recent")
        
        # Clean up records older than 60 seconds
        cutoff_time = current_time - 60
        stats.cleanup_old_records(cutoff_time)
        
        # Should only keep recent records (those within 60 seconds of current time)
        # Records at current_time - 50, current_time - 10, and current_time should remain
        # (since current_time - 50 is within 60 seconds of current_time)
        assert len(stats.call_history) == 3
        assert len(stats.state_transitions) == 1
        
        # Verify timestamps of remaining records
        for record in stats.call_history:
            assert record['timestamp'] >= cutoff_time
        
        for transition in stats.state_transitions:
            assert transition['timestamp'] >= cutoff_time
    
    def test_circuit_breaker_with_memory_prevention(self):
        """Test circuit breaker with memory leak prevention enabled"""
        # Create circuit breaker with short cleanup interval for testing
        cb = SimpleCircuitBreaker(
            adapter_name="test-adapter",
            failure_threshold=2,
            recovery_timeout=1.0,
            success_threshold=1,
            cleanup_interval=0.1,  # Very short for testing
            retention_period=0.05  # Very short retention for testing
        )
        
        # Record some calls
        cb.record_success(execution_time=0.1)
        cb.record_failure(execution_time=0.2)
        cb.record_success(execution_time=0.3)
        
        # Check that records are added
        assert len(cb.stats.call_history) == 3
        
        # Wait for cleanup to trigger
        time.sleep(0.2)
        
        # Record another call to trigger cleanup
        cb.record_success(execution_time=0.4)
        
        # Check that old records were cleaned up (should be less than 4 total)
        assert len(cb.stats.call_history) < 4
    
    def test_force_cleanup(self):
        """Test forced cleanup of circuit breaker"""
        cb = SimpleCircuitBreaker(
            adapter_name="test-adapter",
            cleanup_interval=3600.0,  # Long interval
            retention_period=0.1      # Short retention
        )
        
        # Add some old records
        old_time = time.time() - 1.0
        cb.stats.add_call_record(old_time, True, 0.1)
        cb.stats.add_call_record(old_time, False, 0.2)
        cb.stats.add_state_transition(old_time, "closed", "open", "test")
        
        # Add some recent records
        recent_time = time.time()
        cb.stats.add_call_record(recent_time, True, 0.3)
        cb.stats.add_state_transition(recent_time, "open", "half_open", "test")
        
        # Force cleanup
        cb.force_cleanup()
        
        # Should only keep recent records
        assert len(cb.stats.call_history) == 1
        assert len(cb.stats.state_transitions) == 1
    
    def test_memory_usage_tracking(self):
        """Test memory usage tracking in circuit breaker status"""
        cb = SimpleCircuitBreaker(
            adapter_name="test-adapter",
            cleanup_interval=3600.0,
            retention_period=86400.0
        )
        
        # Add some records
        cb.record_success(execution_time=0.1)
        cb.record_failure(execution_time=0.2)
        cb.record_success(execution_time=0.3)
        
        # Get status
        status = cb.get_status()
        
        # Check memory usage info
        assert "memory_usage" in status
        memory_info = status["memory_usage"]
        
        assert "call_history_size" in memory_info
        assert "state_transitions_size" in memory_info
        assert "last_cleanup" in memory_info
        assert "cleanup_interval" in memory_info
        assert "retention_period" in memory_info
        
        assert memory_info["call_history_size"] == 3
        assert memory_info["cleanup_interval"] == 3600.0
        assert memory_info["retention_period"] == 86400.0
    
    @pytest.mark.asyncio
    async def test_state_transition_recording(self):
        """Test that state transitions are recorded during circuit breaker operation"""
        cb = SimpleCircuitBreaker(
            adapter_name="test-adapter",
            failure_threshold=2,
            recovery_timeout=0.1,  # Short for testing
            success_threshold=1
        )
        
        # Initial state should be CLOSED
        assert cb.state == CircuitState.CLOSED
        assert len(cb.stats.state_transitions) == 0
        
        # Record failures to trigger OPEN state
        cb.record_failure(execution_time=0.1)
        cb.record_failure(execution_time=0.2)
        await asyncio.sleep(0.01)  # Allow async tasks to complete
        
        # Should be OPEN now
        assert cb.state == CircuitState.OPEN
        assert len(cb.stats.state_transitions) == 1
        assert cb.stats.state_transitions[0]['from_state'] == 'closed'
        assert cb.stats.state_transitions[0]['to_state'] == 'open'
        
        # Wait for recovery timeout
        time.sleep(0.3)  # Wait a bit longer to ensure timeout
        
        # Should transition to HALF_OPEN
        cb.is_open()  # This triggers the transition
        assert cb.state == CircuitState.HALF_OPEN
        assert len(cb.stats.state_transitions) == 2
        assert cb.stats.state_transitions[1]['from_state'] == 'open'
        assert cb.stats.state_transitions[1]['to_state'] == 'half_open'
        
        # Record success to close circuit
        cb.record_success(execution_time=0.3)
        await asyncio.sleep(0.01)  # Allow async tasks to complete
        assert cb.state == CircuitState.CLOSED
        assert len(cb.stats.state_transitions) == 3
        assert cb.stats.state_transitions[2]['from_state'] == 'half_open'
        assert cb.stats.state_transitions[2]['to_state'] == 'closed'
    
    @pytest.mark.asyncio
    async def test_reset_clears_history(self):
        """Test that reset clears all history"""
        cb = SimpleCircuitBreaker(adapter_name="test-adapter")
        
        # Add some records
        cb.record_success(execution_time=0.1)
        cb.record_failure(execution_time=0.2)
        cb.stats.add_state_transition(time.time(), "closed", "open", "test")
        
        # Verify records exist
        assert len(cb.stats.call_history) == 2
        assert len(cb.stats.state_transitions) == 1
        
        # Reset
        cb.reset()
        await asyncio.sleep(0.01)  # Allow async tasks to complete
        
        # Verify all history is cleared
        assert len(cb.stats.call_history) == 0
        assert len(cb.stats.state_transitions) == 0
        assert cb.stats.total_calls == 0
        assert cb.stats.total_successes == 0
        assert cb.stats.total_failures == 0
    
    def test_cleanup_interval_configuration(self):
        """Test that cleanup interval can be configured"""
        # Test with different cleanup intervals
        cb1 = SimpleCircuitBreaker(
            adapter_name="test-adapter-1",
            cleanup_interval=1800.0,  # 30 minutes
            retention_period=43200.0  # 12 hours
        )
        
        cb2 = SimpleCircuitBreaker(
            adapter_name="test-adapter-2",
            cleanup_interval=7200.0,  # 2 hours
            retention_period=172800.0  # 48 hours
        )
        
        assert cb1.cleanup_interval == 1800.0
        assert cb1.retention_period == 43200.0
        assert cb2.cleanup_interval == 7200.0
        assert cb2.retention_period == 172800.0


if __name__ == "__main__":
    pytest.main([__file__]) 