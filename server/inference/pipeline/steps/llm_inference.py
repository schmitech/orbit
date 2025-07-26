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