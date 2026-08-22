"""
Audit Storage Strategy
======================

Abstract base class for audit storage backends. Implements the Strategy pattern
to allow switching between Elasticsearch, SQLite, and MongoDB for audit log storage.
"""

import gzip
import base64
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, field


# ============================================================================
# Compression Utilities
# ============================================================================

def compress_text(text: str) -> str:
    """
    Compress text using gzip and encode as base64 for storage.

    Args:
        text: Plain text to compress

    Returns:
        Base64-encoded gzip compressed string
    """
    compressed = gzip.compress(text.encode('utf-8'))
    return base64.b64encode(compressed).decode('ascii')


def decompress_text(compressed_text: str) -> str:
    """
    Decompress a base64-encoded gzip string back to plain text.

    Args:
        compressed_text: Base64-encoded gzip compressed string

    Returns:
        Original plain text
    """
    compressed = base64.b64decode(compressed_text.encode('ascii'))
    return gzip.decompress(compressed).decode('utf-8')


def is_compressed(text: str) -> bool:
    """
    Check if a string appears to be compressed (base64-encoded gzip).

    This is a heuristic check - it tries to decode and decompress.
    Returns False if any step fails.

    Args:
        text: String to check

    Returns:
        True if the string appears to be compressed, False otherwise
    """
    if not text:
        return False
    try:
        compressed = base64.b64decode(text.encode('ascii'))
        # Check for gzip magic number
        return len(compressed) >= 2 and compressed[0:2] == b'\x1f\x8b'
    except Exception:
        return False


@dataclass
class AuditRecord:
    """
    Data class representing an audit record.

    This structure is shared by Elasticsearch, SQLite, and MongoDB storage.
    """
    timestamp: datetime
    query: str
    response: str
    provider: str
    blocked: bool
    ip: str
    ip_metadata: Dict[str, Any] = field(default_factory=dict)
    api_key: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    adapter_name: Optional[str] = None  # Name of the adapter used for this request
    model: Optional[str] = None  # Actual model used for this request
    response_compressed: bool = False  # Flag indicating if response is compressed
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None  # Subset of completion_tokens; informational, already priced within it
    cached_prompt_tokens: Optional[int] = None  # Subset of prompt_tokens served from a provider cache; already priced within it (see PricingService.estimate)
    cost_usd: Optional[float] = None
    input_rate_per_1m: Optional[float] = None
    output_rate_per_1m: Optional[float] = None
    pricing_source: Optional[str] = None  # exact | pattern | provider_default | local_zero | unpriced | unreported
    # Discrete-unit media spend (images/video seconds/TTS characters/STT
    # seconds/OCR pages) — cost_usd above is the single summable cost column
    # for both token-billed and unit-billed requests; these two describe what
    # the unit-billed quantity actually was.
    usage_unit: Optional[str] = None
    usage_quantity: Optional[float] = None
    # Coarse classification of the AI call this row represents — "inference"
    # (chat/text generation, the default), "embedding", "reranking", "image", "video",
    # "audio", or "document" (OCR). Set at the usage-recording call site
    # (record_usage/record_media_generation_usage), not inferred here.
    call_type: Optional[str] = None

    def to_dict(self, compress: bool = False) -> Dict[str, Any]:
        """
        Convert to dictionary representation.

        Args:
            compress: If True, compress the response field

        Returns:
            Dictionary representation of the audit record
        """
        response_value = self.response
        is_response_compressed = self.response_compressed

        if compress and not self.response_compressed:
            response_value = compress_text(self.response)
            is_response_compressed = True

        result = {
            'timestamp': self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
            'query': self.query,
            'response': response_value,
            'response_compressed': is_response_compressed,
            'provider': self.provider,
            'blocked': self.blocked,
            'ip': self.ip,
            'ip_metadata': self.ip_metadata,
        }

        if self.api_key:
            result['api_key'] = self.api_key
        if self.session_id:
            result['session_id'] = self.session_id
        if self.user_id:
            result['user_id'] = self.user_id
        if self.adapter_name:
            result['adapter_name'] = self.adapter_name
        if self.model:
            result['model'] = self.model
        if self.prompt_tokens is not None:
            result['prompt_tokens'] = self.prompt_tokens
        if self.completion_tokens is not None:
            result['completion_tokens'] = self.completion_tokens
        if self.total_tokens is not None:
            result['total_tokens'] = self.total_tokens
        if self.reasoning_tokens is not None:
            result['reasoning_tokens'] = self.reasoning_tokens
        if self.cached_prompt_tokens is not None:
            result['cached_prompt_tokens'] = self.cached_prompt_tokens
        if self.cost_usd is not None:
            result['cost_usd'] = self.cost_usd
        if self.input_rate_per_1m is not None:
            result['input_rate_per_1m'] = self.input_rate_per_1m
        if self.output_rate_per_1m is not None:
            result['output_rate_per_1m'] = self.output_rate_per_1m
        if self.pricing_source:
            result['pricing_source'] = self.pricing_source
        if self.usage_unit is not None:
            result['usage_unit'] = self.usage_unit
        if self.usage_quantity is not None:
            result['usage_quantity'] = self.usage_quantity
        if self.call_type is not None:
            result['call_type'] = self.call_type

        return result

    def to_flat_dict(self, compress: bool = False) -> Dict[str, Any]:
        """
        Convert to flattened dictionary for SQLite storage.
        Nested objects (ip_metadata, api_key) are flattened to individual columns.

        Args:
            compress: If True, compress the response field

        Returns:
            Flattened dictionary for SQLite storage
        """
        response_value = self.response
        is_response_compressed = self.response_compressed

        if compress and not self.response_compressed:
            response_value = compress_text(self.response)
            is_response_compressed = True

        result = {
            'timestamp': self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
            'query': self.query,
            'response': response_value,
            'response_compressed': 1 if is_response_compressed else 0,
            'provider': self.provider,
            'blocked': 1 if self.blocked else 0,
            'ip': self.ip,
            # Flatten ip_metadata
            'ip_type': self.ip_metadata.get('type', 'unknown'),
            'ip_is_local': 1 if self.ip_metadata.get('isLocal', False) else 0,
            'ip_source': self.ip_metadata.get('source', 'unknown'),
            'ip_original_value': self.ip_metadata.get('originalValue', ''),
        }

        # Flatten api_key if present
        if self.api_key:
            result['api_key_value'] = self.api_key.get('key', '')
            result['api_key_timestamp'] = self.api_key.get('timestamp', '')
        else:
            result['api_key_value'] = None
            result['api_key_timestamp'] = None

        if self.session_id:
            result['session_id'] = self.session_id
        else:
            result['session_id'] = None

        if self.user_id:
            result['user_id'] = self.user_id
        else:
            result['user_id'] = None

        if self.adapter_name:
            result['adapter_name'] = self.adapter_name
        else:
            result['adapter_name'] = None

        if self.model:
            result['model'] = self.model
        else:
            result['model'] = None

        result['prompt_tokens'] = self.prompt_tokens
        result['completion_tokens'] = self.completion_tokens
        result['total_tokens'] = self.total_tokens
        result['reasoning_tokens'] = self.reasoning_tokens
        result['cached_prompt_tokens'] = self.cached_prompt_tokens
        result['cost_usd'] = self.cost_usd
        result['input_rate_per_1m'] = self.input_rate_per_1m
        result['output_rate_per_1m'] = self.output_rate_per_1m
        result['pricing_source'] = self.pricing_source
        result['usage_unit'] = self.usage_unit
        result['usage_quantity'] = self.usage_quantity
        result['call_type'] = self.call_type

        return result


