import csv
import io
from typing import Dict, Any

from .base import BaseRenderer


class CSVRenderer(BaseRenderer):
    """Render a document spec to CSV bytes using the stdlib csv module.

    Each section that contains a table is written as a block separated by a
    blank line. Sections without a table are skipped — CSV is inherently
    tabular, so body text and bullet points have nowhere natural to go.
    When only one section has a table the output is a plain flat CSV with no
    separator blocks.
    """

    def render(self, spec: Dict[str, Any]) -> bytes:
        sections_with_tables = [
            s for s in spec.get("sections", [])
            if s.get("table") and len(s["table"]) > 0
        ]

        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        multi = len(sections_with_tables) > 1

        for idx, section in enumerate(sections_with_tables):
            if multi:
                if idx > 0:
                    writer.writerow([])  # blank separator between blocks
                heading = section.get("heading", f"Section {idx + 1}")
                writer.writerow([heading])

            normalized = self._normalize_table_rows(section["table"])
            for row in normalized:
                writer.writerow(row)

        return buf.getvalue().encode("utf-8")
