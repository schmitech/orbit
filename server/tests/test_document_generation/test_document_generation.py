"""
Tests for document generation skill.

Covers:
- DocumentRenderer: all four formats (pdf, docx, xlsx, pptx)
- DocumentGenerationStep: should_execute, process (LLM spec + render), fallback path
- ResponseProcessor.build_result: document fields forwarded
- StreamingHandler.build_done_chunk: document fields forwarded
- ProcessingContext: document fields present
"""

import base64
import functools
import io
import json
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from pypdf import PdfReader

# Add server directory to path (same pattern as test_inference_bug_fixes.py)
_server_dir = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, _server_dir)


@functools.lru_cache(maxsize=1)
def _load_test_config():
    """Load the real config/rewriters-prompts.yaml so tests exercise the actual production
    prompts (issue #279: prompts are no longer hardcoded in Python)."""
    path = os.path.join(_server_dir, '..', 'config', 'rewriters-prompts.yaml')
    with open(path) as f:
        return yaml.safe_load(f)


TEST_CONFIG = _load_test_config()
DOCUMENT_PROMPT_CFG = TEST_CONFIG['rewriters']['document']

# Pre-register 'inference' as a namespace package to skip its heavy __init__.py
if 'inference' not in sys.modules:
    _pkg = types.ModuleType('inference')
    _pkg.__path__ = [os.path.join(_server_dir, 'inference')]
    _pkg.__package__ = 'inference'
    sys.modules['inference'] = _pkg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_SPEC = {
    "title": "Q1 Sales Report",
    "sections": [
        {
            "heading": "Executive Summary",
            "body": "Revenue grew 12% year-over-year.",
            "bullet_points": ["Strong North America", "EMEA slightly below target"],
        },
        {
            "heading": "Sales by Region",
            "body": "Detailed breakdown below.",
            "table": [
                ["Region", "Revenue", "Growth"],
                ["North America", "$4.2M", "+18%"],
                ["EMEA", "$1.9M", "+4%"],
            ],
        },
    ],
    "metadata": {"author": "ORBIT", "date": "2026-05-23"},
}

CHART_SPEC = {
    "title": "Quarterly Revenue",
    "sections": [
        {
            "heading": "Revenue Trend",
            "body": "Revenue increased each quarter.",
            "chart": {
                "type": "bar",
                "title": "Revenue by Quarter",
                "labels": ["Q1", "Q2", "Q3", "Q4"],
                "datasets": [{"label": "Revenue", "data": [2.4, 2.9, 3.2, 3.8]}],
            },
        }
    ],
    "metadata": {"author": "ORBIT", "date": "2026-06-28"},
}


def _make_container(adapter_type: str = "document_generation",
                    document_format: str = "pdf",
                    llm_provider=None,
                    thread_dataset_service=None):
    """Build a minimal ServiceContainer mock for DocumentGenerationStep."""
    adapter_manager = MagicMock()
    adapter_manager.get_adapter_config.return_value = {
        "type": adapter_type,
        "document_format": document_format,
        "rewrite_provider": None,
    }
    adapter_manager.get_overridden_provider = AsyncMock(return_value=None)

    known = {"adapter_manager": adapter_manager, "llm_provider": llm_provider, "config": TEST_CONFIG}
    if thread_dataset_service is not None:
        known["thread_dataset_service"] = thread_dataset_service

    container = MagicMock()
    container.has.side_effect = lambda key: key in known and known[key] is not None
    container.get.side_effect = lambda key: known.get(key)
    container.get_or_none.side_effect = lambda key: known.get(key)
    return container


def _make_memory_service(stored=None):
    """A minimal fake ThreadDatasetService using the same store/get key transform
    as the real service, so tests exercise the same key-alignment as production."""
    store = {}
    if stored:
        store.update(stored)

    service = MagicMock()
    service.enabled = True
    service._generate_dataset_key = MagicMock(side_effect=lambda thread_id: f"thread_dataset:{thread_id}")

    async def get_dataset(key):
        return store.get(key)

    async def store_dataset(thread_id, query_context, raw_results):
        key = service._generate_dataset_key(thread_id)
        store[key] = (query_context, raw_results)
        return key

    service.get_dataset = AsyncMock(side_effect=get_dataset)
    service.store_dataset = AsyncMock(side_effect=store_dataset)
    return service


