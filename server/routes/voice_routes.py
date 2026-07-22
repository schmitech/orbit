"""
Voice Routes

WebSocket endpoints for real-time speech-to-speech (STS) voice conversations with AI.

This endpoint only serves true full-duplex STS providers — the model listens
and speaks over one continuous audio stream, with no discrete STT -> LLM -> TTS
round trip. For regular (non-streaming) voice — a single request that submits
audio and gets an audio reply back, e.g. the "voice-chat" adapter in
config/adapters/audio.yaml — use the standard chat completions endpoint
(chat_routes.py) with audio_input/return_audio; that path is unaffected by
this module.

Handler selection is automatic based on adapter type:
- type: "openai_realtime" -> OpenAIRealtimeWebSocketHandler
- type: "openai_realtime_translation" -> OpenAIRealtimeTranslationWebSocketHandler
- type: "gemini_live" -> GeminiLiveWebSocketHandler
"""

import logging
from typing import Optional, Any, Dict
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request, Query, HTTPException

logger = logging.getLogger(__name__)

REALTIME_STS_ADAPTER_TYPES = ('openai_realtime', 'openai_realtime_translation', 'gemini_live')

router = APIRouter()


def get_chat_service(request: Request):
    """Get chat service from app state."""
    chat_service = getattr(request.app.state, 'chat_service', None)
    if not chat_service:
        raise HTTPException(status_code=503, detail="Chat service not available")
    return chat_service


def get_config(request: Request):
    """Get config from app state."""
    config = getattr(request.app.state, 'config', None)
    if not config:
        raise HTTPException(status_code=503, detail="Configuration not available")
    return config


async def validate_adapter(adapter_name: str, request: Request) -> Dict[str, Any]:
    """
    Validate that the adapter exists and supports real-time audio.

    Args:
        adapter_name: Adapter name to validate
        request: FastAPI request

    Returns:
        Adapter configuration dictionary

    Raises:
        HTTPException: If adapter is invalid or doesn't support real-time audio
    """
    # Get adapter manager from chat service
    chat_service = get_chat_service(request)

    if not hasattr(chat_service, 'context_builder') or not chat_service.context_builder:
        raise HTTPException(status_code=500, detail="Chat service not properly initialized")

    adapter_manager = chat_service.context_builder.adapter_manager
    if not adapter_manager:
        raise HTTPException(status_code=500, detail="Adapter manager not available")

    # Get adapter config
    adapter_config = adapter_manager.get_adapter_config(adapter_name)
    if not adapter_config:
        raise HTTPException(status_code=404, detail=f"Adapter '{adapter_name}' not found")

    # Check if adapter supports real-time audio
    capabilities = adapter_config.get('capabilities', {})
    supports_realtime_audio = capabilities.get('supports_realtime_audio', False)

    if not supports_realtime_audio:
        raise HTTPException(
            status_code=400,
            detail=f"Adapter '{adapter_name}' does not support real-time audio conversations"
        )

    # Check adapter type — this websocket endpoint only serves full-duplex
    # speech-to-speech providers; STT/TTS are handled by the provider itself.
    adapter_type = adapter_config.get('type', '')
    if adapter_type not in REALTIME_STS_ADAPTER_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Adapter '{adapter_name}' (type: '{adapter_type}') is not a real-time "
                f"speech-to-speech provider. Supported types: {', '.join(REALTIME_STS_ADAPTER_TYPES)}."
            )
        )

    logger.debug(
        f"Adapter validation successful: {adapter_name}, "
        f"type: {adapter_type} (Realtime bridge)"
    )

    return adapter_config


