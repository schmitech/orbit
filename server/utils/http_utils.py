"""
HTTP Utilities
==============

This module provides utility functions for HTTP-related operations,
including session management and cleanup.
"""

import asyncio
import logging
from typing import Set
import aiohttp

logger = logging.getLogger(__name__)

# Global set to track all aiohttp sessions
_aiohttp_sessions: Set[aiohttp.ClientSession] = set()

def track_aiohttp_session(session: aiohttp.ClientSession) -> None:
    """
    Track an aiohttp session for later cleanup.
    
    Args:
        session: The aiohttp ClientSession to track
    """
    _aiohttp_sessions.add(session)

async def close_all_aiohttp_sessions() -> None:
    """
    Close all tracked aiohttp sessions.
    This function should be called during application shutdown.
    """
    if not _aiohttp_sessions:
        return
        
    logger.info(f"Closing {len(_aiohttp_sessions)} aiohttp sessions...")
    
    # Create tasks for closing all sessions
    close_tasks = []
    for session in _aiohttp_sessions:
        if not session.closed:
            close_tasks.append(session.close())
    
    # Wait for all sessions to close
    if close_tasks:
        await asyncio.gather(*close_tasks, return_exceptions=True)
    
    # Clear the set
    _aiohttp_sessions.clear()
    logger.info("All aiohttp sessions closed") 