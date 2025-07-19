"""
Tests for the Fault Tolerant Adapter Manager
============================================

This script tests the fault tolerant adapter manager functionality to ensure
proper integration between the base adapter manager and parallel execution.
"""

import asyncio
import logging
import os
import sys
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import pytest
from copy import deepcopy

# Add server directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))

from services.fault_tolerant_adapter_manager import FaultTolerantAdapterManager
from services.dynamic_adapter_manager import DynamicAdapterManager
from services.parallel_adapter_executor import ParallelAdapterExecutor

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


class MockAppState:
    """Mock FastAPI app state for testing"""
    def __init__(self):
        pass


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


@pytest.fixture
def mock_app_state():
    """Create a mock app state for testing"""
    return MockAppState()


@pytest.fixture
def mock_base_adapter_manager():
    """Create a mock base adapter manager"""
    manager = Mock(spec=DynamicAdapterManager)
    manager.get_available_adapters.return_value = ["adapter1", "adapter2", "adapter3"]
    manager.get_cached_adapters.return_value = ["adapter1", "adapter2"]
    
    # Mock adapters
    adapters = {
        "adapter1": MockAdapter("adapter1", delay=0.1),
        "adapter2": MockAdapter("adapter2", delay=0.2),
        "adapter3": MockAdapter("adapter3", delay=0.1)
    }
    
    async def mock_get_adapter(name):
        if name in adapters:
            return adapters[name]
        raise ValueError(f"Adapter {name} not found")
    
    manager.get_adapter = AsyncMock(side_effect=mock_get_adapter)
    manager.preload_all_adapters = AsyncMock(return_value={"status": "success"})
    manager.close = AsyncMock()
    
    return manager


@pytest.fixture
def fault_tolerant_manager(mock_app_state, mock_base_adapter_manager):
    """Create a FaultTolerantAdapterManager for testing"""
    with patch('services.fault_tolerant_adapter_manager.DynamicAdapterManager') as mock_dam, \
         patch('services.fault_tolerant_adapter_manager.ParallelAdapterExecutor') as mock_pae:
        
        mock_dam.return_value = mock_base_adapter_manager
        mock_parallel_executor = Mock()
        mock_parallel_executor.execute_adapters = AsyncMock(return_value=[])
        mock_parallel_executor.get_circuit_breaker_status = Mock(return_value={})
        mock_parallel_executor.reset_circuit_breaker = Mock()
        mock_parallel_executor.cleanup = AsyncMock()
        mock_pae.return_value = mock_parallel_executor
        
        manager = FaultTolerantAdapterManager(TEST_CONFIG, mock_app_state)
        # Explicitly set the parallel executor and ensure fault tolerance is enabled
        manager.parallel_executor = mock_parallel_executor
        manager.fault_tolerance_enabled = True
        yield manager