async def _resolve_voice_adapter_from_api_key(
    websocket: WebSocket,
    requested_adapter_name: Optional[str],
    api_key: Optional[str],
) -> tuple[str, Optional[str]]:
    """
    Resolve adapter and system prompt from API key when available.

    Voice websocket behavior should match the standard pipeline behavior:
    when an API key is present, the adapter associated with that key is the
    source of truth and any explicit adapter path acts only as a fallback.
    """
    if api_key:
        logger.debug(
            "Voice websocket received api_key for adapter '%s' (length=%s)",
            requested_adapter_name or "<auto>",
            len(api_key),
        )
    else:
        logger.debug(
            "Voice websocket received no api_key for adapter '%s'",
            requested_adapter_name or "<auto>",
        )

    if not api_key:
        if not requested_adapter_name:
            raise HTTPException(status_code=401, detail="API key required when adapter is not specified")
        return requested_adapter_name, None

    api_key_service = getattr(websocket.app.state, 'api_key_service', None)
    if not api_key_service:
        logger.warning(
            "api_key_service unavailable while resolving prompt for adapter '%s'",
            requested_adapter_name or "<auto>",
        )
        if requested_adapter_name:
            return requested_adapter_name, None
        raise HTTPException(status_code=503, detail="API key service is not available")

    adapter_manager = getattr(websocket.app.state, 'adapter_manager', None)
    resolved_adapter_name, system_prompt_id = await api_key_service.get_adapter_for_api_key(
        api_key,
        adapter_manager=adapter_manager,
    )
    logger.debug(
        "API key resolution for voice websocket: requested_adapter=%s, resolved_adapter=%s, system_prompt_id=%s",
        requested_adapter_name,
        resolved_adapter_name,
        system_prompt_id,
    )
    if requested_adapter_name and requested_adapter_name != resolved_adapter_name:
        logger.debug(
            "Overriding requested voice adapter '%s' with API-key adapter '%s'",
            requested_adapter_name,
            resolved_adapter_name,
        )
    if system_prompt_id:
        logger.debug("API key has system_prompt_id: %s", system_prompt_id)
    return resolved_adapter_name, str(system_prompt_id) if system_prompt_id else None