# ---------------------------------------------------------------------------
# DocumentRenderer tests
# ---------------------------------------------------------------------------

class TestDocumentRenderer:
    """DocumentRenderer renders valid binary output for each format."""

    def setup_method(self):
        from ai_services.services.document_generation_service import DocumentRenderer
        self.renderer = DocumentRenderer()

    def test_render_pdf(self):
        data = self.renderer.render(SAMPLE_SPEC, "pdf")
        assert isinstance(data, bytes)
        assert len(data) > 100
        assert data[:4] == b"%PDF"   # PDF magic bytes

    def test_render_pdf_wide_table_uses_landscape_page(self):
        spec = {
            "title": "Wide Table",
            "sections": [
                {
                    "heading": "Metrics",
                    "table": [
                        [f"Column {i}" for i in range(1, 10)],
                        [f"Value {i}" for i in range(1, 10)],
                    ],
                }
            ],
            "metadata": {"author": "ORBIT", "date": "2026-06-06"},
        }

        data = self.renderer.render(spec, "pdf")
        page = PdfReader(io.BytesIO(data)).pages[0]
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)

        assert width > height

    def test_render_docx(self):
        data = self.renderer.render(SAMPLE_SPEC, "docx")
        assert isinstance(data, bytes)
        assert len(data) > 100
        # DOCX is a ZIP archive
        assert data[:2] == b"PK"

    def test_render_pdf_embeds_chart_image(self):
        without_chart = {
            **CHART_SPEC,
            "sections": [{k: v for k, v in CHART_SPEC["sections"][0].items() if k != "chart"}],
        }

        pdf_without_chart = self.renderer.render(without_chart, "pdf")
        pdf_with_chart = self.renderer.render(CHART_SPEC, "pdf")

        assert pdf_with_chart[:4] == b"%PDF"
        assert len(pdf_with_chart) > len(pdf_without_chart)

    def test_render_docx_embeds_chart_image(self):
        without_chart = {
            **CHART_SPEC,
            "sections": [{k: v for k, v in CHART_SPEC["sections"][0].items() if k != "chart"}],
        }

        docx_without_chart = self.renderer.render(without_chart, "docx")
        docx_with_chart = self.renderer.render(CHART_SPEC, "docx")

        assert docx_with_chart[:2] == b"PK"
        assert len(docx_with_chart) > len(docx_without_chart)

    def test_render_pptx_embeds_chart_image(self):
        without_chart = {
            **CHART_SPEC,
            "sections": [{k: v for k, v in CHART_SPEC["sections"][0].items() if k != "chart"}],
        }

        pptx_without_chart = self.renderer.render(without_chart, "pptx")
        pptx_with_chart = self.renderer.render(CHART_SPEC, "pptx")

        assert pptx_with_chart[:2] == b"PK"
        assert len(pptx_with_chart) > len(pptx_without_chart)

    def test_render_xlsx(self):
        data = self.renderer.render(SAMPLE_SPEC, "xlsx")
        assert isinstance(data, bytes)
        assert len(data) > 100
        assert data[:2] == b"PK"  # XLSX is also a ZIP

    def test_render_pptx(self):
        data = self.renderer.render(SAMPLE_SPEC, "pptx")
        assert isinstance(data, bytes)
        assert len(data) > 100
        assert data[:2] == b"PK"  # PPTX is also a ZIP

    def test_render_unsupported_format_raises(self):
        with pytest.raises(ValueError, match="Unsupported document format"):
            self.renderer.render(SAMPLE_SPEC, "rtf")

    def test_render_spec_without_table(self):
        spec = {
            "title": "Simple Doc",
            "sections": [{"heading": "Only Text", "body": "No table here.", "bullet_points": []}],
            "metadata": {"author": "ORBIT", "date": "2026-05-23"},
        }
        for fmt in ("pdf", "docx", "xlsx", "pptx"):
            data = self.renderer.render(spec, fmt)
            assert len(data) > 0, f"{fmt} returned empty bytes for spec without table"

    def test_render_minimal_spec(self):
        spec = {"title": "T", "sections": [], "metadata": {}}
        for fmt in ("pdf", "docx", "xlsx", "pptx"):
            data = self.renderer.render(spec, fmt)
            assert len(data) > 0, f"{fmt} failed on minimal spec"

    def test_render_format_case_insensitive(self):
        data_lower = self.renderer.render(SAMPLE_SPEC, "pdf")
        data_upper = self.renderer.render(SAMPLE_SPEC, "PDF")
        assert data_lower[:4] == b"%PDF"
        assert data_upper[:4] == b"%PDF"

    def test_mime_types_mapping(self):
        from ai_services.services.document_generation_service import MIME_TYPES
        assert MIME_TYPES["pdf"] == "application/pdf"
        assert "docx" in MIME_TYPES
        assert "xlsx" in MIME_TYPES
        assert "pptx" in MIME_TYPES


