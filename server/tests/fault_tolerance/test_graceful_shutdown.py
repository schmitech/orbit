"""
Test for graceful shutdown handling in ParallelAdapterExecutor
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))

from services.parallel_adapter_executor import (
    ParallelAdapterExecutor, 
    AdapterExecutionContext,
    AdapterResult
)


class TestGracefulShutdown:
    
    @pytest.fixture
    def mock_adapter_manager(self):
        """Mock adapter manager"""
        manager = Mock()
        manager.get_adapter = Mock(return_value=Mock())
        return manager
    
    @pytest.fixture
    def config_with_shutdown(self):
        """Configuration with shutdown settings"""
        return {
            'fault_tolerance': {
                'failure_threshold': 5,
                'recovery_timeout': 30.0,
                'success_threshold': 3,
                'operation_timeout': 30.0,
                'execution': {
                    'timeout': 35.0,
                    'max_concurrent_adapters': 10,
                    'shutdown_timeout': 5.0  # Short timeout for testing
                }
            }
        }
    
    @pytest.fixture
    def executor(self, mock_adapter_manager, config_with_shutdown):
        """Create executor instance"""
        return ParallelAdapterExecutor(mock_adapter_manager, config_with_shutdown)
    
    def test_shutdown_initialization(self, executor):
        """Test that shutdown components are properly initialized"""
        assert executor._shutdown_event is not None
        assert executor._active_requests == set()
        assert executor._shutdown_timeout == 5.0
        assert not executor.is_shutting_down()
        assert executor.get_active_request_count() == 0
        assert executor.get_active_requests() == []
    
    @pytest.mark.asyncio
    async def test_reject_requests_during_shutdown(self, executor):
        """Test that new requests are rejected during shutdown"""
        # Create mock adapter
        mock_adapter = Mock()
        mock_adapter.get_relevant_context = Mock(return_value=[{"content": "test data"}])
        executor.adapter_manager.get_adapter = Mock(return_value=mock_adapter)
        
        # Start shutdown
        executor._shutdown_event.set()
        
        # Try to execute adapters
        results = await executor.execute_adapters(
            query="test query",
            adapter_names=["test-adapter"]
        )
        
        # Should be rejected
        assert len(results) == 1
        assert not results[0].success
        assert "Executor is shutting down" in str(results[0].error)
        
        # Adapter should not have been called
        mock_adapter.get_relevant_context.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_active_request_tracking(self, executor):
        """Test that active requests are properly tracked"""
        # Create mock adapter that simulates a delay
        mock_adapter = Mock()
        
        async def delayed_get_relevant_context(*args, **kwargs):
            await asyncio.sleep(0.2)  # Simulate processing time
            return [{"content": "test data"}]
        
        mock_adapter.get_relevant_context = delayed_get_relevant_context
        executor.adapter_manager.get_adapter = Mock(return_value=mock_adapter)
        
        # Create context
        context = AdapterExecutionContext(request_id="test-request-123")
        
        # Start execution in background
        task = asyncio.create_task(
            executor.execute_adapters(
                query="test query",
                adapter_names=["test-adapter"],
                context=context
            )
        )
        
        # Wait a bit for execution to start
        await asyncio.sleep(0.1)
        
        # Check that request is tracked
        assert executor.get_active_request_count() == 1
        assert "test-request-123" in executor.get_active_requests()
        
        # Wait for completion
        results = await task
        
        # Check that request is no longer tracked
        assert executor.get_active_request_count() == 0
        assert "test-request-123" not in executor.get_active_requests()
        assert len(results) == 1
        assert results[0].success
    
    @pytest.mark.asyncio
    async def test_graceful_shutdown_with_active_requests(self, executor):
        """Test graceful shutdown with active requests"""
        # Create mock adapter with longer delay
        mock_adapter = Mock()
        
        async def delayed_get_relevant_context(*args, **kwargs):
            await asyncio.sleep(0.3)  # Simulate processing time
            return [{"content": "test data"}]
        
        mock_adapter.get_relevant_context = delayed_get_relevant_context
        executor.adapter_manager.get_adapter = Mock(return_value=mock_adapter)
        
        # Create context
        context = AdapterExecutionContext(request_id="test-request-456")
        
        # Start execution in background
        task = asyncio.create_task(
            executor.execute_adapters(
                query="test query",
                adapter_names=["test-adapter"],
                context=context
            )
        )
        
        # Wait a bit for execution to start
        await asyncio.sleep(0.1)
        
        # Verify request is active
        assert executor.get_active_request_count() == 1
        
        # Start cleanup in background
        cleanup_task = asyncio.create_task(executor.cleanup())
        
        # Wait for cleanup to complete
        await cleanup_task
        
        # Verify shutdown state
        assert executor.is_shutting_down()
        
        # Wait for original task to complete
        results = await task
        
        # Verify results
        assert len(results) == 1
        assert results[0].success
    
    @pytest.mark.asyncio
    async def test_shutdown_timeout_handling(self, executor):
        """Test shutdown timeout when requests don't complete"""
        # Create mock adapter that takes longer than shutdown timeout
        mock_adapter = Mock()
        
        async def long_delayed_get_relevant_context(*args, **kwargs):
            await asyncio.sleep(10.0)  # Longer than shutdown timeout
            return [{"content": "test data"}]
        
        mock_adapter.get_relevant_context = long_delayed_get_relevant_context
        executor.adapter_manager.get_adapter = Mock(return_value=mock_adapter)
        
        # Create context
        context = AdapterExecutionContext(request_id="test-request-789")
        
        # Start execution in background
        task = asyncio.create_task(
            executor.execute_adapters(
                query="test query",
                adapter_names=["test-adapter"],
                context=context
            )
        )
        
        # Wait a bit for execution to start
        await asyncio.sleep(0.1)
        
        # Verify request is active
        assert executor.get_active_request_count() == 1
        
        # Start cleanup (should timeout)
        start_time = time.time()
        await executor.cleanup()
        cleanup_time = time.time() - start_time
        
        # Verify cleanup took approximately the shutdown timeout
        assert cleanup_time >= executor._shutdown_timeout
        assert cleanup_time <= executor._shutdown_timeout + 1.0  # Allow some tolerance
        
        # Verify shutdown state
        assert executor.is_shutting_down()
        
        # Cancel the original task since it won't complete
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    
    @pytest.mark.asyncio
    async def test_multiple_active_requests_during_shutdown(self, executor):
        """Test shutdown with multiple active requests"""
        # Create mock adapter with delay
        mock_adapter = Mock()
        
        async def delayed_get_relevant_context(*args, **kwargs):
            await asyncio.sleep(0.2)  # Simulate processing time
            return [{"content": "test data"}]
        
        mock_adapter.get_relevant_context = delayed_get_relevant_context
        executor.adapter_manager.get_adapter = Mock(return_value=mock_adapter)
        
        # Start multiple executions
        contexts = [
            AdapterExecutionContext(request_id=f"test-request-{i}")
            for i in range(3)
        ]
        
        tasks = []
        for context in contexts:
            task = asyncio.create_task(
                executor.execute_adapters(
                    query="test query",
                    adapter_names=["test-adapter"],
                    context=context
                )
            )
            tasks.append(task)
        
        # Wait a bit for executions to start
        await asyncio.sleep(0.1)
        
        # Verify all requests are active
        assert executor.get_active_request_count() == 3
        
        # Start cleanup
        cleanup_task = asyncio.create_task(executor.cleanup())
        
        # Wait for cleanup to complete
        await cleanup_task
        
        # Verify shutdown state
        assert executor.is_shutting_down()
        
        # Wait for all tasks to complete
        results_list = await asyncio.gather(*tasks)
        
        # Verify all results
        for results in results_list:
            assert len(results) == 1
            assert results[0].success
    
    @pytest.mark.asyncio
    async def test_cleanup_without_active_requests(self, executor):
        """Test cleanup when no requests are active"""
        # Start cleanup immediately
        start_time = time.time()
        await executor.cleanup()
        cleanup_time = time.time() - start_time
        
        # Should complete quickly
        assert cleanup_time < 1.0
        
        # Verify shutdown state
        assert executor.is_shutting_down()
        assert executor.get_active_request_count() == 0
    
    def test_health_status_includes_shutdown_info(self, executor):
        """Test that health status includes shutdown information"""
        health = executor.get_health_status()
        
        assert "shutdown_status" in health
        shutdown_status = health["shutdown_status"]
        
        assert "is_shutting_down" in shutdown_status
        assert "active_request_count" in shutdown_status
        assert "active_requests" in shutdown_status
        assert "shutdown_timeout" in shutdown_status
        
        assert shutdown_status["is_shutting_down"] is False
        assert shutdown_status["active_request_count"] == 0
        assert shutdown_status["active_requests"] == []
        assert shutdown_status["shutdown_timeout"] == 5.0
    
    @pytest.mark.asyncio
    async def test_shutdown_after_cleanup(self, executor):
        """Test that shutdown state persists after cleanup"""
        # Run cleanup
        await executor.cleanup()
        
        # Verify shutdown state
        assert executor.is_shutting_down()
        
        # Try to execute adapters (should be rejected)
        results = await executor.execute_adapters(
            query="test query",
            adapter_names=["test-adapter"]
        )
        
        # Should be rejected
        assert len(results) == 1
        assert not results[0].success
        assert "Executor is shutting down" in str(results[0].error)
    
    @pytest.mark.asyncio
    async def test_exception_handling_during_shutdown(self, executor):
        """Test that exceptions during execution don't break shutdown tracking"""
        # Create mock adapter that raises an exception
        mock_adapter = Mock()
        mock_adapter.get_relevant_context = Mock(side_effect=Exception("Test error"))
        executor.adapter_manager.get_adapter = Mock(return_value=mock_adapter)
        
        # Create context
        context = AdapterExecutionContext(request_id="test-request-error")
        
        # Execute adapters
        results = await executor.execute_adapters(
            query="test query",
            adapter_names=["test-adapter"],
            context=context
        )
        
        # Verify request tracking is cleaned up even with error
        assert executor.get_active_request_count() == 0
        assert "test-request-error" not in executor.get_active_requests()
        
        # Verify results
        assert len(results) == 1
        assert not results[0].success
        assert "Test error" in str(results[0].error)


if __name__ == "__main__":
    pytest.main([__file__]) 