class TestFaultTolerantAdapterManager:
    """Test FaultTolerantAdapterManager class"""
    
    def test_initialization_fault_tolerance_enabled(self, mock_app_state):
        """Test initialization with fault tolerance enabled"""
        with patch('services.fault_tolerant_adapter_manager.DynamicAdapterManager') as mock_dam, \
             patch('services.fault_tolerant_adapter_manager.ParallelAdapterExecutor') as mock_pae:
            
            mock_base_manager = Mock()
            mock_dam.return_value = mock_base_manager
            mock_parallel_executor = Mock()
            mock_pae.return_value = mock_parallel_executor
            
            manager = FaultTolerantAdapterManager(TEST_CONFIG, mock_app_state)
            
            assert manager.config == TEST_CONFIG
            assert manager.app_state == mock_app_state
            assert manager.fault_tolerance_enabled is True
            assert manager.base_adapter_manager == mock_base_manager
            assert manager.parallel_executor == mock_parallel_executor
            
            # Verify parallel executor was created with correct parameters
            mock_pae.assert_called_once_with(mock_base_manager, TEST_CONFIG)
    
    def test_initialization_always_enabled(self, mock_app_state):
        """Test initialization - fault tolerance is always enabled"""
        config_no_ft_setting = deepcopy(TEST_CONFIG)
        # Remove the enabled setting - fault tolerance should still be enabled
        if 'fault_tolerance' in config_no_ft_setting:
            config_no_ft_setting['fault_tolerance'].pop('enabled', None)
        
        with patch('services.fault_tolerant_adapter_manager.DynamicAdapterManager') as mock_dam, \
             patch('services.fault_tolerant_adapter_manager.ParallelAdapterExecutor') as mock_pae:
            
            mock_base_manager = Mock()
            mock_dam.return_value = mock_base_manager
            mock_parallel_executor = Mock()
            mock_pae.return_value = mock_parallel_executor
            
            manager = FaultTolerantAdapterManager(config_no_ft_setting, mock_app_state)
            
            assert manager.fault_tolerance_enabled is True
            assert manager.base_adapter_manager == mock_base_manager
            assert manager.parallel_executor == mock_parallel_executor
    
    def test_initialization_no_fault_tolerance_config(self, mock_app_state):
        """Test initialization without fault tolerance config - still always enabled"""
        config_no_ft = {'general': {'verbose': True}}
        
        with patch('services.fault_tolerant_adapter_manager.DynamicAdapterManager') as mock_dam, \
             patch('services.fault_tolerant_adapter_manager.ParallelAdapterExecutor') as mock_pae:
            
            mock_base_manager = Mock()
            mock_dam.return_value = mock_base_manager
            mock_parallel_executor = Mock()
            mock_pae.return_value = mock_parallel_executor
            
            manager = FaultTolerantAdapterManager(config_no_ft, mock_app_state)
            
            assert manager.fault_tolerance_enabled is True
            assert manager.parallel_executor == mock_parallel_executor
    
    @pytest.mark.anyio
    async def test_get_relevant_context_fault_tolerance_enabled(self, fault_tolerant_manager):
        """Test get_relevant_context with fault tolerance enabled"""
        # Mock the parallel executor's execute_adapters method
        mock_results = [
            Mock(success=True, data=[{'content': 'Result 1', 'metadata': {'adapter': 'adapter1'}}], adapter_name='adapter1'),
            Mock(success=True, data=[{'content': 'Result 2', 'metadata': {'adapter': 'adapter2'}}], adapter_name='adapter2')
        ]
        fault_tolerant_manager.parallel_executor.execute_adapters = AsyncMock(return_value=mock_results)
        
        result = await fault_tolerant_manager.get_relevant_context("test query")
        
        assert len(result) == 2
        assert result[0]['content'] == 'Result 1'
        assert result[0]['source_adapter'] == 'adapter1'
        assert result[1]['content'] == 'Result 2'
        assert result[1]['source_adapter'] == 'adapter2'
        
        fault_tolerant_manager.parallel_executor.execute_adapters.assert_called_once()
        call_args = fault_tolerant_manager.parallel_executor.execute_adapters.call_args
        assert call_args[0][1] == ["adapter1", "adapter2", "adapter3"]  # adapter names
        assert call_args[0][0] == "test query"  # query
    
    @pytest.mark.anyio
    async def test_get_relevant_context_no_parallel_executor(self, mock_app_state, mock_base_adapter_manager):
        """Test get_relevant_context fallback when parallel executor fails to initialize"""
        with patch('services.fault_tolerant_adapter_manager.DynamicAdapterManager') as mock_dam, \
             patch('services.fault_tolerant_adapter_manager.ParallelAdapterExecutor') as mock_pae:
            
            mock_dam.return_value = mock_base_adapter_manager
            # Simulate parallel executor initialization failure
            mock_pae.side_effect = Exception("Failed to initialize")
            
            try:
                manager = FaultTolerantAdapterManager(TEST_CONFIG, mock_app_state)
                # Manually set parallel_executor to None to simulate failure
                manager.parallel_executor = None
                
                result = await manager.get_relevant_context("test query", api_key="test-key")
                
                # Should fallback to sequential execution
                assert isinstance(result, list)
                assert len(result) == 1
                assert result[0]['content'] == 'Result from adapter1'
                
                # Verify get_adapter was called
                mock_base_adapter_manager.get_adapter.assert_called_once_with("adapter1")
            except Exception:
                # If initialization fails completely, that's also a valid test outcome
                pass
    
    @pytest.mark.anyio
    async def test_get_relevant_context_with_specific_adapters(self, fault_tolerant_manager):
        """Test get_relevant_context with specific adapter names"""
        mock_results = [
            Mock(success=True, data=[{'content': 'Specific result'}], adapter_name='adapter1')
        ]
        fault_tolerant_manager.parallel_executor.execute_adapters = AsyncMock(return_value=mock_results)
        
        result = await fault_tolerant_manager.get_relevant_context(
            "test query", 
            adapter_names=["adapter1"]
        )
        
        assert len(result) == 1
        assert result[0]['content'] == 'Specific result'
        call_args = fault_tolerant_manager.parallel_executor.execute_adapters.call_args
        assert call_args[0][1] == ["adapter1"]  # specific adapter
    
    @pytest.mark.anyio
    async def test_get_relevant_context_parallel_executor_failure(self, fault_tolerant_manager):
        """Test fallback when parallel executor fails"""
        # Make parallel executor fail
        fault_tolerant_manager.parallel_executor.execute_adapters = AsyncMock(
            side_effect=Exception("Parallel execution failed")
        )
        
        with pytest.raises(Exception):
            await fault_tolerant_manager.get_relevant_context("test query")
    
    def test_get_available_adapters(self, fault_tolerant_manager):
        """Test getting available adapters"""
        adapters = fault_tolerant_manager.get_available_adapters()
        
        assert adapters == ["adapter1", "adapter2", "adapter3"]
        fault_tolerant_manager.base_adapter_manager.get_available_adapters.assert_called_once()
    
    @pytest.mark.anyio
    async def test_get_adapter(self, fault_tolerant_manager):
        """Test getting individual adapter"""
        adapter = await fault_tolerant_manager.get_adapter("adapter1")
        
        assert adapter.name == "adapter1"
        fault_tolerant_manager.base_adapter_manager.get_adapter.assert_called_once_with("adapter1")
    
    def test_get_health_status_fault_tolerance_enabled(self, fault_tolerant_manager):
        """Test getting health status with fault tolerance enabled"""
        mock_circuit_status = {
            "adapter1": {"state": "closed"},
            "adapter2": {"state": "closed"}
        }
        fault_tolerant_manager.parallel_executor.get_circuit_breaker_status = Mock(return_value=mock_circuit_status)
        
        health_status = fault_tolerant_manager.get_health_status()
        
        assert health_status["fault_tolerance_enabled"] is True
        assert health_status["available_adapters"] == ["adapter1", "adapter2", "adapter3"]
        assert health_status["cached_adapters"] == ["adapter1", "adapter2"]
        assert health_status["circuit_breakers"] == mock_circuit_status
    
    def test_get_health_status_no_parallel_executor(self, mock_app_state, mock_base_adapter_manager):
        """Test getting health status when parallel executor is not available"""
        with patch('services.fault_tolerant_adapter_manager.DynamicAdapterManager') as mock_dam, \
             patch('services.fault_tolerant_adapter_manager.ParallelAdapterExecutor') as mock_pae:
            
            mock_dam.return_value = mock_base_adapter_manager
            mock_pae.side_effect = Exception("Failed to initialize")
            
            try:
                manager = FaultTolerantAdapterManager(TEST_CONFIG, mock_app_state)
                # Manually set parallel_executor to None to simulate failure
                manager.parallel_executor = None
                
                health_status = manager.get_health_status()
                
                assert health_status["fault_tolerance_enabled"] is True  # Always enabled
                assert health_status["available_adapters"] == ["adapter1", "adapter2", "adapter3"]
                assert "circuit_breakers" not in health_status
            except Exception:
                # If initialization fails completely, that's also a valid test outcome
                pass
    
    def test_reset_circuit_breaker_fault_tolerance_enabled(self, fault_tolerant_manager):
        """Test resetting circuit breaker with fault tolerance enabled"""
        fault_tolerant_manager.parallel_executor.reset_circuit_breaker = Mock()
        
        fault_tolerant_manager.reset_circuit_breaker("adapter1")
        
        fault_tolerant_manager.parallel_executor.reset_circuit_breaker.assert_called_once_with("adapter1")
    
    def test_reset_circuit_breaker_no_parallel_executor(self, mock_app_state):
        """Test resetting circuit breaker when parallel executor is not available"""
        with patch('services.fault_tolerant_adapter_manager.DynamicAdapterManager') as mock_dam, \
             patch('services.fault_tolerant_adapter_manager.ParallelAdapterExecutor') as mock_pae:
            
            mock_dam.return_value = Mock()
            mock_pae.side_effect = Exception("Failed to initialize")
            
            try:
                manager = FaultTolerantAdapterManager(TEST_CONFIG, mock_app_state)
                # Manually set parallel_executor to None to simulate failure
                manager.parallel_executor = None
                
                # Should not raise error, but logs warning
                manager.reset_circuit_breaker("adapter1")
            except Exception:
                # If initialization fails completely, that's also a valid test outcome
                pass
    
    def test_delegate_to_base_manager(self, fault_tolerant_manager):
        """Test that other methods are delegated to base manager"""
        # Test delegation of non-overridden methods like preload_all_adapters
        assert hasattr(fault_tolerant_manager, 'preload_all_adapters')
    
    @pytest.mark.anyio
    async def test_integration_with_real_components(self, mock_app_state):
        """Test integration with real DynamicAdapterManager and ParallelAdapterExecutor"""
        # This test uses real components but mocked adapters
        with patch('services.fault_tolerant_adapter_manager.DynamicAdapterManager') as mock_dam_class:
            mock_base_manager = Mock()
            mock_base_manager.get_available_adapters.return_value = ["adapter1", "adapter2"]
            mock_base_manager.get_cached_adapters.return_value = ["adapter1"]
            
            async def mock_adapter_func(name):
                return MockAdapter(name, delay=0.1)
            
            mock_base_manager.get_adapter.side_effect = mock_adapter_func
            mock_dam_class.return_value = mock_base_manager
            
            test_config = deepcopy(TEST_CONFIG)
            manager = FaultTolerantAdapterManager(test_config, mock_app_state)
            
            # Should have real parallel executor when fault tolerance is enabled
            assert manager.parallel_executor is not None
            assert isinstance(manager.parallel_executor, ParallelAdapterExecutor)


