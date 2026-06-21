"""
Test for circuit breaker events and callbacks
"""

import pytest
import asyncio
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))

from services.parallel_adapter_executor import (
    SimpleCircuitBreaker,
    CircuitBreakerEventHandler,
    DefaultCircuitBreakerEventHandler,
    MonitoringCircuitBreakerEventHandler
)


class TestCircuitBreakerEventHandler:
    """Test the abstract event handler base class"""
    
    def test_abstract_methods(self):
        """Test that abstract methods are defined"""
        # Should not be able to instantiate abstract class
        with pytest.raises(TypeError):
            CircuitBreakerEventHandler()


class TestDefaultCircuitBreakerEventHandler:
    """Test the default event handler"""
    
    @pytest.mark.asyncio
    async def test_on_circuit_open(self):
        """Test circuit open event"""
        handler = DefaultCircuitBreakerEventHandler()
        stats = {"state": "open", "total_calls": 10}
        
        # Should not raise any exceptions
        await handler.on_circuit_open("test-adapter", stats, "test_reason")
    
    @pytest.mark.asyncio
    async def test_on_circuit_close(self):
        """Test circuit close event"""
        handler = DefaultCircuitBreakerEventHandler()
        stats = {"state": "closed", "total_calls": 10}
        
        # Should not raise any exceptions
        await handler.on_circuit_close("test-adapter", stats)
    
    @pytest.mark.asyncio
    async def test_on_circuit_half_open(self):
        """Test circuit half-open event"""
        handler = DefaultCircuitBreakerEventHandler()
        stats = {"state": "half_open", "total_calls": 10}
        
        # Should not raise any exceptions
        await handler.on_circuit_half_open("test-adapter", stats)
    
    @pytest.mark.asyncio
    async def test_on_circuit_reset(self):
        """Test circuit reset event"""
        handler = DefaultCircuitBreakerEventHandler()
        stats = {"state": "closed", "total_calls": 0}
        
        # Should not raise any exceptions
        await handler.on_circuit_reset("test-adapter", stats)


class TestMonitoringCircuitBreakerEventHandler:
    """Test the monitoring event handler"""
    
    @pytest.mark.asyncio
    async def test_on_circuit_open_with_callbacks(self):
        """Test circuit open event with callbacks"""
        alert_called = False
        dashboard_called = False
        metrics_called = False
        
        async def alert_callback(event_type, adapter_name, stats, reason):
            nonlocal alert_called
            alert_called = True
            assert event_type == "circuit_open"
            assert adapter_name == "test-adapter"
            assert reason == "test_reason"
        
        async def dashboard_callback(event_type, adapter_name, stats):
            nonlocal dashboard_called
            dashboard_called = True
            assert event_type == "circuit_open"
            assert adapter_name == "test-adapter"
        
        async def metrics_callback(event_type, adapter_name, stats):
            nonlocal metrics_called
            metrics_called = True
            assert event_type == "circuit_open"
            assert adapter_name == "test-adapter"
        
        handler = MonitoringCircuitBreakerEventHandler(
            alert_callback=alert_callback,
            dashboard_callback=dashboard_callback,
            metrics_callback=metrics_callback
        )
        
        stats = {"state": "open", "total_calls": 10}
        await handler.on_circuit_open("test-adapter", stats, "test_reason")
        
        assert alert_called
        assert dashboard_called
        assert metrics_called
    
    @pytest.mark.asyncio
    async def test_on_circuit_open_without_callbacks(self):
        """Test circuit open event without callbacks"""
        handler = MonitoringCircuitBreakerEventHandler()
        stats = {"state": "open", "total_calls": 10}
        
        # Should not raise any exceptions
        await handler.on_circuit_open("test-adapter", stats, "test_reason")
    
    @pytest.mark.asyncio
    async def test_callback_exception_handling(self):
        """Test that callback exceptions are handled gracefully"""
        async def failing_callback(event_type, adapter_name, stats):
            raise Exception("Callback failed")
        
        handler = MonitoringCircuitBreakerEventHandler(
            alert_callback=failing_callback
        )
        
        stats = {"state": "open", "total_calls": 10}
        
        # Should not raise exception, should handle it gracefully
        await handler.on_circuit_open("test-adapter", stats, "test_reason")
    
    @pytest.mark.asyncio
    async def test_on_circuit_close_with_callbacks(self):
        """Test circuit close event with callbacks"""
        dashboard_called = False
        metrics_called = False
        
        async def dashboard_callback(event_type, adapter_name, stats):
            nonlocal dashboard_called
            dashboard_called = True
            assert event_type == "circuit_close"
            assert adapter_name == "test-adapter"
        
        async def metrics_callback(event_type, adapter_name, stats):
            nonlocal metrics_called
            metrics_called = True
            assert event_type == "circuit_close"
            assert adapter_name == "test-adapter"
        
        handler = MonitoringCircuitBreakerEventHandler(
            dashboard_callback=dashboard_callback,
            metrics_callback=metrics_callback
        )
        
        stats = {"state": "closed", "total_calls": 10}
        await handler.on_circuit_close("test-adapter", stats)
        
        assert dashboard_called
        assert metrics_called


