"""
Tests for Docling table-structure extraction (Phase 1.1 of
docs/roadmap/document-understanding-enhancements.md).

Uses a Markdown source rather than a PDF: Docling's table-structure parsing
exercises the same `_extract_tables()` code path for Markdown as for PDF,
without requiring the PDF layout/vision model (torch + torchvision), which
isn't part of this project's CPU-only runtime dependencies.
"""

import sys
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest

warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*builtin type SwigPyPacked.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*builtin type SwigPyObject.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*builtin type swigvarlink.*")

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

pytest.importorskip("docling")

from services.file_processing.docling_processor import DoclingProcessor

TABLE_MARKDOWN = b"""# Report

| Name | Age |
| --- | --- |
| Alice | 30 |
| Bob | 25 |
"""


@pytest.mark.asyncio
async def test_extract_text_captures_structured_table():
    processor = DoclingProcessor(enabled=True)

    await processor.extract_text(TABLE_MARKDOWN, filename="report.md")

    tables = processor._last_tables
    assert len(tables) == 1

    table = tables[0]
    assert table["num_rows"] == 3
    assert table["num_cols"] == 2
    assert len(table["cells"]) == 6

    cell_texts = {cell["text"] for cell in table["cells"]}
    assert {"Name", "Age", "Alice", "30", "Bob", "25"} <= cell_texts


@pytest.mark.asyncio
async def test_extract_text_with_no_table_returns_empty_list():
    processor = DoclingProcessor(enabled=True)

    await processor.extract_text(b"# Report\n\nJust prose, no tables here.\n", filename="prose.md")

    assert processor._last_tables == []


def _fake_table(page_numbers):
    return SimpleNamespace(
        data=SimpleNamespace(num_rows=1, num_cols=1, table_cells=[]),
        prov=[SimpleNamespace(page_no=p) for p in page_numbers],
    )


def test_extract_tables_reports_page_number_for_single_page_table():
    processor = DoclingProcessor(enabled=True)
    doc = SimpleNamespace(tables=[_fake_table([2])])

    tables = processor._extract_tables(doc)

    assert tables[0]["page_number"] == 2
    assert tables[0]["page_range"] is None


def test_extract_tables_reports_page_range_for_multi_page_table():
    processor = DoclingProcessor(enabled=True)
    doc = SimpleNamespace(tables=[_fake_table([3, 4, 5])])

    tables = processor._extract_tables(doc)

    assert tables[0]["page_number"] is None
    assert tables[0]["page_range"] == [3, 5]


def test_extract_tables_reports_unknown_page_when_no_provenance():
    processor = DoclingProcessor(enabled=True)
    doc = SimpleNamespace(tables=[_fake_table([])])

    tables = processor._extract_tables(doc)

    assert tables[0]["page_number"] is None
    assert tables[0]["page_range"] is None
