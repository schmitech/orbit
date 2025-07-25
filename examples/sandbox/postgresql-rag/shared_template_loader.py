#!/usr/bin/env python3
"""
Shared Template Loading Functions
===============================

Consistent template loading across demos to ensure identical behavior
"""

import os
from domain_configuration import DomainConfiguration
from template_library import TemplateLibrary
from template_generator import DomainTemplateGenerator


def load_or_generate_templates(domain: DomainConfiguration) -> TemplateLibrary:
    """
    Generate templates from domain configuration - SINGLE SOURCE OF TRUTH
    
    Args:
        domain: Domain configuration object
        
    Returns:
        TemplateLibrary with generated templates
    """
    generator = DomainTemplateGenerator(domain)
    library = generator.generate_standard_templates()
    
    # Also load any custom templates if they exist
    custom_templates_path = os.path.join(os.path.dirname(__file__), "custom_templates.yaml")
    if os.path.exists(custom_templates_path):
        print("📚 Loading custom templates...")
        library.import_from_yaml(custom_templates_path)
    
    return library