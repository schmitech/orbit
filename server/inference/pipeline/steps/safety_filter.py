"""
Safety Filter Step

This step checks message safety using guardrail services before processing.
"""

import logging
from typing import Dict, Any
from ..base import PipelineStep, ProcessingContext

class SafetyFilterStep(PipelineStep):
    """
    Check message safety using guardrail service.
    
    This step validates incoming messages for security violations
    before they are processed by the LLM.
    """
    
    def should_execute(self, context: ProcessingContext) -> bool:
        """
        Determine if this step should execute.
        
        Returns:
            True if guardrail service is available and message is not already blocked
        """
        return (self.container.has('llm_guard_service') or 
                self.container.has('moderator_service')) and not context.is_blocked
    
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        """
        Process the context and check message safety.
        
        Args:
            context: The processing context
            
        Returns:
            The modified context
        """
        if context.is_blocked:
            return context
        
        self.logger.debug(f"Checking safety for message: {context.message[:100]}...")
        
        # Check with LLM Guard service first if available
        if self.container.has('llm_guard_service'):
            try:
                llm_guard = self.container.get('llm_guard_service')
                
                # Prepare metadata for the security check
                metadata = {}
                if context.session_id:
                    metadata["session_id"] = context.session_id
                
                # Perform LLM Guard security check
                security_result = await llm_guard.check_security(
                    content=context.message,
                    content_type="prompt",
                    user_id=context.user_id,
                    metadata=metadata
                )
                
                if not security_result.get("is_safe", True):
                    self.logger.warning(f"Message blocked by LLM Guard: {security_result.get('flagged_scanners', [])}")
                    context.set_error("Message blocked by security scanner", block=True)
                    return context
                    
            except Exception as e:
                self.logger.error(f"Error during LLM Guard check: {str(e)}")
                # Continue with other checks on error
        
        # Check with Moderator Service if available
        if self.container.has('moderator_service'):
            try:
                moderator = self.container.get('moderator_service')
                is_safe, refusal_message = await moderator.check_safety(context.message)
                
                if not is_safe:
                    self.logger.warning(f"Message blocked by Moderator Service: {refusal_message}")
                    context.set_error("Message blocked by content moderator", block=True)
                    return context
                    
            except Exception as e:
                self.logger.error(f"Error during Moderator Service check: {str(e)}")
                # Continue processing on error
        
        self.logger.debug("Message passed safety checks")
        return context 