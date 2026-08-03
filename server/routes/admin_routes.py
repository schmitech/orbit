"""
Admin routes for ORBIT.

This module contains all admin-related endpoints including:
- API key management
- System prompt management
- Chat history management (inference-only mode)
"""

import logging
import asyncio
import importlib
import json
import re
import uuid
import yaml
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit
from fastapi import APIRouter, Request, Depends, HTTPException, Query, Body
import markdown
import nh3

from models.schema import (
    ApiKeyCreate, ApiKeyResponse, ApiKeyUpdate,
    SystemPromptCreate, SystemPromptUpdate, SystemPromptResponse,
    ApiKeyPromptAssociate, AdapterReloadResponse,
    TemplateReloadResponse, TemplateTestRequest, ApiKeyQuota, ApiKeyQuotaUpdate,
    ApiKeyUsage, ApiKeyQuotaResponse,
)
from config.config_manager import reload_adapters_config
from utils.text_utils import mask_api_key

# Adapter SDK — generates new adapter configs from spec + answers
from jinja2 import UndefinedError
from adapter_sdk import writer as adapter_writer
from adapter_sdk.renderer import render_adapter
from adapter_sdk.specs import get_spec, serialize_registry
from adapter_sdk.validator import validate_answers, validate_yaml_text

# Import auth dependencies
from routes.auth_dependencies import permission_or_api_key, require_permission
from routes.auth_helpers import check_service_availability

# Initialize logger
logger = logging.getLogger(__name__)

# Create the admin router
admin_router = APIRouter(prefix="/admin", tags=["admin"])


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


def get_api_key_service(request: Request):
    """Get the API key service from app state"""
    return request.app.state.api_key_service


def get_prompt_service(request: Request):
    """Get the prompt service from app state"""
    return request.app.state.prompt_service


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


def _serialize_created_at(value) -> Optional[float]:
    """Normalize a created_at value (datetime or ISO string) to a Unix timestamp float."""
    if value is None:
        return None
    if hasattr(value, 'timestamp'):
        return value.timestamp()
    if isinstance(value, str):
        try:
            from datetime import datetime as _dt
            return _dt.fromisoformat(value.replace('Z', '+00:00')).timestamp()
        except Exception:
            return None
    return value


def _tail_file(path: Path, n: int) -> list:
    """Read last n lines by seeking from end of file instead of reading everything."""
    with path.open("rb") as f:
        f.seek(0, 2)
        size = f.tell()
        if size == 0:
            return []
        block_size = 8192
        blocks: list = []
        pos = size
        newline_count = 0

        while pos > 0 and newline_count < n + 1:
            read_size = min(block_size, pos)
            pos -= read_size
            f.seek(pos)
            block = f.read(read_size)
            blocks.insert(0, block)
            newline_count += block.count(b"\n")

        text = b"".join(blocks).decode("utf-8", errors="replace")
        return text.splitlines()[-n:]


# Per-resource-group authorization: bearer token holding the permission, or a
# valid X-API-Key for programmatic/automation access. Conversation content is
# bearer-only (require_permission) so a leaked API key cannot read transcripts.
apikeys_auth = Depends(permission_or_api_key("apikeys.manage"))
adapters_auth = Depends(permission_or_api_key("adapters.manage"))
prompts_auth = Depends(permission_or_api_key("prompts.manage"))
config_auth = Depends(permission_or_api_key("config.manage"))
system_auth = Depends(permission_or_api_key("system.manage"))
logs_auth = Depends(permission_or_api_key("logs.read"))
audit_auth = Depends(permission_or_api_key("audit.read"))
conversations_auth = Depends(require_permission("conversations.read"))


# API Key Management Routes
@admin_router.post("/api-keys", response_model=ApiKeyResponse, dependencies=[apikeys_auth])
async def create_api_key(
    api_key_data: ApiKeyCreate,
    request: Request,
):
    """
    Create a new API key for accessing the server.
    
    This endpoint now requires either:
    - Admin authentication (Bearer token)
    - Valid API key with appropriate permissions
    
    This endpoint allows administrators to create API keys with:
    - Collection-based access control
    - Client identification
    - Usage notes
    - Optional system prompt association
    
    Security considerations:
    - This is an admin-only endpoint
    - Should be protected by additional authentication
    - API keys should be stored securely
    - Keys should be rotated periodically
    
    Args:
        api_key_data: The API key creation request data
        request: The incoming request
        authorized: Authentication check result
        
    Returns:
        ApiKeyResponse containing the created API key and metadata
        
    Raises:
        HTTPException: If API key creation fails or service is unavailable
    """
    # Check if API key service is available
    api_key_service = getattr(request.app.state, 'api_key_service', None)
    check_service_availability(api_key_service, "API key service")
    
    api_key_response = await api_key_service.create_api_key(
        client_name=api_key_data.client_name,
        notes=api_key_data.notes,
        system_prompt_id=api_key_data.system_prompt_id,
        adapter_name=api_key_data.adapter_name
    )
    
    # Log with masked API key
    masked_api_key = mask_api_key(api_key_response.get('api_key'), show_last=True, prefix="***")
    
    # Log creation with appropriate identifier
    if api_key_data.adapter_name:
        logger.info(f"Created API key for adapter '{api_key_data.adapter_name}': {masked_api_key}")
    else:
        logger.info(f"Created API key: {masked_api_key}")
    
    return api_key_response


@admin_router.get("/api-keys", dependencies=[apikeys_auth])
async def list_api_keys(
    request: Request,
    adapter: Optional[str] = None,
    active_only: bool = False,
    limit: int = 100,
    offset: int = 0,
):
    """
    List all API keys in the system with optional filtering and pagination.
    """
    # Check if API key service is available
    api_key_service = getattr(request.app.state, 'api_key_service', None)
    check_service_availability(api_key_service, "API key service")
    prompt_service = getattr(request.app.state, 'prompt_service', None)
    
    try:
        # Validate parameters
        if limit > 1000:
            limit = 1000
        if limit < 1:
            limit = 100
        if offset < 0:
            offset = 0
        
        # Ensure service is initialized
        if not api_key_service._initialized:
            await api_key_service.initialize()
        
        # Build filter query
        filter_query = {}
        if adapter:
            filter_query["adapter_name"] = adapter
        if active_only:
            filter_query["active"] = True
        
        # Retrieve API keys with filtering and pagination using database abstraction
        api_keys = await api_key_service.database.find_many(
            api_key_service.collection_name,
            filter_query,
            limit=limit,
            skip=offset
        )

        prompt_names = {}
        if prompt_service:
            prompt_ids = {
                str(key.get("system_prompt_id"))
                for key in api_keys
                if key.get("system_prompt_id")
            }
            for prompt_id in prompt_ids:
                try:
                    prompt = await prompt_service.get_prompt_by_id(prompt_id)
                    if prompt:
                        prompt_names[prompt_id] = prompt.get("name")
                except Exception as exc:
                    logger.warning(f"Failed to resolve prompt name for API key list prompt {prompt_id}: {exc}")

        # Convert documents to JSON-serializable format
        serialized_keys = []
        for key in api_keys:
            record_id = str(key["_id"]) if key.get("_id") else None
            key_dict = {
                "_id": record_id,   # legacy — admin_panel.js depends on this
                "id": record_id,    # canonical
                "api_key": mask_api_key(key.get("api_key"), show_last=True, prefix="***"),
                "adapter_name": key.get("adapter_name"),
                "client_name": key.get("client_name"),
                "notes": key.get("notes"),
                "active": key.get("active", True),
                "created_at": _serialize_created_at(key.get("created_at")),
            }

            # Handle system_prompt_id if it exists
            if key.get("system_prompt_id"):
                prompt_id = str(key["system_prompt_id"])
                key_dict["system_prompt_id"] = prompt_id
                key_dict["system_prompt_name"] = prompt_names.get(prompt_id)

            serialized_keys.append(key_dict)
        
        return serialized_keys
        
    except Exception as e:
        logger.error(f"Error listing API keys: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list API keys")


