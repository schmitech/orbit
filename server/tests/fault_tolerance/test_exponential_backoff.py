"""
Test for exponential backoff functionality in SimpleCircuitBreaker
"""

import pytest
import asyncio
import time
import random
from unittest.mock import Mock
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))

from services.parallel_adapter_executor import SimpleCircuitBreaker, CircuitState


class TestExponentialBackoff:
    
    def test_exponential_backoff_initialization(self):
        """Test that exponential backoff is properly initialized"""
        cb = SimpleCircuitBreaker(
            "test-adapter",
            failure_threshold=2,
            recovery_timeout=10.0,
            max_recovery_timeout=100.0,
            enable_exponential_backoff=True
        )
        
        assert cb.base_recovery_timeout == 10.0
        assert cb.max_recovery_timeout == 100.0
        assert cb.enable_exponential_backoff is True
        assert cb.recovery_attempts == 0
        assert cb.current_recovery_timeout == 10.0
    
    def test_exponential_backoff_disabled(self):
        """Test that exponential backoff can be disabled"""
        cb = SimpleCircuitBreaker(
            "test-adapter",
            recovery_timeout=10.0,
            enable_exponential_backoff=False
        )
        
        assert cb.enable_exponential_backoff is False
        assert cb._calculate_recovery_timeout() == 10.0
    
    def test_calculate_recovery_timeout_with_backoff(self):
        """Test recovery timeout calculation with exponential backoff"""
        cb = SimpleCircuitBreaker(
            "test-adapter",
            recovery_timeout=10.0,
            max_recovery_timeout=100.0,
            enable_exponential_backoff=True
        )
        
        # First attempt (recovery_attempts = 0)
        timeout1 = cb._calculate_recovery_timeout()
        assert 10.0 <= timeout1 <= 11.0  # Base + jitter
        
        # Second attempt (recovery_attempts = 1)
        cb.recovery_attempts = 1
        timeout2 = cb._calculate_recovery_timeout()
        assert 20.0 <= timeout2 <= 22.0  # 2x base + jitter
        
        # Third attempt (recovery_attempts = 2)
        cb.recovery_attempts = 2
        timeout3 = cb._calculate_recovery_timeout()
        assert 40.0 <= timeout3 <= 44.0  # 4x base + jitter
        
        # Fourth attempt (recovery_attempts = 3)
        cb.recovery_attempts = 3
        timeout4 = cb._calculate_recovery_timeout()
        assert 80.0 <= timeout4 <= 88.0  # 8x base + jitter
        
        # Fifth attempt (recovery_attempts = 4) - should hit max
        cb.recovery_attempts = 4
        timeout5 = cb._calculate_recovery_timeout()
        assert 100.0 <= timeout5 <= 110.0  # Max + jitter
    
    @pytest.mark.asyncio
    async def test_exponential_backoff_in_circuit_lifecycle(self):
        """Test exponential backoff through the circuit breaker lifecycle"""
        cb = SimpleCircuitBreaker(
            "test-adapter",
            failure_threshold=2,
            recovery_timeout=10.0,
            max_recovery_timeout=100.0,
            enable_exponential_backoff=True
        )
        
        # Initial state
        assert cb.recovery_attempts == 0
        assert cb.current_recovery_timeout == 10.0
        
        # First failure - circuit opens
        cb.record_failure()
        cb.record_failure()
        await asyncio.sleep(0.01)  # Allow async tasks to complete
        assert cb.state == CircuitState.OPEN
        assert cb.recovery_attempts == 1
        assert cb.current_recovery_timeout > 10.0  # Should be base + jitter
        
        # Simulate time passing and circuit going to half-open
        cb._state_changed_at = time.time() - cb.current_recovery_timeout - 1
        assert not cb.is_open()  # Should transition to half-open
        
        # Failure in half-open state - circuit opens again
        cb.record_failure()
        await asyncio.sleep(0.01)  # Allow async tasks to complete
        assert cb.state == CircuitState.OPEN
        assert cb.recovery_attempts == 2
        assert cb.current_recovery_timeout > cb.base_recovery_timeout * 2  # Should be 2x base + jitter
        
        # Simulate time passing again
        cb._state_changed_at = time.time() - cb.current_recovery_timeout - 1
        assert not cb.is_open()  # Should transition to half-open
        
        # Success in half-open state - circuit closes
        cb.record_success()
        cb.record_success()
        cb.record_success()
        await asyncio.sleep(0.01)  # Allow async tasks to complete
        assert cb.state == CircuitState.CLOSED
        assert cb.recovery_attempts == 0  # Should reset
        assert cb.current_recovery_timeout == cb.base_recovery_timeout  # Should reset to base
    
    @pytest.mark.asyncio
    async def test_exponential_backoff_reset_on_success(self):
        """Test that exponential backoff resets when circuit closes successfully"""
        cb = SimpleCircuitBreaker(
            "test-adapter",
            failure_threshold=2,
            recovery_timeout=10.0,
            enable_exponential_backoff=True
        )
        
        # Open circuit
        cb.record_failure()
        cb.record_failure()
        await asyncio.sleep(0.01)  # Allow async tasks to complete
        assert cb.recovery_attempts == 1
        assert cb.current_recovery_timeout > 10.0
        
        # Simulate time passing to transition to half-open
        # Use a much longer time to ensure transition
        cb._state_changed_at = time.time() - cb.current_recovery_timeout - 10
        # Call is_open() to trigger the transition check
        cb.is_open()
        assert cb.state == CircuitState.HALF_OPEN  # Should be half-open now
        
        # Success in half-open state should close circuit and reset backoff
        cb.record_success()
        cb.record_success()
        cb.record_success()
        await asyncio.sleep(0.01)  # Allow async tasks to complete
        assert cb.state == CircuitState.CLOSED
        assert cb.recovery_attempts == 0
        assert cb.current_recovery_timeout == 10.0
    
    @pytest.mark.asyncio
    async def test_exponential_backoff_reset_method(self):
        """Test that reset method resets exponential backoff"""
        cb = SimpleCircuitBreaker(
            "test-adapter",
            failure_threshold=2,
            recovery_timeout=10.0,
            enable_exponential_backoff=True
        )
        
        # Open circuit
        cb.record_failure()
        cb.record_failure()
        await asyncio.sleep(0.01)  # Allow async tasks to complete
        assert cb.recovery_attempts == 1
        assert cb.current_recovery_timeout > 10.0
        
        # Reset should clear everything
        cb.reset()
        await asyncio.sleep(0.01)  # Allow async tasks to complete
        assert cb.recovery_attempts == 0
        assert cb.current_recovery_timeout == 10.0
        assert cb.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_exponential_backoff_status_information(self):
        """Test that exponential backoff information is included in status"""
        cb = SimpleCircuitBreaker(
            "test-adapter",
            failure_threshold=2,
            recovery_timeout=10.0,
            max_recovery_timeout=100.0,
            enable_exponential_backoff=True
        )
        
        status = cb.get_status()
        assert "exponential_backoff" in status
        backoff_info = status["exponential_backoff"]
        
        assert backoff_info["enabled"] is True
        assert backoff_info["recovery_attempts"] == 0
        assert backoff_info["current_timeout"] == 10.0
        assert backoff_info["base_timeout"] == 10.0
        assert backoff_info["max_timeout"] == 100.0
        
        # After a failure - need to open the circuit first
        cb.record_failure()
        cb.record_failure()  # This should open the circuit
        await asyncio.sleep(0.01)  # Allow async tasks to complete
        status = cb.get_status()
        backoff_info = status["exponential_backoff"]
        
        assert backoff_info["recovery_attempts"] == 1
        assert backoff_info["current_timeout"] > 10.0
    
    def test_jitter_variation(self):
        """Test that jitter provides variation in timeouts"""
        cb = SimpleCircuitBreaker(
            "test-adapter",
            recovery_timeout=10.0,
            enable_exponential_backoff=True
        )
        
        # Test multiple calculations to ensure jitter variation
        timeouts = []
        for _ in range(10):
            cb.recovery_attempts = 1  # 2x base = 20s
            timeout = cb._calculate_recovery_timeout()
            timeouts.append(timeout)
        
        # All should be in expected range (20-22s with jitter)
        for timeout in timeouts:
            assert 20.0 <= timeout <= 22.0
        
        # Should have some variation due to jitter
        assert len(set(timeouts)) > 1  # At least some different values
    
    def test_max_recovery_timeout_limit(self):
        """Test that recovery timeout doesn't exceed maximum"""
        cb = SimpleCircuitBreaker(
            "test-adapter",
            recovery_timeout=10.0,
            max_recovery_timeout=50.0,
            enable_exponential_backoff=True
        )
        
        # Set high recovery attempts to test max limit
        cb.recovery_attempts = 10  # Would be 2^10 * 10 = 10240s without limit
        timeout = cb._calculate_recovery_timeout()
        
        assert timeout <= 55.0  # Max + jitter
        assert timeout >= 50.0  # At least max


if __name__ == "__main__":
    pytest.main([__file__]) 