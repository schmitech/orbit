"""
Tests for the AI/LLM OCR document processor and OCR services.

Covers:
- AIDocumentProcessor: MIME support, extract_text/metadata via a mocked OcrService
- Registry: 3-way processor_priority (ai_document first) for PDFs and images
- MistralOcrService: extract_document via a mocked client.ocr.process_async
- VisionBackedOcrService: PDF rasterization + per-page vision OCR (mocked vision)
"""

import pytest
import sys
import warnings
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*builtin type SwigPyPacked.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*builtin type SwigPyObject.*")

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.file_processing.base_processor import FileProcessor
from services.file_processing.ai_document_processor import AIDocumentProcessor


AI_CONFIG = {
    'files': {
        'processing': {
            'ai_document_enabled': True,
            'processor_priority': 'ai_document',
            'docling_enabled': False,
            'markitdown_enabled': False,
            'ai_document': {'provider': 'mistral', 'max_pages': 50, 'dpi': 150},
        }
    },
    'ocr': {'mistral': {'enabled': True, 'model': 'mistral-ocr-latest'}},
    'visions': {},
}


def _make_pdf(num_pages: int = 2) -> bytes:
    """Create a minimal multi-page PDF using reportlab."""
    from io import BytesIO
    from reportlab.pdfgen import canvas

    buf = BytesIO()
    c = canvas.Canvas(buf)
    for i in range(num_pages):
        c.drawString(100, 750, f"Page {i + 1} sample text")
        c.showPage()
    c.save()
    return buf.getvalue()


# ============================================================================
# AIDocumentProcessor basics
# ============================================================================

def test_processor_is_file_processor():
    proc = AIDocumentProcessor(enabled=True, config=AI_CONFIG)
    assert isinstance(proc, FileProcessor)
    assert proc.provider == 'mistral'


def test_supports_mime_type():
    proc = AIDocumentProcessor(enabled=True, config=AI_CONFIG)
    assert proc.supports_mime_type('application/pdf') is True
    assert proc.supports_mime_type('image/png') is True
    assert proc.supports_mime_type('image/jpeg') is True
    assert proc.supports_mime_type('text/plain') is False
    assert proc.supports_mime_type('application/vnd.ms-excel') is False


def test_supports_mime_type_disabled():
    proc = AIDocumentProcessor(enabled=False, config=AI_CONFIG)
    assert proc.supports_mime_type('application/pdf') is False
    assert proc.supports_mime_type('image/png') is False


def test_detect_mime_type():
    proc = AIDocumentProcessor(enabled=True, config=AI_CONFIG)
    assert proc._detect_mime_type(b'%PDF-1.7 ...', 'x.pdf') == 'application/pdf'
    assert proc._detect_mime_type(b'\xff\xd8\xff\xe0', 'x.jpg') == 'image/jpeg'
    assert proc._detect_mime_type(b'\x89PNG\r\n\x1a\n', 'x.png') == 'image/png'


async def test_extract_text_and_metadata_with_mocked_service():
    """extract_text/metadata should delegate to the OCR service and tag metadata."""
    pdf = _make_pdf(2)

    mock_service = MagicMock()
    mock_service.initialized = True
    mock_service.extract_document = AsyncMock(
        return_value={'text': '# Page 1\n\n---\n\n# Page 2', 'page_count': 2}
    )

    proc = AIDocumentProcessor(enabled=True, config=AI_CONFIG)

    with patch('ai_services.AIServiceFactory.create_service', return_value=mock_service):
        text = await proc.extract_text(pdf, 'doc.pdf')
        metadata = await proc.extract_metadata(pdf, 'doc.pdf')

    assert text == '# Page 1\n\n---\n\n# Page 2'
    mock_service.extract_document.assert_awaited_once()
    assert metadata['processed_by'] == 'ai_ocr'
    assert metadata['extraction_method'] == 'ai_ocr'
    assert metadata['ocr_provider'] == 'mistral'
    # page_count computed locally from the PDF (no extra API call)
    assert metadata['page_count'] == 2


async def test_metadata_page_count_capped_for_vision_backed():
    """Vision-backed page_count reflects OCR'd pages (capped at max_pages)."""
    pdf = _make_pdf(3)
    config = {
        'files': {'processing': {
            'ai_document_enabled': True,
            'processor_priority': 'ai_document',
            'ai_document': {'provider': 'openai', 'max_pages': 2},
        }},
        'ocr': {}, 'visions': {},
    }
    proc = AIDocumentProcessor(enabled=True, config=config)
    metadata = await proc.extract_metadata(pdf, 'doc.pdf')
    assert metadata['page_count'] == 2  # capped at max_pages for vision-backed


