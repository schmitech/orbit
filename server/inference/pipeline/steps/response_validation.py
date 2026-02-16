"""
Response Validation Step

This step validates the generated response for safety and quality.
"""

import logging
from ..base import PipelineStep, ProcessingContext

logger = logging.getLogger(__name__)

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
            True if moderator service is available, response exists, and not blocked
        """
        return self.container.has('moderator_service') and context.response and not context.is_blocked
    
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
        
        logger.debug(f"Validating response: {context.response[:100]}...")
        
        # Check with Moderator Service if available
        if self.container.has('moderator_service'):
            try:
                moderator = self.container.get('moderator_service')
                is_safe, refusal_message = await moderator.check_safety(context.response)
                
                if not is_safe:
                    logger.warning(f"Response blocked by Moderator Service: {refusal_message}")
                    context.set_error("Response blocked by content moderator", block=True)
                    context.response = ""  # Clear the unsafe response
                    return context
                    
            except Exception as e:
                logger.error(f"Error during Moderator Service response check: {str(e)}")
                # Continue processing on error
        
        logger.debug("Response passed validation checks")
        return context 
