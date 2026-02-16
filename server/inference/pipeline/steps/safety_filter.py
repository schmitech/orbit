"""
Safety Filter Step

This step checks message safety using guardrail services before processing.
"""

import logging
from ..base import PipelineStep, ProcessingContext

logger = logging.getLogger(__name__)

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
            True if moderator service is available and message is not already blocked
        """
        return self.container.has('moderator_service') and not context.is_blocked
    
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
        
        logger.debug(f"Checking safety for message: {context.message[:100]}...")
        
        # Check with Moderator Service if available
        if self.container.has('moderator_service'):
            try:
                moderator = self.container.get('moderator_service')

                # Log the message being checked
                logger.debug(f"Moderator checking message: '{context.message[:100]}...'")

                is_safe, refusal_message = await moderator.check_safety(context.message)

                if not is_safe:
                    logger.warning(f"Message blocked by Moderator Service: {refusal_message} "
                                      f"for message: '{context.message[:50]}...'")
                    # Use the moderator's refusal message so clients understand why the message was blocked
                    error_message = refusal_message or "Message blocked by content moderator"
                    context.set_error(error_message, block=True)
                    return context
                else:
                    logger.debug(f"Moderator passed message: '{context.message[:50]}...'")

            except Exception as e:
                logger.error(f"Error during Moderator Service check: {str(e)}", exc_info=True)
                # Continue processing on error
        
        logger.debug("Message passed safety checks")
        return context 
