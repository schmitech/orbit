"""
Audit Service
=============

Unified audit service that provides a facade for storing audit trails
to different backends (Elasticsearch, SQLite, MongoDB).

This service follows the Strategy pattern to allow runtime selection
of the storage backend based on configuration.
"""

import logging
import ipaddress
from typing import Dict, Any, Optional, List, Union
from datetime import datetime

from .audit_storage_strategy import AuditStorageStrategy, AuditRecord
from .sqlite_audit_strategy import SQLiteAuditStrategy
from .mongodb_audit_strategy import MongoDBDAuditStrategy
from .elasticsearch_audit_strategy import ElasticsearchAuditStrategy

logger = logging.getLogger(__name__)


class AuditService:
    """
    Unified audit service for conversation logging.

    This service provides a facade for storing audit records to different
    backends based on configuration. It maintains backward compatibility
    with the LoggerService.log_conversation() signature.

    Configuration:
        internal_services.audit.enabled: Whether audit logging is enabled
        internal_services.audit.storage_backend: "elasticsearch", "sqlite", "mongodb", or "database"
        internal_services.audit.collection_name: Name of the audit collection/table

    When storage_backend is "database", the service uses the same backend as
    configured in internal_services.backend.type (sqlite or mongodb).
    """

    def __init__(self, config: Dict[str, Any], database_service=None):
        """
        Initialize the audit service.

        Args:
            config: Application configuration dictionary
            database_service: Optional pre-initialized DatabaseService instance.
                             Used for sqlite and mongodb backends.
        """
        self.config = config
        self._database_service = database_service
        self._strategy: Optional[AuditStorageStrategy] = None
        self._initialized = False

        # Get audit configuration
        audit_config = config.get('internal_services', {}).get('audit', {})
        self._enabled = audit_config.get('enabled', True)

        # Get the inference provider from config (for default backend value)
        self._inference_provider = config.get('general', {}).get('inference_provider', 'ollama')

    def _resolve_storage_backend(self) -> str:
        """
        Resolve the storage backend type from configuration.

        Returns:
            The storage backend type: "elasticsearch", "sqlite", or "mongodb"
        """
        audit_config = self.config.get('internal_services', {}).get('audit', {})
        storage_backend = audit_config.get('storage_backend', 'elasticsearch')

        # If "database", use the same backend as internal_services.backend.type
        if storage_backend == 'database':
            backend_type = self.config.get('internal_services', {}).get('backend', {}).get('type', 'sqlite')
            logger.info(f"Audit storage_backend='database' resolved to '{backend_type}'")
            return backend_type

        return storage_backend

    def _create_strategy(self) -> AuditStorageStrategy:
        """
        Create the appropriate storage strategy based on configuration.

        Returns:
            AuditStorageStrategy instance
        """
        backend = self._resolve_storage_backend()

        if backend == 'elasticsearch':
            logger.info("Using Elasticsearch for audit storage")
            return ElasticsearchAuditStrategy(self.config)
        elif backend == 'sqlite':
            logger.info("Using SQLite for audit storage")
            return SQLiteAuditStrategy(self.config, self._database_service)
        elif backend == 'mongodb':
            logger.info("Using MongoDB for audit storage")
            return MongoDBDAuditStrategy(self.config, self._database_service)
        else:
            raise ValueError(f"Unsupported audit storage backend: {backend}")

    async def initialize(self) -> None:
        """
        Initialize the audit service and its storage strategy.
        """
        if self._initialized:
            return

        if not self._enabled:
            logger.info("Audit service is disabled in configuration")
            self._initialized = True
            return

        try:
            self._strategy = self._create_strategy()
            await self._strategy.initialize()

            if self._strategy.is_initialized():
                logger.info(f"Audit service initialized with {self._strategy.backend_name} backend")
                self._initialized = True
            else:
                logger.warning(f"Audit strategy {self._strategy.backend_name} failed to initialize")

        except Exception as e:
            logger.error(f"Failed to initialize audit service: {e}")
            # Don't fail the application if audit service fails
            self._initialized = True

    def _format_ip_address(self, ip: Optional[Union[str, List[str]]]) -> Dict[str, Any]:
        """
        Convert a raw IP value (or list thereof) into structured IP metadata.

        This method is extracted from LoggerService for compatibility.

        Args:
            ip: IP address string or list of IP strings

        Returns:
            Dictionary with IP metadata
        """
        default_val = "unknown"
        default_metadata = {
            "address": default_val,
            "type": "unknown",
            "isLocal": False,
            "source": "unknown",
            "originalValue": ", ".join(ip) if isinstance(ip, list) else (ip or default_val)
        }

        ip_value: Optional[str] = None
        if isinstance(ip, list):
            ip_value = ip[0] if ip else None
        elif isinstance(ip, str):
            ip_value = ip

        if not ip_value:
            return default_metadata

        clean_ip = ip_value.strip()

        # Check for localhost variants
        if clean_ip in ("::1", "::ffff:127.0.0.1", "127.0.0.1") or clean_ip.startswith("::ffff:127."):
            return {
                "address": "localhost",
                "type": "local",
                "isLocal": True,
                "source": "direct",
                "originalValue": clean_ip
            }

        # Handle IPv4-mapped IPv6 addresses
        if clean_ip.startswith("::ffff:"):
            clean_ip = clean_ip[7:]
            ip_type = "ipv4"
        elif ":" in clean_ip:
            ip_type = "ipv6"
        else:
            ip_type = "ipv4"

        return {
            "address": clean_ip,
            "type": ip_type,
            "isLocal": self._is_local_ip(clean_ip),
            "source": "proxy" if isinstance(ip, list) else "direct",
            "originalValue": clean_ip
        }

    def _is_local_ip(self, ip: str) -> bool:
        """Determine if an IP address is local (private or loopback)."""
        try:
            return ipaddress.ip_address(ip).is_private or ipaddress.ip_address(ip).is_loopback
        except ValueError:
            return False

    def _detect_blocked_response(self, response: str, blocked: bool) -> bool:
        """
        Detect if a response indicates a blocked query.

        Args:
            response: The response text
            blocked: Explicit blocked flag

        Returns:
            True if the response appears to be blocked
        """
        if blocked:
            return True

        blocked_phrases = [
            "i cannot assist with that type of request",
            "i cannot assist with that request",
            "i'm unable to help with that",
            "i cannot help with that"
        ]

        return any(phrase in response.lower() for phrase in blocked_phrases)

    async def log_conversation(
        self,
        query: str,
        response: str,
        ip: Optional[str] = None,
        backend: Optional[str] = None,
        blocked: bool = False,
        api_key: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> None:
        """
        Log a conversation interaction to the configured audit backend.

        This method maintains backward compatibility with LoggerService.log_conversation().

        Args:
            query: The user's query
            response: The system's response
            ip: The IP address of the user
            backend: The backend used for the response
            blocked: Whether the query was blocked
            api_key: The API key used for the request
            session_id: The session ID for the conversation
            user_id: The user ID if available
        """
        if not self._enabled or not self._strategy or not self._strategy.is_initialized():
            return

        try:
            timestamp = datetime.now()
            ip_metadata = self._format_ip_address(ip)
            is_blocked = self._detect_blocked_response(response, blocked)

            # Use provided backend or fall back to inference provider
            used_backend = backend or self._inference_provider

            # Build API key metadata if provided
            api_key_data = None
            if api_key:
                api_key_data = {
                    "key": api_key,
                    "timestamp": timestamp.isoformat()
                }

            # Create audit record
            record = AuditRecord(
                timestamp=timestamp,
                query=query,
                response=response,
                backend=used_backend,
                blocked=is_blocked,
                ip=ip_metadata.get("address", "unknown"),
                ip_metadata=ip_metadata,
                api_key=api_key_data,
                session_id=session_id,
                user_id=user_id
            )

            # Store the record
            success = await self._strategy.store(record)

            if not success:
                logger.warning("Failed to store audit record")

        except Exception as e:
            logger.error(f"Error logging conversation to audit: {e}")
            # Don't fail the request if audit logging fails

    async def query_audit_logs(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = 'timestamp',
        sort_order: int = -1
    ) -> List[Dict[str, Any]]:
        """
        Query audit logs with optional filters.

        Args:
            filters: Query criteria (e.g., {'session_id': 'abc', 'blocked': True})
            limit: Maximum number of records to return
            offset: Number of records to skip
            sort_by: Field to sort by (default: 'timestamp')
            sort_order: Sort direction (1=ascending, -1=descending)

        Returns:
            List of matching audit records
        """
        if not self._enabled or not self._strategy or not self._strategy.is_initialized():
            return []

        try:
            return await self._strategy.query(
                filters=filters or {},
                limit=limit,
                offset=offset,
                sort_by=sort_by,
                sort_order=sort_order
            )
        except Exception as e:
            logger.error(f"Error querying audit logs: {e}")
            return []

    async def close(self) -> None:
        """Close the audit service and its storage strategy."""
        if self._strategy:
            await self._strategy.close()
        self._initialized = False
        logger.debug("Audit service closed")

    @property
    def is_enabled(self) -> bool:
        """Check if audit service is enabled."""
        return self._enabled

    @property
    def backend_name(self) -> str:
        """Get the name of the current storage backend."""
        if self._strategy:
            return self._strategy.backend_name
        return "none"
