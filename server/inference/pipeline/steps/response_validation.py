"""
Response Validation Step

This step validates the generated response for safety and quality.
"""

import logging
from typing import Dict, Any
from ..base import PipelineStep, ProcessingContext

class ResponseValidationStep(PipelineStep):
    """
    Perform safety check on the final generated response.
    
    This step validates the LLM-generated response for security violations,
    ensuring that unsafe content is not returned to users.
    """
    
    def should_execute(self, context: ProcessingContext) -> bool:
        """
        Determine if this step should execute.
        
        Returns:
            True if guardrail service is available, response exists, and not blocked
        """
        return (self.container.has('llm_guard_service') or 
                self.container.has('moderator_service')) and context.response and not context.is_blocked
    
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        """
        Process the context and validate the response.
        
        Args:
            context: The processing context
            
        Returns:
            The modified context
        """
        if context.is_blocked or not context.response:
            return context
        
        self.logger.debug(f"Validating response: {context.response[:100]}...")
        
        # Check with LLM Guard service first if available
        if self.container.has('llm_guard_service'):
            try:
                llm_guard = self.container.get('llm_guard_service')
                
                # Prepare metadata for the security check
                metadata = {}
                if context.session_id:
                    metadata["session_id"] = context.session_id
                
                # Perform LLM Guard security check on response
                security_result = await llm_guard.check_security(
                    content=context.response,
                    content_type="response",
                    user_id=context.user_id,
                    metadata=metadata
                )
                
                if not security_result.get("is_safe", True):
                    self.logger.warning(f"Response blocked by LLM Guard: {security_result.get('flagged_scanners', [])}")
                    context.set_error("Response blocked by security scanner", block=True)
                    context.response = ""  # Clear the unsafe response
                    return context
                    
            except Exception as e:
                self.logger.error(f"Error during LLM Guard response check: {str(e)}")
                # Continue with other checks on error
        
        # Check with Moderator Service if available
        if self.container.has('moderator_service'):
            try:
                moderator = self.container.get('moderator_service')
                is_safe, refusal_message = await moderator.check_safety(context.response)
                
                if not is_safe:
                    self.logger.warning(f"Response blocked by Moderator Service: {refusal_message}")
                    context.set_error("Response blocked by content moderator", block=True)
                    context.response = ""  # Clear the unsafe response
                    return context
                    
            except Exception as e:
                self.logger.error(f"Error during Moderator Service response check: {str(e)}")
                # Continue processing on error
        
        self.logger.debug("Response passed validation checks")
        return context 