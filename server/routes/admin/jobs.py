"""
In-memory admin job store and job status endpoint.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional
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