# ---------------------------------------------------------------------------
# DocumentGenerationStep.should_execute tests
# ---------------------------------------------------------------------------

class TestDocumentGenerationStepShouldExecute:
    def setup_method(self):
        from inference.pipeline.steps.document_generation import DocumentGenerationStep
        self.StepClass = DocumentGenerationStep

    def test_executes_for_document_generation_adapter(self):
        from inference.pipeline.base import ProcessingContext
        container = _make_container(adapter_type="document_generation")
        step = self.StepClass(container)
        ctx = ProcessingContext(adapter_name="pdf-generator")
        assert step.should_execute(ctx) is True

    def test_skips_for_image_generation_adapter(self):
        from inference.pipeline.base import ProcessingContext
        container = _make_container(adapter_type="image_generation")
        step = self.StepClass(container)
        ctx = ProcessingContext(adapter_name="image-generator")
        assert step.should_execute(ctx) is False

    def test_skips_when_blocked(self):
        from inference.pipeline.base import ProcessingContext
        container = _make_container(adapter_type="document_generation")
        step = self.StepClass(container)
        ctx = ProcessingContext(adapter_name="pdf-generator", is_blocked=True)
        assert step.should_execute(ctx) is False

    def test_skips_when_no_adapter_manager(self):
        from inference.pipeline.base import ProcessingContext
        container = MagicMock()
        container.has.return_value = False
        step = self.StepClass(container)
        ctx = ProcessingContext(adapter_name="pdf-generator")
        assert step.should_execute(ctx) is False

    def test_does_not_support_streaming(self):
        container = _make_container()
        step = self.StepClass(container)
        assert step.supports_streaming() is False


# ---------------------------------------------------------------------------
# DocumentGenerationStep.process — LLM spec path
# ---------------------------------------------------------------------------