@admin_router.get("/api-keys/{api_key_id}/detail", dependencies=[apikeys_auth])
async def get_api_key_detail(
    api_key_id: str,
    request: Request,
):
    """Get admin-only detail for a specific API key record, including the raw key value."""
    api_key_service = getattr(request.app.state, 'api_key_service', None)
    check_service_availability(api_key_service, "API key service")
    prompt_service = getattr(request.app.state, 'prompt_service', None)

    try:
        if not api_key_service._initialized:
            await api_key_service.initialize()

        key = await api_key_service.database.find_one(
            api_key_service.collection_name,
            {"_id": api_key_id}
        )
        if not key:
            raise HTTPException(status_code=404, detail="API key not found")

        record_id = str(key["_id"]) if key.get("_id") else None
        key_dict = {
            "_id": record_id,   # legacy — admin_panel.js depends on this
            "id": record_id,    # canonical
            "api_key": key.get("api_key"),
            "adapter_name": key.get("adapter_name"),
            "client_name": key.get("client_name"),
            "notes": key.get("notes"),
            "active": key.get("active", True),
            "created_at": _serialize_created_at(key.get("created_at")),
        }

        if key.get("system_prompt_id"):
            prompt_id = str(key["system_prompt_id"])
            key_dict["system_prompt_id"] = prompt_id
            if prompt_service:
                try:
                    prompt = await prompt_service.get_prompt_by_id(prompt_id)
                    if prompt:
                        key_dict["system_prompt_name"] = prompt.get("name")
                except Exception as exc:
                    logger.warning(f"Failed to resolve prompt name for API key detail prompt {prompt_id}: {exc}")

        return key_dict

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving API key detail for {api_key_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve API key detail")


@admin_router.get("/api-keys/{api_key_id}/status", dependencies=[apikeys_auth])
async def get_api_key_status(
    api_key_id: str,
    request: Request,
):
    """
    Get the status of a specific API key.

    Accepts a record _id or raw API key value as the identifier.
    """
    api_key_service = getattr(request.app.state, 'api_key_service', None)
    check_service_availability(api_key_service, "API key service")

    # Try _id first, then raw key, then adapter name
    status = await api_key_service.get_api_key_status_by_id(api_key_id)
    if not status.get("exists"):
        status = await api_key_service.get_api_key_status(api_key_id)
    logger.debug(f"Checked status for API key identifier: {mask_api_key(api_key_id, show_last=True, prefix='***')}")
    return status


@admin_router.patch("/api-keys/{api_key_id}/rename", dependencies=[apikeys_auth])
async def rename_api_key(
    api_key_id: str,
    new_api_key: str = Query(..., min_length=8, description="New API key value"),
    request: Request = None,
):
    """
    Rename an API key by record ID.
    """
    api_key_service = getattr(request.app.state, 'api_key_service', None)
    check_service_availability(api_key_service, "API key service")

    new_api_key = new_api_key.strip()
    if len(new_api_key) < 8:
        raise HTTPException(status_code=422, detail="New API key must be at least 8 characters")

    success = await api_key_service.rename_api_key_by_id(api_key_id, new_api_key)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to rename API key")

    masked_new = mask_api_key(new_api_key, show_last=True, prefix="***")
    logger.info(f"Renamed API key {mask_api_key(api_key_id, show_last=True, prefix='***')} to {masked_new}")
    return {"status": "success", "message": "API key renamed successfully", "new_api_key_masked": masked_new}


@admin_router.put("/api-keys/{api_key_id}", dependencies=[apikeys_auth])
async def update_api_key(
    api_key_id: str,
    data: ApiKeyUpdate,
    request: Request,
):
    """Update editable API key metadata by record ID."""
    api_key_service = getattr(request.app.state, 'api_key_service', None)
    check_service_availability(api_key_service, "API key service")

    adapter_manager = getattr(request.app.state, 'adapter_manager', None)

    success = await api_key_service.update_api_key_metadata(
        api_key_id,
        client_name=data.client_name,
        adapter_name=data.adapter_name,
        system_prompt_id=data.system_prompt_id,
        notes=data.notes,
        adapter_manager=adapter_manager
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update API key")

    logger.info(f"Updated API key metadata for: {mask_api_key(api_key_id, show_last=True, prefix='***')}")
    return {"status": "success", "message": "API key updated successfully"}


@admin_router.post("/api-keys/{api_key_id}/deactivate", dependencies=[apikeys_auth])
async def deactivate_api_key(
    api_key_id: str,
    api_key_service = Depends(get_api_key_service),
):
    """Deactivate an API key by record ID."""
    success = await api_key_service.deactivate_api_key_by_id(api_key_id)

    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    logger.info(f"Deactivated API key: {mask_api_key(api_key_id, show_last=True, prefix='***')}")
    return {"status": "success", "message": "API key deactivated"}


@admin_router.delete("/api-keys/{api_key_id}", dependencies=[apikeys_auth])
async def delete_api_key(
    api_key_id: str,
    api_key_service = Depends(get_api_key_service),
):
    """Delete an API key by record ID."""
    success = await api_key_service.delete_api_key_by_id(api_key_id)

    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    logger.info(f"Deleted API key: {mask_api_key(api_key_id, show_last=True, prefix='***')}")
    return {"status": "success", "message": "API key deleted"}


def _supports_template_reload(adapter_instance, adapter_config: dict) -> bool:
    """Whether an adapter's implementation exposes reload_templates().

    Checks the live instance when cached; otherwise resolves the implementation
    class from config without instantiating it, so uncached adapters report
    accurately instead of always False.
    """
    if adapter_instance is not None:
        return hasattr(adapter_instance, 'reload_templates')

    implementation_path = (adapter_config or {}).get('implementation')
    if not implementation_path or '.' not in implementation_path:
        return False
    try:
        module_path, class_name = implementation_path.rsplit('.', 1)
        module = importlib.import_module(module_path)
        adapter_class = getattr(module, class_name)
        return hasattr(adapter_class, 'reload_templates')
    except Exception:
        return False


@admin_router.get("/adapters/capabilities", dependencies=[adapters_auth])
async def get_adapter_capabilities(
    request: Request,
):
    """Return adapter capability metadata relevant to admin operations."""
    adapter_manager = getattr(request.app.state, 'adapter_manager', None)
    if not adapter_manager:
        raise HTTPException(status_code=503, detail="Adapter manager is not available")

    try:
        available_names = adapter_manager.get_available_adapters() if hasattr(adapter_manager, 'get_available_adapters') else []
        base_manager = getattr(adapter_manager, 'base_adapter_manager', adapter_manager)
        adapter_cache = getattr(base_manager, 'adapter_cache', None)

        capabilities = []
        for adapter_name in available_names:
            adapter_config = adapter_manager.get_adapter_config(adapter_name) if hasattr(adapter_manager, 'get_adapter_config') else {}
            adapter_instance = adapter_cache.get(adapter_name) if adapter_cache and adapter_cache.contains(adapter_name) else None
            capabilities.append({
                "name": adapter_name,
                "adapter_type": (adapter_config or {}).get("adapter"),
                "cached": bool(adapter_instance),
                "supports_template_reload": _supports_template_reload(adapter_instance, adapter_config),
            })

        return {"adapters": capabilities}
    except Exception as e:
        logger.error(f"Failed to get adapter capabilities: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get adapter capabilities")


# ---------------------------------------------------------------------------
# Adapter config file management
# ---------------------------------------------------------------------------

def _get_adapters_dir(request: Request) -> Path:
    """Resolve the adapters config directory from app state."""
    config_path = Path(getattr(request.app.state, 'config_path', 'config/config.yaml'))
    return config_path.parent / "adapters"


def _validate_adapter_filename(filename: str) -> None:
    """Reject path-traversal attempts."""
    if "/" in filename or "\\" in filename or ".." in filename or not filename.endswith(".yaml"):
        raise HTTPException(status_code=400, detail="Invalid adapter filename")


def _find_adapter_block(lines: list[str], adapter_name: str) -> tuple[int, int]:
    """Find start/end line indices of a single adapter entry in YAML content.

    Returns (start, end) where lines[start:end] is the adapter block.
    """
    start = None
    start_indent = 0
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped.startswith("- name:"):
            continue
        name_val = stripped[len("- name:"):].strip().strip('"').strip("'")
        if name_val == adapter_name:
            start = i
            start_indent = len(line) - len(stripped)
            break

    if start is None:
        return -1, -1

    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].lstrip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        current_indent = len(lines[i]) - len(stripped)
        if stripped.startswith("- ") and current_indent <= start_indent:
            end = i
            break
        if current_indent < start_indent:
            end = i
            break

    while end > start + 1 and lines[end - 1].strip() == "":
        end -= 1

    return start, end


def _find_adapter_file(adapters_dir: Path, adapter_name: str):
    """Locate which .yaml file contains an adapter by name. Returns (path, content)."""
    for yaml_file in sorted(adapters_dir.glob("*.yaml")):
        content = yaml_file.read_text(encoding="utf-8")
        try:
            parsed = yaml.safe_load(content) or {}
            for a in parsed.get("adapters", []):
                if isinstance(a, dict) and a.get("name") == adapter_name:
                    return yaml_file, content
        except yaml.YAMLError:
            continue
    return None, ""


def _write_adapter_config(file_path: Path, new_content: str) -> None:
    """Write new adapter config content to disk."""
    file_path.write_text(new_content, encoding="utf-8")
    logger.info("Adapter config updated: %s", file_path)
    from config.config_manager import clear_config_cache
    clear_config_cache()


@admin_router.get("/adapters/config", dependencies=[adapters_auth])
async def list_adapter_configs(
    request: Request,
):
    """List all adapter config files with a summary of each adapter entry."""
    adapters_dir = _get_adapters_dir(request)
    if not adapters_dir.is_dir():
        return {"files": [], "imports": [], "adapters_yaml": ""}

    # Read adapters.yaml to get current imports
    adapters_yaml_path = adapters_dir.parent / "adapters.yaml"
    adapters_yaml_content = ""
    current_imports = []
    if adapters_yaml_path.is_file():
        adapters_yaml_content = adapters_yaml_path.read_text(encoding="utf-8")
        try:
            parsed = yaml.safe_load(adapters_yaml_content) or {}
            raw_imports = parsed.get("import", [])
            if isinstance(raw_imports, str):
                raw_imports = [raw_imports]
            current_imports = [str(i) for i in (raw_imports or [])]
        except yaml.YAMLError:
            pass

    files = []
    for yaml_file in sorted(adapters_dir.glob("*.yaml")):
        entry = {
            "filename": yaml_file.name,
            "path": f"adapters/{yaml_file.name}",
            "imported": f"adapters/{yaml_file.name}" in current_imports,
            "adapters": [],
        }
        try:
            parsed = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
            for adapter in parsed.get("adapters", []):
                if isinstance(adapter, dict):
                    entry["adapters"].append({
                        "name": adapter.get("name", ""),
                        "enabled": adapter.get("enabled", True),
                        "type": adapter.get("type", ""),
                        "adapter": adapter.get("adapter", ""),
                        "datasource": adapter.get("datasource", ""),
                        "inference_provider": adapter.get("inference_provider", ""),
                        "model": adapter.get("model", ""),
                        "embedding_provider": adapter.get("embedding_provider", ""),
                        "allowed_models": adapter.get("allowed_models") or [],
                    })
        except Exception:
            pass  # File might have invalid YAML — show it anyway with empty adapters
        files.append(entry)

    return {"files": files, "imports": current_imports, "adapters_yaml": adapters_yaml_content}


@admin_router.get("/adapters/config/entry/{adapter_name}", dependencies=[adapters_auth])
async def get_adapter_entry(
    adapter_name: str,
    request: Request,
):
    """Return just the YAML block for a single adapter (preserves comments)."""
    adapters_dir = _get_adapters_dir(request)
    file_path, content = _find_adapter_file(adapters_dir, adapter_name)
    if not file_path:
        raise HTTPException(status_code=404, detail=f"Adapter '{adapter_name}' not found in any config file")

    lines = content.split("\n")
    start, end = _find_adapter_block(lines, adapter_name)
    if start < 0:
        raise HTTPException(status_code=404, detail=f"Adapter block '{adapter_name}' not found")

    block = "\n".join(lines[start:end])
    return {"content": block, "filename": file_path.name, "adapter_name": adapter_name}


@admin_router.put("/adapters/config/entry/{adapter_name}", dependencies=[adapters_auth])
async def save_adapter_entry(
    adapter_name: str,
    request: Request,
    body: dict = Body(...)
):
    """Replace a single adapter's YAML block in its source file."""
    new_block = body.get("content")
    if new_block is None:
        raise HTTPException(status_code=422, detail="Missing 'content' field")

    try:
        yaml.safe_load(new_block)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid YAML: {exc}")

    adapters_dir = _get_adapters_dir(request)
    file_path, content = _find_adapter_file(adapters_dir, adapter_name)
    if not file_path:
        raise HTTPException(status_code=404, detail=f"Adapter '{adapter_name}' not found in any config file")

    lines = content.split("\n")
    start, end = _find_adapter_block(lines, adapter_name)
    if start < 0:
        raise HTTPException(status_code=404, detail=f"Adapter block '{adapter_name}' not found")

    new_lines = lines[:start] + new_block.split("\n") + lines[end:]
    new_content = "\n".join(new_lines)
    _write_adapter_config(file_path, new_content)
    return {
        "message": f"Adapter '{adapter_name}' saved. Use 'Reload Adapter' to apply changes.",
    }


@admin_router.patch("/adapters/config/entry/{adapter_name}/toggle", dependencies=[adapters_auth])
async def toggle_adapter_enabled(
    adapter_name: str,
    request: Request,
    body: dict = Body(...)
):
    """Toggle the enabled field of a single adapter in its YAML file."""
    enabled = body.get("enabled")
    if enabled is None:
        raise HTTPException(status_code=422, detail="Missing 'enabled' field")

    adapters_dir = _get_adapters_dir(request)
    file_path, content = _find_adapter_file(adapters_dir, adapter_name)
    if not file_path:
        raise HTTPException(status_code=404, detail=f"Adapter '{adapter_name}' not found in any config file")

    lines = content.split("\n")
    start, end = _find_adapter_block(lines, adapter_name)
    if start < 0:
        raise HTTPException(status_code=404, detail=f"Adapter block '{adapter_name}' not found")

    enabled_str = "true" if enabled else "false"
    found_enabled = False
    for i in range(start, end):
        stripped = lines[i].lstrip()
        if stripped.startswith("enabled:"):
            indent = lines[i][:len(lines[i]) - len(stripped)]
            lines[i] = f"{indent}enabled: {enabled_str}"
            found_enabled = True
            break

    if not found_enabled:
        name_line = lines[start]
        indent = " " * (len(name_line) - len(name_line.lstrip()) + 2)
        lines.insert(start + 1, f"{indent}enabled: {enabled_str}")

    new_content = "\n".join(lines)
    _write_adapter_config(file_path, new_content)

    state = "enabled" if enabled else "disabled"

    # Apply the change to the running adapter manager so the toggle takes
    # effect immediately (disabled adapters are evicted from cache and
    # removed from config_manager; enabled adapters are preloaded).
    adapter_manager = getattr(request.app.state, "adapter_manager", None)
    config_path = getattr(request.app.state, "config_path", None)
    reload_summary = None
    reload_error = None

    if adapter_manager and config_path:
        try:
            new_config = reload_adapters_config(config_path)
            reload_summary = await adapter_manager.reload_adapter_configs(new_config, adapter_name)
        except Exception as e:
            logger.error(
                f"Adapter '{adapter_name}' YAML was {state} but runtime reload failed: {e}",
                exc_info=True,
            )
            reload_error = str(e)
    else:
        reload_error = "adapter_manager or config_path not available in app state"
        logger.warning(
            f"Adapter '{adapter_name}' YAML was {state} but runtime reload skipped: {reload_error}"
        )

    if reload_error:
        message = (
            f"Adapter '{adapter_name}' {state} in config, but runtime reload failed "
            f"({reload_error}). Use 'Reload Adapter' to apply."
        )
    else:
        message = f"Adapter '{adapter_name}' {state} and applied."

    return {
        "message": message,
        "enabled": enabled,
        "reload_summary": reload_summary,
        "reload_error": reload_error,
    }


@admin_router.get("/adapters/config/{filename}", dependencies=[adapters_auth])
async def get_adapter_config_file(
    filename: str,
    request: Request,
):
    """Read the raw YAML content of a specific adapter config file."""
    _validate_adapter_filename(filename)
    file_path = _get_adapters_dir(request) / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Adapter file not found: {filename}")
    content = file_path.read_text(encoding="utf-8")
    return {"content": content, "filename": filename}


@admin_router.put("/adapters/config/{filename}", dependencies=[adapters_auth])
async def save_adapter_config_file(
    filename: str,
    request: Request,
    body: dict = Body(...)
):
    """Validate and write an adapter config file."""
    _validate_adapter_filename(filename)

    content = body.get("content")
    if content is None:
        raise HTTPException(status_code=422, detail="Missing 'content' field")

    try:
        yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid YAML: {exc}")

    file_path = _get_adapters_dir(request) / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Adapter file not found: {filename}")

    _write_adapter_config(file_path, content)
    return {
        "message": f"Adapter config '{filename}' saved. Use 'Reload Adapter' to apply changes.",
    }


# ---------------------------------------------------------------------------
# Adapter creation (adapter SDK)
# ---------------------------------------------------------------------------

def _adapter_sdk_paths(request: Request) -> tuple[Path, Path]:
    """Adapters dir + adapters.yaml for the *running* config.

    The SDK writer's module constants are repo-root relative; the server may run
    with --config elsewhere, so both paths are always passed explicitly.
    """
    adapters_dir = _get_adapters_dir(request)
    return adapters_dir, adapters_dir.parent / "adapters.yaml"


def _render_from_spec(spec_key: str, answers: Dict[str, Any]) -> str:
    """Render a spec + answers to YAML, mapping SDK errors onto HTTP codes."""
    try:
        spec = get_spec(spec_key)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    try:
        return render_adapter(spec, answers)
    except ValueError as exc:
        # Bad/missing variant — the message already lists the valid values.
        raise HTTPException(status_code=422, detail=str(exc))
    except UndefinedError as exc:
        raise HTTPException(status_code=422, detail=f"Missing answer: {exc}")


@admin_router.get("/adapters/specs", dependencies=[adapters_auth])
async def list_adapter_specs():
    """List the adapter families the SDK can generate, with their form questions."""
    return {"specs": serialize_registry()}


@admin_router.post("/adapters/preview", dependencies=[adapters_auth])
async def preview_adapter(
    request: Request,
    body: dict = Body(...),
):
    """Render a spec + answers to YAML without writing it.

    Validation problems come back in `errors` (still HTTP 200) so the UI can show
    them alongside the preview rather than replacing it with an error.
    """
    spec_key = body.get("spec")
    answers = body.get("answers") or {}
    yaml_text = _render_from_spec(spec_key, answers)
    # Over-long answers are ordinary form mistakes, so they are listed alongside the
    # preview rather than replacing it with an error.
    errors = validate_answers(get_spec(spec_key), answers) + validate_yaml_text(yaml_text)
    return {"yaml": yaml_text, "errors": errors}


@admin_router.post("/adapters", dependencies=[adapters_auth])
async def create_adapter(
    request: Request,
    body: dict = Body(...),
):
    """Generate an adapter from a spec, write + register it, and apply it live."""
    answers = body.get("answers") or {}
    register = body.get("register", True)
    overwrite = bool(body.get("overwrite"))

    spec_key = body.get("spec")
    yaml_text = _render_from_spec(spec_key, answers)
    # The form enforces the same bounds, but this endpoint is reachable without it.
    errors = validate_answers(get_spec(spec_key), answers) + validate_yaml_text(yaml_text)
    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))

    name = answers.get("name")
    if not name:
        raise HTTPException(status_code=422, detail="Missing 'name' in answers")
    try:
        adapter_writer.validate_adapter_name(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    adapters_dir, adapters_yaml = _adapter_sdk_paths(request)
    if not adapters_dir.is_dir():
        raise HTTPException(status_code=500, detail=f"Adapters directory not found: {adapters_dir}")

    filename = f"{name}.yaml"
    if (adapters_dir / filename).exists() and not overwrite:
        raise HTTPException(status_code=409, detail=f"Adapter file '{filename}' already exists")

    # The writer only guards the filename; an adapter of the same name living in a
    # different file would silently shadow this one at load time. `overwrite` waives
    # the target-file check above, never this one — otherwise it would be a way to
    # create exactly the duplicate definition this guard exists to prevent.
    existing_file, _ = _find_adapter_file(adapters_dir, name)
    if existing_file and existing_file.name != filename:
        raise HTTPException(
            status_code=409,
            detail=f"Adapter '{name}' already exists in {existing_file.name}"
        )

    try:
        path = adapter_writer.write_adapter(
            name, yaml_text,
            register=register,
            overwrite=overwrite,
            adapters_dir=adapters_dir,
            adapters_yaml=adapters_yaml,
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        # register_import found no import list — the file itself is already written.
        raise HTTPException(
            status_code=500,
            detail=f"Adapter file was written to {adapters_dir / filename} but could not be "
                   f"registered: {exc}"
        )

    from config.config_manager import clear_config_cache
    clear_config_cache()

    # Apply immediately, same contract as the enable/disable toggle.
    adapter_manager = getattr(request.app.state, "adapter_manager", None)
    config_path = getattr(request.app.state, "config_path", None)
    reload_summary = None
    reload_error = None

    if adapter_manager and config_path:
        try:
            new_config = reload_adapters_config(config_path)
            reload_summary = await adapter_manager.reload_adapter_configs(new_config, name)
        except Exception as e:
            logger.error(f"Adapter '{name}' was created but runtime reload failed: {e}", exc_info=True)
            reload_error = str(e)
    else:
        reload_error = "adapter_manager or config_path not available in app state"

    if reload_error:
        message = (
            f"Adapter '{name}' created, but runtime reload failed ({reload_error}). "
            "Use 'Reload Adapters' to apply."
        )
    else:
        message = f"Adapter '{name}' created and applied."

    return {
        "message": message,
        "name": name,
        "filename": filename,
        "path": str(path),
        "registered": bool(register),
        "yaml": yaml_text,
        "reload_summary": reload_summary,
        "reload_error": reload_error,
    }


@admin_router.post("/api-keys/{api_key_id}/prompt", dependencies=[apikeys_auth])
async def associate_prompt_with_api_key(
    api_key_id: str,
    data: ApiKeyPromptAssociate,
    api_key_service = Depends(get_api_key_service),
):
    """Associate a system prompt with an API key by record ID."""
    success = await api_key_service.update_api_key_system_prompt(api_key_id, data.prompt_id)

    if not success:
        raise HTTPException(status_code=404, detail="API key not found or prompt not associated")

    return {"status": "success", "message": "System prompt associated with API key"}


# API Key Quota Management Routes
async def _resolve_api_key(request: Request, api_key_id: str) -> str:
    """Resolve a record _id to the raw API key value for quota service calls."""
    api_key_service = getattr(request.app.state, 'api_key_service', None)
    check_service_availability(api_key_service, "API key service")
    doc = await api_key_service._resolve_key_doc(api_key_id)
    return doc["api_key"]


@admin_router.get("/api-keys/{api_key_id}/quota", response_model=ApiKeyQuotaResponse, dependencies=[apikeys_auth])
async def get_api_key_quota(
    api_key_id: str,
    request: Request,
):
    """Get quota configuration and current usage for an API key by record ID."""
    quota_service = getattr(request.app.state, 'quota_service', None)
    if not quota_service or not quota_service.enabled:
        raise HTTPException(
            status_code=503,
            detail="Quota service is not available. Ensure throttling is enabled in configuration."
        )

    api_key = await _resolve_api_key(request, api_key_id)
    quota_config, usage_stats = await quota_service.get_quota_and_usage(api_key)
    daily_remaining, monthly_remaining = quota_service.calculate_remaining(quota_config, usage_stats)

    # Calculate current throttle delay (for informational purposes)
    throttle_delay_ms = 0
    if quota_config.get('throttle_enabled', True):
        daily_limit = quota_config.get('daily_limit')
        monthly_limit = quota_config.get('monthly_limit')
        daily_used = usage_stats.get('daily_used', 0)
        monthly_used = usage_stats.get('monthly_used', 0)

        # Calculate usage percentage for delay estimation
        percentages = []
        if daily_limit and daily_limit > 0:
            percentages.append(daily_used / daily_limit)
        if monthly_limit and monthly_limit > 0:
            percentages.append(monthly_used / monthly_limit)

        if percentages:
            usage_pct = max(percentages)
            threshold = 0.7  # Default threshold
            if usage_pct >= threshold:
                normalized = (usage_pct - threshold) / (1.0 - threshold)
                normalized = min(1.0, max(0.0, normalized))
                # Exponential curve estimation
                throttle_delay_ms = int(100 + (5000 - 100) * (normalized ** 2))

    # Mask API key for response
    masked_key = mask_api_key(api_key, show_last=True, prefix="***")

    return ApiKeyQuotaResponse(
        api_key_masked=masked_key,
        quota=ApiKeyQuota(
            daily_limit=quota_config.get('daily_limit'),
            monthly_limit=quota_config.get('monthly_limit'),
            throttle_enabled=quota_config.get('throttle_enabled', True),
            throttle_priority=quota_config.get('throttle_priority', 5)
        ),
        usage=ApiKeyUsage(
            daily_used=usage_stats.get('daily_used', 0),
            monthly_used=usage_stats.get('monthly_used', 0),
            daily_reset_at=usage_stats.get('daily_reset_at', 0),
            monthly_reset_at=usage_stats.get('monthly_reset_at', 0),
            last_request_at=usage_stats.get('last_request_at')
        ),
        daily_remaining=daily_remaining,
        monthly_remaining=monthly_remaining,
        throttle_delay_ms=throttle_delay_ms
    )


@admin_router.put("/api-keys/{api_key_id}/quota", dependencies=[apikeys_auth])
async def update_api_key_quota(
    api_key_id: str,
    quota_data: ApiKeyQuotaUpdate,
    request: Request,
):
    """Update quota settings for an API key by record ID."""
    quota_service = getattr(request.app.state, 'quota_service', None)
    if not quota_service or not quota_service.enabled:
        raise HTTPException(
            status_code=503,
            detail="Quota service is not available. Ensure throttling is enabled in configuration."
        )

    api_key = await _resolve_api_key(request, api_key_id)
    success = await quota_service.update_quota_config(
        api_key,
        daily_limit=quota_data.daily_limit,
        monthly_limit=quota_data.monthly_limit,
        throttle_enabled=quota_data.throttle_enabled,
        throttle_priority=quota_data.throttle_priority
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update quota configuration")

    logger.info(f"Updated quota for API key id: {api_key_id}")
    return {"status": "success", "message": "Quota configuration updated successfully"}


@admin_router.post("/api-keys/{api_key_id}/quota/reset", dependencies=[apikeys_auth])
async def reset_api_key_quota(
    api_key_id: str,
    request: Request,
    period: str = Query("daily", pattern="^(daily|monthly|all)$"),
):
    """Reset quota usage counters for an API key by record ID."""
    quota_service = getattr(request.app.state, 'quota_service', None)
    if not quota_service or not quota_service.enabled:
        raise HTTPException(
            status_code=503,
            detail="Quota service is not available. Ensure throttling is enabled in configuration."
        )

    api_key = await _resolve_api_key(request, api_key_id)
    success = await quota_service.reset_usage(api_key, period)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to reset quota usage")

    logger.info(f"Reset {period} quota for API key id: {api_key_id}")
    return {"status": "success", "message": f"Quota usage ({period}) reset successfully"}


@admin_router.get("/quotas/usage-report", dependencies=[apikeys_auth])
async def get_quota_usage_report(
    request: Request,
    period: str = Query("daily", pattern="^(daily|monthly)$"),
    limit: int = Query(100, ge=1, le=1000),
):
    """
    Get a usage report for all API keys.

    Returns aggregated usage statistics for the specified period.

    Args:
        period: The period for the report ("daily" or "monthly")
        limit: Maximum number of keys to include (default: 100, max: 1000)
        request: The incoming request
        authorized: Authentication check result

    Returns:
        List of API keys with their usage statistics

    Raises:
        HTTPException 503: If quota service is not available
    """
    # Check if quota service is available
    quota_service = getattr(request.app.state, 'quota_service', None)
    if not quota_service or not quota_service.enabled:
        raise HTTPException(
            status_code=503,
            detail="Quota service is not available. Ensure throttling is enabled in configuration."
        )

    # Get all API keys
    api_key_service = getattr(request.app.state, 'api_key_service', None)
    if not api_key_service:
        raise HTTPException(status_code=503, detail="API key service is not available")

    try:
        # Get API keys from database
        api_keys = await api_key_service.database.find_many(
            api_key_service.collection_name,
            {"active": True},
            limit=limit
        )

        # Build usage report
        report = []
        for key_doc in api_keys:
            api_key = key_doc.get('api_key', '')
            if not api_key:
                continue

            # Get usage for this key
            usage_stats = await quota_service.get_usage(api_key)
            quota_config = await quota_service.get_quota_config(api_key)

            # Mask API key
            masked_key = mask_api_key(api_key, show_last=True, prefix="***")

            report.append({
                "api_key_masked": masked_key,
                "client_name": key_doc.get('client_name', 'Unknown'),
                "adapter_name": key_doc.get('adapter_name'),
                "period": period,
                "used": usage_stats.get(f'{period}_used', 0),
                "limit": quota_config.get(f'{period}_limit'),
                "throttle_enabled": quota_config.get('throttle_enabled', True),
                "throttle_priority": quota_config.get('throttle_priority', 5)
            })

        return {
            "period": period,
            "total_keys": len(report),
            "usage": report
        }

    except Exception as e:
        logger.error(f"Error generating quota usage report: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate usage report")


# System Prompts Management Routes
@admin_router.post("/prompts", response_model=SystemPromptResponse, dependencies=[prompts_auth])
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


@admin_router.get("/prompts", dependencies=[prompts_auth])
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


@admin_router.get("/prompts/{prompt_id}", dependencies=[prompts_auth])
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


@admin_router.post("/render-markdown", dependencies=[prompts_auth])
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


@admin_router.put("/prompts/{prompt_id}", response_model=SystemPromptResponse, dependencies=[prompts_auth])
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


@admin_router.delete("/prompts/{prompt_id}", dependencies=[prompts_auth])
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


# Chat History Management (only available in inference-only mode)
@admin_router.get("/chat-history/{session_id}", dependencies=[conversations_auth])
async def get_chat_history(
    session_id: str,
    request: Request,
    limit: int = Query(50, ge=1, le=500),
):
    """Get chat history for a session"""
    chat_history_service = getattr(request.app.state, 'chat_history_service', None)
    if not chat_history_service:
        raise HTTPException(status_code=503, detail="Chat history service is not available")

    history = await chat_history_service.get_conversation_history(
        session_id=session_id,
        limit=limit,
        include_metadata=True
    )

    return {"session_id": session_id, "messages": history, "count": len(history)}


# Adapter Hot Reload
@admin_router.post("/reload-adapters", response_model=AdapterReloadResponse, dependencies=[adapters_auth])
async def reload_adapters(
    request: Request,
    adapter_name: Optional[str] = Query(None, description="Optional name of specific adapter to reload"),
):
    """
    Reload adapter configurations from adapters.yaml without server restart.

    This endpoint performs hot-swap of adapters:
    - If adapter_name is None: reloads all adapters
    - If adapter_name is provided: reloads only that specific adapter

    For all adapters:
    - Adds new adapters
    - Removes disabled adapters
    - Updates changed adapter configurations
    - Preserves in-flight requests on old adapters

    For specific adapter:
    - Updates only the named adapter configuration
    - Returns error if adapter not found in config

    Requires admin authentication.

    Query Parameters:
        adapter_name: Optional name of specific adapter to reload

    Returns:
        AdapterReloadResponse with reload summary

    Raises:
        HTTPException: If adapter manager is unavailable, config loading fails,
                      or specific adapter is not found
    """
    # Get adapter manager from app state
    adapter_manager = getattr(request.app.state, 'adapter_manager', None)
    if not adapter_manager:
        raise HTTPException(
            status_code=503,
            detail="Adapter manager is not available"
        )

    # Get config path from app state
    config_path = getattr(request.app.state, 'config_path', None)
    if not config_path:
        raise HTTPException(
            status_code=500,
            detail="Config path is not available in app state"
        )

    try:
        # Reload the configuration from disk
        new_config = reload_adapters_config(config_path)

        # Reload adapters using the adapter manager
        summary = await adapter_manager.reload_adapter_configs(new_config, adapter_name)

        # Under performance.workers > 1, this only reloaded the worker that
        # served this request - bump the durable generation counter so
        # sibling workers pick up the change on their next poll tick (see
        # services/adapter_reload_state.py). No-op in single-process mode.
        import os
        if os.environ.get('ORBIT_SUPERVISOR_PID'):
            from services import adapter_reload_state
            new_generation = await adapter_reload_state.bump_generation(request.app.state, "adapter_config")
            if new_generation is not None:
                last_seen = getattr(request.app.state, "_adapter_reload_last_seen", None)
                if last_seen is not None:
                    # Avoid this same worker redundantly reloading itself again
                    # on its own next poll tick.
                    last_seen["adapter_config"] = new_generation
            else:
                logger.warning("Failed to propagate adapter reload to other workers")

        # Generate appropriate message
        if adapter_name:
            action = summary.get('action', 'reloaded')
            message = f"Adapter '{adapter_name}' {action} successfully"
        else:
            added = summary.get('added', 0)
            removed = summary.get('removed', 0)
            updated = summary.get('updated', 0)
            total = summary.get('total', 0)
            message = f"Adapters reloaded: {added} added, {removed} removed, {updated} updated, {total} total"

        logger.info(f"Adapter reload completed: {message}")

        return AdapterReloadResponse(
            status="success",
            message=message,
            summary=summary,
            timestamp=datetime.utcnow().isoformat() + "Z"
        )

    except FileNotFoundError as e:
        logger.error(f"Config file not found: {str(e)}")
        raise HTTPException(status_code=500, detail="Config file not found")
    except ValueError as e:
        logger.error(f"Adapter reload error: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during adapter reload: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to reload adapters")


@admin_router.post("/reload-adapters/async", dependencies=[adapters_auth])
async def reload_adapters_async(
    request: Request,
    adapter_name: Optional[str] = Query(None, description="Optional name of specific adapter to reload"),
):
    """Start adapter reload as a background admin job."""
    job = _create_admin_job(request, "reload_adapters", adapter_name)

    async def run_job():
        _update_admin_job(request, job["job_id"], status="running", message="Reloading adapters")
        try:
            result = await reload_adapters(request=request, adapter_name=adapter_name)
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
            logger.error(f"Async adapter reload failed: {exc}", exc_info=True)
            _update_admin_job(request, job["job_id"], status="failed", message=str(exc), error=str(exc))

    asyncio.create_task(run_job())
    return {
      "status": "accepted",
      "job_id": job["job_id"],
      "message": "Adapter reload started in background"
    }


# Template Hot Reload
@admin_router.post("/reload-templates", response_model=TemplateReloadResponse, dependencies=[adapters_auth])
async def reload_templates(
    request: Request,
    adapter_name: Optional[str] = Query(None, description="Optional name of specific adapter to reload templates for"),
):
    """
    Reload intent templates from template library files without server restart.

    This endpoint reloads templates for intent-based adapters:
    - If adapter_name is None: reloads templates for all cached intent adapters
    - If adapter_name is provided: reloads templates only for that adapter

    The adapter must already be loaded (cached). This does not reload adapter
    configuration, only re-reads template YAML files and re-indexes in vector store.

    This is useful for:
    - Updating template definitions without restarting the server
    - Adding new templates to an existing adapter
    - Modifying template NL examples or descriptions
    - Iterating on template development

    Requires admin authentication.

    Query Parameters:
        adapter_name: Optional name of specific adapter to reload templates for

    Returns:
        TemplateReloadResponse with reload summary including:
        - templates_loaded: Number of templates loaded
        - adapters_updated: List of adapters that were updated
        - errors: Any errors encountered during reload

    Raises:
        HTTPException 404: If adapter not found or doesn't support template reloading
        HTTPException 503: If adapter manager is unavailable
        HTTPException 500: If reload fails unexpectedly
    """
    adapter_manager = getattr(request.app.state, 'adapter_manager', None)
    if not adapter_manager:
        raise HTTPException(
            status_code=503,
            detail="Adapter manager is not available"
        )

    try:
        summary = await adapter_manager.reload_templates(adapter_name)

        # Under performance.workers > 1, this only reloaded the worker that
        # served this request - bump the durable generation counter so
        # sibling workers pick up the change on their next poll tick (see
        # services/adapter_reload_state.py). No-op in single-process mode.
        import os
        if os.environ.get('ORBIT_SUPERVISOR_PID'):
            from services import adapter_reload_state
            new_generation = await adapter_reload_state.bump_generation(request.app.state, "templates")
            if new_generation is not None:
                last_seen = getattr(request.app.state, "_adapter_reload_last_seen", None)
                if last_seen is not None:
                    last_seen["templates"] = new_generation
            else:
                logger.warning("Failed to propagate template reload to other workers")

        # Generate appropriate message
        if adapter_name:
            message = f"Templates for adapter '{adapter_name}' reloaded: {summary.get('templates_loaded', 0)} templates"
        else:
            adapters_count = len(summary.get('adapters_updated', []))
            message = f"Templates reloaded for {adapters_count} adapter(s): {summary.get('templates_loaded', 0)} total templates"

        if summary.get('errors'):
            message += f" ({len(summary['errors'])} error(s))"

        logger.info(f"Template reload completed: {message}")

        return TemplateReloadResponse(
            status="success",
            message=message,
            summary=summary,
            timestamp=datetime.utcnow().isoformat() + "Z"
        )

    except ValueError as e:
        logger.error(f"Template reload error: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during template reload: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to reload templates")


@admin_router.post("/reload-templates/async", dependencies=[adapters_auth])
async def reload_templates_async(
    request: Request,
    adapter_name: Optional[str] = Query(None, description="Optional name of specific adapter to reload templates for"),
):
    """Start template reload as a background admin job."""
    job = _create_admin_job(request, "reload_templates", adapter_name)

    async def run_job():
        _update_admin_job(request, job["job_id"], status="running", message="Reloading templates")
        try:
            result = await reload_templates(request=request, adapter_name=adapter_name)
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
            logger.error(f"Async template reload failed: {exc}", exc_info=True)
            _update_admin_job(request, job["job_id"], status="failed", message=str(exc), error=str(exc))

    asyncio.create_task(run_job())
    return {
      "status": "accepted",
      "job_id": job["job_id"],
      "message": "Template reload started in background"
    }


@admin_router.post("/adapters/{adapter_name}/test-query", dependencies=[Depends(require_permission("adapters.manage"))])
async def test_adapter_query(
    adapter_name: str,
    body: TemplateTestRequest,
    request: Request,
):
    """
    Test a natural language query against an intent adapter's templates
    without running the full LLM inference pipeline.

    Returns detailed diagnostics: template matching scores, parameter extraction,
    rendered query, and raw datasource results.
    """
    adapter_manager = getattr(request.app.state, 'adapter_manager', None)
    if not adapter_manager:
        raise HTTPException(status_code=503, detail="Adapter manager is not available")

    try:
        adapter = await adapter_manager.get_adapter(adapter_name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Adapter '{adapter_name}' not found: {e}")

    if adapter is None:
        raise HTTPException(status_code=404, detail=f"Adapter '{adapter_name}' not found")

    # Verify adapter is an intent or composite retriever
    from retrievers.base.intent_sql_base import IntentSQLRetriever
    from retrievers.base.intent_http_base import IntentHTTPRetriever
    from retrievers.base.intent_composite_base import CompositeIntentRetriever

    if not isinstance(adapter, (IntentSQLRetriever, IntentHTTPRetriever, CompositeIntentRetriever)):
        raise HTTPException(
            status_code=400,
            detail=f"Adapter '{adapter_name}' is type '{type(adapter).__name__}', not an intent retriever. "
                   f"test-query only works with intent-based adapters."
        )

    from utils.template_diagnostics import diagnose_template_query

    try:
        result = await diagnose_template_query(
            retriever=adapter,
            query=body.query,
            max_templates=body.max_templates,
            execute=body.execute,
            include_all_candidates=body.include_all_candidates,
            verbose=body.verbose,
        )
        return result
    except Exception as e:
        logger.error(f"Template test-query failed for '{adapter_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Test query failed")


@admin_router.get("/jobs/{job_id}", dependencies=[system_auth])
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


@admin_router.get("/info", dependencies=[system_auth])
async def get_server_info(
    request: Request,
):
    """
    Get server information including PID and status.
    
    This endpoint provides information about the running server instance,
    including process ID for process management.
    
    Returns:
        Dictionary containing server information (PID, version, etc.)
    """
    import os

    from services.pause_state import is_paused

    # Under multi-worker mode, os.getpid() is this specific worker's PID, not
    # a stable process to target for stop/status — report the supervisor's
    # PID instead (set by InferenceServer.run(), inherited by all workers).
    pid = int(os.environ.get('ORBIT_SUPERVISOR_PID', os.getpid()))

    return {
        "pid": pid,
        "version": "2.14.0",
        "status": "paused" if await is_paused(request.app.state) else "running"
    }


@admin_router.get("/config", dependencies=[config_auth])
async def get_config(
    request: Request,
):
    """
    Read the raw config.yaml file content.

    Returns the raw file text so that comments, env var references,
    and import directives are preserved.
    """
    config_path = Path(getattr(request.app.state, 'config_path', 'config/config.yaml'))
    if not config_path.is_file():
        raise HTTPException(status_code=404, detail=f"Config file not found: {config_path}")
    content = config_path.read_text(encoding='utf-8')
    return {"content": content, "path": str(config_path.resolve())}


@admin_router.put("/config", dependencies=[config_auth])
async def update_config(
    request: Request,
    body: dict = Body(...)
):
    """
    Validate and write new config.yaml content.

    Accepts {"content": "<yaml string>"}. Validates YAML syntax, then writes
    the new content. A server restart is required for most changes to take effect.
    """
    content = body.get("content")
    if content is None:
        raise HTTPException(status_code=422, detail="Missing 'content' field")

    # Validate YAML syntax
    try:
        yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid YAML: {exc}")

    config_path = Path(getattr(request.app.state, 'config_path', 'config/config.yaml'))
    if not config_path.is_file():
        raise HTTPException(status_code=404, detail=f"Config file not found: {config_path}")

    # Write new content
    config_path.write_text(content, encoding='utf-8')
    logger.debug("Config file updated at %s", config_path)

    # Clear loaded config singleton so next access picks up changes
    from config.config_manager import clear_config_cache
    clear_config_cache()

    return {
        "message": "Config saved. A server restart is required for changes to take effect.",
    }


_TOP_LEVEL_CONFIG_KEY_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*):(?:\s.*)?$')


def _split_config_sections(content: str):
    """Split raw config.yaml text into top-level-key sections by line range.

    Slices the raw text instead of parsing+re-dumping YAML, so comments, env
    var placeholders (${...}), and the import: directive survive untouched.
    A comment/blank-line block immediately above a key is treated as part of
    that key's section, since it documents the section below it.
    """
    lines = content.splitlines(keepends=True)
    key_line_indices = [i for i, line in enumerate(lines) if _TOP_LEVEL_CONFIG_KEY_RE.match(line)]
    if not key_line_indices:
        return None

    starts = []
    for pos, key_idx in enumerate(key_line_indices):
        lower_bound = key_line_indices[pos - 1] + 1 if pos > 0 else 0
        start = key_idx
        while start > lower_bound and (lines[start - 1].strip() == "" or lines[start - 1].lstrip().startswith("#")):
            start -= 1
        starts.append(start)

    sections = []
    for pos, key_idx in enumerate(key_line_indices):
        key = _TOP_LEVEL_CONFIG_KEY_RE.match(lines[key_idx]).group(1)
        end = starts[pos + 1] - 1 if pos + 1 < len(key_line_indices) else len(lines) - 1
        sections.append({"key": key, "start": starts[pos], "end": end})
    return sections, lines


def _load_config_sections(request: Request):
    config_path = Path(getattr(request.app.state, 'config_path', 'config/config.yaml'))
    if not config_path.is_file():
        raise HTTPException(status_code=404, detail=f"Config file not found: {config_path}")
    content = config_path.read_text(encoding='utf-8')
    result = _split_config_sections(content)
    if result is None:
        raise HTTPException(status_code=404, detail="No top-level sections found in config file")
    sections, lines = result
    return config_path, sections, lines


@admin_router.get("/config/sections", dependencies=[config_auth])
async def list_config_sections(request: Request):
    """List config.yaml's top-level keys, for the split settings editor."""
    _config_path, sections, _lines = _load_config_sections(request)
    return {
        "sections": [
            {"key": s["key"], "line_count": s["end"] - s["start"] + 1}
            for s in sections
        ]
    }


@admin_router.get("/config/sections/{key}", dependencies=[config_auth])
async def get_config_section(request: Request, key: str):
    """Read the raw text of a single top-level config.yaml section."""
    _config_path, sections, lines = _load_config_sections(request)
    match = next((s for s in sections if s["key"] == key), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"Section '{key}' not found")
    return {"content": "".join(lines[match["start"]:match["end"] + 1])}


@admin_router.put("/config/sections/{key}", dependencies=[config_auth])
async def update_config_section(request: Request, key: str, body: dict = Body(...)):
    """Validate and splice one section's edited text back into config.yaml."""
    new_section_content = body.get("content")
    if new_section_content is None:
        raise HTTPException(status_code=422, detail="Missing 'content' field")
    if not new_section_content.endswith("\n"):
        new_section_content += "\n"

    config_path, sections, lines = _load_config_sections(request)
    match = next((s for s in sections if s["key"] == key), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"Section '{key}' not found")

    # Count raw top-level key headers by regex rather than trusting yaml.safe_load's
    # parsed keys — PyYAML silently collapses duplicate mapping keys (last one wins),
    # so a pasted-in second "auth:" header would parse clean but still be a structural
    # change we don't want to allow from the per-section editor.
    section_key_headers = [
        m.group(1) for line in new_section_content.splitlines()
        if (m := _TOP_LEVEL_CONFIG_KEY_RE.match(line + "\n"))
    ]
    if section_key_headers != [key]:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Section '{key}' must remain a single top-level key named '{key}'. "
                "Renaming, removing, adding, or duplicating a top-level key here isn't "
                "supported — use the Raw File editor for structural changes."
            ),
        )

    try:
        parsed_section = yaml.safe_load(new_section_content)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid YAML in section '{key}': {exc}")

    # Belt-and-suspenders: the raw header count catches duplicate/renamed/injected
    # headers even when PyYAML would silently collapse them, while this parsed-key
    # check catches any exotic syntax (e.g. multi-line flow mappings) that could
    # confuse the regex-based header count.
    if not isinstance(parsed_section, dict) or list(parsed_section.keys()) != [key]:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Section '{key}' must remain a single top-level key named '{key}'. "
                "Renaming, removing, adding, or duplicating a top-level key here isn't "
                "supported — use the Raw File editor for structural changes."
            ),
        )

    new_content = "".join(lines[:match["start"]] + [new_section_content] + lines[match["end"] + 1:])

    full_key_headers = [
        m.group(1) for line in new_content.splitlines()
        if (m := _TOP_LEVEL_CONFIG_KEY_RE.match(line + "\n"))
    ]
    if full_key_headers != [s["key"] for s in sections]:
        raise HTTPException(
            status_code=422,
            detail=f"Saving section '{key}' would change the config file's top-level structure.",
        )

    try:
        parsed_full = yaml.safe_load(new_content)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid YAML after merging section '{key}': {exc}")

    if not isinstance(parsed_full, dict) or list(parsed_full.keys()) != [s["key"] for s in sections]:
        raise HTTPException(
            status_code=422,
            detail=f"Saving section '{key}' would change the config file's top-level structure.",
        )

    config_path.write_text(new_content, encoding='utf-8')
    logger.debug("Config section '%s' updated at %s", key, config_path)

    from config.config_manager import clear_config_cache
    clear_config_cache()

    return {
        "message": f"'{key}' section saved. A server restart is required for changes to take effect.",
    }


