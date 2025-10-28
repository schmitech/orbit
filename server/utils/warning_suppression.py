"""
Warning suppression utilities for the ORBIT server.

This module provides centralized warning suppression for known deprecation warnings
from third-party libraries that are not under our control.

The warnings are suppressed at the module level to ensure they are applied
before any problematic libraries are imported.
"""

import warnings
import sys
import os

def suppress_known_warnings():
    """
    Suppress known deprecation warnings from third-party libraries.

    This function should be called as early as possible in the application
    startup process, before any third-party libraries are imported.
    """

    # Suppress ALL ResourceWarnings (including unclosed transports, files, etc.)
    # This is more aggressive but necessary to suppress asyncio transport warnings
    warnings.simplefilter("ignore", ResourceWarning)

    # Also add specific filter for unclosed resources as backup
    warnings.filterwarnings(
        "ignore",
        category=ResourceWarning,
        message="unclosed.*"
    )

    # Suppress asyncio transport warnings specifically
    warnings.filterwarnings(
        "ignore",
        category=ResourceWarning,
        message=".*unclosed transport.*"
    )

    # Suppress Cohere Pydantic deprecation warnings.
    # Pydantic v2 migration causes PydanticDeprecatedSince20 warnings, which are not of type DeprecationWarning.
    # We match by message and module, without specifying a category.
    warnings.filterwarnings(
        "ignore", 
        message=".*The `__fields__` attribute is deprecated.*", 
        module="cohere.*"
    )
    
    # Suppress ftfy deprecation warnings
    warnings.filterwarnings(
        "ignore", 
        message=".*fix_entities.*", 
        category=DeprecationWarning,
        module="ftfy.*"
    )
    
    # Suppress ftfy unescape_html warnings
    warnings.filterwarnings(
        "ignore", 
        message=".*unescape_html.*", 
        category=DeprecationWarning,
        module="ftfy.*"
    )
    
    # Suppress websockets deprecation warnings
    warnings.filterwarnings(
        "ignore", 
        message="remove second argument of ws_handler", 
        category=DeprecationWarning,
        module="websockets.legacy.server"
    )
    
    # Also suppress websockets warnings more broadly
    warnings.filterwarnings(
        "ignore", 
        category=DeprecationWarning,
        module="websockets.*"
    )
    
    # Suppress any other known Pydantic v2 deprecation warnings by matching the message content.
    # This is broader and should catch other similar warnings.
    warnings.filterwarnings(
        "ignore", 
        message=".*Pydantic V2.*", 
    )

# Automatically suppress warnings when this module is imported
suppress_known_warnings()