async def _handle_voice_websocket(
    websocket: WebSocket,
    adapter_name: Optional[str],
    session_id: Optional[str] = Query(None, description="Session ID for conversation history"),
    user_id: Optional[str] = Query(None, description="User ID for tracking"),
    api_key: Optional[str] = Query(None, description="API key for authentication"),
    target_language: Optional[str] = Query(None, description="Target language for realtime translation adapters")
):
    """
    WebSocket endpoint for real-time voice conversations.

    This endpoint enables bidirectional audio streaming between client and AI.

    Protocol:
    - Client sends: {"type": "audio_chunk", "data": "base64_audio", "format": "wav"}
    - Server sends: {"type": "audio_chunk", "data": "base64_audio", "format": "wav", "chunk_index": 0}
    - Client can interrupt: {"type": "interrupt"}
    - Server sends transcription (optional): {"type": "transcription", "text": "..."}
    - Server sends errors: {"type": "error", "message": "..."}
    - Server sends completion: {"type": "done", "session_id": "..."}

    Args:
        websocket: WebSocket connection
        adapter_name: Name of the adapter to use
        session_id: Optional session ID for conversation history
        user_id: Optional user ID for tracking

    Example client connection:
        ws://localhost:8000/ws/voice/open-ai-real-time-voice-chat?session_id=abc123
    """
    handler = None

    try:
        from services.pause_state import is_paused
        if await is_paused(websocket.app.state):
            raise HTTPException(status_code=503, detail="Server is paused")

        adapter_name, system_prompt_id = await _resolve_voice_adapter_from_api_key(
            websocket,
            adapter_name,
            api_key,
        )

        # Validate adapter before accepting connection
        adapter_config = await validate_adapter(adapter_name, websocket)

        # Get services from app state
        chat_service = get_chat_service(websocket)
        config = get_config(websocket)

        # Validate API key if required by adapter
        requires_auth = adapter_config.get('capabilities', {}).get('requires_api_key_validation', False)
        if requires_auth:
            if not api_key:
                raise HTTPException(
                    status_code=401,
                    detail="API key required for this adapter"
                )
            # TODO: Add actual API key validation logic here
            # For now, we accept any non-empty API key
            logger.info(f"API key provided for adapter: {adapter_name}")

        # Check adapter type to determine handler
        adapter_type = adapter_config.get('type', '')

        if adapter_type == 'openai_realtime':
            from services.chat_handlers.openai_realtime_websocket_handler import (
                OpenAIRealtimeWebSocketHandler,
            )
            prompt_service = getattr(websocket.app.state, 'prompt_service', None)
            clock_service = getattr(websocket.app.state, 'clock_service', None)
            chat_history_service = getattr(websocket.app.state, 'chat_history_service', None)

            handler = OpenAIRealtimeWebSocketHandler(
                websocket=websocket,
                adapter_name=adapter_name,
                adapter_config=adapter_config,
                config=config,
                session_id=session_id,
                user_id=user_id,
                prompt_service=prompt_service,
                system_prompt_id=system_prompt_id,
                clock_service=clock_service,
                adapter_manager=chat_service.context_builder.adapter_manager,
                api_key=api_key,
                chat_history_service=chat_history_service,
            )
        elif adapter_type == 'openai_realtime_translation':
            from services.chat_handlers.openai_realtime_translation_websocket_handler import (
                OpenAIRealtimeTranslationWebSocketHandler,
            )

            handler = OpenAIRealtimeTranslationWebSocketHandler(
                websocket=websocket,
                adapter_name=adapter_name,
                adapter_config=adapter_config,
                config=config,
                session_id=session_id,
                user_id=user_id,
                target_language=target_language,
            )
        elif adapter_type == 'gemini_live':
            from services.chat_handlers.gemini_live_websocket_handler import (
                GeminiLiveWebSocketHandler,
            )
            prompt_service = getattr(websocket.app.state, 'prompt_service', None)
            clock_service = getattr(websocket.app.state, 'clock_service', None)
            chat_history_service = getattr(websocket.app.state, 'chat_history_service', None)

            handler = GeminiLiveWebSocketHandler(
                websocket=websocket,
                adapter_name=adapter_name,
                adapter_config=adapter_config,
                config=config,
                session_id=session_id,
                user_id=user_id,
                prompt_service=prompt_service,
                system_prompt_id=system_prompt_id,
                clock_service=clock_service,
                adapter_manager=chat_service.context_builder.adapter_manager,
                api_key=api_key,
                chat_history_service=chat_history_service,
            )
        else:
            # validate_adapter() already restricts this endpoint to
            # REALTIME_STS_ADAPTER_TYPES, so this should be unreachable.
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported real-time adapter type: {adapter_type}"
            )

        # Run message loop (each realtime handler accepts the socket inside run())
        await handler.run()

    except HTTPException as e:
        # Send error before closing
        try:
            await websocket.send_json({
                "type": "error",
                "message": e.detail
            })
        except Exception:
            pass
        logger.error(f"HTTP exception in voice WebSocket: {e.detail}")

    except WebSocketDisconnect:
        logger.info(f"Voice WebSocket disconnected for adapter: {adapter_name}")

    except Exception as e:
        logger.error(f"Error in voice WebSocket endpoint: {str(e)}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"Server error: {str(e)}"
            })
        except Exception:
            pass

    finally:
        # Cleanup
        if handler:
            try:
                await handler.cleanup()
            except Exception as e:
                logger.error(f"Error during handler cleanup: {str(e)}")


@router.websocket("/ws/voice")
async def websocket_voice_auto(
    websocket: WebSocket,
    session_id: Optional[str] = Query(None, description="Session ID for conversation history"),
    user_id: Optional[str] = Query(None, description="User ID for tracking"),
    api_key: Optional[str] = Query(None, description="API key for authentication"),
    target_language: Optional[str] = Query(None, description="Target language for realtime translation adapters")
):
    """WebSocket endpoint that resolves the adapter from the API key."""
    await _handle_voice_websocket(
        websocket=websocket,
        adapter_name=None,
        session_id=session_id,
        user_id=user_id,
        api_key=api_key,
        target_language=target_language,
    )