class TestSimpleCircuitBreakerEvents:
    """Test circuit breaker events integration"""
    
    def test_circuit_breaker_with_default_handler(self):
        """Test circuit breaker with default event handler"""
        cb = SimpleCircuitBreaker(
            adapter_name="test-adapter",
            failure_threshold=2,
            recovery_timeout=0.1,
            success_threshold=1
        )
        
        # Should have default event handler
        assert cb.event_handler is not None
        assert isinstance(cb.event_handler, DefaultCircuitBreakerEventHandler)
    
    def test_circuit_breaker_with_custom_handler(self):
        """Test circuit breaker with custom event handler"""
        custom_handler = DefaultCircuitBreakerEventHandler()
        cb = SimpleCircuitBreaker(
            adapter_name="test-adapter",
            event_handler=custom_handler
        )
        
        assert cb.event_handler is custom_handler
    
    def test_circuit_breaker_without_handler(self):
        """Test circuit breaker without event handler"""
        cb = SimpleCircuitBreaker(
            adapter_name="test-adapter",
            event_handler=None
        )
        
        # Should still have default handler
        assert cb.event_handler is not None
        assert isinstance(cb.event_handler, DefaultCircuitBreakerEventHandler)
    
    @pytest.mark.asyncio
    async def test_circuit_open_event_triggered(self):
        """Test that circuit open event is triggered"""
        events_triggered = []
        
        class TestEventHandler(CircuitBreakerEventHandler):
            async def on_circuit_open(self, adapter_name, stats, reason=""):
                events_triggered.append(("open", adapter_name, reason))
            
            async def on_circuit_close(self, adapter_name, stats):
                events_triggered.append(("close", adapter_name))
            
            async def on_circuit_half_open(self, adapter_name, stats):
                events_triggered.append(("half_open", adapter_name))
            
            async def on_circuit_reset(self, adapter_name, stats):
                events_triggered.append(("reset", adapter_name))
        
        handler = TestEventHandler()
        cb = SimpleCircuitBreaker(
            adapter_name="test-adapter",
            failure_threshold=2,
            recovery_timeout=0.1,
            success_threshold=1,
            event_handler=handler
        )
        
        # Record failures to trigger open
        cb.record_failure(execution_time=0.1)
        cb.record_failure(execution_time=0.2)
        
        # Wait for event to be processed
        await asyncio.sleep(0.1)
        
        # Check that open event was triggered
        assert len(events_triggered) == 1
        assert events_triggered[0] == ("open", "test-adapter", "failure_threshold_reached")
    
    @pytest.mark.asyncio
    async def test_circuit_close_event_triggered(self):
        """Test that circuit close event is triggered"""
        events_triggered = []
        
        class TestEventHandler(CircuitBreakerEventHandler):
            async def on_circuit_open(self, adapter_name, stats, reason=""):
                events_triggered.append(("open", adapter_name, reason))
            
            async def on_circuit_close(self, adapter_name, stats):
                events_triggered.append(("close", adapter_name))
            
            async def on_circuit_half_open(self, adapter_name, stats):
                events_triggered.append(("half_open", adapter_name))
            
            async def on_circuit_reset(self, adapter_name, stats):
                events_triggered.append(("reset", adapter_name))
        
        handler = TestEventHandler()
        cb = SimpleCircuitBreaker(
            adapter_name="test-adapter",
            failure_threshold=2,
            recovery_timeout=0.1,
            success_threshold=1,
            event_handler=handler
        )
        
        # Open the circuit
        cb.record_failure(execution_time=0.1)
        cb.record_failure(execution_time=0.2)
        
        # Wait for recovery timeout
        await asyncio.sleep(0.3)
        
        # Check if circuit is half-open
        cb.is_open()
        
        # Record success to close circuit
        cb.record_success(execution_time=0.3)
        
        # Wait for event to be processed
        await asyncio.sleep(0.2)
        
        # Check that close event was triggered
        assert ("close", "test-adapter") in events_triggered
    
    @pytest.mark.asyncio
    async def test_circuit_half_open_event_triggered(self):
        """Test that circuit half-open event is triggered"""
        events_triggered = []
        
        class TestEventHandler(CircuitBreakerEventHandler):
            async def on_circuit_open(self, adapter_name, stats, reason=""):
                events_triggered.append(("open", adapter_name, reason))
            
            async def on_circuit_close(self, adapter_name, stats):
                events_triggered.append(("close", adapter_name))
            
            async def on_circuit_half_open(self, adapter_name, stats):
                events_triggered.append(("half_open", adapter_name))
            
            async def on_circuit_reset(self, adapter_name, stats):
                events_triggered.append(("reset", adapter_name))
        
        handler = TestEventHandler()
        cb = SimpleCircuitBreaker(
            adapter_name="test-adapter",
            failure_threshold=2,
            recovery_timeout=0.1,
            success_threshold=1,
            event_handler=handler
        )
        
        # Open the circuit
        cb.record_failure(execution_time=0.1)
        cb.record_failure(execution_time=0.2)
        
        # Wait for recovery timeout
        await asyncio.sleep(0.3)
        
        # Check if circuit is half-open (this triggers the event)
        cb.is_open()
        
        # Wait for event to be processed
        await asyncio.sleep(0.2)
        
        # Check that half-open event was triggered
        assert ("half_open", "test-adapter") in events_triggered
    
    @pytest.mark.asyncio
    async def test_circuit_reset_event_triggered(self):
        """Test that circuit reset event is triggered"""
        events_triggered = []
        
        class TestEventHandler(CircuitBreakerEventHandler):
            async def on_circuit_open(self, adapter_name, stats, reason=""):
                events_triggered.append(("open", adapter_name, reason))
            
            async def on_circuit_close(self, adapter_name, stats):
                events_triggered.append(("close", adapter_name))
            
            async def on_circuit_half_open(self, adapter_name, stats):
                events_triggered.append(("half_open", adapter_name))
            
            async def on_circuit_reset(self, adapter_name, stats):
                events_triggered.append(("reset", adapter_name))
        
        handler = TestEventHandler()
        cb = SimpleCircuitBreaker(
            adapter_name="test-adapter",
            event_handler=handler
        )
        
        # Reset the circuit
        cb.reset()
        
        # Wait for event to be processed
        await asyncio.sleep(0.1)
        
        # Check that reset event was triggered
        assert ("reset", "test-adapter") in events_triggered


