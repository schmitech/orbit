"""
Gemini inference service implementation using unified architecture.

Uses the google-genai SDK (replacement for deprecated google-generativeai).
"""

import json
from typing import Dict, Any, AsyncGenerator, List, Optional, Tuple
import asyncio
import logging

from ...base import ServiceType
from ...providers import GoogleBaseService
from ...services import InferenceService, ToolCallingResult

logger = logging.getLogger(__name__)


class GeminiInferenceService(InferenceService, GoogleBaseService):
    """
    Gemini inference service using unified architecture.

    Gemini is Google's latest multimodal AI model with:
    - Advanced reasoning capabilities
    - Long context windows
    - Multimodal understanding (text, images, video, audio)
    - Native code generation
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the Gemini inference service."""
        GoogleBaseService.__init__(self, config, ServiceType.INFERENCE, "gemini")

        self.temperature = self._get_temperature(default=0.7)
        self.max_tokens = self._get_max_tokens(default=2048)
        self.top_p = self._get_top_p(default=1.0)
        self.top_k = self._get_top_k(default=40)
        self.disable_safety = config.get('disable_safety', False)

        self._genai_client = None

    def _get_client(self):
        """Get or create the Google GenAI client."""
        if self._genai_client is None:
            from google import genai
            import os

            api_key = self._resolve_api_key("GOOGLE_API_KEY")
            if api_key:
                os.environ["GOOGLE_API_KEY"] = api_key

            self._genai_client = genai.Client()
        return self._genai_client

    def _build_config(self, system_instruction: Optional[str] = None, web_search: bool = False, **kwargs):
        """Build GenerateContentConfig from parameters."""
        from google.genai import types

        config_params = {
            "temperature": kwargs.get('temperature', self.temperature),
            "max_output_tokens": kwargs.get('max_tokens', self.max_tokens),
            "top_p": kwargs.get('top_p', self.top_p),
            "top_k": kwargs.get('top_k', self.top_k),
        }

        if system_instruction:
            config_params["system_instruction"] = system_instruction

        # Enable Google Search grounding when web search is requested
        if web_search:
            config_params["tools"] = [types.Tool(google_search=types.GoogleSearch())]

        if self.disable_safety:
            config_params["safety_settings"] = [
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
            ]

        return types.GenerateContentConfig(**config_params)

    @staticmethod
    def _extract_system_and_contents(
        messages: List[Dict[str, Any]],
    ) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        """Split an OpenAI-format messages list into a Gemini system instruction and contents.

        Gemini requires:
        - system prompt passed separately as system_instruction (not in contents)
        - role "assistant" renamed to "model"
        - each turn wrapped as {"role": ..., "parts": [{"text": ...}]}
        """
        system_instruction = None
        contents = []
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            if role == 'system':
                system_instruction = content
            elif role == 'user':
                contents.append({"role": "user", "parts": [{"text": content}]})
            elif role == 'assistant':
                contents.append({"role": "model", "parts": [{"text": content}]})
        return system_instruction, contents

    def _extract_text(self, response) -> str:
        """Extract text from a Gemini response, with error checking."""
        if not response.candidates:
            raise ValueError("No candidates returned from Gemini")

        candidate = response.candidates[0]

        # Check finish reason
        finish_reason = getattr(candidate, 'finish_reason', None)
        if finish_reason == 2:  # SAFETY
            raise ValueError("Response blocked due to safety concerns")
        elif finish_reason == 3:  # RECITATION
            raise ValueError("Response blocked due to recitation concerns")
        elif finish_reason == 4:  # OTHER
            raise ValueError("Response blocked for other reasons")

        if not candidate.content or not candidate.content.parts:
            raise ValueError("No content parts in response")

        first_part = candidate.content.parts[0]
        if not hasattr(first_part, 'text') or not first_part.text:
            raise ValueError("No text content in response part")

        return first_part.text

    async def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> ToolCallingResult:
        """Single round of tool-enabled generation using the Gemini API."""
        if not self.initialized:
            await self.initialize()

        from google.genai import types as gtypes

        # Convert OpenAI-format tools to Gemini FunctionDeclarations.
        # Strip JSON Schema meta-fields ($schema, $id, $defs, etc.) from the
        # parameters dict — Gemini's FunctionDeclaration Pydantic model uses
        # extra=forbid and rejects them (e.g. MCP servers include $schema).
        function_declarations = []
        for tool in tools:
            fn = tool.get("function", {})
            parameters = fn.get("parameters") or {"type": "object", "properties": {}}
            parameters = self._strip_schema_meta(parameters)
            function_declarations.append(
                gtypes.FunctionDeclaration(
                    name=fn.get("name", ""),
                    description=fn.get("description", ""),
                    parameters=parameters,
                )
            )

        # Convert messages, handling tool call history
        system_instruction, contents = self._extract_system_and_contents_for_tools(messages)

        client = self._get_client()

        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=self.model,
                contents=contents,
                config=gtypes.GenerateContentConfig(
                    temperature=kwargs.get("temperature", self.temperature),
                    max_output_tokens=kwargs.get("max_tokens", self.max_tokens),
                    system_instruction=system_instruction,
                    tools=[gtypes.Tool(function_declarations=function_declarations)],
                ),
            )
        except Exception as e:
            self._handle_google_error(e, "tool-calling generation")
            raise

        if not response.candidates:
            return ToolCallingResult(
                text=None,
                tool_calls=None,
                assistant_message={"role": "assistant", "content": None},
                finish_reason="stop",
            )

        candidate = response.candidates[0]
        text = None
        tool_calls_result = None
        function_call_parts = []

        for part in (candidate.content.parts if candidate.content else []):
            if hasattr(part, "function_call") and part.function_call:
                function_call_parts.append(part)
            elif hasattr(part, "text") and part.text:
                text = part.text

        if function_call_parts:
            tool_calls_result = []
            for part in function_call_parts:
                fc = part.function_call
                args = dict(fc.args) if fc.args else {}
                tool_calls_result.append({
                    "id": f"gemini_{fc.name}",
                    "name": fc.name,
                    "arguments": args,
                })

        # Build OpenAI-format assistant message for the loop.
        # Also stash the raw Gemini Content under _gemini_raw_content so that
        # _extract_system_and_contents_for_tools can echo it back verbatim on
        # the next round. Thinking models (gemini-3.1-pro-preview and similar)
        # embed a thought_signature in function_call Parts; reconstructing the
        # parts from the OpenAI format drops it and causes a 400 on round 2+.
        assistant_msg: Dict[str, Any] = {"role": "assistant", "content": text}
        if tool_calls_result:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"]),
                    },
                }
                for tc in tool_calls_result
            ]
        if candidate.content is not None:
            assistant_msg["_gemini_raw_content"] = candidate.content

        return ToolCallingResult(
            text=text,
            tool_calls=tool_calls_result,
            assistant_message=assistant_msg,
            finish_reason=str(getattr(candidate, "finish_reason", "stop")),
        )

    @staticmethod
    def _extract_system_and_contents_for_tools(
        messages: List[Dict[str, Any]],
    ) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        """Convert OpenAI messages (including tool history) to Gemini contents format."""
        system_instruction = None
        contents = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            role = msg.get("role", "user")
            if role == "system":
                system_instruction = msg.get("content", "")
            elif role == "assistant":
                # Prefer the raw Gemini Content when available — it preserves
                # thought_signature in function_call Parts, which thinking models
                # (e.g. gemini-3.1-pro-preview) require to be echoed back verbatim.
                raw = msg.get("_gemini_raw_content")
                if raw is not None:
                    contents.append(raw)
                else:
                    # Fallback: reconstruct from OpenAI-format fields (no thought_signature,
                    # works for non-thinking models or single-round calls).
                    import json as _json
                    parts = []
                    if msg.get("content"):
                        parts.append({"text": msg["content"]})
                    for tc in msg.get("tool_calls", []):
                        parts.append({
                            "function_call": {
                                "name": tc["function"]["name"],
                                "args": _json.loads(tc["function"].get("arguments") or "{}"),
                            }
                        })
                    if parts:
                        contents.append({"role": "model", "parts": parts})
            elif role == "tool":
                # Collect consecutive tool results into one user turn
                fn_responses = []
                while i < len(messages) and messages[i].get("role") == "tool":
                    t = messages[i]
                    # Find the original tool name from previous assistant turn
                    fn_name = t.get("name", "tool")
                    fn_responses.append({
                        "function_response": {
                            "name": fn_name,
                            "response": {"result": t.get("content", "")},
                        }
                    })
                    i += 1
                contents.append({"role": "user", "parts": fn_responses})
                continue
            else:
                contents.append({"role": "user", "parts": [{"text": msg.get("content", "")}]})
            i += 1
        return system_instruction, contents

    @staticmethod
    def _strip_schema_meta(schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove JSON Schema meta-fields that Gemini's FunctionDeclaration rejects.

        MCP servers commonly include '$schema', '$id', '$defs', and similar
        draft-07 annotations. Gemini's Pydantic model uses extra=forbid so
        any unknown key raises a ValidationError. We strip them recursively
        so nested property schemas are also cleaned.
        """
        if not isinstance(schema, dict):
            return schema
        cleaned = {}
        for k, v in schema.items():
            if k.startswith("$"):
                continue  # drop $schema, $id, $defs, $ref meta-fields
            if isinstance(v, dict):
                v = GeminiInferenceService._strip_schema_meta(v)
            elif isinstance(v, list):
                v = [
                    GeminiInferenceService._strip_schema_meta(item) if isinstance(item, dict) else item
                    for item in v
                ]
            cleaned[k] = v
        return cleaned

    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate response using Gemini."""
        if not self.initialized:
            await self.initialize()

        try:
            kwargs.pop('api_key', None)
            messages = kwargs.pop('messages', None)
            web_search = kwargs.pop('web_search', False)
            client = self._get_client()

            if messages:
                system_instruction, contents = self._extract_system_and_contents(messages)
                config = self._build_config(system_instruction=system_instruction, web_search=web_search, **kwargs)
            else:
                contents = prompt
                config = self._build_config(web_search=web_search, **kwargs)

            response = await asyncio.to_thread(
                client.models.generate_content,
                model=self.model,
                contents=contents,
                config=config,
            )

            return self._extract_text(response)

        except Exception as e:
            self._handle_google_error(e, "text generation")
            raise

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Generate streaming response using Gemini."""
        if not self.initialized:
            await self.initialize()

        try:
            kwargs.pop('api_key', None)
            messages = kwargs.pop('messages', None)
            web_search = kwargs.pop('web_search', False)
            client = self._get_client()

            if messages:
                system_instruction, contents = self._extract_system_and_contents(messages)
                config = self._build_config(system_instruction=system_instruction, web_search=web_search, **kwargs)
            else:
                contents = prompt
                config = self._build_config(web_search=web_search, **kwargs)

            response_iter = client.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=config,
            )

            for chunk in response_iter:
                if chunk.candidates and chunk.candidates[0].content and chunk.candidates[0].content.parts:
                    part = chunk.candidates[0].content.parts[0]
                    if hasattr(part, 'text') and part.text:
                        yield part.text
                        await asyncio.sleep(0)

        except Exception as e:
            self._handle_google_error(e, "streaming generation")
            yield f"Error: {str(e)}"
