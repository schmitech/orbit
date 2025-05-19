"""
Domain adapters for retrievers.
This ensures all adapter modules are properly imported during server startup.
"""

import logging
logger = logging.getLogger(__name__)
logger.info("Loading adapters package - ensure domain adapters are registered")

# Import main adapter modules
from . import domain_adapters
from . import registry
from . import qa

"""
Adapter registration and initialization
"""

from retrievers.adapters.registry import ADAPTER_REGISTRY

def register_adapters():
    """Register all available adapters"""
    # Register QA adapter for all supported datasources
    for datasource in ['sqlite', 'chroma']:
        ADAPTER_REGISTRY.register(
            adapter_type='retriever',
            datasource=datasource,
            adapter_name='qa',
            implementation='retrievers.adapters.domain_adapters.QADocumentAdapter'
        )
    
    # Register generic adapter for all supported datasources
    for datasource in ['sqlite', 'chroma']:
        ADAPTER_REGISTRY.register(
            adapter_type='retriever',
            datasource=datasource,
            adapter_name='generic',
            implementation='retrievers.adapters.domain_adapters.GenericDocumentAdapter'
        )

# Initialize registry
register_adapters()
logger.info("Adapter registry initialized") 