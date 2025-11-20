"""
Admin routes for ORBIT.

This module contains all admin-related endpoints including:
- API key management
- System prompt management
- Chat history management (inference-only mode)
"""

import json
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Request, Depends, HTTPException, Header, Query
from bson import ObjectId

from utils import is_true_value
from models.schema import (
    ApiKeyCreate, ApiKeyResponse, ApiKeyDeactivate,
    SystemPromptCreate, SystemPromptUpdate, SystemPromptResponse,
    ApiKeyPromptAssociate, ChatHistoryClearResponse, AdapterReloadResponse
)
from config.config_manager import reload_adapters_config

# Import auth dependencies
from routes.auth_dependencies import check_admin_or_api_key

# Initialize logger
logger = logging.getLogger(__name__)

# Create the admin router
admin_router = APIRouter(prefix="/admin", tags=["admin"])


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
                    except:
                        key_dict["created_at"] = None
                else:
                    key_dict["created_at"] = created_at

            # Handle system_prompt_id if it exists
            if key.get("system_prompt_id"):
                key_dict["system_prompt_id"] = str(key["system_prompt_id"])

            serialized_keys.append(key_dict)
        
        return serialized_keys
        
    except Exception as e:
        logger.error(f"Error listing API keys: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list API keys: {str(e)}")


@admin_router.get("/api-keys/{api_key}/status")
async def get_api_key_status(
    api_key: str, 
    request: Request,
    authorized: bool = Depends(admin_auth_check)
):
    """
    Get the status of a specific API key.
    
    This endpoint provides detailed status information for an API key:
    - Active/inactive status
    - Last used timestamp
    - Associated collection
    - System prompt association
    - Usage statistics
    
    Security considerations:
    - This is an admin-only endpoint
    - Should be protected by additional authentication
    - API key is masked in logs
    
    Args:
        api_key: The API key to check
        request: The incoming request
        
    Returns:
        Status information for the specified API key
        
    Raises:
        HTTPException: If API key status check fails or service is unavailable
    """
    # Check if API key service is available
    api_key_service = getattr(request.app.state, 'api_key_service', None)
    check_service_availability(api_key_service, "API key service")
    
    status = await api_key_service.get_api_key_status(api_key)
    
    # Log with masked API key
    masked_api_key = f"***{api_key[-4:]}" if api_key else "***"
    logger.debug(f"Checked status for API key: {masked_api_key}")
    
    return status


@admin_router.patch("/api-keys/{old_api_key}/rename")
async def rename_api_key(
    old_api_key: str,
    new_api_key: str,
    request: Request,
    authorized: bool = Depends(admin_auth_check)
):
    """
    Rename an API key by updating its value

    This endpoint allows administrators to rename an existing API key to a new value.
    The new key must not already exist in the system.

    Security considerations:
    - This is an admin-only endpoint
    - Should be protected by additional authentication
    - Both old and new keys are masked in logs

    Args:
        old_api_key: The current API key to rename
        new_api_key: The new API key value (as query parameter)
        request: The incoming request
        authorized: Authentication check result

    Returns:
        Success message with status

    Raises:
        HTTPException: If old key doesn't exist, new key already exists, or rename fails
    """
    # Check if API key service is available
    api_key_service = getattr(request.app.state, 'api_key_service', None)
    check_service_availability(api_key_service, "API key service")

    success = await api_key_service.rename_api_key(old_api_key, new_api_key)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to rename API key")

    # Log with masked API keys
    masked_old_key = f"***{old_api_key[-4:]}" if old_api_key else "***"
    masked_new_key = f"***{new_api_key[-4:]}" if new_api_key else "***"
    logger.info(f"Renamed API key from {masked_old_key} to {masked_new_key}")

    return {"status": "success", "message": f"API key renamed successfully", "new_api_key": new_api_key}


@admin_router.post("/api-keys/deactivate")
async def deactivate_api_key(
    data: ApiKeyDeactivate,
    api_key_service = Depends(get_api_key_service),
    authorized: bool = Depends(admin_auth_check)
):
    """
    Deactivate an API key

    This is an admin-only endpoint and should be properly secured in production.
    """
    # In production, add authentication middleware to restrict access to admin endpoints

    success = await api_key_service.deactivate_api_key(data.api_key)

    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    # Log with masked API key
    masked_api_key = f"***{data.api_key[-4:]}" if data.api_key else "***"
    logger.info(f"Deactivated API key: {masked_api_key}")

    return {"status": "success", "message": "API key deactivated"}


@admin_router.delete("/api-keys/{api_key}")
async def delete_api_key(
    api_key: str,
    api_key_service = Depends(get_api_key_service),
    authorized: bool = Depends(admin_auth_check)
):
    """
    Delete an API key
    
    This is an admin-only endpoint and should be properly secured in production.
    """
    # In production, add authentication middleware to restrict access to admin endpoints
    
    success = await api_key_service.delete_api_key(api_key)
    
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")
    
    # Log with masked API key
    masked_api_key = f"***{api_key[-4:]}" if api_key else "***"
    logger.info(f"Deleted API key: {masked_api_key}")
        
    return {"status": "success", "message": "API key deleted"}


@admin_router.get("/api-keys/info")
async def get_adapter_info(
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key")
):
    """
    Get adapter information for the current API key.

    This endpoint returns information about the adapter and model being used
    by the provided API key. This is useful for clients to display configuration
    details to users.

    The API key is read from the X-API-Key header (same as other endpoints).

    Returns:
        Dictionary containing:
            - client_name: Name of the client associated with this API key
            - adapter_name: Name of the adapter being used
            - model: Model name (from adapter config or global default)

    Raises:
        HTTPException: If API key is invalid, disabled, or adapter not found
    """
    # Get API key service
    api_key_service = getattr(request.app.state, 'api_key_service', None)
    check_service_availability(api_key_service, "API key service")

    # Get adapter manager to ensure we read live config (respects hot-reload)
    adapter_manager = getattr(request.app.state, 'adapter_manager', None)

    # Get adapter info - pass adapter_manager to get live config
    adapter_info = await api_key_service.get_adapter_info(x_api_key, adapter_manager)

    return adapter_info


@admin_router.post("/api-keys/{api_key}/prompt")
async def associate_prompt_with_api_key(
    api_key: str,
    data: ApiKeyPromptAssociate,
    api_key_service = Depends(get_api_key_service),
    authorized: bool = Depends(admin_auth_check)
):
    """Associate a system prompt with an API key"""
    success = await api_key_service.update_api_key_system_prompt(api_key, data.prompt_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="API key not found or prompt not associated")
    
    return {"status": "success", "message": "System prompt associated with API key"}


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
    limit: int = 50
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

    setattr(chat_history_service, 'api_key_service', api_key_service)

    result = await chat_history_service.clear_conversation_history(
        session_id=session_id,
        api_key=x_api_key
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
    config = getattr(request.app.state, 'config', {})

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
            if api_key_service:
                setattr(chat_history_service, 'api_key_service', api_key_service)

            result = await chat_history_service.clear_conversation_history(
                session_id=session_id,
                api_key=x_api_key
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