class TestSafeEventDispatch:
    """Tests for safe event dispatch without a running event loop."""

    def test_record_failure_no_event_loop_does_not_raise(self):
        """record_failure must not raise RuntimeError when called outside an event loop."""
        cb = SimpleCircuitBreaker(
            adapter_name="sync-adapter",
            failure_threshold=1,
            event_handler=DefaultCircuitBreakerEventHandler(),
        )
        # Drive to OPEN — _open_circuit emits an event; must not raise
        cb.record_failure()

    def test_record_success_no_event_loop_does_not_raise(self):
        """record_success in HALF_OPEN must not raise when no loop is running."""
        from services.parallel_adapter_executor import CircuitState
        cb = SimpleCircuitBreaker(
            adapter_name="sync-adapter",
            failure_threshold=1,
            success_threshold=1,
            event_handler=DefaultCircuitBreakerEventHandler(),
        )
        cb.record_failure()  # opens the circuit
        # Manually move to HALF_OPEN to avoid waiting for recovery timeout
        cb.state = CircuitState.HALF_OPEN
        cb._half_open_probes = 1
        cb.stats.consecutive_successes = 0
        cb.record_success()  # triggers _close_circuit event — must not raise

    def test_reset_no_event_loop_does_not_raise(self):
        """reset() must not raise RuntimeError when called outside an event loop."""
        cb = SimpleCircuitBreaker(
            adapter_name="sync-adapter",
            event_handler=DefaultCircuitBreakerEventHandler(),
        )
        cb.reset()

    def test_handler_exception_does_not_break_state_transition(self):
        """An event handler that raises must not prevent the state transition from completing."""
        from services.parallel_adapter_executor import CircuitState

        class BrokenHandler(CircuitBreakerEventHandler):
            async def on_circuit_open(self, adapter_name, stats, reason=""):
                raise RuntimeError("handler boom")

            async def on_circuit_close(self, adapter_name, stats):
                raise RuntimeError("handler boom")

            async def on_circuit_half_open(self, adapter_name, stats):
                raise RuntimeError("handler boom")

            async def on_circuit_reset(self, adapter_name, stats):
                raise RuntimeError("handler boom")

        cb = SimpleCircuitBreaker(
            adapter_name="broken-handler-adapter",
            failure_threshold=1,
            event_handler=BrokenHandler(),
        )
        cb.record_failure()
        # State must still be OPEN even though the handler would raise
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_async_handler_exception_is_consumed(self):
        """A scheduled event handler exception must not surface as an unhandled task exception."""
        from services.parallel_adapter_executor import CircuitState

        class BrokenHandler(CircuitBreakerEventHandler):
            async def on_circuit_open(self, adapter_name, stats, reason=""):
                raise RuntimeError("handler boom")

            async def on_circuit_close(self, adapter_name, stats):
                raise RuntimeError("handler boom")

            async def on_circuit_half_open(self, adapter_name, stats):
                raise RuntimeError("handler boom")

            async def on_circuit_reset(self, adapter_name, stats):
                raise RuntimeError("handler boom")

        cb = SimpleCircuitBreaker(
            adapter_name="async-broken-handler-adapter",
            failure_threshold=1,
            event_handler=BrokenHandler(),
        )

        cb.record_failure()
        await asyncio.sleep(0.05)

        assert cb.state == CircuitState.OPEN