class TestDocumentGenerationStepProcess:
    def setup_method(self):
        from inference.pipeline.steps.document_generation import DocumentGenerationStep
        self.StepClass = DocumentGenerationStep

    @pytest.mark.asyncio
    async def test_process_pdf_sets_context_fields(self):
        from inference.pipeline.base import ProcessingContext

        llm_provider = MagicMock()
        llm_provider.generate = AsyncMock(return_value=json.dumps(SAMPLE_SPEC))
        container = _make_container(document_format="pdf", llm_provider=llm_provider)

        step = self.StepClass(container)
        ctx = ProcessingContext(adapter_name="pdf-generator", message="Write a Q1 sales report")
        result = await step.process(ctx)

        assert result.error is None
        assert result.document is not None
        doc_bytes = base64.b64decode(result.document)
        assert doc_bytes[:4] == b"%PDF"
        assert result.document_format == "pdf"
        assert result.document_revised_prompt == SAMPLE_SPEC["title"]
        assert result.response == SAMPLE_SPEC["title"]

    @pytest.mark.asyncio
    async def test_process_docx_format(self):
        from inference.pipeline.base import ProcessingContext

        llm_provider = MagicMock()
        llm_provider.generate = AsyncMock(return_value=json.dumps(SAMPLE_SPEC))
        container = _make_container(document_format="docx", llm_provider=llm_provider)

        step = self.StepClass(container)
        ctx = ProcessingContext(adapter_name="word-generator", message="Create a word report")
        result = await step.process(ctx)

        assert result.error is None
        doc_bytes = base64.b64decode(result.document)
        assert doc_bytes[:2] == b"PK"   # ZIP / DOCX
        assert result.document_format == "docx"

    @pytest.mark.asyncio
    async def test_process_xlsx_format(self):
        from inference.pipeline.base import ProcessingContext

        llm_provider = MagicMock()
        llm_provider.generate = AsyncMock(return_value=json.dumps(SAMPLE_SPEC))
        container = _make_container(document_format="xlsx", llm_provider=llm_provider)

        step = self.StepClass(container)
        ctx = ProcessingContext(adapter_name="excel-generator", message="Export data to Excel")
        result = await step.process(ctx)

        assert result.error is None
        assert result.document_format == "xlsx"

    @pytest.mark.asyncio
    async def test_process_pptx_format(self):
        from inference.pipeline.base import ProcessingContext

        llm_provider = MagicMock()
        llm_provider.generate = AsyncMock(return_value=json.dumps(SAMPLE_SPEC))
        container = _make_container(document_format="pptx", llm_provider=llm_provider)

        step = self.StepClass(container)
        ctx = ProcessingContext(adapter_name="pptx-generator", message="Build a presentation")
        result = await step.process(ctx)

        assert result.error is None
        assert result.document_format == "pptx"

    @pytest.mark.asyncio
    async def test_process_uses_fallback_when_llm_returns_bad_json(self):
        from inference.pipeline.base import ProcessingContext

        llm_provider = MagicMock()
        llm_provider.generate = AsyncMock(return_value="This is not JSON at all.")
        container = _make_container(document_format="pdf", llm_provider=llm_provider)

        step = self.StepClass(container)
        ctx = ProcessingContext(adapter_name="pdf-generator", message="Make me a report")
        result = await step.process(ctx)

        # Fallback should still produce a valid document
        assert result.error is None
        assert result.document is not None
        doc_bytes = base64.b64decode(result.document)
        assert doc_bytes[:4] == b"%PDF"

    @pytest.mark.asyncio
    async def test_process_uses_fallback_when_no_llm_provider(self):
        from inference.pipeline.base import ProcessingContext

        container = _make_container(document_format="pdf", llm_provider=None)
        step = self.StepClass(container)
        ctx = ProcessingContext(adapter_name="pdf-generator", message="Create a brief report")
        result = await step.process(ctx)

        assert result.error is None
        assert result.document is not None

    @pytest.mark.asyncio
    async def test_process_strips_markdown_fences_from_llm_output(self):
        from inference.pipeline.base import ProcessingContext

        fenced = f"```json\n{json.dumps(SAMPLE_SPEC)}\n```"
        llm_provider = MagicMock()
        llm_provider.generate = AsyncMock(return_value=fenced)
        container = _make_container(document_format="pdf", llm_provider=llm_provider)

        step = self.StepClass(container)
        ctx = ProcessingContext(adapter_name="pdf-generator", message="Report with fenced output")
        result = await step.process(ctx)

        assert result.error is None
        assert result.document_revised_prompt == SAMPLE_SPEC["title"]

    @pytest.mark.asyncio
    async def test_process_uses_conversation_history_in_prompt(self):
        from inference.pipeline.base import ProcessingContext

        captured_prompt = {}

        async def capture_generate(prompt, **kwargs):
            captured_prompt["value"] = prompt
            return json.dumps(SAMPLE_SPEC)

        llm_provider = MagicMock()
        llm_provider.generate = capture_generate
        container = _make_container(document_format="pdf", llm_provider=llm_provider)

        step = self.StepClass(container)
        ctx = ProcessingContext(
            adapter_name="pdf-generator",
            message="Summarize the Q1 results as a PDF",
            context_messages=[
                {"role": "user", "content": "What were our Q1 numbers?"},
                {"role": "assistant", "content": "Revenue was $6.1M."},
            ],
        )
        await step.process(ctx)

        assert "Revenue was $6.1M" in captured_prompt["value"]

    @pytest.mark.asyncio
    async def test_process_falls_through_to_next_provider_on_failure(self):
        """If the first provider fails (e.g. bad API key), the next one is tried and its
        spec is used — the document must NOT degrade to the bare fallback."""
        from inference.pipeline.base import ProcessingContext

        failing_provider = MagicMock()
        failing_provider.generate = AsyncMock(side_effect=Exception("Invalid API key"))
        working_provider = MagicMock()
        working_provider.generate = AsyncMock(return_value=json.dumps(SAMPLE_SPEC))

        # rewrite_provider 'openai' resolves to the failing provider; the global provider works.
        adapter_manager = MagicMock()
        adapter_manager.get_adapter_config.return_value = {
            "type": "document_generation",
            "document_format": "pdf",
            "rewrite_provider": "openai",
        }
        adapter_manager.get_overridden_provider = AsyncMock(return_value=failing_provider)
        container = MagicMock()
        container.has.side_effect = lambda k: k in ("adapter_manager", "llm_provider", "config")
        container.get.side_effect = lambda k: (
            adapter_manager if k == "adapter_manager" else
            working_provider if k == "llm_provider" else TEST_CONFIG
        )
        container.get_or_none.side_effect = lambda k: (
            working_provider if k == "llm_provider" else TEST_CONFIG if k == "config" else None
        )

        step = self.StepClass(container)
        ctx = ProcessingContext(adapter_name="pdf-generator", message="Make me a report")
        result = await step.process(ctx)

        assert result.error is None
        failing_provider.generate.assert_awaited()      # first provider was tried
        working_provider.generate.assert_awaited()       # and we fell through to the next
        # The real spec (not the message-only fallback) was used.
        assert result.document_revised_prompt == SAMPLE_SPEC["title"]

    @pytest.mark.asyncio
    async def test_rewrite_model_passed_to_get_overridden_provider(self):
        """rewrite_model is forwarded as explicit_model_override to get_overridden_provider."""
        from inference.pipeline.base import ProcessingContext

        llm_provider = MagicMock()
        llm_provider.generate = AsyncMock(return_value=json.dumps(SAMPLE_SPEC))

        adapter_manager = MagicMock()
        adapter_manager.get_adapter_config.return_value = {
            "type": "document_generation",
            "document_format": "pdf",
            "rewrite_provider": "openai",
            "rewrite_model": "gpt-5.4-mini",
        }
        adapter_manager.get_overridden_provider = AsyncMock(return_value=llm_provider)

        container = MagicMock()
        container.has.side_effect = lambda k: k in ("adapter_manager", "llm_provider", "config")
        container.get.side_effect = lambda k: (
            adapter_manager if k == "adapter_manager" else llm_provider
        )
        container.get_or_none.side_effect = lambda k: (
            llm_provider if k == "llm_provider" else TEST_CONFIG if k == "config" else None
        )

        step = self.StepClass(container)
        ctx = ProcessingContext(adapter_name="pdf-generator", message="Make a report")
        await step.process(ctx)

        adapter_manager.get_overridden_provider.assert_awaited_once_with(
            "openai", "pdf-generator", explicit_model_override="gpt-5.4-mini"
        )

    @pytest.mark.asyncio
    async def test_rewrite_model_dedup_allows_same_provider_fallback(self):
        """When rewrite_model is set, provider/model and provider are distinct de-dupe
        keys — so the same provider with its default model can serve as a fallback."""
        from inference.pipeline.base import ProcessingContext

        failing_provider = MagicMock()
        failing_provider.generate = AsyncMock(side_effect=Exception("model unavailable"))
        working_provider = MagicMock()
        working_provider.generate = AsyncMock(return_value=json.dumps(SAMPLE_SPEC))

        adapter_manager = MagicMock()
        adapter_manager.get_adapter_config.return_value = {
            "type": "document_generation",
            "document_format": "pdf",
            "rewrite_provider": "openai",
            "rewrite_model": "gpt-5.4-mini",
            "inference_provider": "openai",   # same provider, no model override
        }
        # First call (with explicit_model_override) returns failing_provider;
        # second call (adapter inference_provider, no override) returns working_provider.
        adapter_manager.get_overridden_provider = AsyncMock(
            side_effect=[failing_provider, working_provider]
        )

        container = MagicMock()
        container.has.side_effect = lambda k: k in ("adapter_manager", "config")
        container.get.side_effect = lambda k: adapter_manager if k == "adapter_manager" else TEST_CONFIG
        container.get_or_none.side_effect = lambda k: TEST_CONFIG if k == "config" else None

        step = self.StepClass(container)
        ctx = ProcessingContext(adapter_name="pdf-generator", message="Make a report")
        result = await step.process(ctx)

        assert result.error is None
        failing_provider.generate.assert_awaited()
        working_provider.generate.assert_awaited()
        assert result.document_revised_prompt == SAMPLE_SPEC["title"]

    def test_fallback_spec_uses_prior_analysis_and_context(self):
        """When every provider fails, the fallback document carries the prior assistant
        analysis and thread-cached data — not just the user's question."""
        from inference.pipeline.base import ProcessingContext

        ctx = ProcessingContext(
            adapter_name="pdf-generator",
            message="Put all this findings in the document.",
            context_messages=[
                {"role": "user", "content": "Analyze customer 4096's orders"},
                {"role": "assistant", "content": "Customer 4096 has 3 orders totalling $496.39."},
            ],
            formatted_context="Order #1042 | Shipped | $129.99",
        )

        step = self.StepClass(_make_container(document_format="pdf"))
        spec = step._fallback_spec(ctx)
        bodies = [s.get("body", "") for s in spec["sections"]]
        assert any("Customer 4096 has 3 orders" in b for b in bodies)
        assert any("Order #1042" in b for b in bodies)
        # The bare question must not be the only content.
        assert spec["sections"][0]["heading"] != "Content"

    def test_fallback_spec_uses_message_when_no_prior_content(self):
        """With no prior analysis or context, the fallback records the request itself."""
        from inference.pipeline.base import ProcessingContext

        ctx = ProcessingContext(adapter_name="pdf-generator", message="Make a report")
        step = self.StepClass(_make_container(document_format="pdf"))
        spec = step._fallback_spec(ctx)
        assert spec["sections"] == [
            {"heading": "Content", "body": "Make a report", "bullet_points": []}
        ]

    def test_pdf_prompt_includes_chart_schema(self):
        from inference.pipeline.base import ProcessingContext

        ctx = ProcessingContext(
            adapter_name="pdf-generator",
            message="Make a PDF with sales trends",
        )
        step = self.StepClass(_make_container(document_format="pdf"))

        prompt = step._build_spec_prompt(ctx, "pdf", DOCUMENT_PROMPT_CFG)

        assert '"chart"' in prompt
        assert "chart.type: bar | line | pie | area" in prompt

    def test_pptx_prompt_includes_chart_schema(self):
        from inference.pipeline.base import ProcessingContext

        ctx = ProcessingContext(
            adapter_name="pptx-generator",
            message="Make a PowerPoint with sales trends",
        )
        step = self.StepClass(_make_container(document_format="pptx"))

        prompt = step._build_spec_prompt(ctx, "pptx", DOCUMENT_PROMPT_CFG)

        assert '"chart"' in prompt
        assert "Charts get their own slide" in prompt
        assert "chart.type: bar | line | pie | area" in prompt

    def test_xlsx_prompt_excludes_chart_schema(self):
        from inference.pipeline.base import ProcessingContext

        ctx = ProcessingContext(
            adapter_name="xlsx-generator",
            message="Export sales data",
        )
        step = self.StepClass(_make_container(document_format="xlsx"))

        prompt = step._build_spec_prompt(ctx, "xlsx", DOCUMENT_PROMPT_CFG)

        assert '"chart"' not in prompt
        assert "chart.type" not in prompt

    @pytest.mark.asyncio
    async def test_process_error_on_invalid_format(self):
        """An unrecognised format should set context.error."""
        from inference.pipeline.base import ProcessingContext

        llm_provider = MagicMock()
        llm_provider.generate = AsyncMock(return_value=json.dumps(SAMPLE_SPEC))

        # Build container that returns an unsupported format
        adapter_manager = MagicMock()
        adapter_manager.get_adapter_config.return_value = {
            "type": "document_generation",
            "document_format": "rtf",   # not supported
        }
        adapter_manager.get_overridden_provider = AsyncMock(return_value=None)
        container = MagicMock()
        container.has.side_effect = lambda k: k in ("adapter_manager", "llm_provider")
        container.get.side_effect = lambda k: (
            adapter_manager if k == "adapter_manager" else llm_provider
        )
        container.get_or_none.side_effect = lambda k: (
            llm_provider if k == "llm_provider" else None
        )

        from inference.pipeline.steps.document_generation import DocumentGenerationStep
        step = DocumentGenerationStep(container)
        ctx = ProcessingContext(adapter_name="rtf-generator", message="Make an RTF doc")
        result = await step.process(ctx)

        assert result.error is not None
        assert "rtf" in result.error.lower() or "unsupported" in result.error.lower()