@admin_router.post("/shutdown", dependencies=[system_auth])
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


@admin_router.post("/pause", dependencies=[system_auth])
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


@admin_router.post("/resume", dependencies=[system_auth])
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


@admin_router.post("/restart", dependencies=[system_auth])
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


def _resolve_log_dir_and_candidates(request: Request):
    config = request.app.state.config or {}
    file_config = config.get("logging", {}).get("handlers", {}).get("file", {})
    log_dir = Path(file_config.get("directory", "logs")).resolve()
    base_filename = file_config.get("filename", "orbit.log")
    candidates = sorted(
        [p for p in log_dir.glob(base_filename + "*") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return log_dir, candidates


@admin_router.get("/logs/files", dependencies=[logs_auth])
def list_log_files(request: Request):
    """Return all available log files sorted newest-first."""
    log_dir, candidates = _resolve_log_dir_and_candidates(request)
    files = []
    for i, path in enumerate(candidates):
        stat = path.stat()
        files.append({
            "filename": path.name,
            "size": stat.st_size,
            "updated_at": datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z",
            "is_current": i == 0,
        })
    return {"files": files}


@admin_router.get("/logs/tail", dependencies=[logs_auth])
def tail_log_file(
    request: Request,
    lines: int = Query(200, ge=10, le=500),
    file: str = Query(None),
):
    """
    Return ORBIT log file contents. With no `file` param returns the most
    recently updated file. Pass `file=<filename>` to read a specific rotated file.
    """
    log_dir, candidates = _resolve_log_dir_and_candidates(request)

    if not candidates:
        raise HTTPException(status_code=404, detail="No log files found")

    if file:
        log_path = (log_dir / Path(file).name).resolve()
        if log_path not in candidates:
            raise HTTPException(status_code=404, detail="Log file not found")
    else:
        log_path = candidates[0]

    try:
        mtime = log_path.stat().st_mtime
        tail_lines = _tail_file(log_path, lines)
    except OSError as exc:
        logger.error(f"Failed reading log file {log_path}: {exc}")
        raise HTTPException(status_code=500, detail="Failed to read log file")

    return {
        "file": str(log_path),
        "filename": log_path.name,
        "updated_at": datetime.utcfromtimestamp(mtime).isoformat() + "Z",
        "lines": tail_lines,
    }


# -------------------------------------------------------------------------
# Admin / Auth Audit Events
# -------------------------------------------------------------------------

@admin_router.get("/audit/events", dependencies=[audit_auth])
async def list_admin_audit_events(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    source: str = Query("all", pattern="^(all|admin|inference)$"),
    event_type: Optional[str] = Query(None),
    event_prefix: Optional[str] = Query(None, description="Match event_type that starts with this prefix (e.g. 'auth.', 'admin.api_key.')"),
    actor_id: Optional[str] = Query(None),
    success: Optional[bool] = Query(None),
    resource_type: Optional[str] = Query(None),
    call_type: Optional[str] = Query(None, description="Filter inference rows by AI call kind: inference, embedding, reranking, image, video, audio, document"),
    q: Optional[str] = Query(None, description="Free-text search across actor_username, path, resource_id, ip"),
    since: Optional[str] = Query(None, description="ISO timestamp (inclusive lower bound)"),
    until: Optional[str] = Query(None, description="ISO timestamp (exclusive upper bound)"),
):
    """
    List audit ledger entries, most recent first.

    The ledger can merge two sources:
      - admin/auth audit events
      - inference request audit records

    We oversample each requested source, normalize the row shape, sort by
    timestamp descending, apply the remaining filters, then slice the page.
    """
    def _normalize_admin(row: dict) -> dict:
        return {
            **row,
            "audit_source": "admin",
            "audit_kind": "admin_event",
            "title": row.get("event_type") or "admin.event",
            "subtitle": row.get("action") or "",
            "search_text": " ".join(
                str(row.get(field, "") or "")
                for field in (
                    "event_type",
                    "action",
                    "actor_username",
                    "actor_id",
                    "path",
                    "resource_id",
                    "resource_type",
                    "ip",
                )
            ).lower(),
        }

    def _normalize_inference(row: dict) -> dict:
        api_key = row.get("api_key") or {}
        masked_key = api_key.get("key") if isinstance(api_key, dict) else None

        actor_type = "anonymous"
        actor_id_value = None
        if row.get("user_id"):
            actor_type = "user"
            actor_id_value = row.get("user_id")
        elif masked_key:
            actor_type = "api_key"
            actor_id_value = masked_key

        provider = row.get("provider") or "inference"
        model = row.get("model")
        adapter_name = row.get("adapter_name")
        session_id = row.get("session_id")
        query_text = str(row.get("query") or "")
        response_text = str(row.get("response") or "")

        return {
            **row,
            "audit_source": "inference",
            "audit_kind": "inference_request",
            "call_type": row.get("call_type") or "inference",
            "event_type": "inference.request",
            "action": "BLOCK" if row.get("blocked") else "INFER",
            "resource_type": "inference",
            "resource_id": adapter_name or provider,
            "actor_type": actor_type,
            "actor_id": actor_id_value,
            "actor_username": None,
            "method": row.get("method") or "INFER",
            "path": row.get("path") or provider,
            "status_code": None,
            "success": not bool(row.get("blocked")),
            "request_summary": {
                "provider": provider,
                "model": model,
                "adapter_name": adapter_name,
                "session_id": session_id,
                "user_id": row.get("user_id"),
                "api_key": masked_key,
                "blocked": bool(row.get("blocked")),
                "response_compressed": bool(row.get("response_compressed")),
                "prompt_tokens": row.get("prompt_tokens"),
                "completion_tokens": row.get("completion_tokens"),
                "total_tokens": row.get("total_tokens"),
                "reasoning_tokens": row.get("reasoning_tokens"),
                "cost_usd": row.get("cost_usd"),
                "input_rate_per_1m": row.get("input_rate_per_1m"),
                "output_rate_per_1m": row.get("output_rate_per_1m"),
                "pricing_source": row.get("pricing_source"),
                "usage_unit": row.get("usage_unit"),
                "usage_quantity": row.get("usage_quantity"),
                "call_type": row.get("call_type") or "inference",
            },
            "title": model or provider,
            "subtitle": adapter_name or "inference request",
            "search_text": " ".join(
                value
                for value in (
                    provider,
                    model,
                    adapter_name,
                    session_id,
                    row.get("user_id"),
                    masked_key,
                    row.get("ip"),
                    query_text,
                    response_text,
                )
                if value
            ).lower(),
        }

    audit_service = getattr(request.app.state, "audit_service", None)
    admin_enabled = bool(audit_service and audit_service.admin_events_enabled)
    inference_enabled = bool(audit_service and audit_service.inference_events_enabled)

    if audit_service is None or (not admin_enabled and not inference_enabled):
        raise HTTPException(
            status_code=503,
            detail=(
                "Audit ledger is not enabled. Enable either "
                "internal_services.audit.enabled for inference requests or "
                "internal_services.audit.admin_events.enabled for admin events."
            ),
        )
    if source == "admin" and not admin_enabled:
        raise HTTPException(
            status_code=503,
            detail="Admin audit is not enabled. Set internal_services.audit.admin_events.enabled: true.",
        )
    if source == "inference" and not inference_enabled:
        raise HTTPException(
            status_code=503,
            detail="Inference request audit is not enabled. Set internal_services.audit.enabled: true.",
        )

    native_admin_filters: dict = {}
    if event_type is not None:
        native_admin_filters["event_type"] = event_type
    if actor_id is not None:
        native_admin_filters["actor_id"] = actor_id
    if success is not None:
        native_admin_filters["success"] = success
    if resource_type is not None:
        native_admin_filters["resource_type"] = resource_type

    native_inference_filters: dict = {}
    if success is not None:
        native_inference_filters["blocked"] = not success
    # Legacy rows written before call_type existed are NULL, not "inference" —
    # a native "call_type = 'inference'" filter would exclude them at the
    # storage layer before _normalize_inference()'s NULL-defaulting ever runs.
    # Only push the filter down when it can't misfire on NULL; "inference" is
    # applied via the post-filter below instead, after normalization.
    if call_type is not None and call_type != "inference":
        native_inference_filters["call_type"] = call_type

    merging_sources = source == "all" and admin_enabled and inference_enabled
    needs_post_filter = any(v is not None for v in (event_prefix, q, since, until)) or merging_sources or source != "admin"
    fetch_limit = min(offset + (limit * 10 if needs_post_filter else limit), 5000)

    rows: List[dict] = []
    try:
        if source in ("all", "admin") and admin_enabled:
            admin_rows = await audit_service.query_admin_events(
                filters=native_admin_filters,
                limit=fetch_limit,
                offset=0,
                sort_by="timestamp",
                sort_order=-1,
            )
            rows.extend(_normalize_admin(row) for row in admin_rows)

        if source in ("all", "inference") and inference_enabled:
            inference_rows = await audit_service.query_audit_logs(
                filters=native_inference_filters,
                limit=fetch_limit,
                offset=0,
                sort_by="timestamp",
                sort_order=-1,
            )
            rows.extend(_normalize_inference(row) for row in inference_rows)
    except Exception as exc:
        logger.error(f"Failed to query audit events: {exc}")
        raise HTTPException(status_code=500, detail="Failed to query audit events")

    rows.sort(key=lambda row: str(row.get("timestamp", "")), reverse=True)

    q_lower = q.lower() if q else None
    prefix = event_prefix
    since_val = since
    until_val = until

    def keep(row: dict) -> bool:
        if source != "all" and row.get("audit_source") != source:
            return False
        if event_type and row.get("audit_source") != "admin":
            return False
        if prefix:
            if row.get("audit_source") != "admin":
                return False
            if not str(row.get("event_type", "")).startswith(prefix):
                return False
        if actor_id and str(row.get("actor_id") or "") != actor_id:
            return False
        if resource_type:
            if row.get("audit_source") != "admin":
                return False
            if str(row.get("resource_type") or "") != resource_type:
                return False
        if success is not None and bool(row.get("success")) != success:
            return False
        if call_type:
            if row.get("audit_source") != "inference":
                return False
            if (row.get("call_type") or "inference") != call_type:
                return False
        if since_val and str(row.get("timestamp", "")) < since_val:
            return False
        if until_val and str(row.get("timestamp", "")) >= until_val:
            return False
        if q_lower and q_lower not in str(row.get("search_text", "")):
            return False
        return True

    filtered = [row for row in rows if keep(row)]
    total_after_filter = len(filtered)
    page = filtered[offset : offset + limit]

    for row in page:
        row.pop("search_text", None)

    return {
        "events": page,
        "limit": limit,
        "offset": offset,
        "returned": len(page),
        "total": total_after_filter,
        "sources": {
            "admin": admin_enabled,
            "inference": inference_enabled,
        },
    }


# -------------------------------------------------------------------------
# Observability — token usage / cost aggregation (admin panel "Costs" tab)
# -------------------------------------------------------------------------

@admin_router.get("/observability/usage", dependencies=[audit_auth])
async def get_observability_usage(
    request: Request,
    days: int = Query(7, ge=1, le=365),
    bucket: str = Query("day", pattern="^(hour|day)$"),
    group_by: str = Query("model", pattern="^(model|provider|adapter_name|user_id|call_type|none)$"),
    provider: Optional[str] = Query(None),
    adapter_name: Optional[str] = Query(None),
    call_type: Optional[str] = Query(None, pattern="^(inference|embedding|reranking|image|video|audio|document)$"),
    limit_groups: int = Query(10, ge=1, le=100),
):
    """
    Aggregate token usage and estimated cost over a time window, for the
    admin panel's Costs tab. Cost is an ESTIMATE from the local
    rate table in config/pricing.yaml, not a provider invoice.

    Reuses the audit.read permission (the same dependency that gates
    /admin/audit/events) — it already grants reading full inference
    queries/responses, which is strictly more sensitive than aggregate
    token counts, so a separate permission would only create a role that
    could never be granted meaningfully.
    """
    audit_service = getattr(request.app.state, "audit_service", None)
    if audit_service is None or not audit_service.inference_events_enabled:
        raise HTTPException(
            status_code=503,
            detail="Inference request audit is not enabled. Set internal_services.audit.enabled: true.",
        )

    # Audit records are stored with naive local timestamps (see
    # AuditService.log_conversation's `datetime.now()`), not UTC — the
    # since/until bounds must be constructed in that same naive-local domain,
    # or the string-based range predicates used by every aggregate_usage
    # backend shift the window by the host's UTC offset. `now` (UTC-aware) is
    # kept separately for the response envelope and pricing-staleness check.
    now = datetime.now(timezone.utc)
    now_local = datetime.now()
    since_dt = now_local - timedelta(days=days)
    since = since_dt.isoformat()
    until = now_local.isoformat()

    filters: Dict[str, Any] = {}
    if provider:
        filters["provider"] = provider
    if adapter_name:
        filters["adapter_name"] = adapter_name
    if call_type:
        # Keep legacy NULL rows in the default/all view. An explicit
        # inference filter intentionally follows the audit-events endpoint's
        # semantics, where NULL is interpreted as inference by the backend.
        filters["call_type"] = call_type

    result = await audit_service.aggregate_usage(
        since=since,
        until=until,
        bucket=bucket,
        group_by=group_by,
        filters=filters,
        limit_groups=limit_groups,
    )

    pricing_service = getattr(request.app.state, "pricing_service", None)
    pricing_updated = getattr(pricing_service, "updated", None) if pricing_service else None
    stale = False
    if pricing_updated:
        try:
            updated_dt = datetime.fromisoformat(pricing_updated).replace(tzinfo=timezone.utc)
            stale_after_days = getattr(pricing_service, "_stale_after_days", 120)
            stale = (now - updated_dt).days > stale_after_days
        except ValueError:
            pass

    return {
        "window": {"since": since, "until": until, "bucket": bucket, "days": days},
        "totals": result.get("totals", {}),
        "series": result.get("series", []),
        "groups": result.get("groups", []),
        "pricing": {"updated": pricing_updated, "stale": stale},
    }


# ---------------------------------------------------------------------------
# MCP clients
#
# Servers live in config/mcp_clients.yaml, a heavily commented file whose
# commented-out entries are the catalogue of servers an admin can turn on.
# Writes therefore patch individual scalar lines in place (reusing the adapter
# tab's _find_adapter_block, which matches any "- name:" block) rather than
# round-tripping through yaml.dump, which would erase every comment.
# ---------------------------------------------------------------------------

def _get_mcp_config_path(request: Request) -> Path:
    """Resolve config/mcp_clients.yaml from app state."""
    config_path = Path(getattr(request.app.state, 'config_path', 'config/config.yaml'))
    return config_path.parent / "mcp_clients.yaml"


def _mcp_overridable() -> Dict[str, Any]:
    """The settings a server may override, read from the runtime's own table so
    the panel can never drift from what MCPClientManager actually honors."""
    from services.mcp_client_service import MCPClientManager
    return MCPClientManager._OVERRIDABLE


# Accepted range per numeric setting. Served to the admin panel so the inputs
# and this validation cannot disagree, and enforced here because the panel is
# not the only thing that can call these endpoints.
_MCP_SETTING_BOUNDS: Dict[str, tuple] = {
    "tool_timeout": (1, 600),
    "discovery_timeout": (1, 120),
    "discovery_retry_interval": (0, 3600),
    "max_tool_iterations": (1, 50),
    "tool_result_max_chars": (100, 200000),
}


def _validate_mcp_settings(settings: Any, overridable: Dict[str, Any]) -> None:
    """Reject unknown keys, wrong types, and out-of-range values.

    A null value is allowed: it deletes a per-server override so the server
    inherits the mcp_clients-level default again.
    """
    if not settings:
        return
    if not isinstance(settings, dict):
        raise HTTPException(status_code=422, detail="'settings' must be an object")

    unknown = sorted(set(settings) - set(overridable))
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown MCP setting(s): {', '.join(unknown)}")

    for key, value in settings.items():
        if value is None:
            continue
        _coerce, fallback = overridable[key]
        if isinstance(fallback, bool):
            if not isinstance(value, bool):
                raise HTTPException(status_code=422, detail=f"'{key}' must be true or false")
            continue
        # bool is a subclass of int, so screen it out before the int check.
        if isinstance(value, bool) or not isinstance(value, int):
            raise HTTPException(status_code=422, detail=f"'{key}' must be a whole number")
        low, high = _MCP_SETTING_BOUNDS.get(key, (0, 2_147_483_647))
        if not (low <= value <= high):
            raise HTTPException(
                status_code=422,
                detail=f"'{key}' must be between {low} and {high} (got {value})",
            )


# Transport-identity fields editable from the panel. url/token are scalar
# lines patched by _patch_yaml_scalars; command is also scalar. args is a
# single-line list patched by _patch_yaml_list. env/headers are nested maps
# patched by _patch_yaml_map.
#
# headers is http/sse-only: MCPClientManager._open_session only reads
# server_config["headers"] in its sse/http branches (via _expand_headers) —
# the stdio branch builds a subprocess from command/args/env alone and never
# looks at headers. Editing it for a stdio server would silently persist a
# value the runtime never consumes.
_HTTP_CONNECTION_KEYS = {"url", "token", "headers"}
_STDIO_CONNECTION_KEYS = {"command", "args", "env"}
_MCP_CONNECTION_URL_MAX_LENGTH = 2048
_MCP_CONNECTION_TOKEN_MAX_LENGTH = 8192
_MCP_CONNECTION_COMMAND_MAX_LENGTH = 512
_MCP_CONNECTION_ARG_MAX_LENGTH = 2048
_MCP_CONNECTION_ARGS_MAX_COUNT = 64
_MCP_CONNECTION_ENV_MAX_ENTRIES = 64
_MCP_CONNECTION_ENV_KEY_MAX_LENGTH = 256
_MCP_CONNECTION_ENV_VALUE_MAX_LENGTH = 8192
_MCP_CONNECTION_HEADER_MAX_ENTRIES = 32
_MCP_CONNECTION_HEADER_KEY_MAX_LENGTH = 256
_MCP_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# Map keys are written unquoted into mcp_clients.yaml (only values are
# json.dumps-quoted — see _patch_yaml_map), and the key is always the first
# non-whitespace character on the line. YAML treats a leading indicator
# character (#, !, *, `, |, ", ', :, etc.) or an embedded " #" as structural,
# not literal — e.g. a key of "X #evil" silently truncates the line into a
# comment, turning `headers:` into a bare scalar on reparse instead of a map.
# Restricting to alphanumerics and hyphen (covers every real header name,
# e.g. X-Api-Key, Authorization) sidesteps the entire class of issues rather
# than trying to enumerate which indicator characters are unsafe where.
_MCP_HEADER_KEY_RE = re.compile(r"^[A-Za-z0-9\-]+$")


def _validate_mcp_endpoint_url(url: str) -> None:
    """Require a bounded absolute HTTP(S) endpoint URL.

    MCP's remote transports only support HTTP and SSE over HTTP(S).  Rejecting
    control characters and fragments also prevents ambiguous request targets
    from being written through the admin panel.
    """
    if not url or not url.strip():
        raise HTTPException(status_code=422, detail="'url' must be a non-empty string")
    if len(url) > _MCP_CONNECTION_URL_MAX_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"'url' must be at most {_MCP_CONNECTION_URL_MAX_LENGTH} characters",
        )
    if url != url.strip() or any(ord(char) < 32 or char.isspace() for char in url):
        raise HTTPException(status_code=422, detail="'url' must not contain whitespace or control characters")
    try:
        parsed = urlsplit(url)
        # Accessing port validates it (for example, rejects :99999).
        _ = parsed.port
    except ValueError:
        raise HTTPException(status_code=422, detail="'url' must be a valid HTTP(S) URL")
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname or parsed.fragment:
        raise HTTPException(status_code=422, detail="'url' must be an absolute HTTP(S) URL without a fragment")


def _token_overridden_by_headers(entry: Dict[str, Any]) -> bool:
    """True if this server's `headers` block already sets Authorization.

    _expand_headers applies `headers` entries after the `token` shorthand, so
    only an explicit Authorization header actually overrides it — an unrelated
    header like X-API-Key or X-Tenant does not, and token stays editable.
    """
    headers = entry.get("headers") or {}
    if not isinstance(headers, dict):
        return False
    return any(str(k).lower() == "authorization" for k in headers)


def _validate_mcp_command(command: Any) -> None:
    if not isinstance(command, str) or not command.strip():
        raise HTTPException(status_code=422, detail="'command' must be a non-empty string")
    if len(command) > _MCP_CONNECTION_COMMAND_MAX_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"'command' must be at most {_MCP_CONNECTION_COMMAND_MAX_LENGTH} characters",
        )
    if command != command.strip() or any(ord(ch) < 32 for ch in command):
        raise HTTPException(status_code=422, detail="'command' must not contain control characters")


