"""
Admin routes for ORBIT.

This module contains all admin-related endpoints including:
- API key management
- System prompt management
- Chat history management (inference-only mode)
"""

import logging
import asyncio
import uuid
import yaml
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Request, Depends, HTTPException, Header, Query, Body
import markdown
import nh3

from utils import is_true_value
from models.schema import (
    ApiKeyCreate, ApiKeyResponse, ApiKeyUpdate,
    SystemPromptCreate, SystemPromptUpdate, SystemPromptResponse,
    ApiKeyPromptAssociate, ChatHistoryClearResponse, AdapterReloadResponse,
    TemplateReloadResponse, TemplateTestRequest, ApiKeyQuota, ApiKeyQuotaUpdate,
    ApiKeyUsage, ApiKeyQuotaResponse
)
from config.config_manager import reload_adapters_config

# Import auth dependencies
from routes.auth_dependencies import check_admin_or_api_key, require_admin

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


def check_service_availability(service, service_name: str):
    """Check if a service is available and raise error if not"""
    if service is None:
        raise HTTPException(
            status_code=503, 
            detail=f"{service_name} is not available"
        )


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


async def admin_auth_check(
    request: Request,
    authorized: bool = Depends(check_admin_or_api_key)
):
    """
    Check if the request is authorized via admin auth or API key.
    This allows backward compatibility with existing API key system.
    """
    return authorized


