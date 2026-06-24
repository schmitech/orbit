"""
Intent adapter for SQL datasources that translates natural language queries to SQL
"""

import logging
from typing import Dict, Any, List, Optional, Union
import asyncio

from adapters.http.adapter import HttpAdapter
from adapters.factory import DocumentAdapterFactory

logger = logging.getLogger(__name__)

# Register with the factory
DocumentAdapterFactory.register_adapter("intent", lambda **kwargs: IntentAdapter(**kwargs))
logger.debug("Registered IntentAdapter as 'intent'")


class IntentAdapter(HttpAdapter):
    """
    Adapter that manages domain-specific knowledge for the intent retriever.
    Loads domain configuration and template libraries for text-to-SQL translation.
    Inherits template loading and formatting from HttpAdapter.
    """

    def __init__(self,
                 domain_config_path: Optional[str] = None,
                 template_library_path: Optional[Union[str, List[str]]] = None,
                 confidence_threshold: float = 0.1,
                 config: Dict[str, Any] = None,
                 **kwargs):
        super().__init__(
            domain_config_path=domain_config_path,
            template_library_path=template_library_path,
            confidence_threshold=confidence_threshold,
            config=config,
            **kwargs
        )

    async def initialize_embeddings(self, store_manager=None):
        """Initialize embeddings using the vector store system."""
        logger.debug("Initializing embeddings for intent adapter")

        if store_manager:
            self.store_manager = store_manager
            logger.debug("Store manager registered with intent adapter")

        if self.template_library and hasattr(self, 'store_manager'):
            try:
                from vector_stores.services.template_embedding_store import TemplateEmbeddingStore

                if asyncio.iscoroutinefunction(self.store_manager.get_store):
                    template_store = await self.store_manager.get_store('template_embeddings')
                else:
                    template_store = self.store_manager.get_store('template_embeddings')

                if not template_store:
                    logger.debug("Creating new template embedding store")
                    vector_config = self.config.get('vector_store', {})
                    collection_name = self.config.get('template_collection_name', 'intent_query_templates')

                    store_type = vector_config.get('type') if vector_config else None
                    if not store_type:
                        first_available = self.store_manager.get_first_available_store_type()
                        if first_available:
                            store_type = first_available
                            logger.debug(f"No vector_store type configured, using first available: {store_type}")
                        else:
                            store_type = 'chroma'
                            logger.warning("No vector stores available, defaulting to 'chroma'")

                    if vector_config:
                        vector_config['collection_name'] = collection_name

                    template_store = TemplateEmbeddingStore(
                        store_name='template_embeddings',
                        store_type=store_type,
                        collection_name=collection_name,
                        config=vector_config or {},
                        store_manager=self.store_manager
                    )
                    if hasattr(template_store, 'initialize'):
                        await template_store.initialize()

                self.template_store = template_store
                logger.debug("Template embedding store initialized")

            except Exception as e:
                logger.warning(f"Failed to initialize template embeddings: {e}")
                logger.debug("Intent adapter will work without vector store support")
        else:
            if not self.template_library:
                logger.debug("No template library loaded, skipping embedding initialization")
            if not hasattr(self, 'store_manager'):
                logger.debug("No store manager available, skipping embedding initialization")

        return True


def register_intent_adapter():
    """Register intent adapter with the global adapter registry"""
    logger.debug("Registering intent adapter with global registry...")
    try:
        from adapters.registry import ADAPTER_REGISTRY

        datasources = ['postgres', 'mysql', 'mssql', 'sqlite', 'duckdb', 'athena', 'mongodb', 'http']
        for datasource in datasources:
            ADAPTER_REGISTRY.register(
                adapter_type="retriever",
                datasource=datasource,
                adapter_name="intent",
                implementation='adapters.intent.adapter.IntentAdapter',
                config={'confidence_threshold': 0.1}
            )
            logger.debug(f"Registered intent adapter for {datasource}")

        logger.debug("Intent adapter registration complete")

    except Exception as e:
        logger.error(f"Failed to register intent adapter: {e}")


register_intent_adapter()