def _validate_mcp_args(args: Any) -> None:
    if args is None:
        return
    if not isinstance(args, list):
        raise HTTPException(status_code=422, detail="'args' must be a list of strings")
    if len(args) > _MCP_CONNECTION_ARGS_MAX_COUNT:
        raise HTTPException(
            status_code=422,
            detail=f"'args' must contain at most {_MCP_CONNECTION_ARGS_MAX_COUNT} entries",
        )
    for arg in args:
        if not isinstance(arg, str):
            raise HTTPException(status_code=422, detail="'args' entries must be strings")
        if len(arg) > _MCP_CONNECTION_ARG_MAX_LENGTH:
            raise HTTPException(
                status_code=422,
                detail=f"'args' entries must be at most {_MCP_CONNECTION_ARG_MAX_LENGTH} characters",
            )
        if any(ord(ch) < 32 for ch in arg):
            raise HTTPException(status_code=422, detail="'args' entries must not contain control characters")


def _validate_mcp_env(env: Any) -> None:
    if env is None:
        return
    if not isinstance(env, dict):
        raise HTTPException(status_code=422, detail="'env' must be an object")
    if len(env) > _MCP_CONNECTION_ENV_MAX_ENTRIES:
        raise HTTPException(
            status_code=422,
            detail=f"'env' must contain at most {_MCP_CONNECTION_ENV_MAX_ENTRIES} entries",
        )
    for key, value in env.items():
        if not isinstance(key, str) or not _MCP_ENV_KEY_RE.match(key) or len(key) > _MCP_CONNECTION_ENV_KEY_MAX_LENGTH:
            raise HTTPException(status_code=422, detail=f"'env' key '{key}' is not a valid environment variable name")
        if not isinstance(value, str):
            raise HTTPException(status_code=422, detail=f"'env.{key}' must be a string")
        if len(value) > _MCP_CONNECTION_ENV_VALUE_MAX_LENGTH:
            raise HTTPException(
                status_code=422,
                detail=f"'env.{key}' must be at most {_MCP_CONNECTION_ENV_VALUE_MAX_LENGTH} characters",
            )


