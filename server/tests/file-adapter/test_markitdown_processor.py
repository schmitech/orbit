"""
Tests for MarkItDown Processor

Tests the MarkItDown processor for document-to-markdown conversion,
including MIME type support, text extraction, and lazy initialization.
"""

import pytest
import sys
import warnings
from pathlib import Path
from unittest.mock import Mock, patch

# Suppress SWIG-related deprecation warnings from dependencies
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*builtin type SwigPyPacked.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*builtin type SwigPyObject.*")

# Add server directory to Python path
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from services.file_processing.base_processor import FileProcessor


# ============================================================================
# MarkItDown Processor Availability Tests
# ============================================================================

def test_markitdown_processor_import():
    """Test that MarkItDownProcessor can be imported"""
    try:
        from services.file_processing.markitdown_processor import MarkItDownProcessor
        assert MarkItDownProcessor is not None
    except ImportError as e:
        pytest.skip(f"MarkItDownProcessor not available: {e}")


def test_markitdown_availability_flag():
    """Test MARKITDOWN_AVAILABLE flag is set correctly"""
    from services.file_processing import markitdown_processor

    # Flag should be a boolean
    assert isinstance(markitdown_processor.MARKITDOWN_AVAILABLE, bool)


# ============================================================================
# MarkItDown Processor Initialization Tests
# ============================================================================

def test_markitdown_processor_initialization():
    """Test MarkItDownProcessor initialization"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor

    processor = MarkItDownProcessor(enabled=True)

    assert processor._enabled is True
    assert processor._initialized is False  # Lazy initialization
    assert processor._converter is None  # Not initialized yet


def test_markitdown_processor_disabled():
    """Test MarkItDownProcessor when disabled"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor

    processor = MarkItDownProcessor(enabled=False)

    assert processor._enabled is False

    # Should not support any MIME types when disabled
    assert processor.supports_mime_type("application/pdf") is False
    assert processor.supports_mime_type("text/html") is False


def test_markitdown_processor_plugins_config():
    """Test MarkItDownProcessor plugin configuration"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor

    # Default - plugins disabled
    processor_default = MarkItDownProcessor(enabled=True)
    assert processor_default._enable_plugins is False

    # Explicit plugins enabled
    processor_plugins = MarkItDownProcessor(enabled=True, enable_plugins=True)
    assert processor_plugins._enable_plugins is True


def test_markitdown_processor_lazy_initialization():
    """Test that converter is not initialized until needed"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor

    processor = MarkItDownProcessor(enabled=True)

    # Before any operation, converter should be None
    assert processor._converter is None
    assert processor._initialized is False

    # Calling supports_mime_type should NOT trigger initialization
    processor.supports_mime_type("application/pdf")
    assert processor._initialized is False
    assert processor._converter is None


def test_markitdown_processor_is_file_processor():
    """Test that MarkItDownProcessor inherits from FileProcessor"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor

    processor = MarkItDownProcessor(enabled=True)

    assert isinstance(processor, FileProcessor)


# ============================================================================
# MIME Type Support Tests
# ============================================================================

def test_markitdown_supports_pdf():
    """Test MarkItDown supports PDF files"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor, MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    processor = MarkItDownProcessor(enabled=True)

    assert processor.supports_mime_type("application/pdf") is True


def test_markitdown_supports_office_documents():
    """Test MarkItDown supports Office documents"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor, MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    processor = MarkItDownProcessor(enabled=True)

    # Word documents
    assert processor.supports_mime_type("application/msword") is True
    assert processor.supports_mime_type("application/vnd.openxmlformats-officedocument.wordprocessingml.document") is True

    # PowerPoint
    assert processor.supports_mime_type("application/vnd.ms-powerpoint") is True
    assert processor.supports_mime_type("application/vnd.openxmlformats-officedocument.presentationml.presentation") is True

    # Excel
    assert processor.supports_mime_type("application/vnd.ms-excel") is True
    assert processor.supports_mime_type("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") is True


def test_markitdown_supports_text_formats():
    """Test MarkItDown supports text formats"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor, MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    processor = MarkItDownProcessor(enabled=True)

    assert processor.supports_mime_type("text/html") is True
    assert processor.supports_mime_type("text/csv") is True
    assert processor.supports_mime_type("text/plain") is True
    assert processor.supports_mime_type("text/markdown") is True
    assert processor.supports_mime_type("text/xml") is True
    assert processor.supports_mime_type("application/json") is True
    assert processor.supports_mime_type("application/xml") is True


