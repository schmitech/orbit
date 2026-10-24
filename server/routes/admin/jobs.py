"""
In-memory admin job store and job status endpoint.
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Awaitable, Callable, Optional
from fastapi import APIRouter, Request, HTTPException

from routes.admin._shared import (
    system_auth,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_admin_jobs(request: Request) -> dict:
    """Get or initialize the in-memory admin job store."""
    jobs = getattr(request.app.state, 'admin_jobs', None)
    if jobs is None:
        jobs = {}
        request.app.state.admin_jobs = jobs
    return jobs


def _create_admin_job(request: Request, job_type: str, target: Optional[str] = None) -> dict:
    """Create an in-memory admin job record."""
    jobs = _get_admin_jobs(request)
    job_id = str(uuid.uuid4())
    record = {
        "job_id": job_id,
        "type": job_type,
        "target": target,
        "status": "queued",
        "message": "Queued",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "result": None,
        "error": None,
    }
    jobs[job_id] = record

    # Keep the in-memory store bounded.
    if len(jobs) > 100:
        oldest = sorted(jobs.values(), key=lambda item: item.get("created_at", ""))[:-100]
        for item in oldest:
            jobs.pop(item["job_id"], None)

    return record


def _update_admin_job(request: Request, job_id: str, **updates) -> None:
    """Update an in-memory admin job record."""
    jobs = _get_admin_jobs(request)
    job = jobs.get(job_id)
    if not job:
        return
    job.update(updates)
    job["updated_at"] = datetime.utcnow().isoformat() + "Z"


def run_admin_job_async(
    request: Request,
    job_type: str,
    target: Optional[str],
    running_message: str,
    handler: Callable[[], Awaitable],
    failure_log_message: str,
) -> dict:
    """Create an admin job and run an async handler for it in the background.

    `handler` is awaited with no arguments (callers close over whatever the
    underlying endpoint needs) and must return an object with a `.message`
    attribute and, optionally, `.model_dump()` — matching the response models
    the admin reload endpoints already return. An `HTTPException` raised by
    `handler` fails the job with its `detail`; any other exception fails the
    job with the exception's message and is logged with `failure_log_message`.

    Returns the created job record (callers return its `job_id` to the client).
    """
    job = _create_admin_job(request, job_type, target)

    async def run_job():
        _update_admin_job(request, job["job_id"], status="running", message=running_message)
        try:
            result = await handler()
            _update_admin_job(
                request,
                job["job_id"],
                status="completed",
                message=result.message,
                result=result.model_dump() if hasattr(result, "model_dump") else result,
            )
        except HTTPException as exc:
            _update_admin_job(request, job["job_id"], status="failed", message=str(exc.detail), error=str(exc.detail))
        except Exception as exc:
            logger.error(f"{failure_log_message}: {exc}", exc_info=True)
            _update_admin_job(request, job["job_id"], status="failed", message=str(exc), error=str(exc))

    asyncio.create_task(run_job())
    return job


@router.get("/jobs/{job_id}", dependencies=[system_auth])
async def get_admin_job_status(
    job_id: str,
    request: Request,
):
    """Get status for an async admin job."""
    jobs = _get_admin_jobs(request)
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Admin job not found")
    return job