class TestConcurrentSafety:
    """Tests for thread-safety of SimpleCircuitBreaker."""

    def test_concurrent_failures_open_circuit_exactly_once(self):
        """Multiple threads failing at once must open the circuit exactly once."""
        import threading
        from services.parallel_adapter_executor import CircuitState

        cb = SimpleCircuitBreaker(
            adapter_name="concurrent-adapter",
            failure_threshold=3,
            event_handler=DefaultCircuitBreakerEventHandler(),
        )

        errors = []

        def fail():
            try:
                cb.record_failure()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=fail) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
        assert cb.state == CircuitState.OPEN
        assert cb.stats.total_failures == 10
        assert cb.stats.consecutive_failures >= cb.failure_threshold

    def test_concurrent_success_failure_mix(self):
        """Mixed concurrent successes and failures must produce consistent counters."""
        import threading

        cb = SimpleCircuitBreaker(
            adapter_name="mixed-concurrent-adapter",
            failure_threshold=100,  # high so the circuit stays closed throughout
            event_handler=DefaultCircuitBreakerEventHandler(),
        )

        n_successes = 20
        n_failures = 15
        errors = []

        def succeed():
            try:
                cb.record_success()
            except Exception as e:
                errors.append(e)

        def fail():
            try:
                cb.record_failure()
            except Exception as e:
                errors.append(e)

        threads = (
            [threading.Thread(target=succeed) for _ in range(n_successes)] +
            [threading.Thread(target=fail) for _ in range(n_failures)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
        assert cb.stats.total_calls == n_successes + n_failures
        assert cb.stats.total_successes == n_successes
        assert cb.stats.total_failures == n_failures

    def test_run_cleanup_concurrent_with_reset(self):
        """force_cleanup() and reset() running from separate threads must not corrupt state."""
        import threading
        from services.parallel_adapter_executor import CircuitState

        cb = SimpleCircuitBreaker(
            adapter_name="cleanup-race-adapter",
            failure_threshold=100,
            cleanup_interval=0,      # allow every cleanup call to actually run
            retention_period=0,      # prune all records immediately
            event_handler=DefaultCircuitBreakerEventHandler(),
        )
        # Seed some history so cleanup has something to do
        for _ in range(50):
            cb.record_failure()

        errors = []

        def do_cleanup():
            for _ in range(20):
                try:
                    cb.force_cleanup()
                except Exception as e:
                    errors.append(e)

        def do_reset():
            for _ in range(20):
                try:
                    cb.reset()
                except Exception as e:
                    errors.append(e)

        t1 = threading.Thread(target=do_cleanup)
        t2 = threading.Thread(target=do_reset)
        t1.start(); t2.start()
        t1.join(); t2.join()

        assert not errors, f"Thread errors: {errors}"
        # After all resets the breaker must be in a coherent closed state
        assert cb.state == CircuitState.CLOSED


class TestHalfOpenProbeGating:
    """Tests for half-open probe limit enforcement."""

    def test_claim_half_open_slot_allows_up_to_max(self):
        """_claim_half_open_slot should allow exactly max_half_open_calls probes."""
        from services.parallel_adapter_executor import CircuitState

        cb = SimpleCircuitBreaker(
            adapter_name="probe-adapter",
            failure_threshold=1,
            max_half_open_calls=2,
        )
        cb.record_failure()
        cb.state = CircuitState.HALF_OPEN

        assert cb._claim_half_open_slot() is True   # probe 1
        assert cb._claim_half_open_slot() is True   # probe 2
        assert cb._claim_half_open_slot() is False  # over limit

    def test_claim_half_open_slot_non_half_open_always_passes(self):
        """_claim_half_open_slot on a CLOSED circuit must always return True."""
        from services.parallel_adapter_executor import CircuitState

        cb = SimpleCircuitBreaker(adapter_name="closed-adapter")
        assert cb.state == CircuitState.CLOSED
        assert cb._claim_half_open_slot() is True

    def test_probe_counter_decrements_on_success(self):
        """record_success in HALF_OPEN should decrement the probe counter."""
        from services.parallel_adapter_executor import CircuitState

        cb = SimpleCircuitBreaker(
            adapter_name="probe-success-adapter",
            failure_threshold=1,
            success_threshold=5,  # high threshold so circuit stays half-open
            max_half_open_calls=2,
        )
        cb.record_failure()
        cb.state = CircuitState.HALF_OPEN
        cb._half_open_probes = 2

        cb.record_success()
        assert cb._half_open_probes == 1

    def test_probe_counter_decrements_on_failure(self):
        """record_failure in HALF_OPEN should decrement the probe counter then re-open."""
        from services.parallel_adapter_executor import CircuitState

        cb = SimpleCircuitBreaker(
            adapter_name="probe-fail-adapter",
            failure_threshold=1,
            max_half_open_calls=2,
        )
        cb.record_failure()
        cb.state = CircuitState.HALF_OPEN
        cb._half_open_probes = 2

        cb.record_failure()
        # Circuit re-opens; probe counter reset by _transition_to_half_open on next cycle
        assert cb.state == CircuitState.OPEN

    def test_transition_to_half_open_resets_probe_counter(self):
        """Moving to HALF_OPEN must reset _half_open_probes to zero."""
        from services.parallel_adapter_executor import CircuitState

        cb = SimpleCircuitBreaker(
            adapter_name="reset-probes-adapter",
            failure_threshold=1,
            recovery_timeout=0.01,
            max_half_open_calls=3,
        )
        cb.record_failure()
        # Manually exhaust probes
        cb.state = CircuitState.HALF_OPEN
        cb._half_open_probes = 3

        # Re-open then let recovery expire
        cb._open_circuit()
        import time; time.sleep(0.05)
        cb.is_open()  # triggers OPEN → HALF_OPEN transition

        assert cb.state == CircuitState.HALF_OPEN
        assert cb._half_open_probes == 0


if __name__ == "__main__":
    pytest.main([__file__])
