"""
Table rendering utilities for intent response formatting.

Supports multiple output formats: pipe-separated (default), markdown table, TOON, and CSV.
"""

import csv
import io
import logging
from typing import List, Any, Optional

logger = logging.getLogger(__name__)

try:
    from py_toon_format import dumps as toon_dumps
except ImportError:
    toon_dumps = None


class TableRenderer:
    """Renders tabular data in multiple formats."""

    @staticmethod
    def render(columns: List[str], rows: List[List[Any]], format: Optional[str] = None) -> str:
        """
        Render columns and rows into a table string.

        Args:
            columns: Column header names.
            rows: List of row value lists.
            format: One of None/"pipe" (default pipe-separated),
                    "markdown_table", "toon", "csv".

        Returns:
            Formatted table string.
        """
        effective_format = format or "pipe-separated"
        logger.debug("TableRenderer using format: %s (%d columns, %d rows)", effective_format, len(columns), len(rows))

        if format == "markdown_table":
            return TableRenderer._render_markdown_table(columns, rows)
        elif format == "toon":
            return TableRenderer._render_toon(columns, rows)
        elif format == "csv":
            return TableRenderer._render_csv(columns, rows)
        else:
            return TableRenderer._render_pipe_separated(columns, rows)

    @staticmethod
    def _render_pipe_separated(columns: List[str], rows: List[List[Any]]) -> str:
        """Current default: pipe-separated columns with a dashed separator line."""
        header = " | ".join(str(c) for c in columns)
        text = header + "\n"
        text += "-" * len(header) + "\n"
        for row in rows:
            text += " | ".join(str(v) for v in row) + "\n"
        return text

    @staticmethod
    def _render_markdown_table(columns: List[str], rows: List[List[Any]]) -> str:
        """Standard markdown table with | col | col | and --- separator."""
        header = "| " + " | ".join(str(c) for c in columns) + " |"
        separator = "| " + " | ".join("---" for _ in columns) + " |"
        lines = [header, separator]
        for row in rows:
            lines.append("| " + " | ".join(str(v) for v in row) + " |")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _render_toon(columns: List[str], rows: List[List[Any]]) -> str:
        """TOON format via py_toon_format. Falls back to pipe-separated if unavailable."""
        if toon_dumps is None:
            logger.debug("py_toon_format not installed, falling back to pipe-separated format")
            return TableRenderer._render_pipe_separated(columns, rows)
        try:
            data = [dict(zip(columns, row)) for row in rows]
            return toon_dumps(data)
        except Exception as e:
            logger.warning("TOON rendering failed (%s), falling back to pipe-separated", e)
            return TableRenderer._render_pipe_separated(columns, rows)

    @staticmethod
    def _render_csv(columns: List[str], rows: List[List[Any]]) -> str:
        """CSV format output."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(row)
        return output.getvalue()