# ---------------------------------------------------------------------------
# DocumentGenerationStep.process — generation memory (follow-up refinements)
# ---------------------------------------------------------------------------

class TestDocumentGenerationStepMemory:
    def setup_method(self):
        from inference.pipeline.steps.document_generation import DocumentGenerationStep
        self.StepClass = DocumentGenerationStep

    @pytest.mark.asyncio
    async def test_process_stores_spec_as_generation_memory_after_success(self):
        from inference.pipeline.base import ProcessingContext

        llm_provider = MagicMock()
        llm_provider.generate = AsyncMock(return_value=json.dumps(SAMPLE_SPEC))
        memory_service = _make_memory_service()
        container = _make_container(
            document_format="pdf", llm_provider=llm_provider, thread_dataset_service=memory_service,
        )

        step = self.StepClass(container)
        ctx = ProcessingContext(
            adapter_name="pdf-generator", message="Write a Q1 sales report", session_id="sess-1",
        )
        result = await step.process(ctx)

        assert result.error is None
        memory_service.store_dataset.assert_awaited_once()
        _, kwargs = memory_service.store_dataset.call_args
        assert kwargs["query_context"] == {"spec": SAMPLE_SPEC}

    @pytest.mark.asyncio
    async def test_process_does_not_store_memory_without_session_id(self):
        from inference.pipeline.base import ProcessingContext

        llm_provider = MagicMock()
        llm_provider.generate = AsyncMock(return_value=json.dumps(SAMPLE_SPEC))
        memory_service = _make_memory_service()
        container = _make_container(
            document_format="pdf", llm_provider=llm_provider, thread_dataset_service=memory_service,
        )

        step = self.StepClass(container)
        ctx = ProcessingContext(adapter_name="pdf-generator", message="Write a Q1 sales report")
        await step.process(ctx)

        memory_service.store_dataset.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_process_folds_previous_spec_into_rewrite_prompt(self):
        """A follow-up like 'add a chart to the sales section' should have the
        previous turn's full JSON spec available to the rewrite LLM, not just
        the conversation transcript."""
        from inference.pipeline.base import ProcessingContext

        captured_prompts = []

        async def capture_generate(prompt, **kwargs):
            captured_prompts.append(prompt)
            return json.dumps(SAMPLE_SPEC)

        llm_provider = MagicMock()
        llm_provider.generate = capture_generate
        memory_service = _make_memory_service()
        container = _make_container(
            document_format="pdf", llm_provider=llm_provider, thread_dataset_service=memory_service,
        )

        step = self.StepClass(container)

        first_ctx = ProcessingContext(
            adapter_name="pdf-generator", message="Write a Q1 sales report", session_id="sess-1",
        )
        await step.process(first_ctx)

        second_ctx = ProcessingContext(
            adapter_name="pdf-generator", message="Add a chart to the sales section", session_id="sess-1",
        )
        await step.process(second_ctx)

        assert len(captured_prompts) == 2
        assert SAMPLE_SPEC["title"] in captured_prompts[1]
        assert "refinement" in captured_prompts[1].lower()

    @pytest.mark.asyncio
    async def test_process_omits_previous_generation_slot_with_no_memory(self):
        from inference.pipeline.base import ProcessingContext
        from inference.pipeline.steps._utils import get_generation_memory

        memory_service = _make_memory_service()
        container = _make_container(document_format="pdf", thread_dataset_service=memory_service)

        step = self.StepClass(container)
        ctx = ProcessingContext(
            adapter_name="pdf-generator", message="Write a Q1 sales report", session_id="never-used-before",
        )
        memory = await get_generation_memory(container, ctx.adapter_name, ctx.session_id)
        assert memory is None

        prompt = step._build_spec_prompt(ctx, "pdf", DOCUMENT_PROMPT_CFG, memory=memory)

        assert "Previous document spec" not in prompt


