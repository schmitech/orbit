"""
Admin routes for the Open Inference Server.

This module contains all admin-related endpoints including:
- API key management
- System prompt management
- Chat history management (inference-only mode)
"""

import json
import logging
from typing import Optional
from fastapi import APIRouter, Request, Depends, HTTPException
from bson import ObjectId

from config.config_manager import _is_true_value
from models.schema import (
    ApiKeyCreate, ApiKeyResponse, ApiKeyDeactivate, 
    SystemPromptCreate, SystemPromptUpdate, SystemPromptResponse, 
    ApiKeyPromptAssociate
)

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


def check_inference_only_mode(request: Request, feature_name: str):
    """Check if we're in inference-only mode and raise error if feature is not available"""
    inference_only = _is_true_value(request.app.state.config.get('general', {}).get('inference_only', False))
    auth_enabled = _is_true_value(request.app.state.config.get('auth', {}).get('enabled', False))
    
    # If we're in inference-only mode but auth is disabled, allow API key management
    if inference_only and not auth_enabled and "API key" in feature_name:
        logger.info(f"Allowing {feature_name} in inference-only mode because authentication is disabled")
        return
    
    if inference_only:
        raise HTTPException(
            status_code=503, 
            detail=f"{feature_name} is not available in inference-only mode"
        )


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
    check_inference_only_mode(request, "API key management")
    
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
    check_inference_only_mode(request, "API key management")
    
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
        
        # Retrieve API keys with filtering and pagination
        cursor = api_key_service.api_keys_collection.find(filter_query).skip(offset).limit(limit)
        api_keys = await cursor.to_list(length=limit)
        
        # Convert MongoDB documents to JSON-serializable format
        serialized_keys = []
        for key in api_keys:
            # Convert _id to string
            key_dict = {
                "_id": str(key["_id"]),
                "api_key": f"***{key['api_key'][-4:]}" if key.get("api_key") else "***",
                "adapter_name": key.get("adapter_name"),
                "collection_name": key.get("collection_name"),  # Legacy support
                "client_name": key.get("client_name"),
                "notes": key.get("notes"),
                "active": key.get("active", True),
                "created_at": key.get("created_at").timestamp() if key.get("created_at") else None
            }
            
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
    check_inference_only_mode(request, "API key management")
    
    # Check if API key service is available
    api_key_service = getattr(request.app.state, 'api_key_service', None)
    check_service_availability(api_key_service, "API key service")
    
    status = await api_key_service.get_api_key_status(api_key)
    
    # Log with masked API key
    masked_api_key = f"***{api_key[-4:]}" if api_key else "***"
    logger.info(f"Checked status for API key: {masked_api_key}")
    
    return status


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
    check_inference_only_mode(request, "Prompt management")
    
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
    # Check if inference_only is enabled (this feature is only available in inference-only mode)
    inference_only = _is_true_value(request.app.state.config.get('general', {}).get('inference_only', False))
    if not inference_only:
        raise HTTPException(
            status_code=503, 
            detail="Chat history is only available in inference-only mode"
        )
    
    chat_history_service = getattr(request.app.state, 'chat_history_service', None)
    if not chat_history_service:
        raise HTTPException(status_code=503, detail="Chat history service is not available")
    
    history = await chat_history_service.get_conversation_history(
        session_id=session_id,
        limit=limit,
        include_metadata=True
    )
    
    return {"session_id": session_id, "messages": history, "count": len(history)}