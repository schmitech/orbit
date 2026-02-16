"""
Unit tests for ThreadPoolManager performance utility.
"""

import asyncio
import time
import pytest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor, Future

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.thread_pool_manager import ThreadPoolManager


class TestThreadPoolManager:
    """Test cases for ThreadPoolManager."""
    
    @pytest.fixture
    def mock_config(self):
        """Create a mock configuration for testing."""
        return {
            'performance': {
                'thread_pools': {
                    'io_workers': 5,
                    'cpu_workers': 3,
                    'inference_workers': 2,
                    'embedding_workers': 2,
                    'db_workers': 4
                }
            }
        }
    
    @pytest.fixture
    def thread_pool_manager(self, mock_config):
        """Create a ThreadPoolManager instance for testing."""
        return ThreadPoolManager(mock_config)
    
    def test_initialization(self, mock_config):
        """Test ThreadPoolManager initialization."""
        manager = ThreadPoolManager(mock_config)
        
        # Check that all pools are created
        assert 'io' in manager._pools
        assert 'cpu' in manager._pools
        assert 'inference' in manager._pools
        assert 'embedding' in manager._pools
        assert 'db' in manager._pools
        
        # Check pool sizes
        assert manager._pools['io']._max_workers == 5
        assert manager._pools['cpu']._max_workers == 3
        assert manager._pools['inference']._max_workers == 2
        assert manager._pools['embedding']._max_workers == 2
        assert manager._pools['db']._max_workers == 4
    
    def test_initialization_with_missing_config(self):
        """Test ThreadPoolManager initialization with missing configuration."""
        config = {}  # Empty config
        manager = ThreadPoolManager(config)
        
        # Should use default values
        assert 'io' in manager._pools
        assert manager._pools['io']._max_workers == 50  # Default from implementation
    
    def test_get_pool(self, thread_pool_manager):
        """Test getting specific thread pools."""
        io_pool = thread_pool_manager.get_pool('io')
        cpu_pool = thread_pool_manager.get_pool('cpu')
        
        assert isinstance(io_pool, ThreadPoolExecutor)
        assert isinstance(cpu_pool, ThreadPoolExecutor)
        assert io_pool != cpu_pool  # Different pool instances
    
    def test_get_pool_invalid_type(self, thread_pool_manager):
        """Test getting a pool with invalid type."""
        with pytest.raises(ValueError) as exc_info:
            thread_pool_manager.get_pool('invalid_pool')
        
        assert "Unknown pool type: invalid_pool" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_run_in_pool(self, thread_pool_manager):
        """Test running a function in a specific pool."""
        def cpu_intensive_task(x):
            """Simulate a CPU-intensive task."""
            time.sleep(0.1)  # Simulate work
            return x * x
        
        result = await thread_pool_manager.run_in_pool('cpu', cpu_intensive_task, 5)
        assert result == 25
    
    @pytest.mark.asyncio
    async def test_run_in_pool_with_exception(self, thread_pool_manager):
        """Test running a function that raises an exception."""
        def failing_task():
            raise ValueError("Task failed")
        
        with pytest.raises(ValueError) as exc_info:
            await thread_pool_manager.run_in_pool('io', failing_task)
        
        assert "Task failed" in str(exc_info.value)
    
    def test_submit_to_pool(self, thread_pool_manager):
        """Test submitting a task without waiting."""
        def simple_task(x):
            return x + 1
        
        future = thread_pool_manager.submit_to_pool('io', simple_task, 10)
        assert isinstance(future, Future)
        
        # Wait for result
        result = future.result(timeout=1)
        assert result == 11
    
    @pytest.mark.asyncio
    async def test_batch_executor(self, thread_pool_manager):
        """Test batch executor context manager."""
        results = []
        
        with thread_pool_manager.batch_executor('cpu', max_concurrent=2) as submit:
            # Submit multiple tasks
            task1 = submit(lambda: 1 + 1)
            task2 = submit(lambda: 2 + 2)
            task3 = submit(lambda: 3 + 3)
            
            # Gather results
            results = await asyncio.gather(task1, task2, task3)
        
        assert results == [2, 4, 6]
    
    def test_get_pool_stats(self, thread_pool_manager):
        """Test getting pool statistics."""
        stats = thread_pool_manager.get_pool_stats()
        
        assert 'io' in stats
        assert 'cpu' in stats
        assert 'inference' in stats
        
        # Check stat structure
        io_stats = stats['io']
        assert 'max_workers' in io_stats
        assert 'active_threads' in io_stats
        assert 'queued_tasks' in io_stats
        
        assert io_stats['max_workers'] == 5
    
    def test_shutdown(self, thread_pool_manager):
        """Test shutting down thread pools."""
        # Submit a task to ensure pool is active
        future = thread_pool_manager.submit_to_pool('io', lambda: 42)
        future.result()  # Wait for completion
        
        # Shutdown
        thread_pool_manager.shutdown(wait=True)
        
        # Pools should be cleared
        assert len(thread_pool_manager._pools) == 0
        
        # Should not be able to get pools after shutdown
        with pytest.raises(ValueError):
            thread_pool_manager.get_pool('io')
    
    def test_shutdown_with_pending_tasks(self, thread_pool_manager):
        """Test shutdown behavior with pending tasks."""
        def long_task():
            time.sleep(0.5)
            return "completed"
        
        # Submit a long-running task
        thread_pool_manager.submit_to_pool('cpu', long_task)
        
        # Shutdown without waiting
        thread_pool_manager.shutdown(wait=False)
        
        # Pools should be cleared
        assert len(thread_pool_manager._pools) == 0
    
    def test_context_manager(self, mock_config):
        """Test using ThreadPoolManager as a context manager."""
        with ThreadPoolManager(mock_config) as manager:
            # Should be able to use pools
            pool = manager.get_pool('io')
            assert isinstance(pool, ThreadPoolExecutor)
        
        # After context exit, pools should be shut down
        assert len(manager._pools) == 0
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, thread_pool_manager):
        """Test running multiple concurrent operations across different pools."""
        def io_task(x):
            time.sleep(0.05)  # Simulate I/O
            return f"io_{x}"
        
        def cpu_task(x):
            time.sleep(0.05)  # Simulate CPU work
            return f"cpu_{x}"
        
        def db_task(x):
            time.sleep(0.05)  # Simulate DB query
            return f"db_{x}"
        
        # Run tasks concurrently in different pools
        tasks = [
            thread_pool_manager.run_in_pool('io', io_task, 1),
            thread_pool_manager.run_in_pool('io', io_task, 2),
            thread_pool_manager.run_in_pool('cpu', cpu_task, 1),
            thread_pool_manager.run_in_pool('cpu', cpu_task, 2),
            thread_pool_manager.run_in_pool('db', db_task, 1),
        ]
        
        start_time = time.time()
        results = await asyncio.gather(*tasks)
        elapsed_time = time.time() - start_time
        
        # Check results
        assert 'io_1' in results
        assert 'io_2' in results
        assert 'cpu_1' in results
        assert 'cpu_2' in results
        assert 'db_1' in results
        
        # Should complete faster than sequential execution (5 * 0.05 = 0.25s)
        assert elapsed_time < 0.2  # Some buffer for overhead
    
    @pytest.mark.asyncio
    async def test_pool_isolation(self, thread_pool_manager):
        """Test that different pools are isolated from each other."""
        io_results = []
        cpu_results = []
        
        def io_task(x):
            io_results.append(x)
            return x
        
        def cpu_task(x):
            cpu_results.append(x)
            return x
        
        # Submit tasks to different pools
        await asyncio.gather(
            thread_pool_manager.run_in_pool('io', io_task, 1),
            thread_pool_manager.run_in_pool('cpu', cpu_task, 2),
            thread_pool_manager.run_in_pool('io', io_task, 3),
            thread_pool_manager.run_in_pool('cpu', cpu_task, 4),
        )
        
        # Check that tasks ran in correct pools
        assert io_results == [1, 3]
        assert cpu_results == [2, 4]
    
    def test_fallback_pool_size(self):
        """Test fallback behavior when pool initialization fails."""
        config = {
            'performance': {
                'thread_pools': {
                    'io_workers': -1,  # Invalid value
                }
            }
        }
        
        with patch('logging.Logger.error') as mock_logger:
            manager = ThreadPoolManager(config)
            
            # Should fall back to default size
            assert manager._pools['io']._max_workers == manager._default_pool_size
            
            # Should log error
            mock_logger.assert_called()
    
    @pytest.mark.asyncio
    async def test_run_in_pool_with_kwargs(self, thread_pool_manager):
        """Test running a function with keyword arguments."""
        def task_with_kwargs(x, multiplier=2):
            return x * multiplier
        
        # Test with default kwargs
        result = await thread_pool_manager.run_in_pool('cpu', task_with_kwargs, 5)
        assert result == 10
        
        # Test with custom kwargs
        result = await thread_pool_manager.run_in_pool('cpu', task_with_kwargs, 5, multiplier=3)
        assert result == 15
    
    @pytest.mark.asyncio
    async def test_high_concurrency(self, thread_pool_manager):
        """Test handling many concurrent tasks."""
        def quick_task(x):
            return x * 2
        
        # Submit 100 tasks
        tasks = [
            thread_pool_manager.run_in_pool('io', quick_task, i)
            for i in range(100)
        ]
        
        start_time = time.time()
        results = await asyncio.gather(*tasks)
        elapsed_time = time.time() - start_time
        
        # Verify results
        assert len(results) == 100
        assert results[0] == 0
        assert results[50] == 100
        assert results[99] == 198
        
        # Should handle high concurrency efficiently
        print(f"Processed 100 tasks in {elapsed_time:.3f}s")
        assert elapsed_time < 2.0  # Should be fast even with many tasks
    
    @pytest.mark.asyncio
    async def test_mixed_pool_high_concurrency(self, thread_pool_manager):
        """Test high concurrency across multiple pools."""
        def io_task(x):
            # Simulate quick I/O
            time.sleep(0.001)
            return f"io_{x}"
        
        def cpu_task(x):
            # Simulate CPU work
            sum([i**2 for i in range(100)])
            return f"cpu_{x}"
        
        def db_task(x):
            # Simulate DB query
            time.sleep(0.001)
            return f"db_{x}"
        
        # Create mixed workload
        tasks = []
        for i in range(30):
            tasks.append(thread_pool_manager.run_in_pool('io', io_task, i))
            tasks.append(thread_pool_manager.run_in_pool('cpu', cpu_task, i))
            tasks.append(thread_pool_manager.run_in_pool('db', db_task, i))
        
        start_time = time.time()
        results = await asyncio.gather(*tasks)
        elapsed_time = time.time() - start_time
        
        # Verify results
        assert len(results) == 90  # 30 * 3 pools
        
        # Count results by type
        io_count = sum(1 for r in results if r.startswith('io_'))
        cpu_count = sum(1 for r in results if r.startswith('cpu_'))
        db_count = sum(1 for r in results if r.startswith('db_'))
        
        assert io_count == 30
        assert cpu_count == 30
        assert db_count == 30
        
        print(f"Processed 90 mixed tasks in {elapsed_time:.3f}s")
    
    def test_submit_to_pool_with_kwargs(self, thread_pool_manager):
        """Test submitting a task with keyword arguments."""
        def task_with_kwargs(x, prefix="result"):
            return f"{prefix}_{x}"
        
        # Test with positional args only
        future1 = thread_pool_manager.submit_to_pool('io', task_with_kwargs, 42)
        assert future1.result(timeout=1) == "result_42"
        
        # Test with kwargs
        future2 = thread_pool_manager.submit_to_pool('io', task_with_kwargs, 42, prefix="test")
        assert future2.result(timeout=1) == "test_42"
    
    @pytest.mark.asyncio
    async def test_pool_saturation_handling(self, thread_pool_manager):
        """Test behavior when pools are saturated."""
        def slow_task(x):
            time.sleep(0.1)  # Block thread for 100ms
            return x
        
        # Submit more tasks than workers (io pool has 5 workers)
        tasks = []
        for i in range(10):
            tasks.append(thread_pool_manager.run_in_pool('io', slow_task, i))
        
        start_time = time.time()
        results = await asyncio.gather(*tasks)
        elapsed_time = time.time() - start_time
        
        # With 5 workers and 10 tasks of 0.1s each, should take ~0.2s
        assert 0.15 < elapsed_time < 0.3  # Allow some overhead
        assert len(results) == 10
        assert results == list(range(10))
    
    @pytest.mark.asyncio
    async def test_batch_executor_with_errors(self, thread_pool_manager):
        """Test batch executor handling errors in some tasks."""
        def task_that_may_fail(x):
            if x == 2:
                raise ValueError(f"Task {x} failed")
            return x * 2
        
        with thread_pool_manager.batch_executor('cpu', max_concurrent=3) as submit:
            tasks = [submit(task_that_may_fail, i) for i in range(5)]
            
            # Use return_exceptions=True to handle partial failures
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check results
        assert results[0] == 0
        assert results[1] == 2
        assert isinstance(results[2], ValueError)
        assert "Task 2 failed" in str(results[2])
        assert results[3] == 6
        assert results[4] == 8


if __name__ == '__main__':
    pytest.main([__file__, '-v'])