async def test_metadata_page_count_full_for_mistral():
    """Mistral processes the whole document, so page_count is not capped."""
    pdf = _make_pdf(3)
    proc = AIDocumentProcessor(enabled=True, config=AI_CONFIG)  # provider=mistral, max_pages=50
    metadata = await proc.extract_metadata(pdf, 'doc.pdf')
    assert metadata['page_count'] == 3


# ============================================================================
# Registry priority (3-way)
# ============================================================================

def test_registry_ai_document_first_for_pdf_and_image():
    from services.file_processing.processor_registry import FileProcessorRegistry

    registry = FileProcessorRegistry(AI_CONFIG)

    pdf_names = [p.__class__.__name__ for p in registry.get_processors('application/pdf')]
    img_names = [p.__class__.__name__ for p in registry.get_processors('image/png')]

    assert pdf_names and pdf_names[0] == 'AIDocumentProcessor'
    assert img_names and img_names[0] == 'AIDocumentProcessor'


def test_registry_ai_document_disabled_by_default():
    from services.file_processing.processor_registry import FileProcessorRegistry

    registry = FileProcessorRegistry({})
    names = [p.__class__.__name__ for p in registry._processors]
    assert 'AIDocumentProcessor' not in names


def test_registry_ai_document_fallback_when_not_priority():
    """Enabled but not prioritized: registered, but after the priority processor."""
    from services.file_processing.processor_registry import FileProcessorRegistry
    from services.file_processing.markitdown_processor import MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown not available")

    config = {
        'files': {
            'processing': {
                'ai_document_enabled': True,
                'markitdown_enabled': True,
                'docling_enabled': False,
                'processor_priority': 'markitdown',
                'ai_document': {'provider': 'mistral'},
            }
        },
        'ocr': {'mistral': {'enabled': True}},
    }
    registry = FileProcessorRegistry(config)
    pdf_names = [p.__class__.__name__ for p in registry.get_processors('application/pdf')]
    assert pdf_names[0] == 'MarkItDownProcessor'
    assert 'AIDocumentProcessor' in pdf_names


# ============================================================================
# MistralOcrService
# ============================================================================

async def test_mistral_ocr_service_extract_document():
    from ai_services.implementations.ocr.mistral_ocr_service import MistralOcrService

    config = {'ocr': {'mistral': {'enabled': True, 'api_key': 'sk-test', 'model': 'mistral-ocr-latest'}}}
    service = MistralOcrService(config)

    # Mock the Mistral client's OCR endpoint
    page1 = MagicMock(markdown='Hello')
    page2 = MagicMock(markdown='World')
    response = MagicMock(pages=[page1, page2])
    service.client = MagicMock()
    service.client.ocr.process_async = AsyncMock(return_value=response)
    service.initialized = True

    result = await service.extract_document(b'%PDF-1.7 fake', 'application/pdf', 'doc.pdf')

    assert result['page_count'] == 2
    assert result['text'] == 'Hello\n\n---\n\nWorld'
    # Verify a document_url payload was sent for a PDF
    _, kwargs = service.client.ocr.process_async.call_args
    assert kwargs['document']['type'] == 'document_url'
    assert kwargs['model'] == 'mistral-ocr-latest'


async def test_mistral_ocr_service_image_payload():
    from ai_services.implementations.ocr.mistral_ocr_service import MistralOcrService

    config = {'ocr': {'mistral': {'enabled': True, 'api_key': 'sk-test'}}}
    service = MistralOcrService(config)
    service.client = MagicMock()
    service.client.ocr.process_async = AsyncMock(return_value=MagicMock(pages=[MagicMock(markdown='X')]))
    service.initialized = True

    await service.extract_document(b'\x89PNG\r\n\x1a\n', 'image/png', 'x.png')
    _, kwargs = service.client.ocr.process_async.call_args
    assert kwargs['document']['type'] == 'image_url'
    assert kwargs['document']['image_url'].startswith('data:image/png;base64,')


# ============================================================================
# VisionBackedOcrService (rasterization)
# ============================================================================

