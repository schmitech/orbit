"""
Stream Registry

Manages active streaming requests and provides cancellation capabilities.
Tracks streams by (session_id, request_id) tuple for precise cancellation.
"""

import asyncio
import logging
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import threading

logger = logging.getLogger(__name__)


@dataclass
class StreamInfo:
    """Information about an active stream."""
    session_id: str
    request_id: str
    cancel_event: asyncio.Event
    created_at: datetime
    adapter_name: Optional[str] = None


class StreamRegistry:
    """
    Thread-safe registry for active streaming requests.

    Allows registration and cancellation of streams identified by
    (session_id, request_id) tuple.
    """

    _instance: Optional['StreamRegistry'] = None
    _lock = threading.Lock()

    def __new__(cls) -> 'StreamRegistry':
        """Singleton pattern for global stream registry access."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._streams: Dict[Tuple[str, str], StreamInfo] = {}
                cls._instance._registry_lock = asyncio.Lock()
                cls._instance._initialized = True
        return cls._instance

    async def register(
        self,
        session_id: str,
        request_id: str,
        adapter_name: Optional[str] = None
    ) -> asyncio.Event:
        """
        Register a new stream and return its cancellation event.

        Args:
            session_id: The session identifier
            request_id: Unique request identifier
            adapter_name: Optional adapter name for the request

        Returns:
            asyncio.Event that will be set when cancellation is requested
        """
        async with self._registry_lock:
            key = (session_id, request_id)

            # Clean up any existing stream with same key (shouldn't happen, but be safe)
            if key in self._streams:
                logger.warning(f"Stream {key} already exists, replacing")

            cancel_event = asyncio.Event()
            stream_info = StreamInfo(
                session_id=session_id,
                request_id=request_id,
                cancel_event=cancel_event,
                created_at=datetime.utcnow(),
                adapter_name=adapter_name
            )
            self._streams[key] = stream_info

            logger.debug(f"[STREAM_REGISTRY] Registered stream: session={session_id}, request={request_id}, adapter={adapter_name}, total_active={len(self._streams)}")
            return cancel_event

    async def unregister(self, session_id: str, request_id: str) -> bool:
        """
        Unregister a stream when it completes or is cancelled.

        Args:
            session_id: The session identifier
            request_id: Unique request identifier

        Returns:
            True if stream was found and removed, False otherwise
        """
        async with self._registry_lock:
            key = (session_id, request_id)
            if key in self._streams:
                was_cancelled = self._streams[key].cancel_event.is_set()
                del self._streams[key]
                logger.debug(f"[STREAM_REGISTRY] Unregistered stream: session={session_id}, request={request_id}, was_cancelled={was_cancelled}, remaining_active={len(self._streams)}")
                return True
            logger.debug(f"[STREAM_REGISTRY] Unregister failed - stream not found: session={session_id}, request={request_id}")
            return False

    async def cancel(self, session_id: str, request_id: str) -> bool:
        """
        Request cancellation of a specific stream.

        Args:
            session_id: The session identifier
            request_id: Unique request identifier

        Returns:
            True if stream was found and cancellation requested, False otherwise
        """
        async with self._registry_lock:
            key = (session_id, request_id)
            stream_info = self._streams.get(key)

            if stream_info:
                stream_info.cancel_event.set()
                logger.debug(f"[STREAM_REGISTRY] >>> CANCELLATION SIGNAL SET <<< session={session_id}, request={request_id}, adapter={stream_info.adapter_name}")
                return True

            logger.warning(f"[STREAM_REGISTRY] Cancel failed - stream not found: session={session_id}, request={request_id}, active_streams={list(self._streams.keys())}")
            return False

    async def is_cancelled(self, session_id: str, request_id: str) -> bool:
        """
        Check if a stream has been cancelled.

        Args:
            session_id: The session identifier
            request_id: Unique request identifier

        Returns:
            True if stream exists and cancellation was requested
        """
        async with self._registry_lock:
            key = (session_id, request_id)
            stream_info = self._streams.get(key)
            return stream_info is not None and stream_info.cancel_event.is_set()

    async def get_active_count(self) -> int:
        """Get the count of active streams."""
        async with self._registry_lock:
            return len(self._streams)

    async def cleanup_stale(self, max_age_seconds: int = 3600) -> int:
        """
        Clean up streams older than max_age_seconds.

        Returns:
            Number of stale streams removed
        """
        async with self._registry_lock:
            now = datetime.utcnow()
            stale_keys = [
                key for key, info in self._streams.items()
                if (now - info.created_at).total_seconds() > max_age_seconds
            ]

            for key in stale_keys:
                del self._streams[key]

            if stale_keys:
                logger.info(f"Cleaned up {len(stale_keys)} stale streams")

            return len(stale_keys)


# Global singleton instance
stream_registry = StreamRegistry()
