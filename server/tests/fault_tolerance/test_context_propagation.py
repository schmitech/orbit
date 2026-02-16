"""
Test for request context propagation in ParallelAdapterExecutor
"""

import pytest
import uuid
from unittest.mock import Mock
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))

from services.parallel_adapter_executor import (
    ParallelAdapterExecutor, 
    AdapterExecutionContext,
    AdapterResult
)


class TestContextPropagation:
    
    @pytest.fixture
    def mock_adapter_manager(self):
        """Mock adapter manager"""
        manager = Mock()
        manager.get_adapter = Mock(return_value=Mock())
        return manager
    
    @pytest.fixture
    def config_with_adapters(self):
        """Configuration with adapter definitions"""
        return {
            'adapters': [
                {
                    'name': 'test-adapter-1',
                    'fault_tolerance': {
                        'operation_timeout': 10.0,
                        'failure_threshold': 3,
                        'recovery_timeout': 30.0,
                        'success_threshold': 2
                    }
                },
                {
                    'name': 'test-adapter-2',
                    'fault_tolerance': {
                        'operation_timeout': 15.0,
                        'failure_threshold': 2,
                        'recovery_timeout': 45.0,
                        'success_threshold': 1
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
    def executor(self, mock_adapter_manager, config_with_adapters):
        """Create executor instance"""
        return ParallelAdapterExecutor(mock_adapter_manager, config_with_adapters)
    
    def test_adapter_execution_context_creation(self):
        """Test AdapterExecutionContext creation and log prefix"""
        context = AdapterExecutionContext(
            request_id="test-request-123",
            user_id="user-456",
            trace_id="trace-789",
            session_id="session-abc",
            correlation_id="corr-def"
        )
        
        assert context.request_id == "test-request-123"
        assert context.user_id == "user-456"
        assert context.trace_id == "trace-789"
        assert context.session_id == "session-abc"
        assert context.correlation_id == "corr-def"
        
        # Test log prefix
        log_prefix = context.get_log_prefix()
        assert "[test-request-123]" in log_prefix
        assert "trace:trace-789" in log_prefix
        assert "user:user-456" in log_prefix
        assert "session:session-abc" in log_prefix
    
    def test_adapter_execution_context_minimal(self):
        """Test AdapterExecutionContext with minimal fields"""
        context = AdapterExecutionContext(
            request_id="minimal-request"
        )
        
        assert context.request_id == "minimal-request"
        assert context.user_id is None
        assert context.trace_id is None
        assert context.session_id is None
        assert context.correlation_id is None
        
        # Test log prefix with minimal fields
        log_prefix = context.get_log_prefix()
        assert log_prefix == "[minimal-request]"
    
    def test_adapter_result_with_context(self):
        """Test AdapterResult with context"""
        context = AdapterExecutionContext(
            request_id="test-request",
            user_id="test-user"
        )
        
        result = AdapterResult(
            adapter_name="test-adapter",
            success=True,
            data=[{"content": "test data"}],
            execution_time=1.5,
            context=context
        )
        
        assert result.adapter_name == "test-adapter"
        assert result.success is True
        assert result.context == context
        assert result.context.request_id == "test-request"
        assert result.context.user_id == "test-user"
    
    @pytest.mark.asyncio
    async def test_execute_adapters_with_context(self, executor):
        """Test executing adapters with explicit context"""
        # Create mock adapter that returns successfully
        mock_adapter = Mock()
        mock_adapter.get_relevant_context = Mock(return_value=[{"content": "test data"}])
        executor.adapter_manager.get_adapter = Mock(return_value=mock_adapter)
        
        # Create context
        context = AdapterExecutionContext(
            request_id="test-request-123",
            user_id="test-user-456",
            trace_id="test-trace-789"
        )
        
        # Execute adapters with context
        results = await executor.execute_adapters(
            query="test query",
            adapter_names=["test-adapter-1", "test-adapter-2"],
            context=context
        )
        
        # Verify results
        assert len(results) == 2
        for result in results:
            assert result.success
            assert result.context == context
            assert result.context.request_id == "test-request-123"
            assert result.context.user_id == "test-user-456"
            assert result.context.trace_id == "test-trace-789"
        
        # Verify adapter was called with context information
        assert mock_adapter.get_relevant_context.call_count == 2
        for call in mock_adapter.get_relevant_context.call_args_list:
            kwargs = call[1]  # Get kwargs
            assert kwargs['request_id'] == "test-request-123"
            assert kwargs['user_id'] == "test-user-456"
            assert kwargs['trace_id'] == "test-trace-789"
    
    @pytest.mark.asyncio
    async def test_execute_adapters_without_context(self, executor):
        """Test executing adapters without explicit context (should auto-generate)"""
        # Create mock adapter
        mock_adapter = Mock()
        mock_adapter.get_relevant_context = Mock(return_value=[{"content": "test data"}])
        executor.adapter_manager.get_adapter = Mock(return_value=mock_adapter)
        
        # Execute adapters without context
        results = await executor.execute_adapters(
            query="test query",
            adapter_names=["test-adapter-1"],
            api_key="test-api-key"
        )
        
        # Verify results
        assert len(results) == 1
        result = results[0]
        assert result.success
        assert result.context is not None
        assert result.context.request_id is not None
        assert result.context.api_key == "test-api-key"
        
        # Verify auto-generated request_id is a UUID
        try:
            uuid.UUID(result.context.request_id)
        except ValueError:
            pytest.fail("Auto-generated request_id should be a valid UUID")
    
    @pytest.mark.asyncio
    async def test_context_propagation_to_adapters(self, executor):
        """Test that context information is propagated to adapter calls"""
        # Create mock adapter to capture kwargs
        mock_adapter = Mock()
        mock_adapter.get_relevant_context = Mock(return_value=[{"content": "test data"}])
        executor.adapter_manager.get_adapter = Mock(return_value=mock_adapter)
        
        # Create context with all fields
        context = AdapterExecutionContext(
            request_id="full-context-request",
            user_id="full-context-user",
            trace_id="full-context-trace",
            session_id="full-context-session",
            correlation_id="full-context-correlation"
        )
        
        # Execute adapters
        await executor.execute_adapters(
            query="test query",
            adapter_names=["test-adapter-1"],
            context=context,
            api_key="full-context-api-key"
        )
        
        # Verify all context fields were passed to adapter
        call_args = mock_adapter.get_relevant_context.call_args
        kwargs = call_args[1]  # Get kwargs
        
        assert kwargs['request_id'] == "full-context-request"
        assert kwargs['user_id'] == "full-context-user"
        assert kwargs['trace_id'] == "full-context-trace"
        assert kwargs['session_id'] == "full-context-session"
        assert kwargs['correlation_id'] == "full-context-correlation"
        assert kwargs['api_key'] == "full-context-api-key"
    
    def test_combine_results_with_context(self, executor):
        """Test that _combine_results includes context information"""
        # Create context
        context = AdapterExecutionContext(
            request_id="combine-test-request",
            user_id="combine-test-user",
            trace_id="combine-test-trace"
        )
        
        # Create results with context
        results = [
            AdapterResult(
                adapter_name="adapter-1",
                success=True,
                data=[{"content": "data 1", "score": 0.9}],
                execution_time=1.0,
                context=context
            ),
            AdapterResult(
                adapter_name="adapter-2",
                success=True,
                data=[{"content": "data 2", "score": 0.8}],
                execution_time=1.5,
                context=context
            )
        ]
        
        # Combine results
        combined = executor._combine_results(results)
        
        # Verify context information is included
        assert len(combined) == 2
        
        for item in combined:
            assert item["request_id"] == "combine-test-request"
            assert item["user_id"] == "combine-test-user"
            assert item["trace_id"] == "combine-test-trace"
            assert "adapter_name" in item
            assert "execution_time" in item
            assert "content" in item
    
    def test_combine_results_without_context(self, executor):
        """Test that _combine_results works without context"""
        # Create results without context
        results = [
            AdapterResult(
                adapter_name="adapter-1",
                success=True,
                data=[{"content": "data 1", "score": 0.9}],
                execution_time=1.0,
                context=None
            )
        ]
        
        # Combine results
        combined = executor._combine_results(results)
        
        # Verify basic information is included
        assert len(combined) == 1
        item = combined[0]
        assert item["adapter_name"] == "adapter-1"
        assert item["execution_time"] == 1.0
        assert item["content"] == "data 1"
        
        # Verify context fields are not present
        assert "request_id" not in item
        assert "user_id" not in item
        assert "trace_id" not in item


if __name__ == "__main__":
    pytest.main([__file__]) 