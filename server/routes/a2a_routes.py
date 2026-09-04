"""
A2A (Agent-to-Agent) protocol routes for ORBIT.

Implements the Google A2A specification:
- GET  /.well-known/agent.json  — Agent Card discovery
- POST /a2a                     — JSON-RPC 2.0 task management

Supported methods: tasks/send, tasks/sendSubscribe, tasks/get, tasks/cancel

Authentication: Bearer <orbit-api-key> in Authorization header.
The API key is resolved to an adapter name using the existing key service.

Optional user identity for restricted keys: an API key can be scoped to a
specific set of ORBIT users via `allowed_user_ids` (see ApiKeyService). Since
Authorization already carries the API key itself, a restricted key can only
be used over A2A if the caller also supplies a separate user credential in
`X-ORBIT-User-Authorization: Bearer <session-token-or-jwt>`. Callers using an
unrestricted key can omit this header entirely.
"""

import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from routes.auth_helpers import resolve_authenticated_user, is_authenticated_user_required

logger = logging.getLogger(__name__)

# In-memory task store — keyed by task_id.
# Sufficient for single-process deployments; swap for Redis if needed.
_tasks: dict[str, dict] = {}


def create_a2a_router() -> APIRouter:
    router = APIRouter(tags=["a2a"])

    @router.get("/.well-known/agent.json", include_in_schema=False)
    async def agent_card(request: Request) -> JSONResponse:
        """A2A Agent Card — describes ORBIT's capabilities to other agents."""
        base_url = str(request.base_url).rstrip("/")

        skills = _build_skills(request)

        card = {
            "name": "ORBIT",
            "description": (
                "Open Retrieval-Based Inference Toolkit — AI gateway with RAG, "
                "intent-SQL retrieval, and 37+ LLM provider support."
            ),
            "url": base_url,
            "version": "1.0.0",
            "capabilities": {
                "streaming": True,
                "pushNotifications": False,
                "stateTransitionHistory": False,
            },
            "defaultInputModes": ["text/plain"],
            "defaultOutputModes": ["text/plain"],
            "skills": skills,
            "authentication": {"schemes": ["Bearer"]},
        }

        # Expose MCP mount point if it exists
        if hasattr(request.app, "routes"):
            for route in request.app.routes:
                if getattr(route, "path", "").startswith("/mcp"):
                    card["extensions"] = {"mcp_url": f"{base_url}/mcp"}
                    break

        return JSONResponse(content=card)

    @router.post("/a2a", response_model=None)
    async def a2a(request: Request) -> JSONResponse | StreamingResponse:
        """A2A JSON-RPC 2.0 endpoint."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(content=_err(None, -32700, "Parse error"))

        if body.get("jsonrpc") != "2.0":
            return JSONResponse(content=_err(body.get("id"), -32600, "Invalid Request"))

        rpc_id = body.get("id")
        method = body.get("method", "")
        params = body.get("params") or {}

        if method in ("tasks/send", "tasks/sendSubscribe"):
            from services.pause_state import is_paused
            if await is_paused(request.app.state):
                return JSONResponse(content=_err(rpc_id, -32000, "Server is paused"))

        # Resolve adapter from API key (same logic as REST/OpenAI endpoints)
        adapter_name, api_key = await _resolve_adapter(request)

        if method == "tasks/send":
            return await _tasks_send(request, rpc_id, params, adapter_name, api_key)
        if method == "tasks/sendSubscribe":
            return await _tasks_send_subscribe(request, rpc_id, params, adapter_name, api_key)
        if method == "tasks/get":
            return _tasks_get(rpc_id, params)
        if method == "tasks/cancel":
            return _tasks_cancel(rpc_id, params)

        return JSONResponse(content=_err(rpc_id, -32601, f"Method not found: {method}"))

    return router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _resolve_adapter(request: Request) -> tuple[str, Optional[str]]:
    """Return (adapter name, API key) for the Bearer token.

    The key is returned alongside the adapter name so it can be threaded into
    process_chat: chat history rows stamped with no key have no owner, and any
    valid key can delete an ownerless session (see ChatHistoryService).

    Raises HTTPException (401/403) if a key is provided but invalid.
    Returns 'default' only when no key is present and no key service is configured
    (i.e. API-key enforcement is disabled for this deployment).
    """
    config = request.app.state.config
    auth_header = request.headers.get("Authorization", "")
    api_key_service = getattr(request.app.state, "api_key_service", None)

    # Authorization already carries the API key itself (see module docstring),
    # so a distinct user credential — required to use a key restricted via
    # allowed_user_ids, or mandatory outright under auth.require_authenticated_user —
    # must come from a separate header.
    current_user = await resolve_authenticated_user(
        request, header_name="x-orbit-user-authorization"
    )

    def _enforce_identity(adapter_config: Optional[dict] = None) -> None:
        if current_user or not is_authenticated_user_required(config, adapter_config):
            return
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Send X-ORBIT-User-Authorization: Bearer <user-token>.",
            headers={"WWW-Authenticate": 'Bearer realm="orbit"'},
        )

    if not auth_header.startswith("Bearer "):
        # No key supplied — allow only when the key service is absent (auth disabled)
        if api_key_service:
            raise HTTPException(status_code=401, detail="Missing Bearer token")
        _enforce_identity()
        return "default", None

    api_key = auth_header[len("Bearer "):]
    if not api_key_service:
        _enforce_identity()
        return "default", None

    # Let HTTPException from the key service propagate as-is (401/403/404).
    # Only swallow unexpected non-auth errors and surface them as 503.
    try:
        adapter_manager = getattr(request.app.state, "adapter_manager", None)
        adapter_name, _ = await api_key_service.get_adapter_for_api_key(
            api_key, adapter_manager,
            current_user_id=current_user.get("id") if current_user else None,
            current_user_email=current_user.get("email") if current_user else None,
        )
        adapter_name = adapter_name or "default"
        adapter_config = (
            adapter_manager.get_adapter_config(adapter_name)
            if adapter_manager and adapter_name else None
        )
        _enforce_identity(adapter_config)
        return adapter_name, api_key
    except HTTPException:
        raise
    except Exception as e:
        logger.error("A2A adapter resolution failed: %s", e)
        raise HTTPException(status_code=503, detail="API key service unavailable")


async def _enforce_identity_for_adapter(request: Request, adapter_name: str) -> None:
    """
    Re-check auth.require_authenticated_user against the adapter that will
    actually execute this task.

    `_resolve_adapter` only checked the key-mapped adapter, but
    `params.metadata.adapter`/`skill` can redirect execution to a different
    one — a key mapped to an adapter that opts out of the requirement could
    otherwise reach a sensitive adapter that opts in, with no identity check
    at all. `resolve_authenticated_user` caches on `request.state`, so this
    is not a second token-validation round trip.
    """
    config = request.app.state.config
    adapter_manager = getattr(request.app.state, "adapter_manager", None)
    adapter_config = (
        adapter_manager.get_adapter_config(adapter_name)
        if adapter_manager and adapter_name else None
    )
    if not is_authenticated_user_required(config, adapter_config):
        return
    current_user = await resolve_authenticated_user(request, header_name="x-orbit-user-authorization")
    if current_user:
        return
    raise HTTPException(
        status_code=401,
        detail="Authentication required. Send X-ORBIT-User-Authorization: Bearer <user-token>.",
        headers={"WWW-Authenticate": 'Bearer realm="orbit"'},
    )


def _build_skills(request: Request) -> list:
    """Build A2A skills list from live adapter/skills state."""
    adapter_manager = (
        getattr(request.app.state, "fault_tolerant_adapter_manager", None)
        or getattr(request.app.state, "adapter_manager", None)
    )
    if adapter_manager and hasattr(adapter_manager, "get_all_skills"):
        raw = adapter_manager.get_all_skills()
        if raw:
            return [
                {
                    "id": s.get("adapter_name", s.get("name", "")),
                    "name": s.get("name", ""),
                    "description": s.get("description", ""),
                    "inputModes": ["text/plain"],
                    "outputModes": ["text/plain"],
                }
                for s in raw
            ]

    return [
        {
            "id": "chat",
            "name": "Chat",
            "description": "General-purpose chat with optional RAG retrieval",
            "inputModes": ["text/plain"],
            "outputModes": ["text/plain"],
        }
    ]


def _extract_text(message: dict) -> str:
    parts = message.get("parts") or []
    return " ".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()


def _make_task(task_id: str, message: dict, state: str = "submitted") -> dict:
    return {
        "id": task_id,
        "status": {"state": state},
        "history": [message],
        "artifacts": [],
    }


def _ok(rpc_id, result) -> dict:
    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}


def _err(rpc_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# Method handlers
# ---------------------------------------------------------------------------

async def _tasks_send(
    request: Request, rpc_id, params: dict, adapter_name: str, api_key: Optional[str] = None
) -> JSONResponse:
    task_id = params.get("id") or str(uuid.uuid4())
    message = params.get("message") or {}
    user_text = _extract_text(message)

    if not user_text:
        return JSONResponse(content=_err(rpc_id, -32602, "No text content in message parts"))

    # Allow per-task skill/adapter override via metadata
    metadata = params.get("metadata") or {}
    effective_adapter = metadata.get("adapter") or metadata.get("skill") or adapter_name
    await _enforce_identity_for_adapter(request, effective_adapter)

    chat_service = request.app.state.chat_service

    # Authorize before any context read (task_id is the client-supplied session id).
    # Deliberately outside the try below: that handler converts exceptions into a
    # JSON-RPC error at HTTP 200, which would downgrade the 403 into a success-status
    # response body.
    await chat_service.authorize_session_access(session_id=task_id, api_key=api_key)

    task = _make_task(task_id, message, "working")
    _tasks[task_id] = task

    try:
        client_ip = request.client.host if request.client else "unknown"

        result = await chat_service.process_chat(
            message=user_text,
            client_ip=client_ip,
            adapter_name=effective_adapter,
            session_id=task_id,
            api_key=api_key,
        )

        if "error" in result:
            task["status"] = {"state": "failed", "message": {"text": result["error"]}}
            _tasks[task_id] = task
            return JSONResponse(content=_err(rpc_id, -32000, result["error"]))

        response_text = result.get("response", "")
        agent_message = {
            "role": "agent",
            "parts": [{"type": "text", "text": response_text}],
        }
        task["status"] = {"state": "completed"}
        task["history"].append(agent_message)
        task["artifacts"] = [
            {"name": "response", "parts": [{"type": "text", "text": response_text}]}
        ]
        # Attach sources if present
        if result.get("sources"):
            task["artifacts"][0]["metadata"] = {"sources": result["sources"]}
        _tasks[task_id] = task

        return JSONResponse(content=_ok(rpc_id, task))

    except Exception as e:
        logger.error("A2A tasks/send failed: %s", e)
        task["status"] = {"state": "failed"}
        _tasks[task_id] = task
        return JSONResponse(content=_err(rpc_id, -32000, str(e)))


async def _tasks_send_subscribe(
    request: Request, rpc_id, params: dict, adapter_name: str, api_key: Optional[str] = None
) -> StreamingResponse:
    task_id = params.get("id") or str(uuid.uuid4())
    message = params.get("message") or {}
    user_text = _extract_text(message)

    metadata = params.get("metadata") or {}
    effective_adapter = metadata.get("adapter") or metadata.get("skill") or adapter_name
    await _enforce_identity_for_adapter(request, effective_adapter)

    # Authorize before the generator starts — once streaming begins it is too late
    # to return a 403.
    await request.app.state.chat_service.authorize_session_access(
        session_id=task_id, api_key=api_key
    )

    task = _make_task(task_id, message, "submitted")
    _tasks[task_id] = task

    async def sse_generator():
        # Signal working state
        task["status"] = {"state": "working"}
        _tasks[task_id] = task
        yield _sse(_ok(rpc_id, {"id": task_id, "status": task["status"], "final": False}))

        if not user_text:
            task["status"] = {"state": "failed"}
            _tasks[task_id] = task
            yield _sse(_err(rpc_id, -32602, "No text content in message parts"))
            return

        try:
            chat_service = request.app.state.chat_service
            client_ip = request.client.host if request.client else "unknown"
            accumulated = []

            async for chunk in chat_service.process_chat_stream(
                message=user_text,
                client_ip=client_ip,
                adapter_name=effective_adapter,
                session_id=task_id,
                api_key=api_key,
            ):
                if not chunk or not chunk.startswith("data:"):
                    continue
                payload = chunk[6:].strip()
                if not payload:
                    continue
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    continue

                if data.get("done"):
                    if data.get("error"):
                        raise RuntimeError(data["error"])
                    break

                text = data.get("response")
                if text:
                    accumulated.append(text)
                    yield _sse(
                        _ok(
                            rpc_id,
                            {
                                "id": task_id,
                                "artifact": {
                                    "name": "response",
                                    "parts": [{"type": "text", "text": text}],
                                    "append": True,
                                    "lastChunk": False,
                                },
                                "final": False,
                            },
                        )
                    )

            full_text = "".join(accumulated)
            agent_message = {"role": "agent", "parts": [{"type": "text", "text": full_text}]}
            task["status"] = {"state": "completed"}
            task["history"].append(agent_message)
            task["artifacts"] = [
                {"name": "response", "parts": [{"type": "text", "text": full_text}]}
            ]
            _tasks[task_id] = task

            yield _sse(_ok(rpc_id, {"id": task_id, "status": {"state": "completed"}, "final": True}))

        except Exception as e:
            logger.error("A2A tasks/sendSubscribe failed: %s", e)
            task["status"] = {"state": "failed"}
            _tasks[task_id] = task
            yield _sse(_err(rpc_id, -32000, str(e)))

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _tasks_get(rpc_id, params: dict) -> JSONResponse:
    task_id = params.get("id")
    task = _tasks.get(task_id) if task_id else None
    if task is None:
        return JSONResponse(content=_err(rpc_id, -32001, "Task not found"))
    return JSONResponse(content=_ok(rpc_id, task))


def _tasks_cancel(rpc_id, params: dict) -> JSONResponse:
    task_id = params.get("id")
    task = _tasks.get(task_id) if task_id else None
    if task is None:
        return JSONResponse(content=_err(rpc_id, -32001, "Task not found"))
    task["status"] = {"state": "canceled"}
    _tasks[task_id] = task
    return JSONResponse(content=_ok(rpc_id, task))