def test_markitdown_supports_images():
    """Test MarkItDown supports image formats"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor, MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    processor = MarkItDownProcessor(enabled=True)

    assert processor.supports_mime_type("image/png") is True
    assert processor.supports_mime_type("image/jpeg") is True
    assert processor.supports_mime_type("image/gif") is True
    assert processor.supports_mime_type("image/webp") is True
    assert processor.supports_mime_type("image/tiff") is True


def test_markitdown_supports_audio():
    """Test MarkItDown supports audio formats"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor, MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    processor = MarkItDownProcessor(enabled=True)

    assert processor.supports_mime_type("audio/wav") is True
    assert processor.supports_mime_type("audio/mpeg") is True
    assert processor.supports_mime_type("audio/mp3") is True
    assert processor.supports_mime_type("audio/ogg") is True
    assert processor.supports_mime_type("audio/flac") is True


def test_markitdown_supports_archives():
    """Test MarkItDown supports archive formats"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor, MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    processor = MarkItDownProcessor(enabled=True)

    assert processor.supports_mime_type("application/zip") is True
    assert processor.supports_mime_type("application/x-zip-compressed") is True


def test_markitdown_supports_epub():
    """Test MarkItDown supports EPUB format"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor, MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    processor = MarkItDownProcessor(enabled=True)

    assert processor.supports_mime_type("application/epub+zip") is True


def test_markitdown_supports_outlook():
    """Test MarkItDown supports Outlook MSG files"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor, MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    processor = MarkItDownProcessor(enabled=True)

    assert processor.supports_mime_type("application/vnd.ms-outlook") is True


def test_markitdown_unsupported_types():
    """Test MarkItDown returns False for unsupported types"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor, MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    processor = MarkItDownProcessor(enabled=True)

    # VTT is supported by Docling but not MarkItDown
    assert processor.supports_mime_type("text/vtt") is False

    # Random unsupported types
    assert processor.supports_mime_type("application/x-unknown") is False
    assert processor.supports_mime_type("video/mp4") is False


def test_markitdown_mime_type_case_insensitive():
    """Test MIME type matching is case-insensitive"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor, MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    processor = MarkItDownProcessor(enabled=True)

    # Test various cases
    assert processor.supports_mime_type("APPLICATION/PDF") is True
    assert processor.supports_mime_type("Application/Pdf") is True
    assert processor.supports_mime_type("TEXT/HTML") is True


# ============================================================================
# Text Extraction Tests (with mocking)
# ============================================================================

@pytest.mark.asyncio
async def test_markitdown_extract_text_disabled():
    """Test extract_text raises error when disabled"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor

    processor = MarkItDownProcessor(enabled=False)

    with pytest.raises(ValueError, match="disabled"):
        await processor.extract_text(b"test content", "test.pdf")


@pytest.mark.asyncio
async def test_markitdown_extract_text_not_available():
    """Test extract_text raises ImportError when markitdown not installed"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor

    processor = MarkItDownProcessor(enabled=True)

    # Mock MARKITDOWN_AVAILABLE as False
    with patch('services.file_processing.markitdown_processor.MARKITDOWN_AVAILABLE', False):
        processor._enabled = True  # Force enabled even though not available
        with pytest.raises(ImportError, match="not available"):
            await processor.extract_text(b"test content", "test.pdf")


@pytest.mark.asyncio
async def test_markitdown_extract_text_with_mock():
    """Test extract_text with mocked MarkItDown converter"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor, MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    processor = MarkItDownProcessor(enabled=True)

    # Create mock result
    mock_result = Mock()
    mock_result.text_content = "# Test Document\n\nThis is the extracted content."

    # Create mock converter
    mock_converter = Mock()
    mock_converter.convert = Mock(return_value=mock_result)

    # Inject mock converter
    processor._converter = mock_converter
    processor._initialized = True

    # Test extraction
    result = await processor.extract_text(b"fake pdf content", "test.pdf")

    assert result == "# Test Document\n\nThis is the extracted content."
    mock_converter.convert.assert_called_once()


