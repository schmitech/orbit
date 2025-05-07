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