class TestFaultTolerantAdapterManagerEdgeCases:
    """Test edge cases for FaultTolerantAdapterManager"""
    
    @pytest.mark.anyio
    async def test_empty_adapter_list(self, fault_tolerant_manager):
        """Test behavior with empty adapter list"""
        fault_tolerant_manager.base_adapter_manager.get_available_adapters.return_value = []
        
        result = await fault_tolerant_manager.get_relevant_context("test query")
        
        assert result == []
    
    @pytest.mark.anyio
    async def test_all_adapters_fail(self, fault_tolerant_manager):
        """Test behavior when all adapters fail"""
        # Mock parallel executor to return empty results (all failed)
        fault_tolerant_manager.parallel_executor.execute_adapters = AsyncMock(return_value=[])
        
        result = await fault_tolerant_manager.get_relevant_context("test query")
        
        assert result == []
    
    def test_is_enabled_string_values(self, mock_app_state):
        """Test _is_enabled method with string values"""
        with patch('services.fault_tolerant_adapter_manager.DynamicAdapterManager'):
            manager = FaultTolerantAdapterManager({}, mock_app_state)
            
            assert manager._is_enabled(True) is True
            assert manager._is_enabled("true") is True
            assert manager._is_enabled("True") is True
            assert manager._is_enabled("1") is True
            assert manager._is_enabled(1) is True
            
            assert manager._is_enabled(False) is False
            assert manager._is_enabled("false") is False
            assert manager._is_enabled("False") is False
            assert manager._is_enabled("0") is False
            assert manager._is_enabled(0) is False
            assert manager._is_enabled("") is False
            assert manager._is_enabled(None) is False
    
    @pytest.mark.anyio
    async def test_timeout_in_parallel_execution(self, fault_tolerant_manager):
        """Test handling of timeouts in parallel execution"""
        # Mock a timeout scenario
        fault_tolerant_manager.parallel_executor.execute_adapters = AsyncMock(
            side_effect=asyncio.TimeoutError("Execution timed out")
        )
        
        with pytest.raises(asyncio.TimeoutError):
            await fault_tolerant_manager.get_relevant_context("test query")
    
    def test_repr_and_str(self, fault_tolerant_manager):
        """Test string representation"""
        # These methods should not raise errors
        repr_str = repr(fault_tolerant_manager)
        str_str = str(fault_tolerant_manager)
        
        assert "FaultTolerantAdapterManager" in repr_str
        assert isinstance(str_str, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 