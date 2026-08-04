"""
System prompt CRUD and markdown preview endpoints.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Request, Depends, HTTPException, Body
import markdown
import nh3

from models.schema import (
    SystemPromptCreate, SystemPromptUpdate, SystemPromptResponse,
)

from routes.auth_helpers import check_service_availability
from routes.admin._shared import (
    _serialize_created_at, get_prompt_service,
    prompts_auth,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def _clear_runtime_prompt_caches(request: Request, prompt_id: Optional[str] = None) -> None:
    """Clear in-process prompt/query caches that are outside PromptService Redis."""
    chat_service = getattr(request.app.state, 'chat_service', None)
    if not chat_service or not hasattr(chat_service, 'clear_prompt_cache'):
        return

    try:
        stats = await chat_service.clear_prompt_cache(prompt_id)
        logger.debug("Cleared runtime prompt caches for %s: %s", prompt_id or "all prompts", stats)
    except Exception:
        logger.warning("Failed to clear runtime prompt caches for %s", prompt_id, exc_info=True)


async def _clear_deleted_prompt_associations(request: Request, prompt_id: str) -> None:
    """Detach deleted personas from API keys so admin state has no dangling links."""
    api_key_service = getattr(request.app.state, 'api_key_service', None)
    if not api_key_service or not hasattr(api_key_service, 'clear_system_prompt_associations'):
        return

    cleared = await api_key_service.clear_system_prompt_associations(prompt_id)
    if cleared:
        logger.debug("Detached deleted prompt %s from %s API key(s)", prompt_id, cleared)


# System Prompts Management Routes
@router.post("/prompts", response_model=SystemPromptResponse, dependencies=[prompts_auth])
async def create_prompt(
    prompt_data: SystemPromptCreate,
    request: Request,
):
    """Create a new system prompt"""
    # Check if prompt service is available
    prompt_service = getattr(request.app.state, 'prompt_service', None)
    check_service_availability(prompt_service, "Prompt service")
    
    prompt_id = await prompt_service.create_prompt(
        prompt_data.name,
        prompt_data.prompt,
        prompt_data.version
    )

    await _clear_runtime_prompt_caches(request, str(prompt_id))
    
    prompt = await prompt_service.get_prompt_by_id(prompt_id)
    
    if not prompt:
        raise HTTPException(status_code=500, detail="Failed to retrieve created prompt")
        
    # Format the response according to the model
    return {
        "id": str(prompt_id),
        "name": prompt.get("name"),
        "prompt": prompt.get("prompt"),
        "version": prompt.get("version"),
        "created_at": _serialize_created_at(prompt.get("created_at")) or 0,
        "updated_at": _serialize_created_at(prompt.get("updated_at")) or 0
    }


@router.get("/prompts", dependencies=[prompts_auth])
async def list_prompts(
    name_filter: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    prompt_service = Depends(get_prompt_service),
):
    """
    List all system prompts with optional filtering and pagination.
    
    Args:
        name_filter: Optional name filter (case-insensitive partial match)
        limit: Maximum number of prompts to return (default: 100, max: 1000)
        offset: Number of prompts to skip for pagination (default: 0)
    """
    # Validate parameters
    if limit > 1000:
        limit = 1000
    if limit < 1:
        limit = 100
    if offset < 0:
        offset = 0
    
    return await prompt_service.list_prompts(name_filter=name_filter, limit=limit, offset=offset)


@router.get("/prompts/{prompt_id}", dependencies=[prompts_auth])
async def get_prompt(
    prompt_id: str,
    prompt_service = Depends(get_prompt_service),
):
    """Get a system prompt by ID"""
    prompt = await prompt_service.get_prompt_by_id(prompt_id)
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
        
    # Convert ObjectId to string and datetime to timestamp
    prompt["_id"] = str(prompt["_id"])
    if "created_at" in prompt:
        prompt["created_at"] = _serialize_created_at(prompt["created_at"]) or 0
    if "updated_at" in prompt:
        prompt["updated_at"] = _serialize_created_at(prompt["updated_at"]) or 0
        
    return prompt


@router.post("/render-markdown", dependencies=[prompts_auth])
def render_markdown_preview(
    payload: dict = Body(...),
):
    """Render markdown to sanitized HTML for admin preview panels."""
    text = (payload or {}).get("markdown", "")
    if not isinstance(text, str):
        raise HTTPException(status_code=422, detail="markdown must be a string")
    if len(text) > 50_000:
        raise HTTPException(status_code=422, detail="markdown too large")

    try:
        html = markdown.markdown(
            text,
            extensions=["extra", "tables", "fenced_code", "sane_lists", "nl2br"],
        )
        clean_html = nh3.clean(
            html,
            tags={
                "p", "br", "strong", "em", "code", "pre", "h1", "h2", "h3", "h4", "h5", "h6",
                "ul", "ol", "li", "blockquote", "a", "table", "thead", "tbody", "tr", "th", "td",
                "hr"
            },
            attributes={
                "a": {"href", "title", "target"},
            },
            url_schemes={"http", "https", "mailto"},
        )
        return {"html": clean_html}
    except Exception as e:
        logger.error(f"Error rendering markdown preview: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to render markdown preview")


@router.put("/prompts/{prompt_id}", response_model=SystemPromptResponse, dependencies=[prompts_auth])
async def update_prompt(
    prompt_id: str,
    prompt_data: SystemPromptUpdate,
    request: Request,
    prompt_service = Depends(get_prompt_service),
):
    """Update a system prompt"""
    success = await prompt_service.update_prompt(
        prompt_id,
        prompt_data.prompt,
        prompt_data.version
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Prompt not found or not updated")

    await _clear_runtime_prompt_caches(request, prompt_id)
        
    prompt = await prompt_service.get_prompt_by_id(prompt_id)
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Failed to retrieve updated prompt")
        
    # Format the response according to the model
    return {
        "id": str(prompt_id),
        "name": prompt.get("name"),
        "prompt": prompt.get("prompt"),
        "version": prompt.get("version"),
        "created_at": _serialize_created_at(prompt.get("created_at")) or 0,
        "updated_at": _serialize_created_at(prompt.get("updated_at")) or 0
    }


@router.delete("/prompts/{prompt_id}", dependencies=[prompts_auth])
async def delete_prompt(
    prompt_id: str,
    request: Request,
    prompt_service = Depends(get_prompt_service),
):
    """Delete a system prompt"""
    success = await prompt_service.delete_prompt(prompt_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Prompt not found")

    await _clear_runtime_prompt_caches(request, prompt_id)
    await _clear_deleted_prompt_associations(request, prompt_id)
        
    return {"status": "success", "message": "Prompt deleted"}
