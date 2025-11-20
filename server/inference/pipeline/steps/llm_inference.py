"""
LLM Inference Step

This step handles the core language model generation.
"""

import logging
from typing import Dict, Any, AsyncGenerator, Optional, List
from ..base import PipelineStep, ProcessingContext

class LLMInferenceStep(PipelineStep):
    """
    Generate response using LLM.

    This step is responsible for the core language model inference,
    including prompt building and response generation.
    """

    def __init__(self, container):
        """Initialize the LLM inference step."""
        super().__init__(container)
        self._prompt_cache = {}  # In-memory cache for system prompts when prompt_service unavailable
    
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
        
        self.logger.debug("Generating LLM response")
        debug_enabled = self.logger.isEnabledFor(logging.DEBUG)

        try:
            llm_provider = None
            if context.inference_provider:
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
                self.logger.debug("Sending prompt to LLM: %r", full_prompt)
            
            # Generate response with message format support
            kwargs = {}
            if hasattr(context, 'messages') and context.messages:
                kwargs['messages'] = context.messages

            response = await llm_provider.generate(full_prompt, **kwargs)
            context.response = response

            if debug_enabled:
                self.logger.debug("Full LLM response: %r", response)
            else:
                self.logger.debug("Generated response preview: %s...", response[:100])
            
        except Exception as e:
            self.logger.error(f"Error during LLM inference: {str(e)}")
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
        
        self.logger.debug("Generating streaming LLM response")
        debug_enabled = self.logger.isEnabledFor(logging.DEBUG)

        try:
            llm_provider = None
            if context.inference_provider:
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
                self.logger.debug("Sending streaming prompt to LLM: %r", full_prompt)
            
            # Generate streaming response with message format support
            kwargs = {}
            if hasattr(context, 'messages') and context.messages:
                kwargs['messages'] = context.messages

            accumulated_response = ""
            async for chunk in llm_provider.generate_stream(full_prompt, **kwargs):
                accumulated_response += chunk
                yield chunk
            
            context.response = accumulated_response
            
            if debug_enabled:
                self.logger.debug("Full streaming LLM response: %r", accumulated_response)
            else:
                self.logger.debug("Generated streaming response preview: %s...", accumulated_response[:100])
            
        except Exception as e:
            self.logger.error(f"Error during streaming LLM inference: {str(e)}")
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

        # Always return traditional concatenated format as fallback
        # The messages array (if built) will be passed via kwargs to providers
        return await self._build_traditional_prompt(context)

    def _should_use_message_format(self, context: ProcessingContext) -> bool:
        """
        Determine if we should use message-based format.

        Args:
            context: The processing context

        Returns:
            True if message format should be used
        """
        # Use message format for passthrough adapters with conversation history
        if context.adapter_name and self.container.has('adapter_manager'):
            adapter_manager = self.container.get('adapter_manager')
            adapter_config = adapter_manager.get_adapter_config(context.adapter_name)
            if adapter_config and adapter_config.get('type') == 'passthrough':
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
        parts = []

        # Get base system prompt
        system_prompt = await self._get_system_prompt(context)
        parts.append(system_prompt)

        # Add time instruction if available
        time_instruction = self._build_time_instruction(context)
        if time_instruction:
            parts.append(time_instruction)

        # Add language instruction if needed
        language_instruction = self._build_language_instruction(context)
        if language_instruction:
            parts.append(language_instruction)

        # Add chart instruction
        chart_instruction = self._build_chart_instruction()
        if chart_instruction:
            parts.append(chart_instruction)

        # Add file/document content for file-based adapters (CRITICAL FIX)
        # For message format, the file content MUST be in the system message
        if context.formatted_context:
            # Check if this is a file/multimodal adapter
            is_file_or_multimodal = context.adapter_name and ('file' in context.adapter_name.lower() or 'multimodal' in context.adapter_name.lower())

            if is_file_or_multimodal:
                # Add file content to system message for file adapters
                parts.append(f"\n## UPLOADED FILE CONTENT\n\nThe user has uploaded a file. Here is the content:\n\n{context.formatted_context}\n\n## END OF FILE CONTENT\n")
                parts.append("\n<IMPORTANT>\nThe content above is from the user's uploaded file. When they ask questions, answer based on this file content. The file content is provided in the system message above.\n</IMPORTANT>")
            else:
                # For non-file adapters, add regular context instructions
                parts.append("\n<IMPORTANT>\nWhen answering, prioritize information from the 'Context' section. Use the provided context to answer accurately while maintaining your conversational style. If the context contains the answer, provide it clearly. If the answer is not in the context or system prompt, acknowledge that you don't have that specific information.\n</IMPORTANT>")
        else:
            # For passthrough adapters without context, include conversation-specific instructions
            parts.append("\n<IMPORTANT>\nAnswer based on the information in the system prompt. Maintain your persona and conversational style. If the user's input doesn't seem to be a question, provide a brief acknowledgement.\n</IMPORTANT>")

        return "\n".join(parts)

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

        # Build context section
        context_section = ""
        if context.formatted_context:
            # Add clearer label for file/multimodal adapters
            is_file_or_multimodal = context.adapter_name and ('file' in context.adapter_name.lower() or 'multimodal' in context.adapter_name.lower())
            if is_file_or_multimodal:
                context_section = f"\n**FILE CONTENT (The user has uploaded this file and is asking about it):**\n\n{context.formatted_context}\n\n**END OF FILE CONTENT**\n\nREMEMBER: The content above IS the file the user is asking about. Answer questions about what's in this file based on the content shown above."
            else:
                context_section = f"\nContext:\n{context.formatted_context}"

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

        # Add explicit instruction right before the question
        if context.formatted_context:
            is_file_or_multimodal = context.adapter_name and ('file' in context.adapter_name.lower() or 'multimodal' in context.adapter_name.lower())
            if is_file_or_multimodal:
                parts.append("\n<CRITICAL INSTRUCTION>\nThe user has uploaded a file and is asking about it. The FILE CONTENT is shown above between 'FILE CONTENT' and 'END OF FILE CONTENT'. You MUST answer their question using the file content shown above. Do NOT say you don't see a file - the file content is RIGHT ABOVE in the 'FILE CONTENT' section. Answer based on what's in the file content.\n</CRITICAL INSTRUCTION>")
            else:
                parts.append("\n<IMPORTANT>\nWhen answering, prioritize information from the 'Context' section above. Use the provided context to answer accurately while maintaining your conversational style. If the context contains the answer, provide it clearly. If the answer is not in the context or system prompt, acknowledge that you don't have that specific information.\n</IMPORTANT>")
        else:
            parts.append("\n<IMPORTANT>\nAnswer based on the information in the system prompt. Maintain your persona and conversational style. If the user's input doesn't seem to be a question, provide a brief acknowledgement.\n</IMPORTANT>")

        parts.append(f"\nUser: {context.message}")
        parts.append("Assistant:")

        return "\n".join(parts)
    
    def _build_time_instruction(self, context: ProcessingContext) -> str:
        """
        Build time instruction based on clock service and context.
        """
        if not self.container.has('clock_service'):
            return ""
            
        clock_service = self.container.get('clock_service')
        if not clock_service or not clock_service.enabled:
            return ""
            
        timezone = getattr(context, 'timezone', None)
        current_time_str = clock_service.get_current_time_str(timezone)
        
        if current_time_str:
            return f"System: The current date and time is {current_time_str}."
        
        return ""
    
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
        if not context.system_prompt_id:
            return "You are a helpful assistant."

        # Check in-memory cache first (for cases where prompt_service is unavailable)
        cache_key = f"prompt:{context.system_prompt_id}"
        if cache_key in self._prompt_cache:
            self.logger.debug(f"Using in-memory cached system prompt for {context.system_prompt_id}")
            return self._prompt_cache[cache_key]

        # Fetch from prompt service (which has its own Redis caching)
        if self.container.has('prompt_service'):
            try:
                prompt_service = self.container.get('prompt_service')
                # This call already uses Redis caching internally
                prompt_doc = await prompt_service.get_prompt_by_id(context.system_prompt_id)
                if prompt_doc:
                    prompt_text = prompt_doc.get('prompt', '')
                    # Only cache in memory as a fallback
                    self._prompt_cache[cache_key] = prompt_text
                    return prompt_text
            except Exception as e:
                self.logger.warning(f"Failed to retrieve system prompt: {str(e)}")

        return "You are a helpful assistant."
    
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
        config = self.container.get_or_none('config') or {}
        lang_detect_config = config.get('language_detection', {})
        language_detection_enabled = lang_detect_config.get('enabled', False)
        
        if not language_detection_enabled:
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("Language detection disabled - no instruction added")
            return ""
        
        detected_language = getattr(context, 'detected_language', None)
        detection_meta = getattr(context, 'language_detection_meta', {}) or {}
        # Config thresholds
        min_conf = lang_detect_config.get('min_confidence', 0.8)
        prefer_ascii_en = lang_detect_config.get('prefer_english_for_ascii', True)
        
        if not detected_language:
            # No detection available, prefer safe default to English for ASCII-only messages
            msg = context.message or ""
            ascii_ratio = (sum(1 for c in msg if ord(c) < 128) / len(msg)) if msg else 1.0
            if prefer_ascii_en and ascii_ratio > 0.95:
                return "\nIMPORTANT: Reply entirely in English. Do not include any other language."
            return "\nIMPORTANT: Reply in the same language the user is using. Always match the user's language. Do not provide translations or explanations in other languages."
        
        # Language-specific instructions for better consistency
        language_names = {
            'en': 'English',
            'es': 'Spanish',
            'fr': 'French',
            'de': 'German',
            'it': 'Italian',
            'pt': 'Portuguese',
            'nl': 'Dutch',
            'ru': 'Russian',
            'zh': 'Chinese',
            'ja': 'Japanese',
            'ko': 'Korean',
            'ar': 'Arabic',
            'hi': 'Hindi',
            'th': 'Thai',
            'el': 'Greek',
            'he': 'Hebrew'
        }
        
        language_name = language_names.get(detected_language, detected_language.upper())

        # If detection is low-confidence or heuristic, default to a safe English instruction for ASCII text
        method = detection_meta.get('method') or detection_meta.get('method', '')
        confidence = float(detection_meta.get('confidence', 0.0))
        msg = context.message or ""
        ascii_ratio = (sum(1 for c in msg if ord(c) < 128) / len(msg)) if msg else 1.0

        low_conf_or_heuristic = confidence < min_conf or method in (
            'threshold_fallback', 'heuristic_ascii_bias', 'all_backends_failed', 'length_fallback'
        )
        if prefer_ascii_en and ascii_ratio > 0.95 and low_conf_or_heuristic:
            return "\nIMPORTANT: The user's message appears to be in English or ambiguous. Default to English and respond entirely in English. Do not include translations or any non-English text."
        
        # More specific instruction based on detected language
        # If detection says English, enforce English strongly
        if detected_language == 'en':
            return "\nIMPORTANT: Respond entirely in English. Do not include any non-English words or translations."

        # For non-English detection with high confidence, instruct to respond in detected language
        # BUT add safety check for low confidence or when user seems to be writing English
        if confidence >= 0.85 and method not in ('threshold_fallback', 'heuristic_ascii_bias', 'sticky_previous'):
            instruction = f"\nIMPORTANT: The user is writing in {language_name}. You must respond entirely in {language_name}. Do not include translations, explanations in other languages, or bilingual responses. Write naturally as a native {language_name} speaker would."
        else:
            # For low confidence non-English detection, let the model decide based on actual content
            instruction = "\nIMPORTANT: Match the language of the user's message. If the user is writing in English, respond in English. If they're writing in another language, respond in that same language."
        
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("Using language instruction for %s (%s)", language_name, detected_language)
        
        return instruction
    
    """
    Chart formatting instruction for LLM prompts.
    This function can be integrated into your LLM system prompt or instructions.
    """
    def _build_chart_instruction(self) -> str:
        """
        Build chart formatting instruction for LLM.
        
        Returns:
            Chart instruction string that teaches the LLM how to format charts
            for the markdown renderer with recharts support, while clearly
            distinguishing tables from charts.
        """
        return (
            "<CHART_FORMATTING>\n"
            "## IMPORTANT: Tables vs Charts\n"
            "\n"
            "**TABLES**: When the user requests a 'table', 'data table', 'formatted table', or 'markdown table', "
            "ALWAYS use standard markdown table syntax. DO NOT use chart code blocks for tables.\n"
            "\n"
            "Example for table request:\n"
            "```\n"
            "| Column 1 | Column 2 | Column 3 |\n"
            "|----------|----------|----------|\n"
            "| Value 1  | Value 2  | Value 3  |\n"
            "| Value 4  | Value 5  | Value 6  |\n"
            "```\n"
            "\n"
            "**CHARTS**: Only use chart code blocks when the user explicitly requests:\n"
            "- A 'chart', 'graph', 'bar chart', 'line chart', 'pie chart', etc.\n"
            "- A 'visualization' or 'data visualization'\n"
            "- A 'plot' or 'diagram'\n"
            "- NOT when they ask for a 'table'\n"
            "\n"
            "## Chart Format Options:\n"
            "\n"
            "### 1. Simple Format (for basic charts):\n"
            "```chart\n"
            "type: bar\n"
            "title: Sales by Quarter\n"
            "data: [45000, 52000, 48000, 60000]\n"
            "labels: [Q1, Q2, Q3, Q4]\n"
            "colors: [#3b82f6, #8b5cf6, #ec4899, #f59e0b]\n"
            "```\n"
            "\n"
            "### 2. Table Format (recommended for multi-series data):\n"
            "```chart\n"
            "type: line\n"
            "title: Revenue vs Expenses\n"
            "| Month | Revenue | Expenses |\n"
            "|-------|---------|----------|\n"
            "| Jan   | 100000  | 80000    |\n"
            "| Feb   | 150000  | 90000    |\n"
            "| Mar   | 200000  | 110000   |\n"
            "```\n"
            "\n"
            "## Supported Chart Types:\n"
            "- **bar**: For comparing values across categories\n"
            "- **line**: For showing trends over time\n"
            "- **pie**: For showing proportions/percentages\n"
            "- **area**: For showing cumulative trends\n"
            "- **scatter**: For showing relationships between variables\n"
            "\n"
            "## Guidelines:\n"
            "- **Use markdown tables** when user asks for a 'table' or 'data table'\n"
            "- **Use chart code blocks** only when user explicitly asks for a chart/graph/visualization\n"
            "- Use table format for multiple data series in charts (easier to read)\n"
            "- Include descriptive titles\n"
            "- Labels can contain spaces (e.g., \"Product A\", \"Direct Sales\")\n"
            "- Colors support hex codes (e.g., #3b82f6, #10b981)\n"
            "- Always specify the chart type\n"
            "- Use appropriate chart types for the data context\n"
            "\n"
            "## Example Usage:\n"
            "\n"
            "**When user asks: \"Show me a table of quarterly sales\"**\n"
            "Output:\n"
            "```\n"
            "| Quarter | Sales |\n"
            "|---------|-------|\n"
            "| Q1      | 45000 |\n"
            "| Q2      | 52000 |\n"
            "| Q3      | 48000 |\n"
            "| Q4      | 60000 |\n"
            "```\n"
            "\n"
            "**When user asks: \"Show me a chart of quarterly sales\"**\n"
            "Output:\n"
            "```chart\n"
            "type: bar\n"
            "title: Quarterly Sales Performance\n"
            "data: [45000, 52000, 48000, 60000]\n"
            "labels: [Q1, Q2, Q3, Q4]\n"
            "```\n"
            "</CHART_FORMATTING>\n"
        )
