"""
Datasources Package

This package contains modules for initializing and managing various datasource clients
using a registry-based approach with automatic discovery.
"""

from .datasource_factory import DatasourceFactory
from .registry import get_registry, create_datasource
from .base.base_datasource import BaseDatasource

# Auto-discovery will happen when the registry is first accessed
# This prevents circular import issues during server startup

__all__ = ['DatasourceFactory', 'get_registry', 'create_datasource', 'BaseDatasource'] 