def _validate_mcp_headers(headers: Any) -> None:
    if headers is None:
        return
    if not isinstance(headers, dict):
        raise HTTPException(status_code=422, detail="'headers' must be an object")
    if len(headers) > _MCP_CONNECTION_HEADER_MAX_ENTRIES:
        raise HTTPException(
            status_code=422,
            detail=f"'headers' must contain at most {_MCP_CONNECTION_HEADER_MAX_ENTRIES} entries",
        )
    for key, value in headers.items():
        if (
            not isinstance(key, str)
            or not _MCP_HEADER_KEY_RE.match(key)
            or len(key) > _MCP_CONNECTION_HEADER_KEY_MAX_LENGTH
        ):
            raise HTTPException(status_code=422, detail=f"'headers' key '{key}' is not a valid header name")
        if not isinstance(value, str):
            raise HTTPException(status_code=422, detail=f"'headers.{key}' must be a string")
        if len(value) > _MCP_CONNECTION_TOKEN_MAX_LENGTH:
            raise HTTPException(
                status_code=422,
                detail=f"'headers.{key}' must be at most {_MCP_CONNECTION_TOKEN_MAX_LENGTH} characters",
            )


def _validate_mcp_connection(entry: Dict[str, Any], connection: Any) -> None:
    """Reject connection edits for transports/fields that don't support them.

    A null token clears it (server reverts to no Authorization from the
    token shorthand); url may not be cleared, since a server with no
    endpoint can never be dialed. env/headers are full-replace maps: the
    submitted value is the complete desired map, not a diff.
    """
    if not connection:
        return
    if not isinstance(connection, dict):
        raise HTTPException(status_code=422, detail="'connection' must be an object")

    transport = entry.get("transport", "stdio")
    if transport == "stdio":
        allowed = _STDIO_CONNECTION_KEYS
    elif transport in ("http", "sse"):
        allowed = _HTTP_CONNECTION_KEYS
    else:
        raise HTTPException(
            status_code=422,
            detail=f"Connection fields are only editable for stdio/http/sse servers, not '{transport}'.",
        )

    unknown = sorted(set(connection) - allowed)
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown connection field(s): {', '.join(unknown)}")

    if "url" in connection:
        url = connection["url"]
        if not isinstance(url, str):
            raise HTTPException(status_code=422, detail="'url' must be a string")
        _validate_mcp_endpoint_url(url)

    if "token" in connection:
        token = connection["token"]
        if token is not None and not isinstance(token, str):
            raise HTTPException(status_code=422, detail="'token' must be a string")
        if token is not None and len(token) > _MCP_CONNECTION_TOKEN_MAX_LENGTH:
            raise HTTPException(
                status_code=422,
                detail=f"'token' must be at most {_MCP_CONNECTION_TOKEN_MAX_LENGTH} characters",
            )
        if token is not None:
            merged_headers = dict(entry.get("headers") or {})
            if "headers" in connection and isinstance(connection["headers"], dict):
                merged_headers = dict(connection["headers"])
            if any(str(k).lower() == "authorization" for k in merged_headers):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "This server sets an explicit 'Authorization' header, which overrides "
                        "'token' — edit mcp_clients.yaml directly to change it."
                    ),
                )

    if "command" in connection:
        _validate_mcp_command(connection["command"])
    if "args" in connection:
        _validate_mcp_args(connection["args"])
    if "env" in connection:
        _validate_mcp_env(connection["env"])
    if "headers" in connection:
        _validate_mcp_headers(connection["headers"])


