"""
Tests for File Adapter

Tests the FileAdapter class for document formatting, filtering, and domain-specific processing.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add server directory to Python path
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.append(str(SERVER_DIR))

from adapters.file.adapter import FileAdapter


def test_file_adapter_initialization_defaults():
    """Test FileAdapter initialization with default configuration"""
    adapter = FileAdapter()
    
    assert adapter.confidence_threshold == 0.5
    assert adapter.preserve_file_structure is True
    assert adapter.extract_metadata is True
    assert adapter.max_summary_length == 200
    assert adapter.enable_vision is True
    assert adapter.vision_provider == 'openai'


def test_file_adapter_initialization_custom_config():
    """Test FileAdapter initialization with custom configuration"""
    config = {
        'confidence_threshold': 0.7,
        'preserve_file_structure': False,
        'extract_metadata': False,
        'max_summary_length': 300,
        'enable_vision': False,
        'vision_provider': 'custom_provider'
    }
    
    adapter = FileAdapter(config=config)
    
    assert adapter.confidence_threshold == 0.7
    assert adapter.preserve_file_structure is False
    assert adapter.extract_metadata is False
    assert adapter.max_summary_length == 300
    assert adapter.enable_vision is False
    assert adapter.vision_provider == 'custom_provider'


def test_file_adapter_initialization_files_config():
    """Test FileAdapter initialization reading from files.adapter config section"""
    config = {
        'files': {
            'adapter': {
                'confidence_threshold': 0.6,
                'preserve_file_structure': False,
                'extract_metadata': True,
                'max_summary_length': 250,
            },
            'processing': {
                'vision': {
                    'enabled': False,
                    'provider': 'anthropic'
                }
            }
        }
    }
    
    adapter = FileAdapter(config=config)
    
    assert adapter.confidence_threshold == 0.6
    assert adapter.preserve_file_structure is False
    assert adapter.extract_metadata is True
    assert adapter.max_summary_length == 250
    assert adapter.enable_vision is False
    assert adapter.vision_provider == 'anthropic'


def test_format_document_basic():
    """Test basic document formatting"""
    adapter = FileAdapter()
    
    raw_doc = "This is a test document."
    metadata = {
        'filename': 'test.txt',
        'mime_type': 'text/plain',
        'file_size': 25
    }
    
    result = adapter.format_document(raw_doc, metadata)
    
    assert result['raw_document'] == raw_doc
    assert result['content'] == raw_doc
    assert result['metadata']['filename'] == 'test.txt'
    assert result['metadata']['mime_type'] == 'text/plain'


def test_format_document_with_title():
    """Test document formatting with title in metadata"""
    adapter = FileAdapter()
    
    raw_doc = "Document content here."
    metadata = {
        'title': 'Test Document',
        'filename': 'test.txt'
    }
    
    result = adapter.format_document(raw_doc, metadata)
    
    assert result['title'] == 'Test Document'
    assert 'Title: Test Document' in result['content']
    assert raw_doc in result['content']


def test_format_document_with_summary():
    """Test document formatting with summary"""
    adapter = FileAdapter()
    
    raw_doc = "Full document content."
    metadata = {
        'summary': 'This is a summary',
        'filename': 'test.txt'
    }
    
    result = adapter.format_document(raw_doc, metadata)
    
    assert result['summary'] == 'This is a summary'


def test_format_document_file_metadata():
    """Test document formatting includes file-specific metadata"""
    adapter = FileAdapter()
    
    raw_doc = "Content"
    metadata = {
        'file_id': 'file_123',
        'filename': 'document.pdf',
        'mime_type': 'application/pdf',
        'file_size': 1024,
        'upload_timestamp': '2024-01-01T00:00:00Z',
        'extraction_method': 'pdf_parser'
    }
    
    result = adapter.format_document(raw_doc, metadata)
    
    assert result['file_id'] == 'file_123'
    assert result['filename'] == 'document.pdf'
    assert result['mime_type'] == 'application/pdf'
    assert result['file_size'] == 1024
    assert result['upload_timestamp'] == '2024-01-01T00:00:00Z'
    assert result['extraction_method'] == 'pdf_parser'


def test_format_document_type_document():
    """Test formatting for document-type content (PDF, DOCX)"""
    adapter = FileAdapter()
    
    raw_doc = "Page 1\n\nContent here.\n\nPage 2\n\nMore content."
    metadata = {
        'mime_type': 'application/pdf',
        'filename': 'document.pdf'
    }
    
    result = adapter.format_document(raw_doc, metadata)
    
    assert result['content_type'] == 'document'
    assert 'page_count' in result or 'Document: document.pdf' in result['content']


def test_format_document_type_spreadsheet():
    """Test formatting for spreadsheet-type content (CSV, XLSX)"""
    adapter = FileAdapter()
    
    raw_doc = "Name|Age|City\nJohn|30|NYC\nJane|25|LA"
    metadata = {
        'mime_type': 'text/csv',
        'filename': 'data.csv'
    }
    
    result = adapter.format_document(raw_doc, metadata)
    
    assert result['content_type'] == 'spreadsheet'
    # Should include row/column information
    assert 'Spreadsheet:' in result['content'] or 'row_count' in result


def test_format_document_type_data():
    """Test formatting for data file content (JSON)"""
    adapter = FileAdapter()
    
    raw_doc = '{"key1": "value1", "key2": "value2"}'
    metadata = {
        'mime_type': 'application/json',
        'filename': 'data.json'
    }
    
    result = adapter.format_document(raw_doc, metadata)
    
    assert result['content_type'] == 'data'
    # May include JSON structure info
    assert raw_doc in result['content'] or result['raw_document'] == raw_doc


def test_format_document_type_image():
    """Test formatting for image file content"""
    adapter = FileAdapter()
    
    raw_doc = "Image content"
    metadata = {
        'mime_type': 'image/png',
        'filename': 'image.png',
        'image_description': 'A test image',
        'image_text': 'Extracted text from image'
    }
    
    result = adapter.format_document(raw_doc, metadata)
    
    assert result['content_type'] == 'image'
    if adapter.enable_vision:
        assert 'description' in result or 'Image:' in result['content']


def test_extract_direct_answer_no_context():
    """Test extracting direct answer with no context"""
    adapter = FileAdapter()
    
    result = adapter.extract_direct_answer([])
    
    assert result is None


def test_extract_direct_answer_low_confidence():
    """Test extracting direct answer with low confidence"""
    adapter = FileAdapter(config={'confidence_threshold': 0.5})
    
    context = [{
        'confidence': 0.3,
        'content': 'Some content'
    }]
    
    result = adapter.extract_direct_answer(context)
    
    assert result is None


def test_extract_direct_answer_with_summary():
    """Test extracting direct answer when summary is available"""
    adapter = FileAdapter(config={'confidence_threshold': 0.5})
    
    context = [{
        'confidence': 0.7,
        'summary': 'This is a summary of the content',
        'content': 'Full content here'
    }]
    
    result = adapter.extract_direct_answer(context)
    
    assert result == 'This is a summary of the content'


def test_extract_direct_answer_truncated_content():
    """Test extracting direct answer with content truncation"""
    adapter = FileAdapter(config={
        'confidence_threshold': 0.5,
        'max_summary_length': 20
    })
    
    context = [{
        'confidence': 0.7,
        'content': 'This is a very long content that should be truncated'
    }]
    
    result = adapter.extract_direct_answer(context)
    
    assert result is not None
    assert len(result) <= 23  # 20 + "..." = 23


def test_extract_direct_answer_document_type():
    """Test extracting direct answer for document files"""
    adapter = FileAdapter(config={'confidence_threshold': 0.5})
    
    context = [{
        'confidence': 0.7,
        'file_id': 'file_123',
        'filename': 'document.pdf',
        'content_type': 'document',
        'content': 'Document content here',
        'page_count': 5
    }]
    
    result = adapter.extract_direct_answer(context)
    
    assert result is not None
    assert 'document.pdf' in result or 'document' in result.lower()


def test_extract_direct_answer_data_type():
    """Test extracting direct answer for data files"""
    adapter = FileAdapter(config={'confidence_threshold': 0.5})
    
    context = [{
        'confidence': 0.7,
        'file_id': 'file_123',
        'filename': 'data.csv',
        'content_type': 'spreadsheet',
        'row_count': 100,
        'column_count': 5,
        'content': 'CSV data content'
    }]
    
    result = adapter.extract_direct_answer(context)
    
    assert result is not None
    assert 'data.csv' in result or 'data file' in result.lower()


def test_apply_domain_specific_filtering_empty():
    """Test filtering with empty context"""
    adapter = FileAdapter()
    
    result = adapter.apply_domain_specific_filtering([], "test query")
    
    assert result == []


def test_apply_domain_specific_filtering_confidence_threshold():
    """Test filtering removes items below confidence threshold"""
    adapter = FileAdapter(config={'confidence_threshold': 0.5})
    
    context = [
        {'confidence': 0.7, 'content': 'High confidence'},
        {'confidence': 0.3, 'content': 'Low confidence'},
        {'confidence': 0.6, 'content': 'Medium confidence'}
    ]
    
    result = adapter.apply_domain_specific_filtering(context, "test")
    
    assert len(result) == 2
    assert all(item['confidence'] >= 0.5 for item in result)


def test_apply_domain_specific_filtering_content_type_boost():
    """Test filtering boosts relevant content types"""
    adapter = FileAdapter(config={'confidence_threshold': 0.5})
    
    context = [{
        'confidence': 0.55,
        'content_type': 'document',
        'content': 'Document about PDF processing'
    }]
    
    result = adapter.apply_domain_specific_filtering(context, "document pdf")
    
    assert len(result) == 1
    # Should have boosted confidence
    assert result[0]['confidence'] > 0.55


def test_apply_domain_specific_filtering_filename_boost():
    """Test filtering boosts items with matching filenames"""
    adapter = FileAdapter(config={'confidence_threshold': 0.5})
    
    context = [{
        'confidence': 0.55,
        'filename': 'report_2024.pdf',
        'content': 'Report content'
    }]
    
    result = adapter.apply_domain_specific_filtering(context, "report 2024")
    
    assert len(result) == 1
    # Should have boosted confidence due to filename match
    assert result[0]['confidence'] > 0.55


def test_apply_domain_specific_filtering_sorted():
    """Test filtering returns results sorted by confidence"""
    adapter = FileAdapter(config={'confidence_threshold': 0.5})
    
    context = [
        {'confidence': 0.6, 'content': 'Content 1'},
        {'confidence': 0.8, 'content': 'Content 2'},
        {'confidence': 0.7, 'content': 'Content 3'}
    ]
    
    result = adapter.apply_domain_specific_filtering(context, "test")
    
    assert len(result) == 3
    # Should be sorted descending by confidence
    assert result[0]['confidence'] >= result[1]['confidence']
    assert result[1]['confidence'] >= result[2]['confidence']


def test_classify_content_type_text():
    """Test content type classification for text files"""
    adapter = FileAdapter()
    
    assert adapter._classify_content_type('text/plain') == 'text'
    assert adapter._classify_content_type('text/markdown') == 'text'
    assert adapter._classify_content_type('text/html') == 'text'


def test_classify_content_type_document():
    """Test content type classification for document files"""
    adapter = FileAdapter()
    
    assert adapter._classify_content_type('application/pdf') == 'document'
    assert adapter._classify_content_type('application/vnd.openxmlformats-officedocument.wordprocessingml.document') == 'document'


def test_classify_content_type_spreadsheet():
    """Test content type classification for spreadsheet files"""
    adapter = FileAdapter()
    
    assert adapter._classify_content_type('text/csv') == 'spreadsheet'
    assert adapter._classify_content_type('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') == 'spreadsheet'


def test_classify_content_type_data():
    """Test content type classification for data files"""
    adapter = FileAdapter()
    
    assert adapter._classify_content_type('application/json') == 'data'


def test_classify_content_type_image():
    """Test content type classification for image files"""
    adapter = FileAdapter()
    
    assert adapter._classify_content_type('image/png') == 'image'
    assert adapter._classify_content_type('image/jpeg') == 'image'


def test_classify_content_type_unknown():
    """Test content type classification for unknown types"""
    adapter = FileAdapter()
    
    assert adapter._classify_content_type('application/unknown') == 'unknown'


def test_is_relevant_content_type():
    """Test content type relevance checking"""
    adapter = FileAdapter()
    
    assert adapter._is_relevant_content_type('document', 'pdf document text') is True
    assert adapter._is_relevant_content_type('spreadsheet', 'data table excel') is True
    assert adapter._is_relevant_content_type('image', 'picture photo') is True
    assert adapter._is_relevant_content_type('document', 'unrelated query') is False

