"""
LLM Inference Step

This step handles the core language model generation.
"""

import logging
from typing import Dict, Any, AsyncGenerator
from ..base import PipelineStep, ProcessingContext

class LLMInferenceStep(PipelineStep):
    """
    Generate response using LLM.
    
    This step is responsible for the core language model inference,
    including prompt building and response generation.
    """
    
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
        
        try:
            llm_provider = None
            if context.inference_provider:
                # Get the adapter manager and get the cached/new provider
                adapter_manager = self.container.get('adapter_manager')
                llm_provider = await adapter_manager.get_overridden_provider(context.inference_provider)
            else:
                # Fallback to default provider
                llm_provider = self.container.get('llm_provider')

            # Build the full prompt
            full_prompt = await self._build_prompt(context)
            context.full_prompt = full_prompt
            
            # Debug: Log the prompt being sent
            config = self.container.get_or_none('config') or {}
            if config.get('general', {}).get('verbose', False):
                self.logger.info(f"DEBUG: Sending prompt to LLM: {repr(full_prompt)}")
            
            # Generate response
            response = await llm_provider.generate(full_prompt)
            context.response = response
            
            # Debug: Log the full response if verbose
            config = self.container.get_or_none('config') or {}
            if config.get('general', {}).get('verbose', False):
                self.logger.info(f"DEBUG: Full LLM response: {repr(response)}")
            else:
                self.logger.debug(f"Generated response: {response[:100]}...")
            
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
        
        try:
            llm_provider = None
            if context.inference_provider:
                # Get the adapter manager and get the cached/new provider
                adapter_manager = self.container.get('adapter_manager')
                llm_provider = await adapter_manager.get_overridden_provider(context.inference_provider)
            else:
                # Fallback to default provider
                llm_provider = self.container.get('llm_provider')

            # Build the full prompt
            full_prompt = await self._build_prompt(context)
            context.full_prompt = full_prompt
            
            # Debug: Log the prompt being sent
            config = self.container.get_or_none('config') or {}
            if config.get('general', {}).get('verbose', False):
                self.logger.info(f"DEBUG: Sending streaming prompt to LLM: {repr(full_prompt)}")
            
            # Generate streaming response
            accumulated_response = ""
            async for chunk in llm_provider.generate_stream(full_prompt):
                accumulated_response += chunk
                yield chunk
            
            context.response = accumulated_response
            
            # Debug: Log the full streaming response if verbose
            config = self.container.get_or_none('config') or {}
            if config.get('general', {}).get('verbose', False):
                self.logger.info(f"DEBUG: Full streaming LLM response: {repr(accumulated_response)}")
            else:
                self.logger.debug(f"Generated streaming response: {accumulated_response[:100]}...")
            
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
        # Get system prompt
        system_prompt = await self._get_system_prompt(context)
        
        # Build conversation history
        history_text = self._format_conversation_history(context.context_messages)
        
        # Build context section
        context_section = ""
        if context.formatted_context:
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
        
        if context_section:
            parts.append(context_section)
        
        if history_text:
            parts.append(f"\nConversation History:\n{history_text}")
        
        # Add explicit instruction right before the question
        if context.formatted_context:
            parts.append("\n<IMPORTANT>\nYou MUST answer using ONLY the information provided in the Context section above. Do NOT add any additional information, suggestions, or details that are not explicitly mentioned in the context. If the exact answer is in the context, provide it. If not, say you don't know.\n</IMPORTANT>")
        
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
        
        Args:
            context: The processing context
            
        Returns:
            The system prompt string
        """
        if context.system_prompt_id and self.container.has('prompt_service'):
            try:
                prompt_service = self.container.get('prompt_service')
                prompt_doc = await prompt_service.get_prompt_by_id(context.system_prompt_id)
                if prompt_doc:
                    return prompt_doc.get('prompt', '')
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
            # No language instruction if language detection is disabled
            if config.get('general', {}).get('verbose', False):
                self.logger.info("DEBUG: Language detection disabled - no language instruction added")
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
        
        if config.get('general', {}).get('verbose', False):
            self.logger.info(f"DEBUG: Using language instruction for {language_name} ({detected_language})")
        
        return instruction 
