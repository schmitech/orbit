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

# Import subdirectories with specialized adapters
from . import qa 

"""
Adapter registration and initialization
"""

from retrievers.adapters.registry import ADAPTER_REGISTRY

def register_adapters():
    """Register all available adapters"""
    # Register QA adapter
    ADAPTER_REGISTRY.register(
        adapter_type='retriever',
        datasource='memory',
        adapter_name='qa',
        implementation='retrievers.adapters.domain_adapters.QADocumentAdapter'
    )
    
    # Register generic adapter
    ADAPTER_REGISTRY.register(
        adapter_type='retriever',
        datasource='memory',
        adapter_name='generic',
        implementation='retrievers.adapters.domain_adapters.GenericDocumentAdapter'
    )

# Initialize registry
register_adapters() 