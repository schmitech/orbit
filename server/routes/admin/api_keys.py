"""
API key lifecycle, prompt association, and quota management endpoints.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Request, Depends, HTTPException, Query

from models.schema import (
    ApiKeyCreate, ApiKeyResponse, ApiKeyUpdate,
    ApiKeyPromptAssociate, ApiKeyQuota, ApiKeyQuotaUpdate,
    ApiKeyUsage, ApiKeyQuotaResponse,
)
from utils.text_utils import mask_api_key

from routes.auth_helpers import check_service_availability
from routes.admin._shared import (
    _serialize_created_at, get_api_key_service, apikeys_auth,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# API Key Management Routes
@router.post("/api-keys", response_model=ApiKeyResponse, dependencies=[apikeys_auth])
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
        adapter_name=api_key_data.adapter_name,
        allowed_user_ids=api_key_data.allowed_user_ids,
        allowed_emails=api_key_data.allowed_emails,
    )
    
    # Log with masked API key
    masked_api_key = mask_api_key(api_key_response.get('api_key'), show_last=True, prefix="***")
    
    # Log creation with appropriate identifier
    if api_key_data.adapter_name:
        logger.info(f"Created API key for adapter '{api_key_data.adapter_name}': {masked_api_key}")
    else:
        logger.info(f"Created API key: {masked_api_key}")
    
    return api_key_response


@router.get("/api-keys", dependencies=[apikeys_auth])
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
                "allowed_user_ids": key.get("allowed_user_ids") or [],
                "allowed_emails": key.get("allowed_emails") or [],
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


@router.get("/api-keys/{api_key_id}/detail", dependencies=[apikeys_auth])
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
            "allowed_user_ids": key.get("allowed_user_ids") or [],
            "allowed_emails": key.get("allowed_emails") or [],
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


@router.get("/api-keys/{api_key_id}/status", dependencies=[apikeys_auth])
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


@router.patch("/api-keys/{api_key_id}/rename", dependencies=[apikeys_auth])
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


@router.put("/api-keys/{api_key_id}", dependencies=[apikeys_auth])
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
        allowed_user_ids=data.allowed_user_ids,
        allowed_emails=data.allowed_emails,
        adapter_manager=adapter_manager
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update API key")

    logger.info(f"Updated API key metadata for: {mask_api_key(api_key_id, show_last=True, prefix='***')}")
    return {"status": "success", "message": "API key updated successfully"}


@router.post("/api-keys/{api_key_id}/deactivate", dependencies=[apikeys_auth])
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


@router.delete("/api-keys/{api_key_id}", dependencies=[apikeys_auth])
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


@router.post("/api-keys/{api_key_id}/prompt", dependencies=[apikeys_auth])
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


@router.get("/api-keys/{api_key_id}/quota", response_model=ApiKeyQuotaResponse, dependencies=[apikeys_auth])
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


@router.put("/api-keys/{api_key_id}/quota", dependencies=[apikeys_auth])
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


@router.post("/api-keys/{api_key_id}/quota/reset", dependencies=[apikeys_auth])
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


@router.get("/quotas/usage-report", dependencies=[apikeys_auth])
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