class AuditStorageStrategy(ABC):
    """
    Abstract base class for audit storage backends.

    Implementations must provide methods for initializing the storage,
    storing audit records, querying records, and cleanup.

    This follows the Strategy pattern to allow runtime selection of
    storage backends (Elasticsearch, SQLite, MongoDB).
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the audit storage strategy.

        Args:
            config: Application configuration dictionary
        """
        self.config = config
        self._initialized = False

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the storage backend.

        This method should set up any required connections, create
        tables/indexes, and prepare the backend for use.

        Implementations should set self._initialized = True when complete.
        """
        pass

    @abstractmethod
    async def store(self, record: AuditRecord) -> bool:
        """
        Store an audit record.

        Args:
            record: The audit record to store

        Returns:
            True if the record was stored successfully, False otherwise
        """
        pass

    @abstractmethod
    async def query(
        self,
        filters: Dict[str, Any],
        limit: int = 100,
        offset: int = 0,
        sort_by: str = 'timestamp',
        sort_order: int = -1
    ) -> List[Dict[str, Any]]:
        """
        Query audit records with filters.

        Args:
            filters: Query criteria (e.g., {'session_id': 'abc', 'blocked': True})
            limit: Maximum number of records to return
            offset: Number of records to skip
            sort_by: Field to sort by (default: 'timestamp')
            sort_order: Sort direction (1=ascending, -1=descending)

        Returns:
            List of matching audit records as dictionaries
        """
        pass

    async def aggregate_usage(
        self,
        since: str,
        until: str,
        bucket: str = "day",
        group_by: str = "model",
        filters: Optional[Dict[str, Any]] = None,
        limit_groups: int = 10,
    ) -> Dict[str, Any]:
        """
        Aggregate token usage/cost over a time window for the Observability page.

        Not abstract (default raises NotImplementedError) so out-of-tree
        strategies don't break; AuditService.aggregate_usage catches this and
        returns a zeroed skeleton rather than propagating a 500.

        Args:
            since: ISO timestamp, inclusive lower bound
            until: ISO timestamp, exclusive upper bound
            bucket: "hour" or "day" — time-series bucketing granularity
            group_by: logical dimension name — "model" | "provider" |
                "adapter_name" | "user_id" | "call_type" | "api_key" | "none".
                Each strategy maps it to its own backend field (see
                _GROUP_BY_FIELDS); an unrecognized value yields no groups.
                Grouping by "api_key" groups on the masked key stored on the
                record, not the key itself.
            filters: Optional extra equality filters (e.g. {'provider': 'openai'}).
                Accepted keys are backend-specific (see _FILTERABLE_DIMENSIONS on
                each strategy) but always include "provider", "adapter_name",
                "model", "call_type", and "api_key" — the last matched against
                the masked key, same as the "api_key" group_by dimension.
                Unrecognized keys are silently ignored, never interpolated.
            limit_groups: Max number of distinct groups to return, ranked by cost

        Returns:
            {"totals": {...}, "series": [...], "groups": [...]}
        """
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """
        Close the storage backend and clean up resources.
        """
        pass

    @abstractmethod
    async def clear(self) -> bool:
        """
        Clear all audit records from the storage backend.

        This method deletes all records from the audit table/collection.
        Use with caution - this operation is irreversible.

        Returns:
            True if the clear operation was successful, False otherwise
        """
        pass

    def is_initialized(self) -> bool:
        """Check if the storage backend is initialized."""
        return self._initialized

    @property
    def backend_name(self) -> str:
        """Return the name of this storage backend."""
        return self.__class__.__name__.replace('AuditStrategy', '').lower()
