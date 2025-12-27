"""
Quota Background Tasks
======================

Background tasks for quota management including periodic sync to database
and handling graceful shutdown.
"""

import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)


class QuotaBackgroundTasks:
    """
    Background tasks for quota management.

    Handles:
    - Periodic sync of Redis usage counters to database
    - Graceful shutdown with final sync
    """

    def __init__(self, quota_service, sync_interval: int = 60):
        """
        Initialize background tasks.

        Args:
            quota_service: The QuotaService instance
            sync_interval: Seconds between sync operations (default: 60)
        """
        self.quota_service = quota_service
        self.sync_interval = sync_interval
        self._running = False
        self._sync_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start background task loops."""
        if self._running:
            logger.warning("QuotaBackgroundTasks already running")
            return

        self._running = True
        self._sync_task = asyncio.create_task(self._sync_loop())
        logger.info(f"QuotaBackgroundTasks started with sync interval: {self.sync_interval}s")

    async def stop(self) -> None:
        """Stop background tasks gracefully."""
        if not self._running:
            return

        self._running = False

        # Cancel the sync task
        if self._sync_task and not self._sync_task.done():
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass

        # Perform final sync
        try:
            await self.quota_service.sync_usage_to_database()
            logger.info("Final quota sync completed on shutdown")
        except Exception as e:
            logger.error(f"Failed to perform final quota sync: {e}")

        logger.info("QuotaBackgroundTasks stopped")

    async def _sync_loop(self) -> None:
        """Periodically sync Redis usage to database."""
        logger.info("Starting quota sync loop")

        while self._running:
            try:
                await asyncio.sleep(self.sync_interval)

                if not self._running:
                    break

                synced = await self.quota_service.sync_usage_to_database()
                if synced > 0:
                    logger.debug(f"Synced {synced} quota entries to database")

            except asyncio.CancelledError:
                logger.debug("Quota sync loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in quota sync loop: {e}")
                # Continue running despite errors
                await asyncio.sleep(5)  # Brief pause before retry

    @property
    def is_running(self) -> bool:
        """Check if background tasks are running."""
        return self._running
