"""
Tests for adapter interface and mutation contracts.
"""

from adapters.base import DocumentAdapter
from adapters.file.adapter import FileAdapter
from adapters.qa.base import QADocumentAdapter


class StubAdapter(DocumentAdapter):
    def format_document(self, raw_doc, metadata):
        return {"content": raw_doc, "metadata": metadata}

    def extract_direct_answer(self, context):
        return None

    def apply_domain_specific_filtering(self, context_items, query):
        return [{"query": query, **item} for item in context_items]


def test_base_apply_domain_filtering_delegates_to_specific_filtering():
    adapter = StubAdapter()

    result = adapter.apply_domain_filtering([{"content": "alpha"}], "alpha")

    assert result == [{"query": "alpha", "content": "alpha"}]


def test_file_adapter_filtering_does_not_mutate_input_confidence():
    adapter = FileAdapter(config={"confidence_threshold": 0.1})
    context = [
        {
            "content": "budget",
            "content_type": "document",
            "filename": "budget-report.pdf",
            "confidence": 0.5,
            "upload_timestamp": "2026-06-17T00:00:00Z",
        }
    ]

    result = adapter.apply_domain_specific_filtering(context, "budget")

    assert context[0]["confidence"] == 0.5
    assert result[0]["confidence"] == 0.6


def test_file_adapter_upload_timestamp_does_not_boost_by_itself():
    adapter = FileAdapter(config={"confidence_threshold": 0.1})
    context = [
        {
            "content": "unrelated",
            "content_type": "unknown",
            "filename": "notes.txt",
            "confidence": 0.5,
            "upload_timestamp": "2026-06-17T00:00:00Z",
        }
    ]

    result = adapter.apply_domain_specific_filtering(context, "budget")

    assert result[0]["confidence"] == 0.5


def test_qa_filtering_does_not_mutate_input_and_applies_single_exact_boost():
    adapter = QADocumentAdapter(config={"confidence_threshold": 0.1, "boost_exact_matches": True})
    context = [{"question": "What is Orbit?", "answer": "A gateway", "confidence": 0.5}]

    result = adapter.apply_domain_specific_filtering(context, "What is Orbit?")

    assert context[0]["confidence"] == 0.5
    assert result[0]["confidence"] == 0.75