@router.websocket("/ws/voice/{adapter_name}")
async def websocket_voice(
    websocket: WebSocket,
    adapter_name: str,
    session_id: Optional[str] = Query(None, description="Session ID for conversation history"),
    user_id: Optional[str] = Query(None, description="User ID for tracking"),
    api_key: Optional[str] = Query(None, description="API key for authentication"),
    target_language: Optional[str] = Query(None, description="Target language for realtime translation adapters")
):
    """WebSocket endpoint for real-time voice conversations with explicit adapter path."""
    await _handle_voice_websocket(
        websocket=websocket,
        adapter_name=adapter_name,
        session_id=session_id,
        user_id=user_id,
        api_key=api_key,
        target_language=target_language,
    )


@router.get("/voice/status")
async def voice_status(request: Request):
    """
    Get status of voice service and available adapters.

    Returns information about:
    - Voice service availability
    - Audio providers configured
    - Adapters supporting real-time audio

    Returns:
        Dictionary with voice service status
    """
    try:
        chat_service = get_chat_service(request)
        config = get_config(request)

        # Get adapter manager
        if not hasattr(chat_service, 'context_builder') or not chat_service.context_builder:
            return {
                "available": False,
                "error": "Chat service not properly initialized"
            }

        adapter_manager = chat_service.context_builder.adapter_manager
        if not adapter_manager:
            return {
                "available": False,
                "error": "Adapter manager not available"
            }

        # Find all adapters that support real-time audio
        all_adapters = adapter_manager.get_all_adapter_names()
        voice_adapters = []

        for adapter_name in all_adapters:
            adapter_config = adapter_manager.get_adapter_config(adapter_name)
            if not adapter_config:
                continue

            capabilities = adapter_config.get('capabilities', {})
            if capabilities.get('supports_realtime_audio', False):
                adapter_type = adapter_config.get('type', 'passthrough')
                is_full_duplex = adapter_type in ('openai_realtime', 'openai_realtime_translation', 'gemini_live')

                adapter_info = {
                    "name": adapter_name,
                    "type": adapter_type,
                    "enabled": adapter_config.get('enabled', False),
                    "full_duplex": is_full_duplex
                }

                if adapter_type == 'openai_realtime':
                    adapter_info["mode"] = "openai_realtime"
                    rcfg = (adapter_config.get('config') or {})
                    adapter_info["realtime_model"] = rcfg.get('realtime_model', 'gpt-realtime')
                elif adapter_type == 'openai_realtime_translation':
                    adapter_info["mode"] = "openai_realtime_translation"
                    rcfg = (adapter_config.get('config') or {})
                    adapter_info["realtime_model"] = rcfg.get('realtime_model', 'gpt-realtime-translate')
                    adapter_info["target_language"] = rcfg.get('target_language', 'es')
                elif adapter_type == 'gemini_live':
                    adapter_info["mode"] = "gemini_live"
                    rcfg = (adapter_config.get('config') or {})
                    adapter_info["realtime_model"] = rcfg.get('realtime_model', 'gemini-3.1-flash-live-preview')
                else:
                    # /ws/voice only serves REALTIME_STS_ADAPTER_TYPES (see validate_adapter);
                    # an adapter with supports_realtime_audio: true outside that set is
                    # misconfigured and won't actually connect.
                    logger.warning(
                        f"Adapter '{adapter_name}' has supports_realtime_audio: true but "
                        f"type '{adapter_type}' is not a supported real-time STS provider"
                    )
                    adapter_info["mode"] = "unsupported"

                voice_adapters.append(adapter_info)

        # Get global sound configuration
        sound_config = config.get('sound', {})

        return {
            "available": True,
            "global_audio_enabled": sound_config.get('enabled', False),
            "default_provider": sound_config.get('provider', 'unknown'),
            "adapters": voice_adapters,
            "websocket_endpoint": "/ws/voice/{adapter_name}"
        }

    except Exception as e:
        logger.error(f"Error getting voice status: {str(e)}", exc_info=True)
        return {
            "available": False,
            "error": str(e)
        }