@pytest.mark.asyncio
async def test_markitdown_extract_text_empty_result():
    """Test extract_text handles empty result"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor, MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    processor = MarkItDownProcessor(enabled=True)

    # Create mock result with empty content
    mock_result = Mock()
    mock_result.text_content = ""

    mock_converter = Mock()
    mock_converter.convert = Mock(return_value=mock_result)

    processor._converter = mock_converter
    processor._initialized = True

    result = await processor.extract_text(b"empty content", "empty.pdf")

    assert result == ""


@pytest.mark.asyncio
async def test_markitdown_extract_text_preserves_extension():
    """Test that extract_text preserves file extension for proper format detection"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor, MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    processor = MarkItDownProcessor(enabled=True)

    # Track the temp file path to verify extension
    captured_path = None

    def capture_path(path):
        nonlocal captured_path
        captured_path = path
        mock_result = Mock()
        mock_result.text_content = "content"
        return mock_result

    mock_converter = Mock()
    mock_converter.convert = capture_path

    processor._converter = mock_converter
    processor._initialized = True

    await processor.extract_text(b"docx content", "document.docx")

    # Verify the temp file had the correct extension
    assert captured_path is not None
    assert captured_path.endswith(".docx")


@pytest.mark.asyncio
async def test_markitdown_extract_text_cleans_up_temp_file():
    """Test that extract_text cleans up temporary files"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor, MARKITDOWN_AVAILABLE
    import os

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    processor = MarkItDownProcessor(enabled=True)

    captured_path = None

    def capture_and_convert(path):
        nonlocal captured_path
        captured_path = path
        # Verify file exists during conversion
        assert os.path.exists(path)
        mock_result = Mock()
        mock_result.text_content = "content"
        return mock_result

    mock_converter = Mock()
    mock_converter.convert = capture_and_convert

    processor._converter = mock_converter
    processor._initialized = True

    await processor.extract_text(b"test content", "test.txt")

    # Verify temp file was cleaned up after conversion
    assert captured_path is not None
    assert not os.path.exists(captured_path)


@pytest.mark.asyncio
async def test_markitdown_extract_text_handles_conversion_error():
    """Test extract_text handles conversion errors properly"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor, MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    processor = MarkItDownProcessor(enabled=True)

    mock_converter = Mock()
    mock_converter.convert = Mock(side_effect=Exception("Conversion failed"))

    processor._converter = mock_converter
    processor._initialized = True

    with pytest.raises(Exception, match="Conversion failed"):
        await processor.extract_text(b"bad content", "bad.pdf")


# ============================================================================
# Metadata Extraction Tests
# ============================================================================

@pytest.mark.asyncio
async def test_markitdown_extract_metadata_basic():
    """Test basic metadata extraction"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor, MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    processor = MarkItDownProcessor(enabled=True)
    processor._initialized = True
    processor._converter = Mock()

    file_data = b"test content"
    filename = "document.pdf"

    metadata = await processor.extract_metadata(file_data, filename)

    assert metadata["filename"] == filename
    assert metadata["file_size"] == len(file_data)
    assert metadata["processed_by"] == "markitdown"
    assert metadata["format"] == "PDF"


@pytest.mark.asyncio
async def test_markitdown_extract_metadata_various_formats():
    """Test metadata extraction identifies various formats"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor, MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    processor = MarkItDownProcessor(enabled=True)
    processor._initialized = True
    processor._converter = Mock()

    test_cases = [
        ("document.docx", "DOCX"),
        ("spreadsheet.xlsx", "XLSX"),
        ("presentation.pptx", "PPTX"),
        ("page.html", "HTML"),
        ("data.json", "JSON"),
        ("archive.zip", "ZIP"),
        ("book.epub", "EPUB"),
    ]

    for filename, expected_format in test_cases:
        metadata = await processor.extract_metadata(b"content", filename)
        assert metadata["format"] == expected_format, f"Failed for {filename}"


