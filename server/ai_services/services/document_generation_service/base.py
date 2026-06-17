import io
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class BaseRenderer:
    """Shared config helpers and cross-format utilities."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._cfg: Dict[str, Any] = config or {}

    def _get(self, fmt: str, *keys, default=None):
        """Safe nested lookup: self._cfg[fmt][keys[0]][keys[1]]..."""
        node = self._cfg.get(fmt, {})
        for k in keys:
            if not isinstance(node, dict):
                return default
            node = node.get(k)
            if node is None:
                return default
        if node == {}:
            return default
        return node

    def _meta(self, key: str, default: str = "") -> str:
        return self._cfg.get("metadata", {}).get(key, default)

    def _build_meta_line(self, spec: Dict[str, Any]) -> str:
        meta = spec.get("metadata", {})
        parts = []
        configured_author = self._meta("author", "")
        author = configured_author or meta.get("author", "ORBIT")
        org = self._meta("organization", "")
        display_author = f"{author} — {org}" if org else author
        parts.append(f"Author: {display_author}")
        if meta.get("date"):
            parts.append(f"Date: {meta['date']}")
        return "  |  ".join(parts)

    @staticmethod
    def _normalize_table_rows(table_data):
        safe_rows = [[str(cell) for cell in row] for row in table_data if row]
        if not safe_rows:
            return []
        column_count = max(len(row) for row in safe_rows)
        return [row + [""] * (column_count - len(row)) for row in safe_rows]