def _mcp_endpoint_label(server: Dict[str, Any]) -> str:
    """One-line human description of where a server lives."""
    transport = server.get("transport", "stdio")
    if transport == "stdio":
        parts = [str(server.get("command", ""))] + [str(a) for a in (server.get("args") or [])]
        return " ".join(p for p in parts if p)
    return str(server.get("url", ""))


def _read_mcp_config(request: Request) -> tuple[Path, str, Dict[str, Any]]:
    """Return (path, raw_text, parsed mcp_clients block)."""
    path = _get_mcp_config_path(request)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"MCP config not found at {path}")
    content = path.read_text(encoding="utf-8")
    try:
        parsed = yaml.safe_load(content) or {}
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid YAML in mcp_clients.yaml: {exc}")
    block = parsed.get("mcp_clients")
    if not isinstance(block, dict):
        raise HTTPException(status_code=404, detail="mcp_clients.yaml has no 'mcp_clients' section")
    return path, content, block


@admin_router.get("/mcp/servers", dependencies=[config_auth])
async def list_mcp_servers(request: Request):
    """Configured MCP servers with their effective settings and provenance."""
    path, _, block = _read_mcp_config(request)
    overridable = _mcp_overridable()

    defaults = {}
    for key, (_coerce, fallback) in overridable.items():
        defaults[key] = block[key] if key in block else fallback

    servers = []
    for entry in block.get("servers") or []:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        overrides = {k: entry[k] for k in overridable if k in entry}
        effective = dict(defaults)
        effective.update(overrides)
        transport = entry.get("transport", "stdio")
        connection = None
        if transport in ("http", "sse"):
            connection = {
                "url": entry.get("url", ""),
                "token": entry.get("token", ""),
                "headers": entry.get("headers") or {},
                "uses_custom_headers": _token_overridden_by_headers(entry),
            }
        elif transport == "stdio":
            connection = {
                "command": entry.get("command", ""),
                "args": entry.get("args") or [],
                "env": entry.get("env") or {},
            }
        servers.append({
            "name": entry["name"],
            "transport": transport,
            "enabled": entry.get("enabled", True),
            "endpoint": _mcp_endpoint_label(entry),
            "overrides": overrides,
            "effective": effective,
            "connection": connection,
        })

    return {
        "enabled": block.get("enabled", False),
        "path": path.name,
        "settings": [
            {
                "key": key,
                "default": defaults[key],
                "type": "boolean" if isinstance(fallback, bool) else "number",
                "min": _MCP_SETTING_BOUNDS.get(key, (0, 0))[0],
                "max": _MCP_SETTING_BOUNDS.get(key, (0, 0))[1],
            }
            for key, (_c, fallback) in overridable.items()
        ],
        "defaults": defaults,
        "servers": servers,
    }