@pytest.mark.asyncio
async def test_markitdown_extract_metadata_no_extension():
    """Test metadata extraction handles files without extension"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor, MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    processor = MarkItDownProcessor(enabled=True)
    processor._initialized = True
    processor._converter = Mock()

    metadata = await processor.extract_metadata(b"content", "noextension")

    assert metadata["format"] == "unknown"


@pytest.mark.asyncio
async def test_markitdown_extract_metadata_disabled():
    """Test metadata extraction when processor is disabled"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor

    processor = MarkItDownProcessor(enabled=False)

    metadata = await processor.extract_metadata(b"content", "test.pdf")

    # Should still return basic metadata
    assert metadata["filename"] == "test.pdf"
    assert metadata["file_size"] == 7
    # Should not have markitdown-specific metadata
    assert "processed_by" not in metadata


# ============================================================================
# Supported Formats Tests
# ============================================================================

def test_markitdown_get_supported_formats():
    """Test get_supported_formats returns expected formats"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor, MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    processor = MarkItDownProcessor(enabled=True)

    formats = processor.get_supported_formats()

    assert isinstance(formats, list)
    assert len(formats) > 0

    # Check for key formats
    assert "PDF" in formats
    assert "DOCX" in formats
    assert "XLSX" in formats
    assert "HTML" in formats
    assert "ZIP" in formats
    assert "EPUB" in formats


def test_markitdown_get_supported_formats_not_available():
    """Test get_supported_formats returns empty when not available"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor

    processor = MarkItDownProcessor(enabled=True)

    with patch('services.file_processing.markitdown_processor.MARKITDOWN_AVAILABLE', False):
        formats = processor.get_supported_formats()
        assert formats == []


def test_markitdown_supports_advanced_features():
    """Test supports_advanced_features method"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor, MARKITDOWN_AVAILABLE

    processor_enabled = MarkItDownProcessor(enabled=True)
    processor_disabled = MarkItDownProcessor(enabled=False)

    if MARKITDOWN_AVAILABLE:
        assert processor_enabled.supports_advanced_features() is True

    assert processor_disabled.supports_advanced_features() is False


# ============================================================================
# Processor Registry Integration Tests
# ============================================================================

def test_registry_markitdown_disabled_by_default():
    """Test that MarkItDown is disabled by default in registry"""
    from services.file_processing.processor_registry import FileProcessorRegistry

    # Default config (markitdown_enabled defaults to False)
    config = {}
    registry = FileProcessorRegistry(config)

    # Should not have MarkItDownProcessor registered
    processor_names = [p.__class__.__name__ for p in registry._processors]
    assert "MarkItDownProcessor" not in processor_names


def test_registry_markitdown_enabled():
    """Test enabling MarkItDown in registry"""
    from services.file_processing.processor_registry import FileProcessorRegistry
    from services.file_processing.markitdown_processor import MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    config = {
        'files': {
            'processing': {
                'markitdown_enabled': True,
                'docling_enabled': False  # Disable to simplify test
            }
        }
    }

    registry = FileProcessorRegistry(config)

    # Should have MarkItDownProcessor registered
    processor_names = [p.__class__.__name__ for p in registry._processors]
    assert "MarkItDownProcessor" in processor_names


def test_registry_priority_docling_first():
    """Test Docling has priority over MarkItDown by default"""
    from services.file_processing.processor_registry import FileProcessorRegistry
    from services.file_processing.markitdown_processor import MARKITDOWN_AVAILABLE
    from services.file_processing.docling_processor import DOCLING_AVAILABLE

    if not MARKITDOWN_AVAILABLE or not DOCLING_AVAILABLE:
        pytest.skip("Both markitdown and docling must be available")

    config = {
        'files': {
            'processing': {
                'docling_enabled': True,
                'markitdown_enabled': True,
                'processor_priority': 'docling'  # Default
            }
        }
    }

    registry = FileProcessorRegistry(config)

    # Get processor for PDF (both support it)
    processor = registry.get_processor("application/pdf")

    # Docling should be selected (registered first)
    assert processor.__class__.__name__ == "DoclingProcessor"


def test_registry_priority_markitdown_first():
    """Test MarkItDown can have priority over Docling"""
    from services.file_processing.processor_registry import FileProcessorRegistry
    from services.file_processing.markitdown_processor import MARKITDOWN_AVAILABLE
    from services.file_processing.docling_processor import DOCLING_AVAILABLE

    if not MARKITDOWN_AVAILABLE or not DOCLING_AVAILABLE:
        pytest.skip("Both markitdown and docling must be available")

    config = {
        'files': {
            'processing': {
                'docling_enabled': True,
                'markitdown_enabled': True,
                'processor_priority': 'markitdown'
            }
        }
    }

    registry = FileProcessorRegistry(config)

    # Get processor for PDF (both support it)
    processor = registry.get_processor("application/pdf")

    # MarkItDown should be selected (registered first)
    assert processor.__class__.__name__ == "MarkItDownProcessor"


def test_registry_markitdown_only():
    """Test MarkItDown-only configuration"""
    from services.file_processing.processor_registry import FileProcessorRegistry
    from services.file_processing.markitdown_processor import MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    config = {
        'files': {
            'processing': {
                'docling_enabled': False,
                'markitdown_enabled': True
            }
        }
    }

    registry = FileProcessorRegistry(config)

    # Get processor for PDF
    processor = registry.get_processor("application/pdf")

    # MarkItDown should be selected
    assert processor.__class__.__name__ == "MarkItDownProcessor"


def test_registry_markitdown_plugins_config():
    """Test MarkItDown plugin configuration through registry"""
    from services.file_processing.processor_registry import FileProcessorRegistry
    from services.file_processing.markitdown_processor import MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    config = {
        'files': {
            'processing': {
                'markitdown_enabled': True,
                'docling_enabled': False,
                'markitdown': {
                    'enable_plugins': True
                }
            }
        }
    }

    registry = FileProcessorRegistry(config)

    # Find MarkItDownProcessor
    markitdown_processor = None
    for p in registry._processors:
        if p.__class__.__name__ == "MarkItDownProcessor":
            markitdown_processor = p
            break

    assert markitdown_processor is not None
    assert markitdown_processor._enable_plugins is True


# ============================================================================
# Edge Cases and Error Handling Tests
# ============================================================================

@pytest.mark.asyncio
async def test_markitdown_converter_init_failure():
    """Test handling of converter initialization failure"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor

    processor = MarkItDownProcessor(enabled=True)

    # Mock MarkItDown to raise during initialization
    with patch('services.file_processing.markitdown_processor.MarkItDown', side_effect=Exception("Init failed")):
        with patch('services.file_processing.markitdown_processor.MARKITDOWN_AVAILABLE', True):
            processor._ensure_initialized()

            # Should be marked as initialized (to prevent retries) but converter should be None
            assert processor._initialized is True
            assert processor._converter is None


