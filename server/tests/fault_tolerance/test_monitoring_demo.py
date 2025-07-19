"""
Test module to demonstrate circuit breaker monitoring in action.

This module tests:
1. Circuit breaker event handling
2. Memory leak prevention
3. Event handler logging
4. Circuit state transitions
"""

import asyncio
import time
import logging
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))

from services.parallel_adapter_executor import (
    SimpleCircuitBreaker, 
    DefaultCircuitBreakerEventHandler,
    MonitoringCircuitBreakerEventHandler,
    CircuitBreakerEventHandler
)

# Set up logging to see the events
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

class DemoEventHandler(CircuitBreakerEventHandler):
    """Demo event handler that logs all events with custom formatting"""
    
    async def on_circuit_open(self, adapter_name: str, stats: dict, reason: str = ""):
        """Log circuit open event with detailed info"""
        logger.error(f"🚨 CIRCUIT OPENED: {adapter_name} - Reason: {reason}")
        logger.error(f"   Stats: {stats}")
    
    async def on_circuit_close(self, adapter_name: str, stats: dict):
        """Log circuit close event"""
        logger.info(f"✅ CIRCUIT CLOSED: {adapter_name}")
        logger.info(f"   Stats: {stats}")
    
    async def on_circuit_half_open(self, adapter_name: str, stats: dict):
        """Log circuit half-open event"""
        logger.warning(f"🟡 CIRCUIT HALF-OPEN: {adapter_name}")
        logger.warning(f"   Stats: {stats}")
    
    async def on_circuit_reset(self, adapter_name: str, stats: dict):
        """Log circuit reset event"""
        logger.info(f"🔄 CIRCUIT RESET: {adapter_name}")
        logger.info(f"   Stats: {stats}")

async def test_circuit_breaker_events():
    """Demonstrate circuit breaker events in action"""
    logger.info("🚀 Starting Circuit Breaker Monitoring Demo")
    
    # Create circuit breaker with demo event handler
    cb = SimpleCircuitBreaker(
        adapter_name="demo-adapter",
        failure_threshold=3,  # Open after 3 failures
        recovery_timeout=2.0,  # Try recovery after 2 seconds
        success_threshold=2,   # Close after 2 successes
        event_handler=DemoEventHandler()
    )
    
    logger.info(f"📊 Initial circuit state: {cb.get_status()}")
    
    # Simulate some successful calls
    logger.info("✅ Simulating successful calls...")
    for i in range(5):
        cb.record_success(execution_time=0.1)
        logger.info(f"   Success {i+1}: {cb.get_status()}")
        await asyncio.sleep(0.1)
    
    # Simulate failures to trigger circuit open
    logger.info("❌ Simulating failures to trigger circuit open...")
    for i in range(4):
        cb.record_failure(execution_time=0.2)
        logger.info(f"   Failure {i+1}: {cb.get_status()}")
        await asyncio.sleep(0.1)
    
    # Wait for recovery timeout
    logger.info("⏰ Waiting for recovery timeout...")
    await asyncio.sleep(3.0)
    
    # Check if circuit is half-open
    logger.info("🔍 Checking circuit state...")
    is_open = cb.is_open()
    logger.info(f"   Circuit is_open(): {is_open}")
    
    # Simulate successful recovery
    logger.info("✅ Simulating successful recovery...")
    for i in range(3):
        cb.record_success(execution_time=0.1)
        logger.info(f"   Recovery success {i+1}: {cb.get_status()}")
        await asyncio.sleep(0.1)
    
    # Test memory cleanup
    logger.info("🧹 Testing memory cleanup...")
    cb.force_cleanup()
    
    # Test reset
    logger.info("🔄 Testing circuit reset...")
    cb.reset()
    
    logger.info("🎉 Demo completed!")

async def test_monitoring_handler():
    """Demonstrate monitoring event handler with callbacks"""
    logger.info("📊 Starting Monitoring Handler Demo")
    
    # Track callback calls
    callback_calls = []
    
    async def alert_callback(event_type, adapter_name, stats, reason=""):
        callback_calls.append(("alert", event_type, adapter_name, reason))
        logger.info(f"🚨 ALERT: {event_type} for {adapter_name} - {reason}")
    
    async def dashboard_callback(event_type, adapter_name, stats):
        callback_calls.append(("dashboard", event_type, adapter_name))
        logger.info(f"📈 DASHBOARD: {event_type} for {adapter_name}")
    
    async def metrics_callback(event_type, adapter_name, stats):
        callback_calls.append(("metrics", event_type, adapter_name))
        logger.info(f"📊 METRICS: {event_type} for {adapter_name}")
    
    # Create monitoring event handler
    monitoring_handler = MonitoringCircuitBreakerEventHandler(
        alert_callback=alert_callback,
        dashboard_callback=dashboard_callback,
        metrics_callback=metrics_callback
    )
    
    # Create circuit breaker with monitoring handler
    cb = SimpleCircuitBreaker(
        adapter_name="monitoring-demo",
        failure_threshold=2,
        recovery_timeout=1.0,
        success_threshold=1,
        event_handler=monitoring_handler
    )
    
    # Trigger circuit open
    logger.info("❌ Triggering circuit open...")
    cb.record_failure(execution_time=0.1)
    cb.record_failure(execution_time=0.2)
    
    # Wait for events to process
    await asyncio.sleep(0.5)
    
    # Wait for recovery and trigger close
    await asyncio.sleep(1.5)
    cb.is_open()  # This triggers half-open
    cb.record_success(execution_time=0.1)  # This triggers close
    
    # Wait for events to process
    await asyncio.sleep(0.5)
    
    logger.info(f"📋 Callback calls made: {len(callback_calls)}")
    for call in callback_calls:
        logger.info(f"   {call}")

if __name__ == "__main__":
    # Run as a demo script
    async def main():
        """Run all demos"""
        logger.info("🎬 Circuit Breaker Monitoring Demo Suite")
        logger.info("=" * 50)
        
        # Demo 1: Basic event handling
        await test_circuit_breaker_events()
        
        logger.info("\n" + "=" * 50)
        
        # Demo 2: Monitoring handler with callbacks
        await test_monitoring_handler()
        
        logger.info("\n" + "=" * 50)
        logger.info("🎉 All demos completed!")
    
    asyncio.run(main()) 