async def _reload_mcp_clients(request: Request, server_name: Optional[str] = None) -> Dict[str, Any]:
    """Re-read config from disk and apply the change.

    Reuses reload_adapters_config so mcp_clients.yaml's ${VAR} references
    expand exactly as they do at startup, then splices only the mcp_clients
    key into the live app-state config in place (it is the same dict object
    registered as 'config' in the pipeline DI container, so pipeline steps
    see the update without any other live service being touched).

    When `server_name` is given and a manager already exists and stays
    enabled, only that server's entry is rebuilt and re-dialed — every other
    configured server keeps its live tool cache untouched, so editing one
    server never forces an unrelated one to redial. Any other case (MCP newly
    enabled, MCP disabled, or a defaults-level change) rebuilds the whole
    manager, since defaults feed every server's effective settings.
    """
    import services.mcp_client_service as mcp_client_service

    config_path = getattr(request.app.state, "config_path", None)
    if not config_path:
        raise RuntimeError("Server config path is not available")

    new_config = reload_adapters_config(config_path)
    app_config = getattr(request.app.state, "config", None)
    if app_config is None:
        app_config = {}
        request.app.state.config = app_config
    new_mcp_config = new_config.get("mcp_clients", {})
    app_config["mcp_clients"] = new_mcp_config

    existing_manager = mcp_client_service.get_current_mcp_client_manager()
    scoped = (
        server_name is not None
        and existing_manager is not None
        and new_mcp_config.get("enabled", False)
    )

    if scoped:
        manager = existing_manager
        entry = next(
            (
                s for s in (new_mcp_config.get("servers") or [])
                if isinstance(s, dict) and s.get("name") == server_name
            ),
            None,
        )
        await manager.update_server(server_name, entry)
        try:
            await manager.refresh_tool_cache([server_name])
        except Exception as exc:
            logger.warning("MCP tool discovery failed after reload: %s", exc)
    else:
        manager = mcp_client_service.reload_mcp_client_manager(app_config)
        if manager is not None:
            try:
                await manager.refresh_tool_cache()
            except Exception as exc:
                logger.warning("MCP tool discovery failed after reload: %s", exc)

    servers: Dict[str, Any] = {}
    if manager is not None:
        for name in manager._server_configs:
            servers[name] = {
                "reachable": name not in manager._failed_discovery_servers,
                "tool_count": len(manager._tools_cache.get(name, [])),
            }

    return {"enabled": manager is not None, "servers": servers}