@pytest.mark.asyncio
async def test_markitdown_extract_text_no_converter():
    """Test extract_text fails gracefully when converter is None"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor, MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    processor = MarkItDownProcessor(enabled=True)
    processor._initialized = True
    processor._converter = None  # Simulate failed initialization

    with pytest.raises(RuntimeError, match="failed to initialize"):
        await processor.extract_text(b"content", "test.pdf")


def test_markitdown_supports_mime_type_when_not_available():
    """Test supports_mime_type returns False when library not available"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor

    processor = MarkItDownProcessor(enabled=True)

    with patch('services.file_processing.markitdown_processor.MARKITDOWN_AVAILABLE', False):
        assert processor.supports_mime_type("application/pdf") is False


# ============================================================================
# Comparison with Docling Tests
# ============================================================================

def test_markitdown_unique_formats():
    """Test formats MarkItDown supports that Docling doesn't"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor, MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    processor = MarkItDownProcessor(enabled=True)

    # MarkItDown-specific formats (not supported by Docling)
    assert processor.supports_mime_type("application/epub+zip") is True
    assert processor.supports_mime_type("application/zip") is True
    assert processor.supports_mime_type("application/vnd.ms-excel") is True  # XLS (old Excel)


def test_markitdown_and_docling_common_formats():
    """Test formats supported by both MarkItDown and Docling"""
    from services.file_processing.markitdown_processor import MarkItDownProcessor, MARKITDOWN_AVAILABLE

    if not MARKITDOWN_AVAILABLE:
        pytest.skip("markitdown library not available")

    processor = MarkItDownProcessor(enabled=True)

    # Common formats
    common_formats = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # DOCX
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # PPTX
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # XLSX
        "text/html",
        "image/png",
        "image/jpeg",
    ]

    for mime_type in common_formats:
        assert processor.supports_mime_type(mime_type) is True, f"Failed for {mime_type}"
