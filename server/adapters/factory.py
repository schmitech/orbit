"""
Document Adapter Factory for creating adapter instances.
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
    """

    _registered_adapters: Dict[str, Callable] = {
        'qa': lambda **kwargs: _create_qa_adapter(**kwargs),
        'generic': lambda **kwargs: _create_generic_adapter(**kwargs),
        'file': lambda **kwargs: _create_file_adapter(**kwargs),
        'conversational': lambda **kwargs: _create_conversational_adapter(**kwargs),
    }

    @classmethod
    def register_adapter(cls, adapter_type: str, factory_func: Callable):
        """
        Register a new adapter type with its factory function.

        Args:
            adapter_type: Type identifier for the adapter (e.g., 'qa', 'generic')
            factory_func: Function that creates the adapter instance
        """
        cls._registered_adapters[adapter_type.lower()] = factory_func
        logger.debug(f"Registered adapter type in factory: {adapter_type}")

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

        if adapter_type_lower in cls._registered_adapters:
            return cls._registered_adapters[adapter_type_lower](**kwargs)

        raise ValueError(f"Unsupported adapter type: {adapter_type}")


def _create_qa_adapter(**kwargs) -> DocumentAdapter:
    from adapters.qa.base import QADocumentAdapter
    return QADocumentAdapter(**kwargs)


def _create_generic_adapter(**kwargs) -> DocumentAdapter:
    from adapters.generic.adapter import GenericDocumentAdapter
    return GenericDocumentAdapter(**kwargs)


def _create_file_adapter(**kwargs) -> DocumentAdapter:
    from adapters.file.adapter import FileAdapter
    return FileAdapter(**kwargs)


def _create_conversational_adapter(**kwargs) -> DocumentAdapter:
    from adapters.passthrough.adapter import ConversationalAdapter
    return ConversationalAdapter(**kwargs)