async def test_vision_backed_ocr_rasterizes_pdf_pages():
    from ai_services.implementations.ocr.vision_ocr_service import OpenAIOcrService

    pdf = _make_pdf(2)

    config = {'ai_document': {'max_pages': 50, 'dpi': 100}, 'visions': {}}
    service = OpenAIOcrService(config)

    mock_vision = MagicMock()
    mock_vision.initialized = True
    mock_vision.extract_text_from_image = AsyncMock(side_effect=['text A', 'text B'])

    with patch('ai_services.AIServiceFactory.create_service', return_value=mock_vision):
        result = await service.extract_document(pdf, 'application/pdf', 'doc.pdf')

    assert result['page_count'] == 2
    assert result['text'] == 'text A\n\n---\n\ntext B'
    assert mock_vision.extract_text_from_image.await_count == 2


async def test_vision_backed_ocr_applies_model_override():
    """A files.processing.ai_document.model override must reach the VisionService config."""
    from ai_services.implementations.ocr.vision_ocr_service import OpenAIOcrService

    config = {
        'ai_document': {'max_pages': 50, 'dpi': 100, 'model': 'gpt-override-vision'},
        'visions': {'openai': {'model': 'gpt-from-vision-yaml', 'api_key': 'x'}},
    }
    service = OpenAIOcrService(config)

    mock_vision = MagicMock()
    mock_vision.initialized = True

    with patch('ai_services.AIServiceFactory.create_service', return_value=mock_vision) as mock_create:
        await service.initialize()

    args, kwargs = mock_create.call_args
    passed_config = args[2]
    assert passed_config['visions']['openai']['model'] == 'gpt-override-vision'
    # Must bypass the shared cache when overriding
    assert kwargs.get('use_cache') is False


def _make_multipage_tiff(num_pages: int = 3) -> bytes:
    """Create a multi-page TIFF using Pillow."""
    from io import BytesIO
    from PIL import Image

    pages = [Image.new("RGB", (60, 40), color=(i * 40, i * 40, i * 40)) for i in range(num_pages)]
    buf = BytesIO()
    pages[0].save(buf, format="TIFF", save_all=True, append_images=pages[1:])
    return buf.getvalue()


async def test_vision_backed_ocr_splits_multipage_tiff():
    """A multi-page TIFF should be OCR'd frame-by-frame, not as a single image."""
    from ai_services.implementations.ocr.vision_ocr_service import OpenAIOcrService

    tiff = _make_multipage_tiff(3)
    config = {'ai_document': {'max_pages': 50}, 'visions': {}}
    service = OpenAIOcrService(config)

    mock_vision = MagicMock()
    mock_vision.initialized = True
    mock_vision.extract_text_from_image = AsyncMock(side_effect=['f1', 'f2', 'f3'])

    with patch('ai_services.AIServiceFactory.create_service', return_value=mock_vision):
        result = await service.extract_document(tiff, 'image/tiff', 'scan.tiff')

    assert result['page_count'] == 3
    assert result['text'] == 'f1\n\n---\n\nf2\n\n---\n\nf3'
    assert mock_vision.extract_text_from_image.await_count == 3


async def test_vision_backed_ocr_single_frame_image_unchanged():
    """A single-frame image is sent as-is (one OCR call)."""
    from io import BytesIO
    from PIL import Image
    from ai_services.implementations.ocr.vision_ocr_service import OpenAIOcrService

    buf = BytesIO()
    Image.new("RGB", (40, 40), color=(10, 20, 30)).save(buf, format="PNG")
    png = buf.getvalue()

    service = OpenAIOcrService({'ai_document': {}, 'visions': {}})
    mock_vision = MagicMock()
    mock_vision.initialized = True
    mock_vision.extract_text_from_image = AsyncMock(return_value='single')

    with patch('ai_services.AIServiceFactory.create_service', return_value=mock_vision):
        result = await service.extract_document(png, 'image/png', 'x.png')

    assert result['page_count'] == 1
    assert result['text'] == 'single'
    # The original bytes are forwarded unchanged for single-frame images
    mock_vision.extract_text_from_image.assert_awaited_once_with(png)


async def test_vision_backed_ocr_max_pages_cap():
    from ai_services.implementations.ocr.vision_ocr_service import OpenAIOcrService

    pdf = _make_pdf(3)
    config = {'ai_document': {'max_pages': 1, 'dpi': 100}, 'visions': {}}
    service = OpenAIOcrService(config)

    mock_vision = MagicMock()
    mock_vision.initialized = True
    mock_vision.extract_text_from_image = AsyncMock(return_value='only page')

    with patch('ai_services.AIServiceFactory.create_service', return_value=mock_vision):
        result = await service.extract_document(pdf, 'application/pdf', 'doc.pdf')

    assert result['page_count'] == 1
    assert mock_vision.extract_text_from_image.await_count == 1