# ---------------------------------------------------------------------------
# ProcessingContext document fields
# ---------------------------------------------------------------------------

class TestProcessingContextDocumentFields:
    def test_document_fields_default_to_none(self):
        from inference.pipeline.base import ProcessingContext
        ctx = ProcessingContext()
        assert ctx.document is None
        assert ctx.document_format is None
        assert ctx.document_url is None
        assert ctx.document_revised_prompt is None

    def test_document_fields_assignable(self):
        from inference.pipeline.base import ProcessingContext
        ctx = ProcessingContext()
        ctx.document = "abc123"
        ctx.document_format = "pdf"
        ctx.document_url = "/api/files/xyz/content"
        ctx.document_revised_prompt = "Q1 Report"
        assert ctx.document == "abc123"
        assert ctx.document_format == "pdf"
        assert ctx.document_url == "/api/files/xyz/content"
        assert ctx.document_revised_prompt == "Q1 Report"


# ---------------------------------------------------------------------------
# ResponseProcessor.build_result — document fields
# ---------------------------------------------------------------------------

class TestResponseProcessorDocumentFields:
    def setup_method(self):
        sys.path.insert(0, _server_dir)
        from services.chat_handlers.response_processor import ResponseProcessor
        self.ResponseProcessor = ResponseProcessor

    def _make_processor(self):
        conv_handler = AsyncMock()
        conv_handler.check_limit_warning = AsyncMock(return_value=None)
        conv_handler.store_turn = AsyncMock(return_value=("uid", "aid"))
        logger_service = AsyncMock()
        return self.ResponseProcessor(
            config={},
            conversation_handler=conv_handler,
            logger_service=logger_service,
        )

    def test_build_result_includes_document_url(self):
        proc = self._make_processor()
        result = proc.build_result(
            response="Q1 Sales Report",
            sources=[],
            metadata={},
            processing_time=0.5,
            document_url="/api/files/abc/content",
            document_format="pdf",
            document_revised_prompt="Q1 Sales Report",
        )
        assert result["document_url"] == "/api/files/abc/content"
        assert result["document_format"] == "pdf"
        assert result["document_revised_prompt"] == "Q1 Sales Report"

    def test_build_result_no_document_when_url_absent(self):
        proc = self._make_processor()
        result = proc.build_result(
            response="Normal response",
            sources=[],
            metadata={},
            processing_time=0.1,
        )
        assert "document_url" not in result
        assert "document_format" not in result

    def test_build_result_document_format_defaults_to_pdf(self):
        proc = self._make_processor()
        result = proc.build_result(
            response="Doc",
            sources=[],
            metadata={},
            processing_time=0.1,
            document_url="/api/files/xyz/content",
            document_format=None,  # Should default to "pdf"
        )
        assert result["document_format"] == "pdf"

    def test_build_result_omits_revised_prompt_when_absent(self):
        proc = self._make_processor()
        result = proc.build_result(
            response="Doc",
            sources=[],
            metadata={},
            processing_time=0.1,
            document_url="/api/files/xyz/content",
            document_format="docx",
        )
        assert "document_revised_prompt" not in result


