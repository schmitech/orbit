"""
Discovery routes for ORBIT.

Client-facing endpoints that do not require admin authentication.
These are called by client proxies and the orbitchat UI using an X-API-Key header
(or no auth for fully public endpoints).

Includes:
- Adapter / model / skill discovery
- Conversation and chat-history management (API-key-authenticated, not admin-gated)
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request

from models.schema import (
    AdapterSkillsResponse,
    ChatHistoryClearResponse,
    SkillInfo,
    SkillsResponse,
)
from utils import is_true_value

logger = logging.getLogger(__name__)

discovery_router = APIRouter(prefix="/admin", tags=["discovery"])


def _check_service(service, name: str):
    if service is None:
        raise HTTPException(status_code=503, detail=f"{name} is not available")


# ---------------------------------------------------------------------------
# Adapter info (API-key-authenticated, used by client proxies)
# ---------------------------------------------------------------------------

async def _get_adapter_info_response(request: Request, x_api_key: str):
    api_key_service = getattr(request.app.state, 'api_key_service', None)
    _check_service(api_key_service, "API key service")
    adapter_manager = getattr(request.app.state, 'adapter_manager', None)
    return await api_key_service.get_adapter_info(x_api_key, adapter_manager)


@discovery_router.get("/api-keys/info")
async def get_adapter_info(
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key")
):
    """Get adapter information for the current API key."""
    return await _get_adapter_info_response(request, x_api_key)


@discovery_router.get("/adapters/info")
async def get_adapter_info_alias(
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key")
):
    """Alias for adapter info endpoint used by middleware proxies to reduce API key exposure."""
    return await _get_adapter_info_response(request, x_api_key)


# ---------------------------------------------------------------------------
# Model discovery
# ---------------------------------------------------------------------------

@discovery_router.get("/models")
async def list_available_models(
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key")
):
    """
    List all inference models available in the system.

    Requires a valid API key (X-API-Key header). No admin credentials needed.

    Derives the list from enabled providers in config/inference.yaml.
    Each enabled provider contributes its configured default model. Ollama
    presets are included as additional entries.

    Returns a flat list that clients can use to populate a model picker.
    """
    config = getattr(request.app.state, 'config', {})
    inference_cfg = config.get('inference', {})

    models = []
    for provider_name, provider_cfg in inference_cfg.items():
        if not isinstance(provider_cfg, dict):
            continue
        if not provider_cfg.get('enabled', False):
            continue
        model_name = provider_cfg.get('model') or provider_cfg.get('use_preset')
        if not model_name:
            continue
        safe_model = model_name.replace('/', '-').replace(':', '-')
        models.append({
            "name": f"{provider_name}-{safe_model}",
            "provider": provider_name,
            "model": model_name,
        })

    for preset_name, preset_cfg in config.get('ollama_presets', {}).items():
        if not isinstance(preset_cfg, dict):
            continue
        preset_model = preset_cfg.get('model', preset_name)
        models.append({
            "name": f"ollama-{preset_name}",
            "provider": "ollama",
            "model": preset_model,
            "preset": preset_name,
        })

    for preset_name, preset_cfg in config.get('llama_cpp_presets', {}).items():
        if not isinstance(preset_cfg, dict):
            continue
        preset_model = preset_cfg.get('model_path', preset_name)
        models.append({
            "name": f"llama_cpp-{preset_name}",
            "provider": "llama_cpp",
            "model": preset_model,
            "preset": preset_name,
        })

    return {"models": models}


@discovery_router.get("/adapters/{adapter_name}/models")
async def list_adapter_models(
    adapter_name: str,
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key")
):
    """
    List models available for a specific adapter.

    Requires a valid API key (X-API-Key header). No admin credentials needed.

    If the adapter defines an 'allowed_models' list in its config, that list
    is returned and 'has_restrictions' is true.

    If no 'allowed_models' are defined, the adapter's single default model
    (inference_provider + model) is returned and 'has_restrictions' is false.

    Clients can use this endpoint to build a per-adapter model picker.
    """
    adapter_manager = getattr(request.app.state, 'fault_tolerant_adapter_manager', None)
    if not adapter_manager:
        adapter_manager = getattr(request.app.state, 'adapter_manager', None)
    if not adapter_manager:
        raise HTTPException(status_code=503, detail="Adapter manager is not available")

    resolved_name = adapter_name
    api_key_service = getattr(request.app.state, 'api_key_service', None)
    if api_key_service and x_api_key:
        try:
            is_valid, key_adapter_name, _ = await api_key_service.validate_api_key(x_api_key, adapter_manager)
            if is_valid and key_adapter_name:
                resolved_name = key_adapter_name
        except Exception:
            pass

    adapter_config = adapter_manager.get_adapter_config(resolved_name) if hasattr(adapter_manager, 'get_adapter_config') else None
    if adapter_config is None:
        raise HTTPException(status_code=404, detail=f"Adapter '{resolved_name}' not found")

    allowed = adapter_config.get('allowed_models') or []

    if allowed:
        models = [
            {"name": m.get('name', ''), "provider": m.get('provider', ''), "model": m.get('model', '')}
            for m in allowed
            if m.get('name') and m.get('provider') and m.get('model')
        ]
        return {
            "adapter_name": resolved_name,
            "has_restrictions": True,
            "models": models,
        }

    inference_provider = adapter_config.get('inference_provider')
    config = getattr(request.app.state, 'config', {})
    default_provider = config.get('general', {}).get('inference_provider', 'default')
    provider = inference_provider or default_provider
    model = adapter_config.get('model', '')

    if not model:
        inference_cfg = config.get('inference', {}).get(provider, {})
        model = inference_cfg.get('model', '')

    safe_model = model.replace('/', '-').replace(':', '-') if model else ''
    default_entry = {
        "name": f"{provider}-{safe_model}" if safe_model else provider,
        "provider": provider,
        "model": model,
    }

    return {
        "adapter_name": resolved_name,
        "has_restrictions": False,
        "models": [default_entry] if model else [],
    }


# ---------------------------------------------------------------------------
# Skills discovery
# ---------------------------------------------------------------------------

@discovery_router.get("/skills", response_model=SkillsResponse)
async def list_skills(request: Request):
    """
    List all skills registered in ORBIT.

    A skill is an adapter marked with expose_as_skill: true in its config.
    Returns name, description, adapter_name, and enabled state for each skill.
    """
    adapter_manager = getattr(request.app.state, 'fault_tolerant_adapter_manager', None)
    if not adapter_manager:
        adapter_manager = getattr(request.app.state, 'adapter_manager', None)
    if not adapter_manager:
        raise HTTPException(status_code=503, detail="Adapter manager is not available")

    raw_skills = (
        adapter_manager.get_all_skills()
        if hasattr(adapter_manager, 'get_all_skills')
        else []
    )
    logger.debug("Skills list requested: %s registered skill(s)", len(raw_skills))
    return SkillsResponse(skills=[SkillInfo(**s) for s in raw_skills])


@discovery_router.get("/adapters/{adapter_name}/skills", response_model=AdapterSkillsResponse)
async def list_adapter_skills(
    adapter_name: str,
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """
    List skills available to a specific adapter.

    Returns the available_skills list from the adapter's capabilities config.
    Requires a valid API key (X-API-Key header).
    """
    adapter_manager = getattr(request.app.state, 'fault_tolerant_adapter_manager', None)
    if not adapter_manager:
        adapter_manager = getattr(request.app.state, 'adapter_manager', None)
    if not adapter_manager:
        raise HTTPException(status_code=503, detail="Adapter manager is not available")

    resolved_name = adapter_name
    api_key_service = getattr(request.app.state, 'api_key_service', None)
    if api_key_service and x_api_key:
        try:
            is_valid, key_adapter_name, _ = await api_key_service.validate_api_key(x_api_key, adapter_manager)
            if is_valid and key_adapter_name:
                resolved_name = key_adapter_name
        except Exception:
            logger.debug("Adapter skills lookup failed API key validation for '%s'", adapter_name, exc_info=True)

    adapter_config = adapter_manager.get_adapter_config(resolved_name) if hasattr(adapter_manager, 'get_adapter_config') else None
    if adapter_config is None:
        logger.warning("Adapter skills requested for unknown adapter '%s' (resolved from '%s')", resolved_name, adapter_name)
        raise HTTPException(status_code=404, detail=f"Adapter '{resolved_name}' not found")

    available_skills = adapter_config.get('capabilities', {}).get('available_skills', [])
    logger.debug(
        "Adapter skills requested: requested='%s', resolved='%s', available_skills=%s",
        adapter_name,
        resolved_name,
        available_skills,
    )
    return AdapterSkillsResponse(adapter_name=resolved_name, available_skills=available_skills)


# ---------------------------------------------------------------------------
# Conversation management (X-API-Key authenticated, not admin-gated)
# ---------------------------------------------------------------------------

@discovery_router.delete("/chat-history/{session_id}", response_model=ChatHistoryClearResponse)
async def clear_chat_history(
    session_id: str,
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """Clear chat history for a specific session."""
    config = getattr(request.app.state, 'config', {})
    chat_history_service = getattr(request.app.state, 'chat_history_service', None)

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


@discovery_router.delete("/conversations/{session_id}")
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
    """
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

    chat_history_service = getattr(request.app.state, 'chat_history_service', None)
    file_processing_service = getattr(request.app.state, 'file_processing_service', None)

    file_ids_list = [fid.strip() for fid in file_ids.split(',') if fid.strip()] if file_ids else []

    deleted_files_count = 0
    deleted_messages_count = 0
    file_deletion_errors = []

    if file_processing_service:
        # Merge explicit file IDs from the request with any generated images tracked server-side.
        # Server-side lookup handles images the frontend couldn't collect (old sessions, multiple
        # images where only the latest imageUrl was stored, etc.).
        generated_ids = await file_processing_service.get_generated_file_ids_for_session(
            session_id, x_api_key
        )
        all_file_ids = list(dict.fromkeys(file_ids_list + generated_ids))  # deduplicate, preserve order

        if all_file_ids:
            logger.debug("Deleting %s file(s) for session %s", len(all_file_ids), session_id)
        for file_id in all_file_ids:
            try:
                success = await file_processing_service.delete_file(file_id, x_api_key)
                if success:
                    deleted_files_count += 1
                    logger.debug("Deleted file %s", file_id)
                else:
                    file_deletion_errors.append(file_id)
                    logger.warning("Failed to delete file %s", file_id)
            except Exception as e:
                logger.error("Error deleting file %s: %s", file_id, e)
                file_deletion_errors.append(file_id)

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
                logger.debug("Cleared %s messages for session %s", deleted_messages_count, session_id)
            else:
                logger.warning("Failed to clear conversation history: %s", result.get('error'))
        except Exception as e:
            logger.error("Error clearing conversation history: %s", e)

    message_parts = []
    if deleted_messages_count > 0:
        message_parts.append(f"{deleted_messages_count} message(s)")
    if deleted_files_count > 0:
        message_parts.append(f"{deleted_files_count} file(s)")

    return {
        "status": "success",
        "message": f"Deleted conversation: {', '.join(message_parts) if message_parts else 'no data found'}",
        "session_id": session_id,
        "deleted_messages": deleted_messages_count,
        "deleted_files": deleted_files_count,
        "file_deletion_errors": file_deletion_errors if file_deletion_errors else None,
        "timestamp": datetime.now().isoformat()
    }
