import io
from typing import Dict, Any, List

from .base import BaseRenderer


class MarkdownRenderer(BaseRenderer):
    """Render a document spec to Markdown bytes."""

    def render(self, spec: Dict[str, Any]) -> bytes:
        lines: List[str] = []

        title = spec.get("title", "Document")
        lines.append(f"# {title}")

        meta_line = self._build_meta_line(spec)
        if meta_line:
            lines.append(f"*{meta_line}*")

        lines.append("")

        for section in spec.get("sections", []):
            if section.get("heading"):
                lines.append(f"## {section['heading']}")
                lines.append("")
            if section.get("body"):
                lines.append(section["body"])
                lines.append("")
            for point in section.get("bullet_points") or []:
                lines.append(f"- {point}")
            if section.get("bullet_points"):
                lines.append("")
            table_data = section.get("table")
            if table_data and len(table_data) > 0:
                lines.extend(self._render_table(table_data))
                lines.append("")

        return "\n".join(lines).encode("utf-8")

    @staticmethod
    def _render_table(table_data) -> List[str]:
        normalized = MarkdownRenderer._normalize_table_rows(table_data)
        if not normalized:
            return []

        col_count = len(normalized[0])
        # Compute column widths for alignment
        widths = [
            max(len(str(normalized[r][c])) for r in range(len(normalized)))
            for c in range(col_count)
        ]

        def _row_line(row: List[str]) -> str:
            cells = [str(cell).ljust(widths[c]) for c, cell in enumerate(row)]
            return "| " + " | ".join(cells) + " |"

        lines = []
        lines.append(_row_line(normalized[0]))
        lines.append("| " + " | ".join("-" * w for w in widths) + " |")
        for row in normalized[1:]:
            lines.append(_row_line(row))
        return lines
