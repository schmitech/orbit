"""
Chat history lookup (inference-only mode).
"""

import logging
from fastapi import APIRouter, Request, HTTPException, Query

from routes.admin._shared import (
    conversations_auth,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# Chat History Management (only available in inference-only mode)
@router.get("/chat-history/{session_id}", dependencies=[conversations_auth])
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
