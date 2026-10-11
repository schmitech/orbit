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


def _fake_item(text, page_numbers):
    return SimpleNamespace(
        text=text,
        prov=[SimpleNamespace(page_no=p) for p in page_numbers],
    )


def _fake_doc_with_items(markdown_text, items):
    return SimpleNamespace(
        export_to_markdown=lambda **kwargs: markdown_text,
        iterate_items=lambda: [(item, 0) for item in items],
    )


def test_extract_page_segments_uses_item_provenance_not_enumeration():
    """Page numbers must come from Docling's own provenance, never from
    counting marker-delimited parts — a document whose first content is on
    page 2 (e.g. an earlier page was skipped/blank) must report page 2."""
    processor = DoclingProcessor(enabled=True)
    doc = _fake_doc_with_items(
        "Page two text.Page four text.",
        [
            _fake_item("Page two text.", [2]),
            _fake_item("Page four text.", [4]),
        ],
    )

    text, segments = processor._extract_page_segments(doc)

    assert text == "Page two text.Page four text."
    assert segments == [
        {"start": 0, "end": len("Page two text."), "page_numbers": [2]},
        {"start": len("Page two text."), "end": len(text), "page_numbers": [4]},
    ]


def test_extract_page_segments_item_spanning_multiple_pages():
    processor = DoclingProcessor(enabled=True)
    doc = _fake_doc_with_items("Spanning text.", [_fake_item("Spanning text.", [3, 4])])

    text, segments = processor._extract_page_segments(doc)

    assert segments == [{"start": 0, "end": len(text), "page_numbers": [3, 4]}]


def test_extract_page_segments_returns_empty_when_no_provenance():
    """A format with no physical pages (e.g. Markdown/HTML source) must never
    fabricate a page-1 citation — no provenance means no segments at all."""
    processor = DoclingProcessor(enabled=True)
    doc = _fake_doc_with_items(
        "Some prose with no page info.",
        [_fake_item("Some prose with no page info.", [])],
    )

    text, segments = processor._extract_page_segments(doc)

    assert text == "Some prose with no page info."
    assert segments == []


def test_extract_page_segments_skips_items_with_no_provenance_but_keeps_others():
    processor = DoclingProcessor(enabled=True)
    doc = _fake_doc_with_items(
        "No page info.Known page.",
        [
            _fake_item("No page info.", []),
            _fake_item("Known page.", [5]),
        ],
    )

    text, segments = processor._extract_page_segments(doc)

    assert segments == [{"start": len("No page info."), "end": len(text), "page_numbers": [5]}]


def test_extract_page_segments_empty_text_returns_no_segments():
    processor = DoclingProcessor(enabled=True)
    doc = _fake_doc_with_items("", [])

    text, segments = processor._extract_page_segments(doc)

    assert text == ""
    assert segments == []


@pytest.mark.asyncio
async def test_extract_text_reports_no_page_segments_for_markdown_source():
    """Markdown-sourced documents carry no physical-page provenance in
    Docling, so page citation must stay unknown rather than defaulting to 1."""
    processor = DoclingProcessor(enabled=True)

    await processor.extract_text(b"# Report\n\nJust prose, no tables here.\n", filename="prose.md")

    assert processor._last_page_segments == []
