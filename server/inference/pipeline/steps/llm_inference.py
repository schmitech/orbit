"""
LLM Inference Step

This step handles the core language model generation.
"""

import logging
from collections import OrderedDict
from typing import AsyncGenerator

from ai_services.errors import sanitize_provider_error
from ..base import PipelineStep, ProcessingContext
from ..prompt_builder import PromptInstructionBuilder
from ..mcp_tool_loop import run_tool_calling_loop
from ._utils import NO_LLM_ADAPTER_TYPES, record_usage

logger = logging.getLogger(__name__)

class LLMInferenceStep(PipelineStep):
    """
    Generate response using LLM.

    This step is responsible for the core language model inference,
    including prompt building and response generation.
    """

    def __init__(self, container):
        """Initialize the LLM inference step."""
        super().__init__(container)
        self._prompt_cache: OrderedDict[str, str] = OrderedDict()  # LRU cache for system prompts (max 100)
        self._prompt_cache_max_size = 100

    async def _resolve_llm_provider(self, context: ProcessingContext):
        """Resolve the LLM provider for this request, preferring adapter overrides."""
        if self.container.has('adapter_manager'):
            adapter_manager = self.container.get('adapter_manager')
            adapter_name = getattr(context, 'adapter_name', None)
            # Runtime model override (from request body) takes priority over adapter config
            if context.runtime_provider and context.runtime_model_name:
                return await adapter_manager.get_overridden_provider(
                    context.runtime_provider,
                    adapter_name,
                    explicit_model_override=context.runtime_model_name,
                    explicit_param_overrides=context.runtime_param_overrides,
                )
            if context.inference_provider:
                return await adapter_manager.get_overridden_provider(
                    context.inference_provider, adapter_name
                )
        return self.container.get('llm_provider')

    def _create_prompt_builder(self) -> PromptInstructionBuilder:
        """Create a shared prompt builder backed by the pipeline services."""
        return PromptInstructionBuilder(
            config=self.container.get_or_none('config') or {},
            prompt_service=self.container.get_or_none('prompt_service'),
            clock_service=self.container.get_or_none('clock_service'),
            prompt_cache=self._prompt_cache,
            prompt_cache_max_size=self._prompt_cache_max_size,
            builder_logger=self.logger,
        )

    def clear_prompt_cache(self, prompt_id: str = None) -> int:
        """Clear in-memory system prompt cache entries held by this step."""
        return self._create_prompt_builder().clear_prompt_cache(prompt_id)
    
    def should_execute(self, context: ProcessingContext) -> bool:
        """
        Determine if this step should execute.

        Returns:
            True if LLM provider is available, not blocked, and not an image generation adapter
        """
        if not self.container.has('llm_provider') or context.is_blocked:
            return False
        # Defer to ImageGenerationStep for image generation adapters
        if context.adapter_name and self.container.has('adapter_manager'):
            try:
                adapter_manager = self.container.get('adapter_manager')
                adapter_config = adapter_manager.get_adapter_config(context.adapter_name)
                if adapter_config and adapter_config.get('type') in NO_LLM_ADAPTER_TYPES:
                    return False
            except Exception:
                pass
        return True
    
    def supports_streaming(self) -> bool:
        """This step supports streaming responses."""
        return True
    
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        """
        Process the context and generate LLM response.
        
        Args:
            context: The processing context
            
        Returns:
            The modified context with generated response
        """
        if context.is_blocked:
            return context
        
        logger.debug("Generating LLM response")
        debug_enabled = self.logger.isEnabledFor(logging.DEBUG)

        try:
            llm_provider = await self._resolve_llm_provider(context)
            if llm_provider is None:
                context.set_error("No LLM provider available: check adapter and provider configuration")
                return context

            if self._should_run_mcp_tools(context):
                try:
                    if await self._run_inline_mcp_tools(context, llm_provider):
                        return context
                except NotImplementedError:
                    logger.warning(
                        "Adapter '%s' has mcp_tools enabled but provider '%s' does not "
                        "support generate_with_tools; falling back to plain generation.",
                        context.adapter_name, self._effective_provider_name(context),
                    )

            # Build the full prompt
            full_prompt = await self._build_prompt(context)
            context.full_prompt = full_prompt

            if debug_enabled:
                logger.debug("Sending prompt to LLM: %r", full_prompt)

            # Generate response with message format support
            kwargs = {}
            if hasattr(context, 'messages') and context.messages:
                kwargs['messages'] = context.messages
            if getattr(context, 'web_search', False):
                kwargs['web_search'] = True

            usage_sink: dict = {}
            response = await llm_provider.generate_tracked(
                full_prompt,
                usage_sink=usage_sink,
                cache_prefix_len=context.cacheable_prefix_len,
                **kwargs,
            )
            context.response = response
            self._record_usage(context, usage_sink)

            if debug_enabled:
                logger.debug("Full LLM response: %r", response)
            else:
                logger.debug("Generated response preview: %s...", response[:100])
            
        except Exception as e:
            logger.exception("Error during LLM inference")
            user_message = sanitize_provider_error(
                e,
                provider=getattr(context, 'inference_provider', None),
                operation="text generation",
            )
            context.set_error(user_message)

        return context
    
    async def process_stream(self, context: ProcessingContext) -> AsyncGenerator[str, None]:
        """
        Process the context for streaming response.
        
        Args:
            context: The processing context
            
        Yields:
            Response chunks as they are generated
        """
        if context.is_blocked:
            return
        
        logger.debug("Generating streaming LLM response")
        debug_enabled = self.logger.isEnabledFor(logging.DEBUG)

        try:
            llm_provider = await self._resolve_llm_provider(context)
            if llm_provider is None:
                error_msg = "No LLM provider available: check adapter and provider configuration"
                context.set_error(error_msg)
                yield error_msg
                return

            if self._should_run_mcp_tools(context):
                try:
                    if await self._run_inline_mcp_tools(context, llm_provider):
                        yield context.response
                        return
                except NotImplementedError:
                    logger.warning(
                        "Adapter '%s' has mcp_tools enabled but provider '%s' does not "
                        "support generate_with_tools; falling back to plain generation.",
                        context.adapter_name, self._effective_provider_name(context),
                    )

            # Build the full prompt
            full_prompt = await self._build_prompt(context)
            context.full_prompt = full_prompt

            if debug_enabled:
                logger.debug("Sending streaming prompt to LLM: %r", full_prompt)
            
            # Generate streaming response with message format support
            kwargs = {}
            if hasattr(context, 'messages') and context.messages:
                kwargs['messages'] = context.messages
            if getattr(context, 'web_search', False):
                kwargs['web_search'] = True

            accumulated_response = ""
            llm_chunk_count = 0
            usage_sink: dict = {}
            cancelled = False
            async for chunk in llm_provider.generate_stream_tracked(
                full_prompt,
                usage_sink=usage_sink,
                cache_prefix_len=context.cacheable_prefix_len,
                **kwargs,
            ):
                # Check for cancellation before yielding each chunk
                if context.is_cancelled():
                    logger.debug("[LLM_INFERENCE] >>> CANCELLATION DETECTED <<< after %d chunks, accumulated_chars=%d", llm_chunk_count, len(accumulated_response))
                    cancelled = True
                    break

                llm_chunk_count += 1
                accumulated_response += chunk
                yield chunk

            context.response = accumulated_response
            if not cancelled:
                self._record_usage(context, usage_sink)

            if debug_enabled:
                logger.debug("Full streaming LLM response: %r", accumulated_response)
            else:
                logger.debug("Generated streaming response preview: %s...", accumulated_response[:100])
            
        except Exception as e:
            logger.exception("Error during streaming LLM inference")
            user_message = sanitize_provider_error(
                e,
                provider=getattr(context, 'inference_provider', None),
                operation="streaming generation",
            )
            yield user_message
            context.set_error(user_message)
    
    def _should_run_mcp_tools(self, context: ProcessingContext) -> bool:
        """
        True if this adapter opportunistically wants inline MCP tool access
        AND at least one server it may reach opted into opportunistic mode.
        Provider tool-calling support is checked at call time
        (NotImplementedError fallback), not here, so an adapter can change
        inference_provider later without this check going stale.
        """
        if not getattr(context, 'mcp_tools', False):
            return False
        mcp_manager = self._get_mcp_manager()
        if mcp_manager is None:
            return False
        return bool(mcp_manager.opportunistic_servers(context.mcp_servers_allowlist))

    def _get_mcp_manager(self):
        """Get (or lazily initialize) the MCPClientManager from config."""
        config = self.container.get_or_none('config') or {}
        from services.mcp_client_service import get_mcp_client_manager
        return get_mcp_client_manager(config)

    @staticmethod
    def _effective_provider_name(context: ProcessingContext) -> str:
        """
        Return the provider name actually resolved for this request, for use
        in error/warning messages. context.runtime_provider (a per-request
        "model" override) takes priority over the adapter's static
        inference_provider, mirroring the same precedence _resolve_llm_provider
        uses — otherwise a fallback triggered by a runtime override would
        misleadingly blame the adapter's default provider instead of the one
        that actually failed.
        """
        return getattr(context, 'runtime_provider', None) or getattr(context, 'inference_provider', None) or '?'

    async def _run_inline_mcp_tools(self, context: ProcessingContext, llm_provider) -> bool:
        """
        Attempt the inline MCP tool-calling loop for an ordinary conversational
        adapter (no skill swap). Returns True if it fully handled the response
        (context.response/context.sources set), False if it could not run
        (e.g. no tools discovered) and the caller should fall back to the
        plain generate()/generate_stream() path.
        """
        mcp_manager = self._get_mcp_manager()
        tools = await mcp_manager.get_all_tools(
            allowed_servers=context.mcp_servers_allowlist,
            opportunistic_only=True,
        )
        if not tools:
            logger.warning(
                "mcp_tools enabled for adapter '%s' but no opportunistic MCP tools were discovered; "
                "falling back to plain generation.", context.adapter_name,
            )
            return False

        # Build the same message format used for native-chat-format providers,
        # so RAG/file context (formatted_context) is included exactly as it
        # is for the plain generate() path today.
        await self._build_message_format(context)

        usage_sink: dict = {}
        final_text, sources, _ = await run_tool_calling_loop(
            provider=llm_provider,
            mcp_manager=mcp_manager,
            messages=context.messages,
            tools=tools,
            max_iterations=mcp_manager.max_tool_iterations_for(
                mcp_manager.servers_in_tools(tools)
            ),
            cancel_event=context.cancel_event,
            is_cancelled=context.is_cancelled,
            usage_sink=usage_sink,
        )
        context.response = final_text or ""
        context.sources = (context.sources or []) + sources
        # Tokens are now summed across every provider call the loop made
        # (see accumulate_usage_sink). "partial" only means a genuine gap —
        # a cancelled loop, or a provider in the loop that never reports
        # usage at all — never a blanket assumption for every MCP request.
        provider_name = usage_sink.get("provider") or self._effective_provider_name(context)
        model_name = usage_sink.get("model") or getattr(context, 'runtime_model_name', None)
        partial = bool(context.is_cancelled()) or not usage_sink.get("reported")
        record_usage(
            self.container, context, usage_sink, provider_name, model_name,
            extra={"partial": partial, "calls": usage_sink.get("calls", 0), "source": "mcp_tools"},
        )
        return True

    def _record_usage(self, context: ProcessingContext, usage_sink: dict) -> None:
        """
        Turn a raw usage_sink (filled by generate_tracked/generate_stream_tracked)
        into context.metadata["usage"], adding a cost estimate from the pricing
        service when available. Never raises — usage/cost is best-effort.
        """
        provider = usage_sink.get("provider") or self._effective_provider_name(context)
        model = usage_sink.get("model") or getattr(context, 'runtime_model_name', None)
        record_usage(self.container, context, usage_sink, provider, model)

    def _uses_native_chat_format(self, context: ProcessingContext) -> bool:
        """Return True for providers/adapters that accept a structured messages array."""
        if context.adapter_name and self.container.has('adapter_manager'):
            adapter_manager = self.container.get('adapter_manager')
            adapter_config = adapter_manager.get_adapter_config(context.adapter_name)
            if adapter_config and adapter_config.get('type') == 'passthrough':
                return True
        inference_provider = getattr(context, 'inference_provider', None)
        if inference_provider and inference_provider.startswith('ollama'):
            return True
        return False

    async def _build_prompt(self, context: ProcessingContext) -> str:
        """Build the full prompt for LLM generation."""
        if self._uses_native_chat_format(context):
            await self._build_message_format(context)
            if hasattr(context, 'messages') and context.messages:
                system_content = context.messages[0].get('content', '')
                return f"{system_content}\n\nUser: {context.message}"
        context.messages = None
        return await self._build_traditional_prompt(context)

    async def _build_traditional_prompt(self, context: ProcessingContext) -> str:
        """Build a single concatenated prompt string for providers that don't accept a messages array."""
        builder = self._create_prompt_builder()
        system_content = await builder.build_system_message_content(context)

        parts = [system_content]

        if context.context_messages:
            history = []
            for msg in context.context_messages:
                role = msg.get('role', '').lower()
                content = msg.get('content', '')
                if role and content:
                    history.append(f"{role.title()}: {content}")
            if history:
                parts.append(f"\nConversation History:\n" + "\n".join(history))

        parts.append(f"\nUser: {context.message}")
        parts.append("Assistant:")
        return "\n".join(parts)

    async def _build_message_format(self, context: ProcessingContext) -> None:
        """
        Build messages array for providers that support native message format.

        Args:
            context: The processing context
        """
        messages = []

        # Build system message, tracking the cacheable (turn-invariant) prefix
        # length so a supporting provider can place a prompt-caching breakpoint.
        system_content, prefix_len = await self._create_prompt_builder().build_system_message(context)
        context.cacheable_prefix_len = prefix_len
        messages.append({"role": "system", "content": system_content})

        # Add conversation history
        if context.context_messages:
            for msg in context.context_messages:
                messages.append({
                    "role": msg.get('role', 'user'),
                    "content": msg.get('content', '')
                })

        # Add current user message
        messages.append({"role": "user", "content": context.message})

        # Store messages for provider to use
        context.messages = messages

    async def _build_system_message_content(self, context: ProcessingContext) -> str:
        """
        Build the content for the system message.

        Args:
            context: The processing context

        Returns:
            System message content
        """
        return await self._create_prompt_builder().build_system_message_content(context)
