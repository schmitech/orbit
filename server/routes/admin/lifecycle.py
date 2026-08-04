"""
Server lifecycle endpoints: shutdown, pause, resume, restart.
"""

import logging
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException

from routes.admin._shared import (
    system_auth,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/shutdown", dependencies=[system_auth])
async def shutdown_server(
    request: Request,
):
    """
    Gracefully shutdown the server.
    
    This endpoint initiates a graceful shutdown of the server. The shutdown
    is performed asynchronously to allow the response to be sent before
    the server stops accepting new requests.
    
    Security considerations:
    - This is an admin-only endpoint
    - Should be protected by additional authentication
    - Only accessible to authenticated admin users
    
    Returns:
        Dictionary confirming shutdown initiation
    """
    import asyncio
    import signal
    
    logger.info("Graceful shutdown initiated via /admin/shutdown endpoint")
    
    # Schedule shutdown in background to allow response to be sent
    async def shutdown_background():
        await asyncio.sleep(0.5)  # Small delay to ensure response is sent
        import os
        # Under multi-worker mode, this request was handled by one of several
        # worker processes — sending SIGTERM to ourselves only kills that one
        # worker, which the supervisor treats as an unhealthy child and
        # immediately replaces, leaving the server running. Target the
        # supervisor (all workers descend from it) so the whole pool shuts
        # down, matching single-process behavior where we ARE the supervisor.
        pid = int(os.environ.get('ORBIT_SUPERVISOR_PID', os.getpid()))
        os.kill(pid, signal.SIGTERM)
    
    # Schedule the shutdown
    asyncio.create_task(shutdown_background())
    
    return {
        "status": "success",
        "message": "Server shutdown initiated",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


@router.post("/pause", dependencies=[system_auth])
async def pause_server(
    request: Request,
):
    """
    Pause the server: reject new chat requests without stopping the process.

    Existing in-flight requests are unaffected. Health checks continue to
    report the process as alive so monitoring/load-balancer probes are not
    disrupted while paused. The flag is broadcast through the shared cache
    service (when configured) so it takes effect across all worker processes,
    not just the one that handled this request.
    """
    from services.pause_state import set_paused

    if not await set_paused(request.app.state, True):
        logger.error("Failed to pause server: shared cache write failed")
        raise HTTPException(
            status_code=503,
            detail="Failed to pause server: could not write pause state to the shared cache backend"
        )
    logger.info("Server paused via /admin/pause endpoint")

    return {
        "status": "success",
        "message": "Server paused",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


@router.post("/resume", dependencies=[system_auth])
async def resume_server(
    request: Request,
):
    """Resume normal request processing after a pause."""
    from services.pause_state import set_paused

    if not await set_paused(request.app.state, False):
        logger.error("Failed to resume server: shared cache write failed")
        raise HTTPException(
            status_code=503,
            detail="Failed to resume server: could not write pause state to the shared cache backend"
        )
    logger.info("Server resumed via /admin/resume endpoint")

    return {
        "status": "success",
        "message": "Server resumed",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


@router.post("/restart", dependencies=[system_auth])
async def restart_server(
    request: Request,
):
    """
    Restart the server process in place.

    This endpoint re-execs the current Python process after a short delay so
    the HTTP response can be sent back to the admin UI first.
    """
    import asyncio
    import os
    import sys

    supervisor_pid = os.environ.get('ORBIT_SUPERVISOR_PID')
    if supervisor_pid is not None and int(supervisor_pid) != os.getpid():
        # We're one of several worker processes under a multi-process
        # supervisor — re-exec'ing this worker alone would leave the
        # supervisor and sibling workers in an inconsistent state. Restarting
        # the whole server in multi-worker mode requires stopping and
        # relaunching the supervisor itself, which `orbit restart` already
        # does correctly from outside the process (see bin/orbit/services/
        # server_service.py).
        raise HTTPException(
            status_code=501,
            detail="/admin/restart is not supported when performance.workers > 1; use 'orbit restart' instead"
        )

    logger.info("Server restart initiated via /admin/restart endpoint")

    async def restart_background():
        await asyncio.sleep(0.5)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    asyncio.create_task(restart_background())

    return {
        "status": "success",
        "message": "Server restart initiated",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
