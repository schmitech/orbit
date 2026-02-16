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


if __name__ == "__main__":
    pytest.main([__file__]) 