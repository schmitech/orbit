"""
Message Consumer Service
========================

Host-agnostic consumer that bridges a MessageBroker to the inference pipeline.
Runs identically whether hosted in-process (server lifespan) or in a standalone
worker.

For each inbound message it:
  1. Parses the request contract (unparseable -> raise -> dead-letter queue).
  2. Resolves the adapter from the API key (same rules as the REST/A2A surfaces:
     a valid key is required when a key service is configured; a per-message
     `adapter` override is applied only after the key is validated).
  3. Runs PipelineChatService.process_chat.
  4. Publishes a response envelope to the message's reply_to (falling back to the
     broker's configured results queue), correlated by correlation_id.

Business-level failures (missing/invalid key, empty message, pipeline error result)
publish a `status: "failed"` envelope and ack — the client always gets an answer.
Only unparseable messages and unexpected exceptions propagate, routing to the DLQ.
"""

import json
import logging
from typing import Any, Dict, Optional, Tuple

from ..message_brokers.base import BrokerMessage, MessageBroker

logger = logging.getLogger(__name__)


class MessageConsumerService:
    """Consumes request messages off a broker and replies with pipeline responses."""

    def __init__(
        self,
        config: Dict[str, Any],
        broker: MessageBroker,
        chat_service,
        api_key_service=None,
        adapter_manager=None,
    ):
        self.config = config
        self.broker = broker
        self.chat_service = chat_service
        self.api_key_service = api_key_service
        self.adapter_manager = adapter_manager

    async def start(self) -> None:
        await self.broker.connect()
        await self.broker.consume(self._handle)
        logger.info("Message consumer started")

    async def stop(self) -> None:
        await self.broker.close()
        logger.info("Message consumer stopped")

    async def _handle(self, msg: BrokerMessage) -> None:
        # Parse — unparseable bodies cannot be answered, so route them to the DLQ.
        request = json.loads(msg.body)
        if not isinstance(request, dict):
            raise ValueError("Message body must be a JSON object")

        request_id = request.get("id")
        correlation_id = msg.correlation_id or request_id
        reply_to = msg.reply_to  # None -> broker falls back to its results queue

        user_text = (request.get("message") or "").strip()
        session_id = request.get("session_id") or correlation_id
        adapter_override = request.get("adapter")
        # API key may arrive in the body or an AMQP header.
        api_key = (
            request.get("api_key")
            or msg.headers.get("x-api-key")
            or msg.headers.get("api_key")
        )

        try:
            adapter_name, system_prompt_id = await self._resolve_adapter(api_key, adapter_override)
        except PermissionError as e:
            await self._publish(reply_to, correlation_id, self._failed(request_id, str(e)))
            return

        if not user_text:
            await self._publish(
                reply_to, correlation_id, self._failed(request_id, "message must not be empty")
            )
            return

        # Pass the key-derived context (system prompt id + api key) so MQ requests
        # behave identically to /v1/chat. Unexpected exceptions here propagate ->
        # broker rejects -> DLQ.
        result = await self.chat_service.process_chat(
            message=user_text,
            client_ip="mq",
            adapter_name=adapter_name,
            system_prompt_id=system_prompt_id,
            api_key=api_key,
            session_id=session_id,
        )

        if "error" in result:
            envelope = self._failed(request_id, result["error"])
        else:
            envelope = {
                "id": request_id,
                "status": "completed",
                "response": result.get("response", ""),
                "sources": result.get("sources", []),
                "error": None,
                "metadata": result.get("metadata", {}),
            }
        await self._publish(reply_to, correlation_id, envelope)

    async def _resolve_adapter(
        self, api_key: Optional[str], adapter_override: Optional[str]
    ) -> Tuple[str, Optional[Any]]:
        """Return (adapter_name, system_prompt_id) for a request.

        Mirrors a2a_routes._resolve_adapter / the /v1/chat key resolution: when a key
        service is configured a valid key is mandatory, and both the adapter and its
        associated system prompt id come from the key. The per-message adapter override
        is honored only after validation; the system prompt id (tied to the key, not the
        adapter) is preserved regardless. When no key service is configured (auth
        disabled), the override or 'default' is used with no prompt id. Raises
        PermissionError on missing/invalid keys.
        """
        if not self.api_key_service:
            return adapter_override or "default", None

        if not api_key:
            raise PermissionError("Missing API key")

        try:
            adapter_name, system_prompt_id = await self.api_key_service.get_adapter_for_api_key(
                api_key, self.adapter_manager
            )
        except PermissionError:
            raise
        except Exception as e:
            # Invalid keys surface as HTTPException(401/403) from the key service.
            raise PermissionError(f"API key resolution failed: {e}")

        return (adapter_override or adapter_name or "default"), system_prompt_id

    @staticmethod
    def _failed(request_id: Optional[str], error: str) -> Dict[str, Any]:
        return {
            "id": request_id,
            "status": "failed",
            "response": None,
            "sources": [],
            "error": error,
            "metadata": {},
        }

    async def _publish(self, reply_to: Optional[str], correlation_id: Optional[str], envelope: Dict[str, Any]) -> None:
        await self.broker.publish(
            reply_to, json.dumps(envelope).encode(), correlation_id=correlation_id
        )
