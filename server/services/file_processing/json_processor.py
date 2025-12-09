"""
JSON Processor

Handles JSON files with token-efficient output for LLMs with limited context.
Provides schema extraction and smart sampling instead of dumping entire content.

Configuration is read from config.yaml under files.processing.json
"""

import logging
import json
from typing import Dict, Any, List, Union, Optional
from .base_processor import FileProcessor

logger = logging.getLogger(__name__)

# Default values (used when config is not provided)
DEFAULT_FULL_DATA_ITEM_THRESHOLD = 200  # Include all items for arrays <= this size
DEFAULT_MAX_ARRAY_PREVIEW_ITEMS = 3
DEFAULT_MAX_SCHEMA_DEPTH = 4
DEFAULT_MAX_STRING_LENGTH = 100
DEFAULT_MAX_OBJECT_KEYS = 20


class JSONProcessor(FileProcessor):
    """
    Processor for JSON files with token-efficient output.

    Optimized for LLMs with limited context (e.g., local Ollama with 8K tokens).
    Instead of dumping entire JSON, extracts:
    - Schema/structure information
    - Sample data from arrays
    - Key statistics

    Configuration (from config.yaml files.processing.json):
    - full_data_item_threshold: Max items for full data mode (default: 200)
    - max_array_preview_items: Items to show in array previews (default: 3)
    - max_schema_depth: Max depth for schema extraction (default: 4)
    - max_string_length: Max string length before truncation (default: 100)
    - max_object_keys: Max keys to show for large objects (default: 20)

    Supports: application/json
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize JSON processor with optional configuration.

        Args:
            config: Configuration dictionary (typically from config.yaml)
        """
        super().__init__()
        self._load_config(config)

    def _load_config(self, config: Optional[Dict[str, Any]] = None):
        """Load settings from config or use defaults."""
        json_config = {}
        if config:
            json_config = config.get('files', {}).get('processing', {}).get('json', {})

        self.full_data_item_threshold = json_config.get(
            'full_data_item_threshold', DEFAULT_FULL_DATA_ITEM_THRESHOLD
        )
        self.max_array_preview_items = json_config.get(
            'max_array_preview_items', DEFAULT_MAX_ARRAY_PREVIEW_ITEMS
        )
        self.max_schema_depth = json_config.get(
            'max_schema_depth', DEFAULT_MAX_SCHEMA_DEPTH
        )
        self.max_string_length = json_config.get(
            'max_string_length', DEFAULT_MAX_STRING_LENGTH
        )
        self.max_object_keys = json_config.get(
            'max_object_keys', DEFAULT_MAX_OBJECT_KEYS
        )

        logger.debug(
            f"JSONProcessor config: full_data_item_threshold={self.full_data_item_threshold}, "
            f"max_array_preview_items={self.max_array_preview_items}, "
            f"max_schema_depth={self.max_schema_depth}"
        )

    def supports_mime_type(self, mime_type: str) -> bool:
        """Check if this processor supports the MIME type."""
        return mime_type.lower() == 'application/json'

    def _get_type_name(self, value: Any) -> str:
        """Get a human-readable type name for a value."""
        if value is None:
            return "null"
        elif isinstance(value, bool):
            return "boolean"
        elif isinstance(value, int):
            return "integer"
        elif isinstance(value, float):
            return "number"
        elif isinstance(value, str):
            return "string"
        elif isinstance(value, list):
            return "array"
        elif isinstance(value, dict):
            return "object"
        return type(value).__name__

    def _truncate_string(self, s: str, max_len: int = None) -> str:
        """Truncate long strings with ellipsis."""
        if max_len is None:
            max_len = self.max_string_length
        if len(s) <= max_len:
            return s
        return s[:max_len] + "..."

    def _extract_schema(self, data: Any, depth: int = 0, path: str = "") -> Dict[str, Any]:
        """
        Extract schema information from JSON data.

        Returns a schema dict describing the structure without full data.
        """
        if depth > self.max_schema_depth:
            return {"type": self._get_type_name(data), "truncated": True}

        if data is None:
            return {"type": "null"}
        elif isinstance(data, bool):
            return {"type": "boolean", "example": data}
        elif isinstance(data, (int, float)):
            return {"type": self._get_type_name(data), "example": data}
        elif isinstance(data, str):
            return {
                "type": "string",
                "length": len(data),
                "example": self._truncate_string(data)
            }
        elif isinstance(data, list):
            schema = {
                "type": "array",
                "length": len(data)
            }
            if data:
                # Sample first item to infer array item type
                first_item = data[0]
                schema["items"] = self._extract_schema(first_item, depth + 1, f"{path}[0]")
                # Check if array is homogeneous
                if len(data) > 1:
                    types = set(self._get_type_name(item) for item in data[:10])
                    schema["homogeneous"] = len(types) == 1
            return schema
        elif isinstance(data, dict):
            schema = {
                "type": "object",
                "key_count": len(data)
            }
            keys = list(data.keys())
            if len(keys) > self.max_object_keys:
                schema["keys_truncated"] = True
                keys = keys[:self.max_object_keys]

            schema["properties"] = {}
            for key in keys:
                schema["properties"][key] = self._extract_schema(
                    data[key], depth + 1, f"{path}.{key}"
                )
            return schema

        return {"type": self._get_type_name(data)}

    def _format_value_compact(self, value: Any, depth: int = 0) -> str:
        """Format a value compactly for preview."""
        if value is None:
            return "null"
        elif isinstance(value, bool):
            return str(value).lower()
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, str):
            return f'"{self._truncate_string(value)}"'
        elif isinstance(value, list):
            if depth > 1:
                return f"[...{len(value)} items]"
            if not value:
                return "[]"
            items = [self._format_value_compact(v, depth + 1) for v in value[:2]]
            if len(value) > 2:
                items.append(f"...+{len(value) - 2} more")
            return f"[{', '.join(items)}]"
        elif isinstance(value, dict):
            if depth > 1:
                return f"{{...{len(value)} keys}}"
            if not value:
                return "{}"
            keys = list(value.keys())[:2]
            items = [f"{k}: {self._format_value_compact(value[k], depth + 1)}" for k in keys]
            if len(value) > 2:
                items.append(f"...+{len(value) - 2} more")
            return f"{{{', '.join(items)}}}"
        return str(value)

    def _format_array_sample(self, data: List, max_items: int = None) -> str:
        """Format a sample of array items."""
        if max_items is None:
            max_items = self.max_array_preview_items
        if not data:
            return "  (empty array)"

        lines = []
        sample_items = data[:max_items]

        for i, item in enumerate(sample_items):
            if isinstance(item, dict):
                # For objects, show key-value pairs compactly
                preview = self._format_value_compact(item)
                lines.append(f"  [{i}]: {preview}")
            else:
                lines.append(f"  [{i}]: {self._format_value_compact(item)}")

        if len(data) > max_items:
            lines.append(f"  ... and {len(data) - max_items} more items")

        return "\n".join(lines)

    def _format_object_summary(self, data: Dict, indent: str = "") -> str:
        """Format object with key summaries."""
        lines = []
        keys = list(data.keys())

        if len(keys) > self.max_object_keys:
            shown_keys = keys[:self.max_object_keys]
            lines.append(f"{indent}(showing {self.max_object_keys} of {len(keys)} keys)")
        else:
            shown_keys = keys

        for key in shown_keys:
            value = data[key]
            type_name = self._get_type_name(value)

            if isinstance(value, list):
                lines.append(f"{indent}{key}: array[{len(value)}]")
            elif isinstance(value, dict):
                lines.append(f"{indent}{key}: object{{{len(value)} keys}}")
            elif isinstance(value, str):
                preview = self._truncate_string(value, 50)
                lines.append(f'{indent}{key}: "{preview}"')
            else:
                lines.append(f"{indent}{key}: {self._format_value_compact(value)}")

        return "\n".join(lines)

    def _format_item_full(self, item: Any, index: int) -> str:
        """Format a single item with all key-value pairs for searchability."""
        if isinstance(item, dict):
            # Format each key-value pair for exact lookup support
            parts = []
            for key, value in item.items():
                if value is None:
                    parts.append(f"{key}=null")
                elif isinstance(value, str):
                    # Don't truncate strings in full data mode for searchability
                    parts.append(f"{key}={value}")
                elif isinstance(value, (list, dict)):
                    # Compact format for nested structures
                    parts.append(f"{key}={self._format_value_compact(value)}")
                else:
                    parts.append(f"{key}={value}")
            return f"  [{index}]: {' | '.join(parts)}"
        else:
            return f"  [{index}]: {self._format_value_compact(item)}"

    async def extract_text(self, file_data: bytes, filename: str = None) -> str:
        """
        Extract token-efficient text representation from JSON.

        Instead of dumping entire JSON, provides:
        - Structure summary
        - Schema information
        - Sample data for arrays
        """
        logger.debug(f"JSONProcessor.extract_text() called for file: {filename or 'unknown'} (token-optimized)")

        try:
            data = json.loads(file_data.decode('utf-8'))
            lines = []

            if isinstance(data, dict):
                lines.append(f"JSON Object with {len(data)} keys:")
                lines.append("")
                lines.append("Structure:")
                lines.append(self._format_object_summary(data, "  "))

                # If any values are arrays, show samples
                array_keys = [k for k, v in data.items() if isinstance(v, list) and v]
                if array_keys:
                    lines.append("")
                    lines.append("Array samples:")
                    for key in array_keys[:3]:  # Limit to 3 arrays
                        arr = data[key]
                        lines.append(f"  {key} ({len(arr)} items):")
                        sample = self._format_array_sample(arr, 2)
                        # Indent the sample
                        lines.append("  " + sample.replace("\n", "\n  "))

            elif isinstance(data, list):
                lines.append(f"JSON Array with {len(data)} items")

                if data:
                    # Determine item type
                    item_types = set(self._get_type_name(item) for item in data[:10])
                    if len(item_types) == 1:
                        lines.append(f"Item type: {item_types.pop()}")
                    else:
                        lines.append(f"Item types: {', '.join(sorted(item_types))}")

                    # If items are objects, show common keys
                    if isinstance(data[0], dict):
                        all_keys = set()
                        for item in data[:10]:
                            if isinstance(item, dict):
                                all_keys.update(item.keys())
                        if all_keys:
                            lines.append(f"Keys found: {', '.join(sorted(all_keys)[:15])}")
                            if len(all_keys) > 15:
                                lines.append(f"  ...and {len(all_keys) - 15} more keys")

                    lines.append("")

                    # For small arrays, include ALL data to enable exact lookups
                    if len(data) <= self.full_data_item_threshold:
                        logger.debug(f"JSONProcessor: Small array ({len(data)} items), including all data for exact lookups")
                        lines.append("Data:")
                        for i, item in enumerate(data):
                            lines.append(self._format_item_full(item, i))
                    else:
                        # Large array: use token-efficient summary
                        logger.debug(f"JSONProcessor: Large array ({len(data)} items), using summary mode")
                        lines.append("Sample items:")
                        lines.append(self._format_array_sample(data, self.max_array_preview_items))

            else:
                # Primitive value
                lines.append(f"JSON value ({self._get_type_name(data)}): {self._format_value_compact(data)}")

            result = "\n".join(lines)
            logger.debug(f"JSONProcessor extracted {len(result)} chars (token-optimized) from {filename or 'unknown'}")
            return result

        except Exception as e:
            logger.error(f"Error processing JSON: {e}")
            raise
    
    async def extract_metadata(self, file_data: bytes, filename: str = None) -> Dict[str, Any]:
        """Extract metadata from JSON."""
        metadata = await super().extract_metadata(file_data, filename)
        
        try:
            data = json.loads(file_data.decode('utf-8'))
            
            if isinstance(data, dict):
                metadata.update({
                    'object_type': 'dict',
                    'keys': ', '.join(str(k) for k in data.keys()),  # Convert to comma-separated string
                    'key_count': len(data),
                })
            elif isinstance(data, list):
                metadata.update({
                    'object_type': 'array',
                    'item_count': len(data),
                })
            
            metadata['mime_type'] = 'application/json'
        
        except Exception as e:
            logger.warning(f"Error extracting JSON metadata: {e}")
        
        return metadata