@admin_router.post("/mcp/reload", dependencies=[config_auth])
async def reload_mcp_clients(request: Request):
    """Manually re-apply mcp_clients.yaml without restarting the server."""
    return await _reload_mcp_clients(request)


@admin_router.get("/mcp/tools", dependencies=[config_auth])
async def discover_mcp_tools(request: Request):
    """Re-dial every enabled MCP server and report reachability plus its tools.

    Uses the live MCPClientManager as-is — the PATCH endpoints already apply
    config changes to it immediately, so this only needs to force a fresh
    re-dial for current reachability, not reload config from disk (which
    would rebuild the manager and re-dial every server on every click). Use
    POST /mcp/reload to pick up out-of-band edits to mcp_clients.yaml.
    """
    from services.mcp_client_service import get_mcp_client_manager

    manager = get_mcp_client_manager(getattr(request.app.state, "config", {}) or {})
    if manager is None:
        return {
            "available": False,
            "reason": "MCP is disabled. Set mcp_clients.enabled: true.",
            "servers": {},
        }

    try:
        await manager.refresh_tool_cache()
    except Exception as exc:
        logger.warning("MCP tool discovery failed: %s", exc)

    servers: Dict[str, Any] = {}
    for name in manager._server_configs:
        tools = []
        for tool in manager._tools_cache.get(name, []):
            fn = tool.get("function", {})
            params = fn.get("parameters", {}) or {}
            required = params.get("required", []) or []
            tools.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "parameters": [
                    {
                        "name": pname,
                        "type": (pspec or {}).get("type", "string"),
                        "required": pname in required,
                        "description": (pspec or {}).get("description", ""),
                    }
                    for pname, pspec in (params.get("properties") or {}).items()
                ],
            })
        servers[name] = {
            "reachable": name not in manager._failed_discovery_servers,
            "tools": tools,
        }

    return {"available": True, "servers": servers}


def _last_key_line(lines: list, start: int, end: int, indent: str) -> int:
    """Index after the block's last real `key:` line at `indent`.

    A block's end can sit far past its last setting — the final server entry
    in mcp_clients.yaml runs to EOF, past ~240 lines of commented-out server
    templates. Appending at `end` would drop a new setting into the middle of
    that catalogue: still valid YAML, but orphaned from the server it
    configures. Insert against the last real key instead.
    """
    insert_at = start + 1
    for i in range(start + 1, min(end, len(lines))):
        stripped = lines[i].lstrip()
        if not stripped or stripped.startswith("#") or stripped.startswith("- "):
            continue
        if len(lines[i]) - len(stripped) != len(indent):
            continue
        insert_at = i + 1
    return insert_at


def _patch_yaml_scalars(lines: list, start: int, end: int, values: Dict[str, Any], indent: str) -> list:
    """Set or insert `key: value` scalar lines within lines[start:end].

    Keys mapped to None are removed, which is how an override reverts to
    inheriting the mcp_clients-level default.
    """
    for key, value in values.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif isinstance(value, (int, float)):
            rendered = str(value)
        else:
            # Strings (url, token) are quoted so ${VAR} references, colons, and
            # other YAML-significant characters can never be misparsed — json's
            # double-quote escaping is a valid subset of YAML's.
            rendered = json.dumps(str(value))

        found = -1
        for i in range(start, min(end, len(lines))):
            stripped = lines[i].lstrip()
            if stripped.startswith(key + ":") and len(lines[i]) - len(stripped) == len(indent):
                found = i
                break

        if value is None:
            if found >= 0:
                del lines[found]
                end -= 1
            continue

        if found >= 0:
            lines[found] = f"{indent}{key}: {rendered}"
        else:
            lines.insert(_last_key_line(lines, start, end, indent), f"{indent}{key}: {rendered}")
            end += 1
    return lines


def _find_block_header(lines: list, start: int, end: int, key: str, indent: str) -> tuple[int, int]:
    """Find a nested `key:` block within lines[start:end] at `indent`.

    Returns (header_index, body_end) where lines[header_index+1:body_end] is
    the block's body (deeper-indented subkey lines). (-1, -1) if not found.
    """
    header = -1
    for i in range(start, min(end, len(lines))):
        stripped = lines[i].lstrip()
        if stripped.startswith(key + ":") and len(lines[i]) - len(stripped) == len(indent):
            header = i
            break
    if header < 0:
        return -1, -1

    body_end = min(end, len(lines))
    for i in range(header + 1, min(end, len(lines))):
        stripped = lines[i].lstrip()
        if not stripped:
            # A blank line ends the map body — these config files use blank
            # lines as separators between entries, never inside one.
            body_end = i
            break
        if stripped.startswith("#"):
            continue
        if len(lines[i]) - len(stripped) <= len(indent):
            body_end = i
            break
    return header, body_end


def _patch_yaml_map(lines: list, start: int, end: int, key: str, target_map: Dict[str, str], indent: str) -> list:
    """Replace a nested `key:` block (env/headers) with `target_map` in full.

    `target_map` is the complete desired map, not a diff: any subkey
    currently in the block but absent from `target_map` is deleted, every
    entry in `target_map` is set. An empty `target_map` removes the block
    (including its header line) entirely.
    """
    sub_indent = indent + "  "
    header, body_end = _find_block_header(lines, start, end, key, indent)

    if header < 0:
        if not target_map:
            return lines
        insert_at = _last_key_line(lines, start, end, indent)
        new_lines = [f"{indent}{key}:"]
        for subkey, value in target_map.items():
            new_lines.append(f"{sub_indent}{subkey}: {json.dumps(str(value))}")
        lines[insert_at:insert_at] = new_lines
        return lines

    remaining = dict(target_map)
    i = header + 1
    while i < body_end:
        stripped = lines[i].lstrip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        matched_key = None
        for subkey in list(remaining):
            if stripped.startswith(subkey + ":") and len(lines[i]) - len(stripped) == len(sub_indent):
                matched_key = subkey
                break
        if matched_key is not None:
            lines[i] = f"{sub_indent}{matched_key}: {json.dumps(str(remaining.pop(matched_key)))}"
            i += 1
            continue
        # Subkey not present in target_map: drop the line.
        del lines[i]
        body_end -= 1

    for subkey, value in remaining.items():
        lines.insert(body_end, f"{sub_indent}{subkey}: {json.dumps(str(value))}")
        body_end += 1

    if body_end == header + 1:
        # Body is now empty: drop the header line too.
        del lines[header]

    return lines


def _patch_yaml_list(lines: list, start: int, end: int, key: str, values: Any, indent: str) -> list:
    """Rewrite a single-line `key: [...]` list (args) within lines[start:end].

    `values` of None deletes the line entirely; an explicit empty list is
    still written since it differs in meaning from "field untouched".
    """
    found = -1
    for i in range(start, min(end, len(lines))):
        stripped = lines[i].lstrip()
        if stripped.startswith(key + ":") and len(lines[i]) - len(stripped) == len(indent):
            found = i
            break

    if values is None:
        if found >= 0:
            del lines[found]
        return lines

    rendered = f"{indent}{key}: {json.dumps(list(values))}"
    if found >= 0:
        lines[found] = rendered
    else:
        lines.insert(_last_key_line(lines, start, end, indent), rendered)
    return lines


@admin_router.patch("/mcp/servers/{server_name}", dependencies=[config_auth])
async def update_mcp_server(server_name: str, request: Request, body: dict = Body(...)):
    """Update one server's enabled flag, setting overrides, and (for http/sse
    transports) its url/token connection fields.

    `settings` values of null delete the override so the server inherits the
    mcp_clients-level default again. `connection.token` of null clears the
    token; `connection.url` may not be null.
    """
    path, content, block = _read_mcp_config(request)
    overridable = _mcp_overridable()

    entry = next(
        (
            s for s in (block.get("servers") or [])
            if isinstance(s, dict) and s.get("name") == server_name
        ),
        None,
    )
    if entry is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_name}' not found")

    settings = body.get("settings") or {}
    _validate_mcp_settings(settings, overridable)

    connection = body.get("connection") or {}
    _validate_mcp_connection(entry, connection)

    lines = content.split("\n")
    start, end = _find_adapter_block(lines, server_name)
    if start < 0:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_name}' not found")

    name_line = lines[start]
    indent = " " * (len(name_line) - len(name_line.lstrip()) + 2)

    map_fields = {k: connection[k] for k in ("env", "headers") if k in connection}
    list_fields = {k: connection[k] for k in ("args",) if k in connection}
    scalar_connection = {k: v for k, v in connection.items() if k not in map_fields and k not in list_fields}

    values: Dict[str, Any] = dict(settings)
    values.update(scalar_connection)
    if "enabled" in body:
        values["enabled"] = bool(body["enabled"])

    lines = _patch_yaml_scalars(lines, start, end, values, indent)

    for map_key, target_map in map_fields.items():
        start, end = _find_adapter_block(lines, server_name)
        lines = _patch_yaml_map(lines, start, end, map_key, target_map or {}, indent)

    for list_key, list_values in list_fields.items():
        start, end = _find_adapter_block(lines, server_name)
        lines = _patch_yaml_list(lines, start, end, list_key, list_values, indent)

    new_content = "\n".join(lines)

    try:
        reparsed = yaml.safe_load(new_content) or {}
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Edit produced invalid YAML: {exc}")
    if not isinstance(reparsed.get("mcp_clients"), dict):
        raise HTTPException(status_code=422, detail="Edit would remove the mcp_clients section")

    _write_adapter_config(path, new_content)

    reload_summary, reload_error = None, None
    try:
        reload_summary = await _reload_mcp_clients(request, server_name=server_name)
    except Exception as exc:
        reload_error = str(exc)
        logger.error("MCP config saved but reload failed: %s", exc)

    message = (
        f"'{server_name}' saved and applied." if reload_error is None
        else f"'{server_name}' saved, but reload failed ({reload_error}). Restart to apply."
    )
    return {"message": message, "reload_summary": reload_summary, "reload_error": reload_error}


@admin_router.patch("/mcp/defaults", dependencies=[config_auth])
async def update_mcp_defaults(request: Request, body: dict = Body(...)):
    """Update the mcp_clients-level defaults and the global enabled gate."""
    path, content, block = _read_mcp_config(request)
    overridable = _mcp_overridable()

    settings = body.get("settings") or {}
    _validate_mcp_settings(settings, overridable)

    lines = content.split("\n")
    start = -1
    for i, line in enumerate(lines):
        if line.startswith("mcp_clients:"):
            start = i
            break
    if start < 0:
        raise HTTPException(status_code=404, detail="mcp_clients.yaml has no 'mcp_clients' section")

    # Defaults are the scalars between "mcp_clients:" and the "servers:" list.
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].lstrip().startswith("servers:"):
            end = i
            break

    values: Dict[str, Any] = dict(settings)
    if "enabled" in body:
        values["enabled"] = bool(body["enabled"])

    lines = _patch_yaml_scalars(lines, start + 1, end, values, "  ")
    new_content = "\n".join(lines)

    try:
        reparsed = yaml.safe_load(new_content) or {}
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Edit produced invalid YAML: {exc}")
    if not isinstance(reparsed.get("mcp_clients"), dict):
        raise HTTPException(status_code=422, detail="Edit would remove the mcp_clients section")

    _write_adapter_config(path, new_content)

    reload_summary, reload_error = None, None
    try:
        reload_summary = await _reload_mcp_clients(request)
    except Exception as exc:
        reload_error = str(exc)
        logger.error("MCP config saved but reload failed: %s", exc)

    message = (
        "Defaults saved and applied." if reload_error is None
        else f"Defaults saved, but reload failed ({reload_error}). Restart to apply."
    )
    return {"message": message, "reload_summary": reload_summary, "reload_error": reload_error}
