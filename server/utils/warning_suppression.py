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
    
    # Suppress Cohere Pydantic deprecation warnings
    warnings.filterwarnings(
        "ignore", 
        message=".*__fields__.*", 
        category=DeprecationWarning,
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
    
    # Suppress any other known warnings
    warnings.filterwarnings(
        "ignore", 
        message=".*PydanticDeprecatedSince20.*", 
        category=DeprecationWarning
    )
    
    # Set environment variable to suppress warnings at the Python level
    os.environ.setdefault('PYTHONWARNINGS', 'ignore::DeprecationWarning:cohere,ignore::DeprecationWarning:ftfy')

# Automatically suppress warnings when this module is imported
suppress_known_warnings()
