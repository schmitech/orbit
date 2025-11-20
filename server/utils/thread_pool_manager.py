import asyncio
import logging
import time
from functools import partial
from typing import Dict, Optional, Any, Callable
from concurrent.futures import ThreadPoolExecutor, Future
from contextlib import contextmanager


class ThreadPoolManager:
    """
    Manages specialized thread pools for different types of operations.
    
    This class provides centralized management of multiple thread pools,
    each optimized for specific workload types (I/O, CPU, inference, etc.).
    """
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialize the ThreadPoolManager with configuration.
        
        Args:
            config: Configuration dictionary containing thread pool settings
            logger: Optional logger instance
        """
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self._pools: Dict[str, ThreadPoolExecutor] = {}
        self._default_pool_size = 10

        # Task tracking for debugging
        self._task_counter = 0
        self._active_tasks: Dict[int, Dict[str, Any]] = {}
        
        # Initialize all thread pools
        self._initialize_pools()
        
    def _initialize_pools(self) -> None:
        """Initialize all configured thread pools."""
        perf_config = self.config.get('performance', {})
        thread_pool_config = perf_config.get('thread_pools', {})
        
        # Create specialized thread pools based on configuration
        pool_configs = {
            'io': thread_pool_config.get('io_workers', 50),
            'cpu': thread_pool_config.get('cpu_workers', 30),
            'inference': thread_pool_config.get('inference_workers', 20),
            'embedding': thread_pool_config.get('embedding_workers', 15),
            'db': thread_pool_config.get('db_workers', 25)
        }
        
        for pool_name, worker_count in pool_configs.items():
            try:
                self._pools[pool_name] = ThreadPoolExecutor(
                    max_workers=worker_count,
                    thread_name_prefix=f"orbit-{pool_name}-"
                )
                self.logger.debug(f"ThreadPoolManager: Initialized {pool_name} pool with {worker_count} workers")
            except Exception as e:
                self.logger.error(f"Failed to initialize {pool_name} thread pool: {str(e)}")
                # Fallback to default pool size
                self._pools[pool_name] = ThreadPoolExecutor(
                    max_workers=self._default_pool_size,
                    thread_name_prefix=f"orbit-{pool_name}-"
                )
                
    def get_pool(self, pool_type: str) -> ThreadPoolExecutor:
        """
        Get a specific thread pool by type.
        
        Args:
            pool_type: Type of thread pool ('io', 'cpu', 'inference', 'embedding', 'db')
            
        Returns:
            ThreadPoolExecutor for the specified type
            
        Raises:
            ValueError: If pool_type is not recognized
        """
        if pool_type not in self._pools:
            raise ValueError(f"Unknown pool type: {pool_type}. Available types: {list(self._pools.keys())}")
        return self._pools[pool_type]
    
    async def run_in_pool(self, pool_type: str, func: Callable, *args, **kwargs) -> Any:
        """
        Run a function in a specific thread pool.

        Args:
            pool_type: Type of thread pool to use
            func: Function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            Result of the function execution
        """
        pool = self.get_pool(pool_type)
        loop = asyncio.get_event_loop()

        # Track task for debugging
        self._task_counter += 1
        task_id = self._task_counter
        start_time = time.time()
        func_name = getattr(func, '__name__', str(func))
        self._active_tasks[task_id] = {
            'pool': pool_type,
            'func': func_name,
            'start_time': start_time,
            'args': str(args)[:100],  # Truncate for logging
            'kwargs': str(kwargs)[:100] if kwargs else '{}'
        }

        pool_stats = self._get_pool_info(pool)
        self.logger.debug(
            f"ThreadPool[{pool_type}] Task #{task_id}: Submitting '{func_name}' "
            f"(active_threads={pool_stats['active']}, queued={pool_stats['queued']})"
        )

        try:
            # If there are kwargs, use functools.partial to bind them
            if kwargs:
                func_with_kwargs = partial(func, *args, **kwargs)
                result = await loop.run_in_executor(pool, func_with_kwargs)
            else:
                result = await loop.run_in_executor(pool, func, *args)

            # Log completion
            elapsed = time.time() - start_time
            del self._active_tasks[task_id]
            self.logger.debug(
                f"ThreadPool[{pool_type}] Task #{task_id}: Completed in {elapsed:.3f}s"
            )

            return result

        except Exception as e:
            # Log error
            elapsed = time.time() - start_time
            del self._active_tasks[task_id]
            self.logger.error(
                f"ThreadPool[{pool_type}] Task #{task_id}: Failed after {elapsed:.3f}s - {str(e)}"
            )
            raise
    
    def submit_to_pool(self, pool_type: str, func: Callable, *args, **kwargs) -> Future:
        """
        Submit a function to a specific thread pool without waiting.
        
        Args:
            pool_type: Type of thread pool to use
            func: Function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            Future representing the pending result
        """
        pool = self.get_pool(pool_type)
        
        # If there are kwargs, use functools.partial to bind them
        if kwargs:
            func_with_kwargs = partial(func, *args, **kwargs)
            return pool.submit(func_with_kwargs)
        else:
            return pool.submit(func, *args)
    
    @contextmanager
    def batch_executor(self, pool_type: str, max_concurrent: Optional[int] = None):
        """
        Context manager for batch execution with concurrency control.
        
        Args:
            pool_type: Type of thread pool to use
            max_concurrent: Maximum concurrent executions (defaults to pool size)
            
        Yields:
            A function to submit tasks to the batch executor
        """
        pool = self.get_pool(pool_type)
        semaphore = asyncio.Semaphore(max_concurrent or pool._max_workers)
        
        async def submit_task(func: Callable, *args, **kwargs):
            async with semaphore:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(pool, func, *args, **kwargs)
        
        yield submit_task
    
    def _get_pool_info(self, pool: ThreadPoolExecutor) -> Dict[str, Any]:
        """Get information about a specific pool."""
        return {
            'max_workers': pool._max_workers,
            'active': len(pool._threads),
            'queued': pool._work_queue.qsize() if hasattr(pool._work_queue, 'qsize') else 0
        }
    
    def get_pool_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Get statistics for all thread pools.
        
        Returns:
            Dictionary containing stats for each pool
        """
        stats = {}
        for pool_name, pool in self._pools.items():
            stats[pool_name] = {
                'max_workers': pool._max_workers,
                'active_threads': len(pool._threads),
                'queued_tasks': pool._work_queue.qsize() if hasattr(pool._work_queue, 'qsize') else 'N/A'
            }
        
        return stats
    
    def shutdown(self, wait: bool = True) -> None:
        """
        Shutdown all thread pools.
        
        Args:
            wait: Whether to wait for pending tasks to complete
        """
        self.logger.info("Shutting down thread pools...")
        final_stats = self.get_pool_stats()
        self.logger.debug("ThreadPoolManager final statistics:")
        for pool_name, stats in final_stats.items():
            self.logger.debug(
                f"  {pool_name}: max_workers={stats['max_workers']}, "
                f"active_threads={stats['active_threads']}, "
                f"queued_tasks={stats['queued_tasks']}"
            )
            
            if self._active_tasks:
                self.logger.warning(
                    f"ThreadPoolManager: {len(self._active_tasks)} tasks still active at shutdown"
                )
        
        for pool_name, pool in self._pools.items():
            try:
                pool.shutdown(wait=wait)
                self.logger.info(f"Shut down {pool_name} thread pool")
            except Exception as e:
                self.logger.error(f"Error shutting down {pool_name} thread pool: {str(e)}")
        self._pools.clear()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures pools are shut down."""
        self.shutdown()
    
    def log_current_status(self):
        """Log current thread pool status - useful for monitoring."""
        stats = self.get_pool_stats()
        self.logger.debug("ThreadPoolManager Current Status:")
        self.logger.debug("=" * 60)
        
        total_active = 0
        total_queued = 0
        
        for pool_name, pool_stats in stats.items():
            active = pool_stats['active_threads']
            queued = pool_stats['queued_tasks']
            max_workers = pool_stats['max_workers']
            
            # Calculate utilization
            utilization = (active / max_workers * 100) if max_workers > 0 else 0
            
            self.logger.info(
                f"  {pool_name:12} | Workers: {active:3}/{max_workers:3} ({utilization:5.1f}%) | "
                f"Queued: {queued if queued != 'N/A' else 0:3}"
            )
            
            # Track totals
            if isinstance(active, int):
                total_active += active
            if queued != 'N/A' and isinstance(queued, int):
                total_queued += queued
            
            # Show active tasks if any
            if 'active_tasks' in pool_stats:
                for task in pool_stats['active_tasks']:
                    self.logger.info(
                        f"    └─ Task #{task['task_id']}: {task['function']} "
                        f"(running for {task['duration']:.1f}s)"
                    )
        
        self.logger.info("-" * 60)
        self.logger.info(
            f"  Total: {total_active} active threads, {total_queued} queued tasks"
        )
        self.logger.info("=" * 60)