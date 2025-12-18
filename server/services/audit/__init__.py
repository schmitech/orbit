"""
Audit Service Module
====================

This module provides audit trail storage capabilities for the Orbit platform.
It supports multiple storage backends (Elasticsearch, SQLite, MongoDB) through
the Strategy pattern.

Features:
    - Multiple storage backends (Elasticsearch, SQLite, MongoDB)
    - Optional gzip compression for response field (reduces storage by ~70-90%)
    - Configurable via config.yaml under internal_services.audit

Usage:
    from services.audit import AuditService

    audit_service = AuditService(config, database_service)
    await audit_service.initialize()
    await audit_service.log_conversation(query="Hello", response="Hi there!")

Compression utilities (for direct use if needed):
    from services.audit import compress_text, decompress_text, is_compressed
"""

from .audit_service import AuditService
from .audit_storage_strategy import (
    AuditStorageStrategy,
    AuditRecord,
    compress_text,
    decompress_text,
    is_compressed,
)
from .sqlite_audit_strategy import SQLiteAuditStrategy
from .mongodb_audit_strategy import MongoDBDAuditStrategy
from .elasticsearch_audit_strategy import ElasticsearchAuditStrategy

__all__ = [
    'AuditService',
    'AuditStorageStrategy',
    'AuditRecord',
    'SQLiteAuditStrategy',
    'MongoDBDAuditStrategy',
    'ElasticsearchAuditStrategy',
    # Compression utilities
    'compress_text',
    'decompress_text',
    'is_compressed',
]
