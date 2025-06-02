import os
import io
import sys
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock

# Get the directory of this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Add the parent directory to Python path for imports
if str(SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR.parent))

# Import services - handle import errors gracefully
try:
    from services.file_service import FileService
except ImportError as e:
    # If the import fails, we need to adjust the path
    sys.path.insert(0, str(SCRIPT_DIR))
    from file_service import FileService


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test uploads"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def config(temp_dir):
    return {
        'file_upload': {
            'max_size_mb': 10,
            'allowed_extensions': ['.txt', '.pdf', '.docx', '.doc', '.xlsx', '.xls', '.csv', '.md', '.json'],
            'upload_directory': temp_dir,
            'auto_store_in_vector_db': True,
            'chunk_size': 1000,
            'chunk_overlap': 200,
            'save_to_disk': True
        }
    }


@pytest.fixture
def retriever_service():
    mock_service = Mock()
    mock_service.store_document = AsyncMock(return_value={'success': True})
    return mock_service


@pytest.fixture
def file_service(config, retriever_service):
    return FileService(config, retriever_service)


class TestFileService:
    
    @pytest.mark.asyncio
    async def test_validate_file_size(self, file_service):
        """Test file size validation"""
        # Test file size validation
        large_file = b'x' * (file_service.max_file_size + 1)
        result = file_service._validate_file(large_file, 'test.txt')
        assert not result['valid']
        assert 'exceeds maximum allowed size' in result['error']
        
        # Test valid file size
        valid_file = b'x' * 1000
        result = file_service._validate_file(valid_file, 'test.txt')
        assert result['valid']

    @pytest.mark.asyncio
    async def test_validate_file_extension(self, file_service):
        """Test file extension validation"""
        # Test invalid extension
        result = file_service._validate_file(b'test', 'test.invalid')
        assert not result['valid']
        assert 'not allowed' in result['error']
        
        # Test valid extension
        result = file_service._validate_file(b'test', 'test.txt')
        assert result['valid']

    @pytest.mark.asyncio
    async def test_validate_empty_file(self, file_service):
        """Test empty file validation"""
        result = file_service._validate_file(b'', 'test.txt')
        assert not result['valid']
        assert 'empty' in result['error']

    @pytest.mark.asyncio
    async def test_process_text_file(self, file_service):
        """Test processing a text file"""
        content = b'Hello, this is a test file'
        result = await file_service.process_file_upload(content, 'test.txt')
        
        assert result['success']
        assert result['file_id'] is not None
        assert result['filename'] == 'test.txt'
        assert 'text' in result['mime_type']
        assert result['text_preview'] == 'Hello, this is a test file'

    @pytest.mark.asyncio
    async def test_process_pdf_file(self, file_service):
        """Test processing a PDF file"""
        # Create a minimal PDF content
        pdf_content = b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nxref\n0 1\n0000000000 65535 f \ntrailer\n<< /Size 1 /Root 1 0 R >>\nstartxref\n0\n%%EOF'
        
        # Mock the PDF processing
        with patch('services.file_service.HAS_PDF', True), \
             patch('services.file_service.PdfReader') as mock_pdf_reader:
            
            # Create mock page with text extraction
            mock_page = Mock()
            mock_page.extract_text.return_value = 'Test PDF content'
            
            # Create mock PDF reader
            mock_reader_instance = Mock()
            mock_reader_instance.pages = [mock_page]
            mock_pdf_reader.return_value = mock_reader_instance
            
            result = await file_service.process_file_upload(pdf_content, 'test.pdf')
            
            assert result['success']
            assert result['file_id'] is not None
            assert result['filename'] == 'test.pdf'
            assert result['text_preview'] == 'Page 1:\nTest PDF content'

    @pytest.mark.asyncio
    async def test_process_pdf_file_without_library(self, file_service):
        """Test PDF processing when pypdf is not available"""
        pdf_content = b'%PDF-1.4\ntest content'
        
        with patch('services.file_service.HAS_PDF', False):
            result = await file_service.process_file_upload(pdf_content, 'test.pdf')
            
            assert not result['success']
            assert 'PDF processing not available' in result['error']

    @pytest.mark.asyncio
    async def test_process_docx_file(self, file_service):
        """Test processing a DOCX file"""
        # Create a minimal DOCX-like content
        docx_content = b'PK\x03\x04\x14\x00\x06\x00\x08\x00\x00\x00!\x00'
        
        with patch('services.file_service.HAS_DOCX', True), \
             patch('services.file_service.docx2python') as mock_docx:
            
            # Create a mock document context manager
            mock_doc = Mock()
            mock_doc.text = 'Test DOCX content'
            
            # Set up the context manager
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_doc)
            mock_context.__exit__ = Mock(return_value=None)
            mock_docx.return_value = mock_context
            
            result = await file_service.process_file_upload(docx_content, 'test.docx')
            
            assert result['success']
            assert result['file_id'] is not None
            assert result['filename'] == 'test.docx'
            assert result['text_preview'] == 'Test DOCX content'

    @pytest.mark.asyncio
    async def test_process_docx_file_without_library(self, file_service):
        """Test DOCX processing when docx2python is not available"""
        docx_content = b'PK\x03\x04'
        
        with patch('services.file_service.HAS_DOCX', False):
            result = await file_service.process_file_upload(docx_content, 'test.docx')
            
            assert not result['success']
            assert 'DOCX processing not available' in result['error']

    @pytest.mark.asyncio
    async def test_process_excel_file(self, file_service):
        """Test processing an Excel file"""
        excel_content = b'PK\x03\x04\x14\x00\x06\x00\x08\x00\x00\x00!\x00'
        
        with patch('services.file_service.HAS_EXCEL', True), \
             patch('services.file_service.openpyxl.load_workbook') as mock_load_workbook:
            
            # Create mock sheet
            mock_sheet = Mock()
            mock_sheet.iter_rows.return_value = [
                ['Header1', 'Header2'],
                ['Value1', 'Value2']
            ]
            
            # Create mock workbook with proper __getitem__ support
            mock_workbook = Mock()
            mock_workbook.sheetnames = ['Sheet1']
            # Use a MagicMock to properly support __getitem__
            mock_workbook = MagicMock()
            mock_workbook.sheetnames = ['Sheet1']
            mock_workbook.__getitem__.return_value = mock_sheet
            mock_load_workbook.return_value = mock_workbook
            
            result = await file_service.process_file_upload(excel_content, 'test.xlsx')
            
            assert result['success']
            assert result['file_id'] is not None
            assert result['filename'] == 'test.xlsx'
            assert 'Sheet: Sheet1' in result['text_preview']

    @pytest.mark.asyncio
    async def test_process_excel_file_without_library(self, file_service):
        """Test Excel processing when openpyxl is not available"""
        excel_content = b'PK\x03\x04'
        
        with patch('services.file_service.HAS_EXCEL', False):
            result = await file_service.process_file_upload(excel_content, 'test.xlsx')
            
            assert not result['success']
            assert 'Excel processing not available' in result['error']

    @pytest.mark.asyncio
    async def test_process_csv_file(self, file_service):
        """Test processing a CSV file"""
        content = b'header1,header2\nvalue1,value2\nvalue3,value4'
        result = await file_service.process_file_upload(content, 'test.csv')
        
        assert result['success']
        assert result['file_id'] is not None
        assert result['filename'] == 'test.csv'
        # The CSV processing creates pipe-separated format, so check for that
        assert 'header1 | header2' in result['text_preview'] or 'header1,header2' in result['text_preview']
        assert 'value1' in result['text_preview']

    @pytest.mark.asyncio
    async def test_process_json_file(self, file_service):
        """Test processing a JSON file"""
        content = b'{"key": "value", "number": 123}'
        result = await file_service.process_file_upload(content, 'test.json')
        
        assert result['success']
        assert result['file_id'] is not None
        assert result['filename'] == 'test.json'
        assert '"key": "value"' in result['text_preview']

    @pytest.mark.asyncio
    async def test_file_storage_and_retrieval(self, file_service, temp_dir):
        """Test file storage, info retrieval, and deletion"""
        content = b'Test content for storage'
        
        result = await file_service.process_file_upload(content, 'test.txt')
        
        assert result['success']
        assert result['file_id'] is not None
        assert result['file_path'] is not None
        assert Path(result['file_path']).exists()
        
        # Test file info retrieval
        file_info = await file_service.get_file_info(result['file_id'])
        assert file_info is not None
        assert file_info['file_id'] == result['file_id']
        assert file_info['file_size'] == len(content)
        
        # Test file deletion
        delete_result = await file_service.delete_file(result['file_id'])
        assert delete_result
        assert not Path(result['file_path']).exists()

    @pytest.mark.asyncio
    async def test_text_chunking(self, file_service):
        """Test text chunking functionality"""
        # Create a long text with multiple sentences
        sentences = [f'This is sentence number {i}.' for i in range(100)]
        long_text = ' '.join(sentences)
        
        chunks = file_service._split_text_into_chunks(long_text)
        
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= file_service.chunk_size
            assert len(chunk) > 0
        
        # Test short text doesn't get chunked
        short_text = "This is a short text."
        short_chunks = file_service._split_text_into_chunks(short_text)
        assert len(short_chunks) == 1
        assert short_chunks[0] == short_text

    @pytest.mark.asyncio
    async def test_vector_db_storage(self, file_service, retriever_service):
        """Test vector database storage"""
        content = b'Test content for vector storage'
        
        # Mock the vector storage
        with patch.object(file_service, '_store_in_vector_db', 
                         return_value={'success': True, 'chunks_stored': 1}) as mock_store:
            
            result = await file_service.process_file_upload(content, 'test.txt', 'test_collection')
            
            assert result['success']
            assert len(result['storage_results']) > 0
            mock_store.assert_called_once()

    @pytest.mark.asyncio
    async def test_mime_type_detection(self, file_service):
        """Test MIME type detection"""
        # Test with magic library available
        with patch('services.file_service.HAS_MAGIC', True), \
             patch('services.file_service.magic.from_buffer', return_value='text/plain'):
            
            mime_type = file_service._detect_mime_type(b'test content', 'test.txt')
            assert mime_type == 'text/plain'
        
        # Test fallback to mimetypes module
        with patch('services.file_service.HAS_MAGIC', False):
            mime_type = file_service._detect_mime_type(b'test content', 'test.txt')
            assert mime_type == 'text/plain'
        
        # Test unknown extension
        with patch('services.file_service.HAS_MAGIC', False):
            mime_type = file_service._detect_mime_type(b'test content', 'test.unknown')
            assert mime_type == 'application/octet-stream'

    @pytest.mark.asyncio
    async def test_error_handling(self, file_service):
        """Test various error conditions"""
        # Test with empty file
        result = await file_service.process_file_upload(b'', 'test.txt')
        assert not result['success']
        assert 'empty' in result['error']
        
        # Test with unsupported file type
        result = await file_service.process_file_upload(b'test', 'test.xyz')
        assert not result['success']
        assert 'not allowed' in result['error']
        
        # Test with oversized file
        large_content = b'x' * (file_service.max_file_size + 1)
        result = await file_service.process_file_upload(large_content, 'test.txt')
        assert not result['success']
        assert 'exceeds maximum allowed size' in result['error']

    @pytest.mark.asyncio
    async def test_unicode_handling(self, file_service):
        """Test handling of different text encodings"""
        # Test UTF-8 content
        utf8_content = 'Hello, 世界! 🌍'.encode('utf-8')
        result = await file_service.process_file_upload(utf8_content, 'test_utf8.txt')
        assert result['success']
        assert 'Hello, 世界! 🌍' in result['text_preview']
        
        # Test Latin-1 content that would fail UTF-8 decoding
        latin1_content = 'Café élève'.encode('latin-1')
        result = await file_service.process_file_upload(latin1_content, 'test_latin1.txt')
        assert result['success']

    @pytest.mark.asyncio
    async def test_get_file_info_nonexistent(self, file_service):
        """Test getting info for non-existent file"""
        file_info = await file_service.get_file_info('nonexistent-id')
        assert file_info is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_file(self, file_service):
        """Test deleting non-existent file"""
        result = await file_service.delete_file('nonexistent-id')
        assert not result

    def test_timestamp_format(self, file_service):
        """Test timestamp generation"""
        timestamp = file_service._get_timestamp()
        assert timestamp.endswith('Z')
        assert 'T' in timestamp  # ISO format includes T separator