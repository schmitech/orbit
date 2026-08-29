"""
Tool Skill (SKILL.md) admin CRUD — docs/roadmap/mcp-tool-skills.md Phase 3.

Modeled on routes/admin/prompts.py. Distinct from ORBIT-skill routing
(``capabilities.expose_as_skill``) — see docs/roadmap/mcp-tool-skills.md §1
for the terminology split; these are the procedural SKILL.md playbooks bound
to MCP tools via ``mcp_tools`` globs.

Auditing is handled generically by middleware/admin_audit_middleware.py for
every admin-route mutation, same as prompts/mcp — no explicit audit calls
are made here.
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException, Body

from models.schema import ToolSkillCreate, ToolSkillUpdate, ToolSkillResponse
from routes.auth_helpers import check_service_availability
from routes.admin._shared import (
    _serialize_created_at, get_tool_skill_service, config_auth,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _to_response(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "name": doc.get("name"),
        "description": doc.get("description"),
        "mcp_tools": doc.get("mcp_tools", []),
        "body": doc.get("body"),
        "enabled": doc.get("enabled", True),
        "version": doc.get("version"),
        "priority": doc.get("priority", 0),
        "created_at": _serialize_created_at(doc.get("created_at")) or 0,
        "updated_at": _serialize_created_at(doc.get("updated_at")) or 0,
    }


async def _refresh_registry(request: Request) -> None:
    """Re-merge the DB skill set into the live ToolSkillRegistry, and — under
    multi-worker mode — signal sibling workers to do the same (mirrors
    routes/admin/mcp.py's ``_reload_mcp_clients`` propagation)."""
    tool_skill_service = getattr(request.app.state, 'tool_skill_service', None)
    if tool_skill_service is None:
        return

    from services.tool_skill_service import refresh_tool_skill_registry_db
    app_config = getattr(request.app.state, "config", None) or {}
    await refresh_tool_skill_registry_db(app_config, tool_skill_service)

    if os.environ.get("ORBIT_SUPERVISOR_PID"):
        from services import adapter_reload_state

        new_generation = await adapter_reload_state.bump_generation(request.app.state, "tool_skills")
        if new_generation is not None:
            last_seen = getattr(request.app.state, "_adapter_reload_last_seen", None)
            if last_seen is not None:
                last_seen["tool_skills"] = new_generation
        else:
            logger.warning("Failed to propagate tool skill reload to other workers")


@router.post("/skills", response_model=ToolSkillResponse, dependencies=[config_auth])
async def create_skill(
    skill_data: ToolSkillCreate,
    request: Request,
):
    """Create a new tool skill."""
    tool_skill_service = getattr(request.app.state, 'tool_skill_service', None)
    check_service_availability(tool_skill_service, "Tool skill service")

    skill_id = await tool_skill_service.create_skill(
        name=skill_data.name,
        description=skill_data.description,
        mcp_tools=skill_data.mcp_tools,
        body=skill_data.body,
        enabled=skill_data.enabled,
        version=skill_data.version,
        priority=skill_data.priority,
    )

    await _refresh_registry(request)

    doc = await tool_skill_service.get_skill_by_id(skill_id)
    if not doc:
        raise HTTPException(status_code=500, detail="Failed to retrieve created tool skill")
    return _to_response(doc)


@router.get("/skills", dependencies=[config_auth])
async def list_skills(
    name_filter: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    tool_skill_service = Depends(get_tool_skill_service),
):
    """List all tool skills with optional filtering and pagination."""
    check_service_availability(tool_skill_service, "Tool skill service")

    if limit > 1000:
        limit = 1000
    if limit < 1:
        limit = 100
    if offset < 0:
        offset = 0

    docs = await tool_skill_service.list_skills(name_filter=name_filter, limit=limit, offset=offset)
    return [_to_response(doc) for doc in docs]


@router.get("/skills/{skill_id}", dependencies=[config_auth])
async def get_skill(
    skill_id: str,
    tool_skill_service = Depends(get_tool_skill_service),
):
    """Get a tool skill by ID."""
    check_service_availability(tool_skill_service, "Tool skill service")

    doc = await tool_skill_service.get_skill_by_id(skill_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Tool skill not found")
    return _to_response(doc)


@router.post("/skills/validate", dependencies=[config_auth])
def validate_skill(
    payload: dict = Body(...),
):
    """Validate a skill's fields without persisting it — lets the panel show
    inline errors (bad name slug, empty mcp_tools, oversize body, ...)
    before a create/update request is sent."""
    from services.tool_skill_service import _validate_skill_fields, SkillValidationError

    try:
        fields = _validate_skill_fields(
            name=payload.get("name"),
            description=payload.get("description"),
            mcp_tools=payload.get("mcp_tools"),
            body=payload.get("body"),
            enabled=payload.get("enabled", True),
            version=payload.get("version"),
            priority=payload.get("priority", 0),
            label="Tool skill",
        )
    except SkillValidationError as exc:
        return {"valid": False, "error": str(exc)}

    return {"valid": True, "normalized": fields}


@router.put("/skills/{skill_id}", response_model=ToolSkillResponse, dependencies=[config_auth])
async def update_skill(
    skill_id: str,
    skill_data: ToolSkillUpdate,
    request: Request,
    tool_skill_service = Depends(get_tool_skill_service),
):
    """Update a tool skill. Name is immutable."""
    check_service_availability(tool_skill_service, "Tool skill service")

    success = await tool_skill_service.update_skill(
        skill_id,
        description=skill_data.description,
        mcp_tools=skill_data.mcp_tools,
        body=skill_data.body,
        enabled=skill_data.enabled,
        version=skill_data.version,
        priority=skill_data.priority,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Tool skill not found or not updated")

    await _refresh_registry(request)

    doc = await tool_skill_service.get_skill_by_id(skill_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Failed to retrieve updated tool skill")
    return _to_response(doc)


@router.delete("/skills/{skill_id}", dependencies=[config_auth])
async def delete_skill(
    skill_id: str,
    request: Request,
    tool_skill_service = Depends(get_tool_skill_service),
):
    """Delete a tool skill."""
    check_service_availability(tool_skill_service, "Tool skill service")

    success = await tool_skill_service.delete_skill(skill_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tool skill not found")

    await _refresh_registry(request)

    return {"status": "success", "message": "Tool skill deleted"}
