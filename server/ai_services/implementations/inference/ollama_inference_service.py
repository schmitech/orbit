"""
Ollama inference service implementation using unified architecture.

This is a migrated version of the Ollama inference provider that uses
the new unified AI services architecture and integrates with existing
ollama_utils for maximum compatibility.
"""

import logging
from typing import Dict, Any, AsyncGenerator, List
import json
import uuid

from ...errors import sanitize_provider_error
from ...providers import OllamaBaseService
from ...services import InferenceService, ToolCallingResult

logger = logging.getLogger(__name__)


class OllamaInferenceService(InferenceService, OllamaBaseService):
    """
    Ollama inference service using unified architecture.

    This implementation leverages:
    1. Ollama utilities integration from OllamaBaseService
    2. Model warm-up and retry logic inherited
    3. Configuration parsing from base classes
    4. Connection verification automatic

    Simplified with automatic handling of Ollama-specific functionality.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Ollama inference service.

        Args:
            config: Configuration dictionary
        """
        # Initialize via InferenceService which will cooperate with OllamaBaseService
        InferenceService.__init__(self, config, "ollama")

        # Get inference-specific configuration
        self.temperature = self._get_temperature(default=0.7)
        self.top_p = self._get_top_p(default=0.9)

        # Ollama doesn't have max_tokens, uses num_predict instead
        provider_config = self._extract_provider_config()
        self.num_predict = provider_config.get('num_predict', -1)  # -1 means no limit
        self.think = provider_config.get('think', False)  # Enable/disable think mode

    @staticmethod
    def _normalize_messages_for_ollama(
        messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Convert OpenAI-format loop history into Ollama /api/chat message format.

        - Tool-result messages are reduced to {"role","content","tool_name"}.
          tool_name lets the model match a result back to the call that
          produced it (important for parallel tool calls); Ollama versions that
          don't use the field simply ignore it.
        - Assistant tool-call turns are re-encoded with dict arguments, which is
          the shape Ollama expects (vs OpenAI's JSON-string arguments).
        - All other messages pass through unchanged.
        """
        ollama_messages: List[Dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role")
            if role == "tool":
                tool_msg: Dict[str, Any] = {
                    "role": "tool",
                    "content": msg.get("content", ""),
                }
                if msg.get("name"):
                    tool_msg["tool_name"] = msg["name"]
                ollama_messages.append(tool_msg)
            elif role == "assistant" and msg.get("tool_calls"):
                ollama_tool_calls = []
                for tc in msg["tool_calls"]:
                    fn = tc.get("function", {})
                    args = fn.get("arguments", "{}")
                    if isinstance(args, str):
                        # Defensive: our own loop emits valid JSON, but guard
                        # against malformed history rather than raising here.
                        try:
                            args = json.loads(args)
                        except (ValueError, TypeError):
                            args = {}
                    ollama_tool_calls.append({
                        "function": {"name": fn.get("name", ""), "arguments": args}
                    })
                ollama_messages.append({
                    "role": "assistant",
                    "content": msg.get("content") or "",
                    "tool_calls": ollama_tool_calls,
                })
            else:
                ollama_messages.append(msg)
        return ollama_messages

    async def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> ToolCallingResult:
        """
        Single round of tool-enabled generation via Ollama's /api/chat endpoint.

        Ollama supports tools= natively for models that implement function calling
        (e.g. gemma4, llama3.1, qwen2.5, mistral-nemo). Models that don't support
        tool calling will respond with plain text; the loop exits cleanly on the
        first iteration.

        Differences from OpenAI format handled here:
        - Ollama tool-call arguments are already dicts, not JSON strings.
        - Ollama tool calls have no id — synthetic ids are generated so the
          loop can match tool results on the next round.
        - Tool result messages use role "tool"; Ollama accepts tool_call_id
          being present but does not require it.
        """
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize Ollama inference service")

        ollama_messages = self._normalize_messages_for_ollama(messages)

        payload = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": False,
            # Honor the preset's think setting (mirrors generate/generate_stream).
            # Disabling thinking keeps each loop iteration fast; some presets
            # (e.g. functiongemma) require it off.
            "think": kwargs.get("think", self.think),
            "options": {
                "temperature": kwargs.get("temperature", self.temperature),
                "top_p": kwargs.get("top_p", self.top_p),
                # Honor the preset's output cap so final answers aren't cut to
                # Ollama's chat default (-1 = no limit).
                "num_predict": kwargs.get("num_predict", self.num_predict),
            },
        }
        # Omit tools when none are offered — the final synthesis call passes []
        # on purpose to force a text answer instead of further tool calls.
        if tools:
            payload["tools"] = tools

        async def _call():
            session = await self.session_manager.get_session()
            url = f"{self.base_url}/api/chat"
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ValueError(f"Ollama error: {error_text}")
                return await response.json()

        data = await self.execute_with_retry(_call)
        msg_data = data.get("message", {})
        content = msg_data.get("content") or None
        raw_tool_calls = msg_data.get("tool_calls") or []

        # Ollama returns arguments as dicts and omits call ids — normalise to
        # OpenAI format so the MCPAgentStep loop works unchanged.
        tool_calls_result = None
        assistant_msg: Dict[str, Any] = {"role": "assistant", "content": content}

        if raw_tool_calls:
            normalized = []
            openai_tcs = []
            for tc in raw_tool_calls:
                fn = tc.get("function", {})
                call_id = tc.get("id") or f"call_{uuid.uuid4().hex[:8]}"
                args = fn.get("arguments", {})
                # Ensure args is a dict (Ollama returns dicts, not strings)
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                normalized.append({"id": call_id, "name": fn.get("name", ""), "arguments": args})
                openai_tcs.append({
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": fn.get("name", ""),
                        "arguments": json.dumps(args),
                    },
                })
            tool_calls_result = normalized
            assistant_msg["tool_calls"] = openai_tcs

        return ToolCallingResult(
            text=content,
            tool_calls=tool_calls_result,
            assistant_message=assistant_msg,
            finish_reason="tool_calls" if tool_calls_result else "stop",
        )

    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response using Ollama.

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters (including 'messages' for chat format)

        Returns:
            The generated response text
        """
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize Ollama inference service")

        async def _generate():
            session = await self.session_manager.get_session()

            # Check if we have messages format (chat)
            messages = kwargs.pop('messages', None)

            if messages:
                # Use chat endpoint for messages
                url = f"{self.base_url}/api/chat"
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "think": kwargs.pop('think', self.think),
                    "options": {
                        "temperature": kwargs.pop('temperature', self.temperature),
                        "top_p": kwargs.pop('top_p', self.top_p),
                    }
                }
            else:
                # Use generate endpoint for simple prompts
                url = f"{self.base_url}/api/generate"
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "think": kwargs.pop('think', self.think),
                    "options": {
                        "temperature": kwargs.pop('temperature', self.temperature),
                        "top_p": kwargs.pop('top_p', self.top_p),
                        "num_predict": kwargs.pop('num_predict', self.num_predict),
                    }
                }

            # Add any other kwargs to options
            payload["options"].update(kwargs)

            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ValueError(f"Ollama error: {error_text}")

                data = await response.json()

                # Get response based on endpoint used
                if messages:
                    return data.get('message', {}).get('content', '')
                else:
                    return data.get('response', '')

        # Use Ollama's retry handler
        return await self.execute_with_retry(_generate)

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """
        Generate streaming response using Ollama.

        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters (including 'messages' for chat format)

        Yields:
            Response chunks as they are generated
        """
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize Ollama inference service")

        try:
            session = await self.session_manager.get_session()

            # Check if we have messages format (chat)
            messages = kwargs.pop('messages', None)

            if messages:
                # Use chat endpoint for messages
                url = f"{self.base_url}/api/chat"
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "stream": True,
                    "think": kwargs.pop('think', self.think),
                    "options": {
                        "temperature": kwargs.pop('temperature', self.temperature),
                        "top_p": kwargs.pop('top_p', self.top_p),
                    }
                }
            else:
                # Use generate endpoint for simple prompts
                url = f"{self.base_url}/api/generate"
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": True,
                    "think": kwargs.pop('think', self.think),
                    "options": {
                        "temperature": kwargs.pop('temperature', self.temperature),
                        "top_p": kwargs.pop('top_p', self.top_p),
                        "num_predict": kwargs.pop('num_predict', self.num_predict),
                    }
                }

            # Add any other kwargs to options
            payload["options"].update(kwargs)

            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(
                        "Ollama HTTP %s during streaming generation: %s",
                        response.status,
                        error_text,
                    )
                    http_error = RuntimeError(f"Ollama HTTP {response.status}")
                    http_error.status_code = response.status
                    yield sanitize_provider_error(
                        http_error,
                        provider=self.provider_name,
                        operation="streaming generation",
                    )
                    return

                # Stream the response
                async for line in response.content:
                    if line:
                        try:
                            chunk = json.loads(line.decode('utf-8'))

                            # Get content based on endpoint used
                            if messages:
                                content = chunk.get('message', {}).get('content', '')
                            else:
                                content = chunk.get('response', '')

                            if content:
                                yield content

                            # Check if done
                            if chunk.get('done', False):
                                break

                        except json.JSONDecodeError:
                            continue  # Skip invalid JSON lines

        except Exception as e:
            logger.exception("Error in streaming generation")
            yield sanitize_provider_error(
                e,
                provider=self.provider_name,
                operation="streaming generation",
            )
