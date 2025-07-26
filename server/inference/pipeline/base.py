"""
Base classes for the pipeline architecture.

This module defines the core interfaces and data structures used throughout
the pipeline-based inference system.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, AsyncGenerator
from dataclasses import dataclass, field
import logging

@dataclass
class ProcessingContext:
    """
    Shared context passed through pipeline steps.
    
    This context carries all the data needed for processing a request
    through the pipeline, including input, intermediate results, and output.
    """
    # Input data
    message: str = ""
    adapter_name: str = ""
    system_prompt_id: Optional[str] = None
    context_messages: List[Dict[str, str]] = field(default_factory=list)
    
    # Processing data
    retrieved_docs: List[Dict[str, Any]] = field(default_factory=list)
    formatted_context: str = ""
    full_prompt: str = ""
    
    # Output data
    response: str = ""
    sources: List[Dict[str, Any]] = field(default_factory=list)
    tokens: int = 0
    processing_time: float = 0.0
    
    # Control flow
    is_blocked: bool = False
    error: Optional[str] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    
    # Security tracking
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    api_key: Optional[str] = None
    
    def has_error(self) -> bool:
        """Check if the context has an error."""
        return self.is_blocked or self.error is not None
    
    def set_error(self, error: str, block: bool = True) -> None:
        """
        Set an error on the context.
        
        Args:
            error: The error message
            block: Whether to block further processing
        """
        self.error = error
        if block:
            self.is_blocked = True


class PipelineStep(ABC):
    """
    Base interface for pipeline steps.
    
    Each step in the pipeline implements this interface to process
    the context and optionally modify it.
    """
    
    def __init__(self, container: 'ServiceContainer'):
        """
        Initialize the pipeline step.
        
        Args:
            container: The service container for dependency injection
        """
        self.container = container
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    async def process(self, context: ProcessingContext) -> ProcessingContext:
        """
        Process the context and return modified context.
        
        Args:
            context: The processing context
            
        Returns:
            The modified context
        """
        pass
    
    @abstractmethod
    def should_execute(self, context: ProcessingContext) -> bool:
        """
        Determine if this step should execute based on context.
        
        Args:
            context: The processing context
            
        Returns:
            True if the step should execute, False otherwise
        """
        pass
    
    def get_name(self) -> str:
        """Get the name of this step."""
        return self.__class__.__name__
    
    async def pre_process(self, context: ProcessingContext) -> None:
        """
        Hook called before processing.
        
        Override this method to add pre-processing logic.
        
        Args:
            context: The processing context
        """
        pass
    
    async def post_process(self, context: ProcessingContext) -> None:
        """
        Hook called after processing.
        
        Override this method to add post-processing logic.
        
        Args:
            context: The processing context
        """
        pass
    
    def supports_streaming(self) -> bool:
        """
        Check if this step supports streaming responses.
        
        Returns:
            True if the step can handle streaming, False otherwise
        """
        return False
    
    async def process_stream(self, context: ProcessingContext) -> AsyncGenerator[str, None]:
        """
        Process the context for streaming response.
        
        This method should be implemented by steps that support streaming.
        By default, it raises NotImplementedError.
        
        Args:
            context: The processing context
            
        Yields:
            Response chunks as they are generated
        """
        raise NotImplementedError(f"{self.get_name()} does not support streaming") 