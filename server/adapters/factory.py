"""
Document Adapter Factory for creating adapter instances.

NOTE: This factory pattern may be deprecated in favor of the unified registry system.
It is maintained here for backward compatibility during the transition.
"""

import logging
from typing import Dict, Callable
from adapters.base import DocumentAdapter

# Configure logging
logger = logging.getLogger(__name__)


class DocumentAdapterFactory:
    """
    Factory for creating document adapters.

    This class provides a simple factory pattern for creating adapter instances.
    The registry system (adapters.registry) provides a more comprehensive solution
    and may eventually replace this factory.
    """

    _registered_adapters: Dict[str, Callable] = {}

    @classmethod
    def register_adapter(cls, adapter_type: str, factory_func: Callable):
        """
        Register a new adapter type with its factory function.

        Args:
            adapter_type: Type identifier for the adapter (e.g., 'qa', 'generic')
            factory_func: Function that creates the adapter instance
        """
        cls._registered_adapters[adapter_type.lower()] = factory_func
        logger.info(f"Registered adapter type in factory: {adapter_type}")

    @classmethod
    def create_adapter(cls, adapter_type: str, **kwargs) -> DocumentAdapter:
        """
        Create a document adapter instance.

        Args:
            adapter_type: Type of adapter to create (e.g., 'qa', 'generic')
            **kwargs: Additional arguments to pass to the adapter

        Returns:
            A document adapter instance

        Raises:
            ValueError: If the adapter type is not supported
        """
        adapter_type_lower = adapter_type.lower()

        # Try to get from registered adapters first
        if adapter_type_lower in cls._registered_adapters:
            return cls._registered_adapters[adapter_type_lower](**kwargs)

        # Fall back to built-in adapters (these will be imported dynamically)
        if adapter_type_lower == 'qa':
            # Import here to avoid circular dependencies
            from adapters.qa.base import QADocumentAdapter
            return QADocumentAdapter(**kwargs)
        elif adapter_type_lower == 'generic':
            from adapters.generic.adapter import GenericDocumentAdapter
            return GenericDocumentAdapter(**kwargs)
        elif adapter_type_lower == 'file':
            from adapters.file.adapter import FileAdapter
            return FileAdapter(**kwargs)
        elif adapter_type_lower == 'conversational':
            from adapters.passthrough.adapter import ConversationalAdapter
            return ConversationalAdapter(**kwargs)
        else:
            raise ValueError(f"Unsupported adapter type: {adapter_type}")
