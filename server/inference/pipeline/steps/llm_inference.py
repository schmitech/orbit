"""
LLM Inference Step

This step handles the core language model generation.
"""

import logging
from collections import OrderedDict
from typing import AsyncGenerator
from ..base import PipelineStep, ProcessingContext
from ..prompt_builder import PromptInstructionBuilder

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
    
    def should_execute(self, context: ProcessingContext) -> bool:
        """
        Determine if this step should execute.
        
        Returns:
            True if LLM provider is available and not blocked
        """
        return self.container.has('llm_provider') and not context.is_blocked
    
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
            llm_provider = None
            if context.inference_provider and self.container.has('adapter_manager'):
                # Get the adapter manager and get the cached/new provider
                adapter_manager = self.container.get('adapter_manager')
                # Pass adapter_name to get model-specific provider if configured
                adapter_name = getattr(context, 'adapter_name', None)
                llm_provider = await adapter_manager.get_overridden_provider(context.inference_provider, adapter_name)
            else:
                # Fallback to default provider
                llm_provider = self.container.get('llm_provider')

            # Build the full prompt
            full_prompt = await self._build_prompt(context)
            context.full_prompt = full_prompt

            if debug_enabled:
                logger.debug("Sending prompt to LLM: %r", full_prompt)

            # Generate response with message format support
            kwargs = {}
            if hasattr(context, 'messages') and context.messages:
                kwargs['messages'] = context.messages

            response = await llm_provider.generate(full_prompt, **kwargs)
            context.response = response

            if debug_enabled:
                logger.debug("Full LLM response: %r", response)
            else:
                logger.debug("Generated response preview: %s...", response[:100])
            
        except Exception as e:
            logger.error(f"Error during LLM inference: {str(e)}")
            context.set_error(f"Failed to generate response: {str(e)}")
        
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
            llm_provider = None
            if context.inference_provider and self.container.has('adapter_manager'):
                # Get the adapter manager and get the cached/new provider
                adapter_manager = self.container.get('adapter_manager')
                # Pass adapter_name to get model-specific provider if configured
                adapter_name = getattr(context, 'adapter_name', None)
                llm_provider = await adapter_manager.get_overridden_provider(context.inference_provider, adapter_name)
            else:
                # Fallback to default provider
                llm_provider = self.container.get('llm_provider')

            # Build the full prompt
            full_prompt = await self._build_prompt(context)
            context.full_prompt = full_prompt

            if debug_enabled:
                logger.debug("Sending streaming prompt to LLM: %r", full_prompt)
            
            # Generate streaming response with message format support
            kwargs = {}
            if hasattr(context, 'messages') and context.messages:
                kwargs['messages'] = context.messages

            accumulated_response = ""
            llm_chunk_count = 0
            async for chunk in llm_provider.generate_stream(full_prompt, **kwargs):
                # Check for cancellation before yielding each chunk
                if context.is_cancelled():
                    logger.debug(f"[LLM_INFERENCE] >>> CANCELLATION DETECTED <<< after {llm_chunk_count} chunks, accumulated_chars={len(accumulated_response)}")
                    break

                llm_chunk_count += 1
                accumulated_response += chunk
                # Uncomment to debug streaming
                # logger.debug(f"LLM_STREAM: Received chunk #{llm_chunk_count} from provider: {repr(chunk[:30]) if len(chunk) > 30 else repr(chunk)}")
                yield chunk

            context.response = accumulated_response
            
            if debug_enabled:
                logger.debug("Full streaming LLM response: %r", accumulated_response)
            else:
                logger.debug("Generated streaming response preview: %s...", accumulated_response[:100])
            
        except Exception as e:
            logger.error(f"Error during streaming LLM inference: {str(e)}")
            error_chunk = f"Error: {str(e)}"
            yield error_chunk
            context.set_error(f"Failed to generate streaming response: {str(e)}")
    
    async def _build_prompt(self, context: ProcessingContext) -> str:
        """
        Build the full prompt for LLM generation.

        Args:
            context: The processing context

        Returns:
            The complete prompt string
        """
        # Check if we should use message format (for passthrough adapters)
        if self._should_use_message_format(context):
            await self._build_message_format(context)
            # Return a simplified fallback prompt derived from the already-built messages
            # to avoid duplicate logging and work
            if hasattr(context, 'messages') and context.messages:
                # Extract system content from the first message (already built)
                system_content = context.messages[0].get('content', '') if context.messages else ''
                return f"{system_content}\n\nUser: {context.message}"

        # Build traditional concatenated format for non-message-format adapters
        return await self._build_traditional_prompt(context)

    def _should_use_message_format(self, context: ProcessingContext) -> bool:
        """
        Determine if we should use message-based format.

        Args:
            context: The processing context

        Returns:
            True if message format should be used
        """
        # Use message format for passthrough adapters
        if context.adapter_name and self.container.has('adapter_manager'):
            adapter_manager = self.container.get('adapter_manager')
            adapter_config = adapter_manager.get_adapter_config(context.adapter_name)
            if adapter_config and adapter_config.get('type') == 'passthrough':
                return True

        # Use message format for Ollama-based providers - smaller models perform
        # significantly better with structured system/user roles than with a single
        # concatenated prompt string in the user role
        inference_provider = getattr(context, 'inference_provider', None)
        if inference_provider and inference_provider.startswith('ollama'):
            return True

        return False

    async def _build_message_format(self, context: ProcessingContext) -> None:
        """
        Build messages array for providers that support native message format.

        Args:
            context: The processing context
        """
        messages = []

        # Build system message
        system_content = await self._build_system_message_content(context)
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

    async def _build_traditional_prompt(self, context: ProcessingContext) -> str:
        """
        Build traditional concatenated prompt (backward compatibility).

        Args:
            context: The processing context

        Returns:
            The complete prompt string
        """
        # Get system prompt
        system_prompt = await self._get_system_prompt(context)

        # Build conversation history
        history_text = self._format_conversation_history(context.context_messages)

        # Build context section wrapped in <context> tags
        context_section = ""
        if context.formatted_context:
            is_file_or_multimodal = context.adapter_name and ('file' in context.adapter_name.lower() or 'multimodal' in context.adapter_name.lower())
            if is_file_or_multimodal:
                context_section = f"\n<context>\n## UPLOADED FILE CONTENT\n\n{context.formatted_context}\n</context>"
            else:
                context_section = f"\n<context>\n{context.formatted_context}\n</context>"

        # Build the complete prompt
        parts = [system_prompt]

        # Add time instruction
        time_instruction = self._build_time_instruction(context)
        if time_instruction:
            parts.append(time_instruction)

        # Add language matching instruction based on detection
        language_instruction = self._build_language_instruction(context)
        if language_instruction:
            parts.append(language_instruction)

        # Add chart instruction
        chart_instruction = self._build_chart_instruction()
        if chart_instruction:
            parts.append(chart_instruction)

        if context_section:
            parts.append(context_section)

        if history_text:
            parts.append(f"\nConversation History:\n{history_text}")

        # Add concise instruction right before the question
        if context.formatted_context:
            is_file_or_multimodal = context.adapter_name and ('file' in context.adapter_name.lower() or 'multimodal' in context.adapter_name.lower())
            if is_file_or_multimodal:
                parts.append("\nAnswer using the uploaded file content in <context>. If the answer is not there, say so.")
            else:
                parts.append("\nPrioritize the <context> section when answering. If the answer is not there, say so.")
        else:
            parts.append("\nAnswer based on the system prompt. Maintain your persona.")

        parts.append(f"\nUser: {context.message}")
        parts.append("Assistant:")

        return "\n".join(parts)
    
    def _build_time_instruction(self, context: ProcessingContext) -> str:
        """
        Build time instruction based on clock service and context.

        Uses the clock service to generate a formatted time instruction
        that can be injected into the prompt. Supports per-adapter
        timezone and format overrides.

        Args:
            context: The processing context containing timezone and time_format

        Returns:
            Formatted time instruction string, or empty string if disabled
        """
        return self._create_prompt_builder().build_time_instruction(context)
    
    async def _get_system_prompt(self, context: ProcessingContext) -> str:
        """
        Get the system prompt for the context.

        The prompt_service already handles Redis caching internally,
        so we just need to call it and optionally cache in memory.

        Args:
            context: The processing context

        Returns:
            The system prompt string
        """
        return await self._create_prompt_builder().get_system_prompt(context)
    
    def _format_conversation_history(self, context_messages: list) -> str:
        """
        Format conversation history for the prompt.
        
        Args:
            context_messages: List of conversation messages
            
        Returns:
            Formatted conversation history
        """
        if not context_messages:
            return ""
        
        history = []
        for msg in context_messages:
            role = msg.get('role', '').lower()
            content = msg.get('content', '')
            if role and content:
                history.append(f"{role.title()}: {content}")
        
        return "\n".join(history)
    
    def _build_language_instruction(self, context: ProcessingContext) -> str:
        """
        Build language instruction based on detected language.
        
        Args:
            context: The processing context
            
        Returns:
            Language instruction string or empty string
        """
        return self._create_prompt_builder().build_language_instruction(context)
    
    def _build_chart_instruction(self) -> str:
        """
        Build compact chart formatting instruction for LLM.

        Returns:
            Chart instruction string for the markdown renderer with recharts support.
        """
        return self._create_prompt_builder().build_chart_instruction()