# ---------------------------------------------------------------------------
# StreamingHandler.build_done_chunk — document fields
# ---------------------------------------------------------------------------

class TestStreamingHandlerDocumentFields:
    def setup_method(self):
        sys.path.insert(0, _server_dir)
        from services.chat_handlers.streaming_handler import StreamingHandler, StreamingState
        self.StreamingHandler = StreamingHandler
        self.StreamingState = StreamingState

    def _make_handler(self):
        return self.StreamingHandler(config={}, audio_handler=MagicMock())

    @staticmethod
    def _parse_sse(sse: str) -> dict:
        """build_done_chunk returns 'data: {...}\\n\\n' — extract the JSON payload."""
        assert sse.startswith("data: "), f"Expected SSE prefix, got: {sse!r}"
        return json.loads(sse[len("data: "):].strip())

    def test_build_done_chunk_includes_document_url(self):
        handler = self._make_handler()
        state = self.StreamingState()
        sse = handler.build_done_chunk(
            state=state,
            document_url="/api/files/abc/content",
            document_format="xlsx",
            document_revised_prompt="Monthly Sales",
        )
        chunk = self._parse_sse(sse)
        assert chunk["document_url"] == "/api/files/abc/content"
        assert chunk["document_format"] == "xlsx"
        assert chunk["document_revised_prompt"] == "Monthly Sales"

    def test_build_done_chunk_no_document_when_url_absent(self):
        handler = self._make_handler()
        state = self.StreamingState()
        sse = handler.build_done_chunk(state=state)
        chunk = self._parse_sse(sse)
        assert "document_url" not in chunk
        assert "document_format" not in chunk

    def test_build_done_chunk_document_format_defaults_to_pdf(self):
        handler = self._make_handler()
        state = self.StreamingState()
        sse = handler.build_done_chunk(
            state=state,
            document_url="/api/files/abc/content",
            document_format=None,
        )
        chunk = self._parse_sse(sse)
        assert chunk["document_format"] == "pdf"