# API Key Management Routes
@admin_router.post("/api-keys", response_model=ApiKeyResponse)
async def create_api_key(
    api_key_data: ApiKeyCreate,
    request: Request,
    authorized: bool = Depends(admin_auth_check)
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
    masked_api_key = f"***{api_key_response['api_key'][-4:]}" if api_key_response.get('api_key') else "***"
    
    # Log creation with appropriate identifier
    if api_key_data.adapter_name:
        logger.info(f"Created API key for adapter '{api_key_data.adapter_name}': {masked_api_key}")
    else:
        logger.info(f"Created API key: {masked_api_key}")
    
    return api_key_response


@admin_router.get("/api-keys")
async def list_api_keys(
    request: Request,
    collection: Optional[str] = None,
    adapter: Optional[str] = None,
    active_only: bool = False,
    limit: int = 100,
    offset: int = 0,
    authorized: bool = Depends(admin_auth_check)
):
    """
    List all API keys in the system with optional filtering and pagination.
    
    This endpoint provides a list of all API keys with:
    - Masked key values
    - Adapter associations
    - Client information
    - Creation timestamps
    - Status information
    
    Security considerations:
    - This is an admin-only endpoint
    - Should be protected by additional authentication
    - API keys are masked in the response
    - Limited to 1000 keys per request
    
    Args:
        collection: Optional collection name filter (legacy support)
        adapter: Optional adapter name filter
        active_only: If True, only return active keys
        limit: Maximum number of keys to return (default: 100, max: 1000)
        offset: Number of keys to skip for pagination (default: 0)
        request: The incoming request
        
    Returns:
        List of API key records with masked values
        
    Raises:
        HTTPException: If API key listing fails or service is unavailable
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
        elif collection:
            # Legacy support for collection-based filtering
            filter_query["collection_name"] = collection
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
            # _id is already a string from the database service
            key_dict = {
                "_id": str(key["_id"]) if key.get("_id") else None,
                "api_key": f"***{key['api_key'][-4:]}" if key.get("api_key") else "***",
                "adapter_name": key.get("adapter_name"),
                "collection_name": key.get("collection_name"),  # Legacy support
                "client_name": key.get("client_name"),
                "notes": key.get("notes"),
                "active": key.get("active", True),
                "created_at": None
            }

            # Handle created_at timestamp (could be datetime object or ISO string from SQLite)
            created_at = key.get("created_at")
            if created_at:
                if hasattr(created_at, 'timestamp'):
                    # It's a datetime object (MongoDB)
                    key_dict["created_at"] = created_at.timestamp()
                elif isinstance(created_at, str):
                    # It's an ISO string (SQLite) - parse and convert to timestamp
                    from datetime import datetime
                    try:
                        dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        key_dict["created_at"] = dt.timestamp()
                    except Exception:
                        key_dict["created_at"] = None
                else:
                    key_dict["created_at"] = created_at

            # Handle system_prompt_id if it exists
            if key.get("system_prompt_id"):
                prompt_id = str(key["system_prompt_id"])
                key_dict["system_prompt_id"] = prompt_id
                key_dict["system_prompt_name"] = prompt_names.get(prompt_id)

            serialized_keys.append(key_dict)
        
        return serialized_keys
        
    except Exception as e:
        logger.error(f"Error listing API keys: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list API keys: {str(e)}")


@admin_router.get("/api-keys/{api_key_id}/detail")
async def get_api_key_detail(
    api_key_id: str,
    request: Request,
    authorized: bool = Depends(admin_auth_check)
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

        key_dict = {
            "_id": str(key["_id"]) if key.get("_id") else None,
            "api_key": key.get("api_key"),
            "adapter_name": key.get("adapter_name"),
            "collection_name": key.get("collection_name"),
            "client_name": key.get("client_name"),
            "notes": key.get("notes"),
            "active": key.get("active", True),
            "created_at": None,
        }

        created_at = key.get("created_at")
        if created_at:
            if hasattr(created_at, 'timestamp'):
                key_dict["created_at"] = created_at.timestamp()
            elif isinstance(created_at, str):
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    key_dict["created_at"] = dt.timestamp()
                except Exception:
                    key_dict["created_at"] = None
            else:
                key_dict["created_at"] = created_at

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
        raise HTTPException(status_code=500, detail=f"Failed to retrieve API key detail: {str(e)}")


@admin_router.get("/api-keys/{api_key_id}/status")
async def get_api_key_status(
    api_key_id: str,
    request: Request,
    authorized: bool = Depends(admin_auth_check)
):
    """
    Get the status of a specific API key.

    Accepts a record _id, raw API key value, or adapter name for
    backwards compatibility with client proxies.
    """
    api_key_service = getattr(request.app.state, 'api_key_service', None)
    check_service_availability(api_key_service, "API key service")

    # Try _id first, then raw key, then adapter name
    status = await api_key_service.get_api_key_status_by_id(api_key_id)
    if not status.get("exists"):
        status = await api_key_service.get_api_key_status(api_key_id)
    logger.debug(f"Checked status for API key identifier: {api_key_id}")
    return status


@admin_router.patch("/api-keys/{api_key_id}/rename")
async def rename_api_key(
    api_key_id: str,
    new_api_key: str = Query(..., min_length=8, description="New API key value"),
    request: Request = None,
    authorized: bool = Depends(admin_auth_check)
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

    masked_new = f"***{new_api_key[-4:]}" if new_api_key else "***"
    logger.info(f"Renamed API key {api_key_id} to {masked_new}")
    return {"status": "success", "message": "API key renamed successfully", "new_api_key_masked": masked_new}


@admin_router.put("/api-keys/{api_key_id}")
async def update_api_key(
    api_key_id: str,
    data: ApiKeyUpdate,
    request: Request,
    authorized: bool = Depends(admin_auth_check)
):
    """Update editable API key metadata by record ID."""
    api_key_service = getattr(request.app.state, 'api_key_service', None)
    check_service_availability(api_key_service, "API key service")

    adapter_manager = getattr(request.app.state, 'fault_tolerant_adapter_manager', None)
    if not adapter_manager:
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

    logger.info(f"Updated API key metadata for: {api_key_id}")
    return {"status": "success", "message": "API key updated successfully"}


@admin_router.post("/api-keys/{api_key_id}/deactivate")
async def deactivate_api_key(
    api_key_id: str,
    api_key_service = Depends(get_api_key_service),
    authorized: bool = Depends(admin_auth_check)
):
    """Deactivate an API key by record ID."""
    success = await api_key_service.deactivate_api_key_by_id(api_key_id)

    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    logger.info(f"Deactivated API key: {api_key_id}")
    return {"status": "success", "message": "API key deactivated"}


@admin_router.delete("/api-keys/{api_key_id}")
async def delete_api_key(
    api_key_id: str,
    api_key_service = Depends(get_api_key_service),
    authorized: bool = Depends(admin_auth_check)
):
    """Delete an API key by record ID."""
    success = await api_key_service.delete_api_key_by_id(api_key_id)

    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    logger.info(f"Deleted API key: {api_key_id}")
    return {"status": "success", "message": "API key deleted"}


async def _get_adapter_info_response(
    request: Request,
    x_api_key: str
):
    """
    Shared handler for adapter info endpoints.
    """
    api_key_service = getattr(request.app.state, 'api_key_service', None)
    check_service_availability(api_key_service, "API key service")

    adapter_manager = getattr(request.app.state, 'adapter_manager', None)
    adapter_info = await api_key_service.get_adapter_info(x_api_key, adapter_manager)
    return adapter_info


@admin_router.get("/api-keys/info")
async def get_adapter_info(
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key")
):
    """
    Get adapter information for the current API key.
    """
    return await _get_adapter_info_response(request, x_api_key)


@admin_router.get("/adapters/info")
async def get_adapter_info_alias(
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key")
):
    """
    Alias for adapter info endpoint used by middleware proxies to reduce API key exposure.
    """
    return await _get_adapter_info_response(request, x_api_key)


@admin_router.get("/adapters/capabilities")
async def get_adapter_capabilities(
    request: Request,
    authorized: bool = Depends(admin_auth_check)
):
    """Return adapter capability metadata relevant to admin operations."""
    adapter_manager = getattr(request.app.state, 'fault_tolerant_adapter_manager', None)
    if not adapter_manager:
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
                "supports_template_reload": bool(adapter_instance and hasattr(adapter_instance, 'reload_templates')),
            })

        return {"adapters": capabilities}
    except Exception as e:
        logger.error(f"Failed to get adapter capabilities: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get adapter capabilities: {str(e)}")


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


def _backup_and_write(file_path: Path, new_content: str) -> str:
    """Create .bak backup and write new content. Returns backup path string."""
    backup_path = file_path.with_suffix(".yaml.bak")
    shutil.copy2(file_path, backup_path)
    logger.info("Adapter config backup created at %s", backup_path)
    file_path.write_text(new_content, encoding="utf-8")
    logger.info("Adapter config updated: %s", file_path)
    from config.config_manager import load_config
    load_config.cache_clear()
    return str(backup_path.resolve())


@admin_router.get("/adapters/config")
async def list_adapter_configs(
    request: Request,
    authorized: bool = Depends(admin_auth_check)
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
                    })
        except Exception:
            pass  # File might have invalid YAML — show it anyway with empty adapters
        files.append(entry)

    return {"files": files, "imports": current_imports, "adapters_yaml": adapters_yaml_content}


@admin_router.get("/adapters/config/entry/{adapter_name}")
async def get_adapter_entry(
    adapter_name: str,
    request: Request,
    authorized: bool = Depends(admin_auth_check)
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


@admin_router.put("/adapters/config/entry/{adapter_name}")
async def save_adapter_entry(
    adapter_name: str,
    request: Request,
    authorized: bool = Depends(admin_auth_check),
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
    backup = _backup_and_write(file_path, new_content)
    return {
        "message": f"Adapter '{adapter_name}' saved. Use 'Reload Adapter' to apply changes.",
        "backup": backup,
    }


@admin_router.patch("/adapters/config/entry/{adapter_name}/toggle")
async def toggle_adapter_enabled(
    adapter_name: str,
    request: Request,
    authorized: bool = Depends(admin_auth_check),
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
    backup = _backup_and_write(file_path, new_content)

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
            reload_summary = await adapter_manager.reload_adapters(new_config, adapter_name)
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
        "backup": backup,
        "reload_summary": reload_summary,
        "reload_error": reload_error,
    }


@admin_router.get("/adapters/config/{filename}")
async def get_adapter_config_file(
    filename: str,
    request: Request,
    authorized: bool = Depends(admin_auth_check)
):
    """Read the raw YAML content of a specific adapter config file."""
    _validate_adapter_filename(filename)
    file_path = _get_adapters_dir(request) / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Adapter file not found: {filename}")
    content = file_path.read_text(encoding="utf-8")
    return {"content": content, "filename": filename}


@admin_router.put("/adapters/config/{filename}")
async def save_adapter_config_file(
    filename: str,
    request: Request,
    authorized: bool = Depends(admin_auth_check),
    body: dict = Body(...)
):
    """Validate, back up, and write an adapter config file."""
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

    backup = _backup_and_write(file_path, content)
    return {
        "message": f"Adapter config '{filename}' saved. Use 'Reload Adapter' to apply changes.",
        "backup": backup,
    }


@admin_router.post("/api-keys/{api_key_id}/prompt")
async def associate_prompt_with_api_key(
    api_key_id: str,
    data: ApiKeyPromptAssociate,
    api_key_service = Depends(get_api_key_service),
    authorized: bool = Depends(admin_auth_check)
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


@admin_router.get("/api-keys/{api_key_id}/quota", response_model=ApiKeyQuotaResponse)
async def get_api_key_quota(
    api_key_id: str,
    request: Request,
    authorized: bool = Depends(admin_auth_check)
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
    masked_key = f"***{api_key[-4:]}" if len(api_key) >= 4 else "***"

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


@admin_router.put("/api-keys/{api_key_id}/quota")
async def update_api_key_quota(
    api_key_id: str,
    quota_data: ApiKeyQuotaUpdate,
    request: Request,
    authorized: bool = Depends(admin_auth_check)
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


@admin_router.post("/api-keys/{api_key_id}/quota/reset")
async def reset_api_key_quota(
    api_key_id: str,
    request: Request,
    period: str = Query("daily", pattern="^(daily|monthly|all)$"),
    authorized: bool = Depends(admin_auth_check)
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


@admin_router.get("/quotas/usage-report")
async def get_quota_usage_report(
    request: Request,
    period: str = Query("daily", pattern="^(daily|monthly)$"),
    limit: int = Query(100, ge=1, le=1000),
    authorized: bool = Depends(admin_auth_check)
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
            masked_key = f"***{api_key[-4:]}" if len(api_key) >= 4 else "***"

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
        raise HTTPException(status_code=500, detail=f"Failed to generate usage report: {str(e)}")


# System Prompts Management Routes
@admin_router.post("/prompts", response_model=SystemPromptResponse)
async def create_prompt(
    prompt_data: SystemPromptCreate,
    request: Request,
    authorized: bool = Depends(admin_auth_check)
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
    
    prompt = await prompt_service.get_prompt_by_id(prompt_id)
    
    if not prompt:
        raise HTTPException(status_code=500, detail="Failed to retrieve created prompt")
        
    # Format the response according to the model
    return {
        "id": str(prompt_id),
        "name": prompt.get("name"),
        "prompt": prompt.get("prompt"),
        "version": prompt.get("version"),
        "created_at": prompt.get("created_at").timestamp() if prompt.get("created_at") else 0,
        "updated_at": prompt.get("updated_at").timestamp() if prompt.get("updated_at") else 0
    }


@admin_router.get("/prompts")
async def list_prompts(
    name_filter: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    prompt_service = Depends(get_prompt_service),
    authorized: bool = Depends(admin_auth_check)
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


@admin_router.get("/prompts/{prompt_id}")
async def get_prompt(
    prompt_id: str,
    prompt_service = Depends(get_prompt_service),
    authorized: bool = Depends(admin_auth_check)
):
    """Get a system prompt by ID"""
    prompt = await prompt_service.get_prompt_by_id(prompt_id)
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
        
    # Convert ObjectId to string and datetime to timestamp
    prompt["_id"] = str(prompt["_id"])
    if "created_at" in prompt:
        prompt["created_at"] = prompt["created_at"].timestamp()
    if "updated_at" in prompt:
        prompt["updated_at"] = prompt["updated_at"].timestamp()
        
    return prompt


@admin_router.post("/render-markdown")
def render_markdown_preview(
    payload: dict = Body(...),
    authorized: bool = Depends(admin_auth_check)
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


@admin_router.put("/prompts/{prompt_id}", response_model=SystemPromptResponse)
async def update_prompt(
    prompt_id: str,
    prompt_data: SystemPromptUpdate,
    prompt_service = Depends(get_prompt_service),
    authorized: bool = Depends(admin_auth_check)
):
    """Update a system prompt"""
    success = await prompt_service.update_prompt(
        prompt_id,
        prompt_data.prompt,
        prompt_data.version
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Prompt not found or not updated")
        
    prompt = await prompt_service.get_prompt_by_id(prompt_id)
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Failed to retrieve updated prompt")
        
    # Format the response according to the model
    return {
        "id": str(prompt_id),
        "name": prompt.get("name"),
        "prompt": prompt.get("prompt"),
        "version": prompt.get("version"),
        "created_at": prompt.get("created_at").timestamp() if prompt.get("created_at") else 0,
        "updated_at": prompt.get("updated_at").timestamp() if prompt.get("updated_at") else 0
    }


@admin_router.delete("/prompts/{prompt_id}")
async def delete_prompt(
    prompt_id: str,
    prompt_service = Depends(get_prompt_service),
    authorized: bool = Depends(admin_auth_check)
):
    """Delete a system prompt"""
    success = await prompt_service.delete_prompt(prompt_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Prompt not found")
        
    return {"status": "success", "message": "Prompt deleted"}


# Chat History Management (only available in inference-only mode)
@admin_router.get("/chat-history/{session_id}")
async def get_chat_history(
    session_id: str,
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    authorized: bool = Depends(admin_auth_check)
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


@admin_router.delete("/chat-history/{session_id}", response_model=ChatHistoryClearResponse)
async def clear_chat_history(
    session_id: str,
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Clear chat history for a specific session."""
    config = getattr(request.app.state, 'config', {})
    chat_history_service = getattr(request.app.state, 'chat_history_service', None)

    # Determine if conversational adapters are active
    adapters_config = config.get('adapters', [])
    conversational_adapter_enabled = any(
        isinstance(adapter, dict)
        and adapter.get('adapter') == 'conversational'
        and is_true_value(adapter.get('enabled', True))
        for adapter in adapters_config
    )

    if not conversational_adapter_enabled:
        raise HTTPException(
            status_code=503,
            detail="Chat history management is only available with an active conversational adapter"
        )

    if not chat_history_service:
        raise HTTPException(status_code=503, detail="Chat history service is not available")

    if x_session_id and x_session_id != session_id:
        raise HTTPException(
            status_code=400,
            detail="Session ID in header does not match URL parameter"
        )

    if not x_api_key:
        raise HTTPException(
            status_code=400,
            detail="API key is required for clearing conversation history"
        )

    api_key_service = getattr(request.app.state, 'api_key_service', None)
    if not api_key_service:
        raise HTTPException(status_code=503, detail="API key service is not available")

    result = await chat_history_service.clear_conversation_history(
        session_id=session_id,
        api_key=x_api_key,
        api_key_service=api_key_service
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear conversation history: {result.get('error', 'Unknown error')}"
        )

    logger.debug(
        "Cleared conversation history for session %s: %s messages",
        session_id,
        result.get("deleted_count", 0)
    )

    return ChatHistoryClearResponse(
        status="success",
        message=f"Cleared {result['deleted_count']} messages from session {session_id}",
        session_id=session_id,
        deleted_count=result['deleted_count'],
        timestamp=result['timestamp']
    )


# Adapter Hot Reload
@admin_router.post("/reload-adapters", response_model=AdapterReloadResponse)
async def reload_adapters(
    request: Request,
    adapter_name: Optional[str] = Query(None, description="Optional name of specific adapter to reload"),
    authorized: bool = Depends(admin_auth_check)
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
        summary = await adapter_manager.reload_adapters(new_config, adapter_name)

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
        raise HTTPException(
            status_code=500,
            detail=f"Config file not found: {str(e)}"
        )
    except ValueError as e:
        logger.error(f"Adapter reload error: {str(e)}")
        raise HTTPException(
            status_code=404,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error during adapter reload: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload adapters: {str(e)}"
        )


@admin_router.post("/reload-adapters/async")
async def reload_adapters_async(
    request: Request,
    adapter_name: Optional[str] = Query(None, description="Optional name of specific adapter to reload"),
    authorized: bool = Depends(admin_auth_check)
):
    """Start adapter reload as a background admin job."""
    job = _create_admin_job(request, "reload_adapters", adapter_name)

    async def run_job():
        _update_admin_job(request, job["job_id"], status="running", message="Reloading adapters")
        try:
            result = await reload_adapters(request=request, adapter_name=adapter_name, authorized=authorized)
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
@admin_router.post("/reload-templates", response_model=TemplateReloadResponse)
async def reload_templates(
    request: Request,
    adapter_name: Optional[str] = Query(None, description="Optional name of specific adapter to reload templates for"),
    authorized: bool = Depends(admin_auth_check)
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
        raise HTTPException(
            status_code=404,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error during template reload: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload templates: {str(e)}"
        )


@admin_router.post("/reload-templates/async")
async def reload_templates_async(
    request: Request,
    adapter_name: Optional[str] = Query(None, description="Optional name of specific adapter to reload templates for"),
    authorized: bool = Depends(admin_auth_check)
):
    """Start template reload as a background admin job."""
    job = _create_admin_job(request, "reload_templates", adapter_name)

    async def run_job():
        _update_admin_job(request, job["job_id"], status="running", message="Reloading templates")
        try:
            result = await reload_templates(request=request, adapter_name=adapter_name, authorized=authorized)
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


@admin_router.post("/adapters/{adapter_name}/test-query")
async def test_adapter_query(
    adapter_name: str,
    body: TemplateTestRequest,
    request: Request,
    admin_user: dict = Depends(require_admin)
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
        raise HTTPException(status_code=500, detail=f"Test query failed: {e}")


@admin_router.get("/jobs/{job_id}")
async def get_admin_job_status(
    job_id: str,
    request: Request,
    authorized: bool = Depends(admin_auth_check)
):
    """Get status for an async admin job."""
    jobs = _get_admin_jobs(request)
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Admin job not found")
    return job


@admin_router.delete("/conversations/{session_id}")
async def delete_conversation_with_files(
    session_id: str,
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    file_ids: str = Query(default="", description="Comma-separated list of file IDs to delete")
):
    """
    Delete a conversation and all associated files.

    This endpoint performs a complete conversation deletion:
    1. Deletes each file provided in file_ids (metadata, content, and vector store chunks)
    2. Clears conversation history

    File tracking is managed by the frontend (localStorage). The backend is stateless
    and requires file_ids to be provided explicitly.

    Args:
        session_id: The session identifier for the conversation
        file_ids: Comma-separated list of file IDs to delete (from frontend)
        x_api_key: API key for authentication
        x_session_id: Optional session ID header (must match URL parameter)

    Returns:
        Status message with deletion details

    Raises:
        HTTPException: If deletion fails or services unavailable
    """
    getattr(request.app.state, 'config', {})

    # Validate session ID consistency
    if x_session_id and x_session_id != session_id:
        raise HTTPException(
            status_code=400,
            detail="Session ID in header does not match URL parameter"
        )

    if not x_api_key:
        raise HTTPException(
            status_code=400,
            detail="API key is required for deleting conversation"
        )

    # Get required services
    chat_history_service = getattr(request.app.state, 'chat_history_service', None)
    file_processing_service = getattr(request.app.state, 'file_processing_service', None)

    # Parse file_ids from query parameter
    file_ids_list = [fid.strip() for fid in file_ids.split(',') if fid.strip()] if file_ids else []

    # Track deletion results
    deleted_files_count = 0
    deleted_messages_count = 0
    file_deletion_errors = []

    # Step 1: Delete provided files
    if file_ids_list and file_processing_service:
        logger.debug(f"Deleting {len(file_ids_list)} file(s) for session {session_id}")

        for file_id in file_ids_list:
            try:
                # Delete file (includes metadata, content, and vector chunks)
                success = await file_processing_service.delete_file(file_id, x_api_key)
                if success:
                    deleted_files_count += 1
                    logger.debug(f"Deleted file {file_id}")
                else:
                    file_deletion_errors.append(file_id)
                    logger.warning(f"Failed to delete file {file_id}")
            except Exception as e:
                logger.error(f"Error deleting file {file_id}: {e}")
                file_deletion_errors.append(file_id)

    # Step 2: Clear conversation history
    if chat_history_service:
        try:
            api_key_service = getattr(request.app.state, 'api_key_service', None)
            result = await chat_history_service.clear_conversation_history(
                session_id=session_id,
                api_key=x_api_key,
                api_key_service=api_key_service
            )

            if result.get("success"):
                deleted_messages_count = result.get("deleted_count", 0)
                logger.debug(f"Cleared {deleted_messages_count} messages for session {session_id}")
            else:
                logger.warning(f"Failed to clear conversation history: {result.get('error')}")
        except Exception as e:
            logger.error(f"Error clearing conversation history: {e}")
            # Don't fail the entire request if only history clearing fails

    # Build response message
    message_parts = []
    if deleted_messages_count > 0:
        message_parts.append(f"{deleted_messages_count} message(s)")
    if deleted_files_count > 0:
        message_parts.append(f"{deleted_files_count} file(s)")

    message = f"Deleted conversation: {', '.join(message_parts) if message_parts else 'no data found'}"

    return {
        "status": "success",
        "message": message,
        "session_id": session_id,
        "deleted_messages": deleted_messages_count,
        "deleted_files": deleted_files_count,
        "file_deletion_errors": file_deletion_errors if file_deletion_errors else None,
        "timestamp": datetime.now().isoformat()
    }


@admin_router.get("/info")
async def get_server_info(
    request: Request,
    authorized: bool = Depends(admin_auth_check)
):
    """
    Get server information including PID and status.
    
    This endpoint provides information about the running server instance,
    including process ID for process management.
    
    Returns:
        Dictionary containing server information (PID, version, etc.)
    """
    import os
    
    return {
        "pid": os.getpid(),
        "version": "2.6.5",
        "status": "running"
    }


@admin_router.get("/config")
async def get_config(
    request: Request,
    authorized: bool = Depends(admin_auth_check)
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


@admin_router.put("/config")
async def update_config(
    request: Request,
    authorized: bool = Depends(admin_auth_check),
    body: dict = Body(...)
):
    """
    Validate, back up, and write new config.yaml content.

    Accepts {"content": "<yaml string>"}. Validates YAML syntax,
    creates a .bak backup, then writes the new content. A server
    restart is required for most changes to take effect.
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

    # Back up current file
    backup_path = config_path.with_suffix('.yaml.bak')
    shutil.copy2(config_path, backup_path)
    logger.info("Config backup created at %s", backup_path)

    # Write new content
    config_path.write_text(content, encoding='utf-8')
    logger.info("Config file updated at %s", config_path)

    # Clear load_config LRU cache so next access picks up changes
    from config.config_manager import load_config
    load_config.cache_clear()

    return {
        "message": "Config saved. A server restart is required for changes to take effect.",
        "backup": str(backup_path.resolve())
    }


@admin_router.post("/shutdown")
async def shutdown_server(
    request: Request,
    authorized: bool = Depends(admin_auth_check)
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
        # Try to get the uvicorn server instance
        # The server is stored in the app's lifespan context
        # We'll use signal-based shutdown as a reliable method
        import os
        # Send SIGTERM to current process for graceful shutdown
        os.kill(os.getpid(), signal.SIGTERM)
    
    # Schedule the shutdown
    asyncio.create_task(shutdown_background())
    
    return {
        "status": "success",
        "message": "Server shutdown initiated",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


@admin_router.post("/restart")
async def restart_server(
    request: Request,
    authorized: bool = Depends(admin_auth_check)
):
    """
    Restart the server process in place.

    This endpoint re-execs the current Python process after a short delay so
    the HTTP response can be sent back to the admin UI first.
    """
    import asyncio
    import os
    import sys

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


@admin_router.get("/logs/tail")
def tail_log_file(
    request: Request,
    lines: int = Query(200, ge=10, le=500),
    authorized: bool = Depends(admin_auth_check)
):
    """
    Return the most recently updated ORBIT log file contents.
    """
    config = request.app.state.config or {}
    file_config = config.get("logging", {}).get("handlers", {}).get("file", {})
    log_dir = Path(file_config.get("directory", "logs"))
    base_filename = file_config.get("filename", "orbit.log")
    log_prefix = base_filename + "*"

    candidates = sorted(
        [path for path in log_dir.glob(log_prefix) if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not candidates:
        raise HTTPException(status_code=404, detail="No log files found")

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

@admin_router.get("/audit/events")
async def list_admin_audit_events(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    event_type: Optional[str] = Query(None),
    event_prefix: Optional[str] = Query(None, description="Match event_type that starts with this prefix (e.g. 'auth.', 'admin.api_key.')"),
    actor_id: Optional[str] = Query(None),
    success: Optional[bool] = Query(None),
    resource_type: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Free-text search across actor_username, path, resource_id, ip"),
    since: Optional[str] = Query(None, description="ISO timestamp (inclusive lower bound)"),
    until: Optional[str] = Query(None, description="ISO timestamp (exclusive upper bound)"),
    authorized: bool = Depends(admin_auth_check),
):
    """
    List admin/auth audit events, most recent first.

    Server-side filters: `event_type` / `actor_id` / `success` / `resource_type`
    go through the underlying strategy's dict-filter. `event_prefix`, `q`,
    `since`, and `until` are applied in Python after the fetch — the current
    storage strategies don't support range/regex queries natively. To keep
    post-filtering bounded, each oversample fetches up to `limit * 10` rows
    (capped) and then slices to the requested page.
    """
    audit_service = getattr(request.app.state, "audit_service", None)
    if audit_service is None or not audit_service.admin_events_enabled:
        raise HTTPException(
            status_code=503,
            detail="Admin audit is not enabled. Set internal_services.audit.admin_events.enabled: true.",
        )

    native_filters: dict = {}
    if event_type is not None:
        native_filters["event_type"] = event_type
    if actor_id is not None:
        native_filters["actor_id"] = actor_id
    if success is not None:
        native_filters["success"] = success
    if resource_type is not None:
        native_filters["resource_type"] = resource_type

    needs_post_filter = any(v is not None for v in (event_prefix, q, since, until))
    fetch_limit = min(limit * 10, 5000) if needs_post_filter else limit
    fetch_offset = 0 if needs_post_filter else offset

    try:
        rows = await audit_service.query_admin_events(
            filters=native_filters,
            limit=fetch_limit,
            offset=fetch_offset,
            sort_by="timestamp",
            sort_order=-1,
        )
    except Exception as exc:
        logger.error(f"Failed to query admin audit events: {exc}")
        raise HTTPException(status_code=500, detail="Failed to query audit events")

    if needs_post_filter:
        q_lower = q.lower() if q else None
        prefix = event_prefix
        since_val = since
        until_val = until

        def keep(row: dict) -> bool:
            if prefix and not str(row.get("event_type", "")).startswith(prefix):
                return False
            if since_val and str(row.get("timestamp", "")) < since_val:
                return False
            if until_val and str(row.get("timestamp", "")) >= until_val:
                return False
            if q_lower:
                hay = " ".join(
                    str(row.get(field, "") or "")
                    for field in ("actor_username", "actor_id", "path", "resource_id", "ip", "event_type")
                ).lower()
                if q_lower not in hay:
                    return False
            return True

        filtered = [r for r in rows if keep(r)]
        total_after_filter = len(filtered)
        page = filtered[offset : offset + limit]
    else:
        page = rows
        total_after_filter = None  # unknown without a second count query

    return {
        "events": page,
        "limit": limit,
        "offset": offset,
        "returned": len(page),
        # `total` is an approximation when post-filtering is active (only counts
        # what was fetched in the oversample window); null otherwise.
        "total": total_after_filter,
    }
