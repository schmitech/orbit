"""
Adapter package for document transformation and domain-specific formatting.

This package provides a unified system for adapting retrieved documents to different
domain contexts (QA, Intent, Generic, etc.).
"""

import logging

from adapters.base import DocumentAdapter
from adapters.registry import AdapterRegistry, ADAPTER_REGISTRY
from adapters.factory import DocumentAdapterFactory

logger = logging.getLogger(__name__)

__all__ = [
    'DocumentAdapter',
    'AdapterRegistry',
    'ADAPTER_REGISTRY',
    'DocumentAdapterFactory',
]


def register_adapters():
    """Register all built-in adapters with the registry"""
    logger.info("Registering built-in domain adapters...")

    # Import adapter modules to trigger their registration
    # These modules have module-level registration code
    try:
        import adapters.intent.adapter  # SQL Intent adapter
        import adapters.http.adapter     # HTTP adapter
        import adapters.elasticsearch.adapter  # Elasticsearch adapter
        import adapters.file.adapter  # File adapter
        logger.info("Imported adapter modules with auto-registration")
    except ImportError as e:
        logger.warning(f"Failed to import some adapter modules: {e}")

    # Register adapters for all supported datasources
    for datasource in ['sqlite', 'chroma', 'qdrant', 'postgres', 'pinecone', 'elasticsearch', 'opensearch', 'http', 'mysql', 'mssql']:
        # Register QA document adapter with default config
        ADAPTER_REGISTRY.register(
            adapter_type="retriever",
            datasource=datasource,
            adapter_name="qa",
            implementation='adapters.qa.base.QADocumentAdapter',
            config={
                'confidence_threshold': 0.7,
                'boost_exact_matches': False,
                'verbose': False
            }
        )
        logger.debug(f"Registered QA adapter for {datasource}")

        # Register Generic document adapter with default config
        ADAPTER_REGISTRY.register(
            adapter_type="retriever",
            datasource=datasource,
            adapter_name="generic",
            implementation='adapters.generic.adapter.GenericDocumentAdapter',
            config={
                'confidence_threshold': 0.3,
                'verbose': False
            }
        )
        logger.debug(f"Registered Generic adapter for {datasource}")

    logger.info("Built-in domain adapters registration complete")

    # Register passthrough conversational adapter
    def _create_conversational_adapter(config=None, **kwargs):
        from adapters.passthrough.adapter import ConversationalAdapter
        return ConversationalAdapter(config=config, **kwargs)

    DocumentAdapterFactory.register_adapter(
        "conversational",
        _create_conversational_adapter
    )

    ADAPTER_REGISTRY.register(
        adapter_type="passthrough",
        datasource="none",
        adapter_name="conversational",
        factory_func=_create_conversational_adapter,
        config={}
    )

    logger.info("Registered conversational passthrough adapter")

    # Register passthrough multimodal adapter
    def _create_multimodal_adapter(config=None, **kwargs):
        from adapters.passthrough.adapter import MultimodalAdapter
        return MultimodalAdapter(config=config, **kwargs)

    DocumentAdapterFactory.register_adapter(
        "multimodal",
        _create_multimodal_adapter
    )

    ADAPTER_REGISTRY.register(
        adapter_type="passthrough",
        datasource="none",
        adapter_name="multimodal",
        factory_func=_create_multimodal_adapter,
        config={}
    )

    logger.info("Registered multimodal passthrough adapter")


# Register adapters when module is imported
register_adapters()