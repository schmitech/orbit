#!/usr/bin/env python3
"""
Test suite for aiohttp session tracking functionality
"""

import os
import sys
import pytest
import pytest_asyncio

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.http_utils import setup_aiohttp_session_tracking, _aiohttp_sessions, close_all_aiohttp_sessions
import aiohttp


@pytest_asyncio.fixture
async def session_tracking_setup():
    """Fixture to set up and clean up aiohttp session tracking for tests."""
    # Clear any existing sessions from the tracking registry
    _aiohttp_sessions.clear()
    
    # Set up session tracking
    setup_aiohttp_session_tracking()
    
    yield
    
    # Clean up after tests
    await close_all_aiohttp_sessions()


@pytest.mark.asyncio
async def test_session_tracking_enabled(session_tracking_setup):
    """Test that aiohttp sessions are automatically tracked when created."""
    # Verify no sessions are tracked initially
    assert len(_aiohttp_sessions) == 0, "No sessions should be tracked initially"
    
    # Create a new aiohttp session
    session = aiohttp.ClientSession()
    
    # Verify the session was automatically tracked
    assert len(_aiohttp_sessions) == 1, "Session should be automatically tracked"
    assert session in _aiohttp_sessions, "Created session should be in tracking registry"
    
    # Clean up the session
    await session.close()


@pytest.mark.asyncio
async def test_multiple_sessions_tracked(session_tracking_setup):
    """Test that multiple aiohttp sessions are all tracked."""
    # Verify no sessions are tracked initially
    assert len(_aiohttp_sessions) == 0
    
    # Create multiple sessions
    session1 = aiohttp.ClientSession()
    session2 = aiohttp.ClientSession()
    session3 = aiohttp.ClientSession()
    
    # Verify all sessions are tracked
    assert len(_aiohttp_sessions) == 3, "All three sessions should be tracked"
    assert session1 in _aiohttp_sessions
    assert session2 in _aiohttp_sessions
    assert session3 in _aiohttp_sessions
    
    # Clean up sessions individually
    await session1.close()
    await session2.close()
    await session3.close()


@pytest.mark.asyncio
async def test_session_cleanup(session_tracking_setup):
    """Test that tracked sessions are properly cleaned up."""
    # Create some test sessions
    aiohttp.ClientSession()
    aiohttp.ClientSession()
    
    # Verify sessions are tracked
    assert len(_aiohttp_sessions) == 2, "Both sessions should be tracked"
    
    # Call the cleanup function
    await close_all_aiohttp_sessions()
    
    # Verify all sessions are cleaned up
    assert len(_aiohttp_sessions) == 0, "All sessions should be cleaned up"


@pytest.mark.asyncio
async def test_cleanup_with_already_closed_session(session_tracking_setup):
    """Test cleanup handles already closed sessions gracefully."""
    # Create a session and close it manually
    session = aiohttp.ClientSession()
    await session.close()
    
    # Verify it's still in the tracking registry
    assert len(_aiohttp_sessions) == 1, "Closed session should still be in registry"
    
    # Call cleanup - should handle the already closed session gracefully
    await close_all_aiohttp_sessions()
    
    # Verify cleanup completed successfully
    assert len(_aiohttp_sessions) == 0, "Registry should be cleared after cleanup"


@pytest.mark.asyncio
async def test_session_tracking_idempotent(session_tracking_setup):
    """Test that calling setup_aiohttp_session_tracking multiple times is safe."""
    # Call setup multiple times
    setup_aiohttp_session_tracking()
    setup_aiohttp_session_tracking()
    setup_aiohttp_session_tracking()
    
    # Create a session - it should only be tracked once
    session = aiohttp.ClientSession()
    
    # Should still work correctly
    assert len(_aiohttp_sessions) == 1, "Session should be tracked exactly once despite multiple setups"
    
    # Clean up
    await session.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 