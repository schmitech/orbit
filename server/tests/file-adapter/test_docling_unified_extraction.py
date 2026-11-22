"""
Tests for DoclingProcessor.extract() — the unified single-conversion path
added by docs/roadmap/complete/file-processing-unified-extraction-result.md.
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.file_processing import docling_processor
from services.file_processing.docling_processor import DoclingProcessor


@pytest.fixture(autouse=True)
def _docling_not_required(monkeypatch):
    """These tests exercise DoclingProcessor.extract() against a fake
    converter, so the real docling package must not be required to run
    them — only DoclingProcessor's own control flow is under test."""
    monkeypatch.setattr(docling_processor, "DOCLING_AVAILABLE", True)


def _processor_with_fake_converter(convert_fn):
    processor = DoclingProcessor(enabled=True)
    processor._initialized = True
    processor._converter = SimpleNamespace(convert=convert_fn)
    return processor


def _fake_item(text, page_numbers):
    return SimpleNamespace(
        text=text,
        prov=[SimpleNamespace(page_no=p) for p in page_numbers],
    )


def _fake_doc(markdown_text, items=None, tables=None, page_count=3):
    return SimpleNamespace(
        export_to_markdown=lambda: markdown_text,
        iterate_items=lambda: iter([(item, 0) for item in (items or [])]),
        tables=tables or [],
        page_count=page_count,
    )


@pytest.mark.asyncio
async def test_extract_raises_when_conversion_fails():
    """A failed conversion must propagate so _extract_content's processor
    fallback loop still triggers — not be swallowed the way the old
    metadata-only try/except did."""
    def fake_convert(temp_path):
        raise RuntimeError("simulated conversion failure")

    processor = _processor_with_fake_converter(fake_convert)

    with pytest.raises(RuntimeError, match="simulated conversion failure"):
        await processor.extract(b"irrelevant bytes", filename="doc.pdf")


@pytest.mark.asyncio
async def test_extract_returns_content_when_metadata_derivation_fails():
    """A failure while deriving extra metadata fields from the already-
    converted document must not discard the text/tables/page_segments
    already derived from that same successful conversion."""
    class _BadDoc:
        def export_to_markdown(self):
            return "# Hello\n\nSome text."

        def iterate_items(self):
            return iter([])

        tables: ClassVar[list] = []

        @property
        def page_count(self):
            raise RuntimeError("simulated metadata derivation failure")

    processor = _processor_with_fake_converter(lambda temp_path: SimpleNamespace(document=_BadDoc()))

    result = await processor.extract(b"irrelevant bytes", filename="doc.pdf")

    assert result.text == "# Hello\n\nSome text."
    assert result.tables == []
    assert "page_count" not in result.metadata


@pytest.mark.asyncio
async def test_extract_sequential_calls_do_not_clobber_prior_result():
    """Calling extract() again on a shared processor instance must not
    mutate a previously-returned ExtractionResult's tables/page_segments —
    the bug class this doc exists to close. Each fake document has its own
    page provenance so a result that leaked the other call's segments (or
    dropped its own) would be caught, not just one with mismatched text."""
    def _table(text):
        return SimpleNamespace(
            data=SimpleNamespace(
                num_rows=1,
                num_cols=1,
                table_cells=[SimpleNamespace(start_row_offset_idx=0, start_col_offset_idx=0, row_span=1, col_span=1, text=text)],
            ),
            prov=[],
        )

    docs = [
        _fake_doc(
            "first document text",
            items=[_fake_item("first document text", [1])],
            tables=[_table("first")],
        ),
        _fake_doc(
            "second document text",
            items=[_fake_item("second document text", [9])],
            tables=[_table("second")],
        ),
    ]
    calls = iter(docs)
    processor = _processor_with_fake_converter(lambda temp_path: SimpleNamespace(document=next(calls)))

    result1 = await processor.extract(b"first bytes", filename="a.pdf")
    result2 = await processor.extract(b"second bytes", filename="b.pdf")

    assert result1.text == "first document text"
    assert result1.tables[0]["cells"][0]["text"] == "first"
    assert result1.page_segments == [{"start": 0, "end": len("first document text"), "page_numbers": [1]}]

    assert result2.text == "second document text"
    assert result2.tables[0]["cells"][0]["text"] == "second"
    assert result2.page_segments == [{"start": 0, "end": len("second document text"), "page_numbers": [9]}]

    # result1 must still hold its own segments after result2 was computed.
    assert result1.page_segments == [{"start": 0, "end": len("first document text"), "page_numbers": [1]}]
