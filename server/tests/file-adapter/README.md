# File Adapter Test Suite

Test suite for the ORBIT File Adapter System.

## Test Structure

The test suite is organized into the following modules:

### Unit Tests

#### `test_file_storage.py`
Tests for the file storage backend (FilesystemStorage):
- File put/get/delete operations
- Metadata sidecar handling
- Atomic writes
- Directory structure creation
- Special character handling
- Concurrent operations

**Coverage**: Storage abstraction layer (Phase 1.1)

#### `test_chunking.py`
Tests for text chunking strategies:
- Fixed-size chunking with overlap
- Semantic chunking with sentence boundaries
- Chunk ID generation
- Metadata preservation
- Edge cases (empty text, special characters)

**Coverage**: Chunking strategies (Phase 1.3)

#### `test_metadata_store.py`
Tests for SQLite-based metadata tracking:
- File upload recording
- Processing status updates
- Chunk tracking
- File listing and filtering by API key
- File and chunk deletion
- Multi-tenancy isolation

**Coverage**: File metadata store (Phase 1.4)

#### `test_file_processing.py`
Tests for file processors and processing service:
- Text processor (and other format processors)
- Processor registry
- File processing service workflow
- Validation (file type, size limits)
- Chunking strategy initialization
- Error handling
- Configuration handling (adapter config → global defaults → hardcoded defaults)

**Coverage**: File processing pipeline (Phase 1.2 & Phase 2)

#### `test_file_adapter.py`
Tests for FileAdapter document formatting and domain-specific processing:
- Adapter initialization (default, custom, global config)
- Document formatting (basic, with title/summary, file metadata)
- Content type classification (document, spreadsheet, data, image)
- Direct answer extraction
- Domain-specific filtering and confidence boosting
- Content type relevance checking

**Coverage**: File adapter formatting and filtering (Phase 2)

#### `test_file_retriever.py`
Tests for FileVectorRetriever vector search and retrieval:
- Retriever initialization (default, adapter config, global config)
- Configuration priority (adapter → global → default)
- Collection retrieval by file_id, api_key, collection_name
- Vector store search operations
- Result formatting with metadata enrichment
- Chunk indexing and deletion
- Integration with metadata store

**Coverage**: File vector retrieval (Phase 3)

### Integration Tests

#### `test_integration.py`
End-to-end workflow tests:
- Complete upload → process → store workflow
- Multiple file types
- Upload and delete workflow
- Concurrent uploads
- Multi-tenancy isolation
- Large file processing
- Error recovery
- File lifecycle management
- System under load

**Coverage**: Full system integration (Phase 3 & Phase 4)

## Running Tests

### Run All File Adapter Tests

```bash
# From project root
cd server
pytest tests/file-adapter/ -v

# Or with coverage
pytest tests/file-adapter/ --cov=services/file_storage --cov=services/file_processing --cov=services/file_metadata -v
```

### Run Specific Test Modules

```bash
# Storage tests only
pytest tests/file-adapter/test_file_storage.py -v

# Chunking tests only
pytest tests/file-adapter/test_chunking.py -v

# Metadata tests only
pytest tests/file-adapter/test_metadata_store.py -v

# Processing tests only
pytest tests/file-adapter/test_file_processing.py -v

# Retriever tests only
pytest tests/file-adapter/test_file_retriever.py -v

# Integration tests only
pytest tests/file-adapter/test_integration.py -v

# Chat with file context tests (NEW)
pytest tests/file-adapter/test_chat_with_file_context.py -v

# Chat routes integration tests (NEW)
pytest tests/file-adapter/test_chat_routes_with_files.py -v

# Multiple file retrieval tests (NEW)
pytest tests/file-adapter/test_file_retriever_multiple_files.py -v

# File routes integration tests
pytest tests/file-adapter/test_file_routes_integration.py -v

# Full pipeline tests for all file types (NEW)
pytest tests/file-adapter/test_file_types_full_pipeline.py -v
```

### Run Specific Tests

```bash
# Run a specific test function
pytest tests/file-adapter/test_file_storage.py::test_put_file_basic -v

# Run tests matching a pattern
pytest tests/file-adapter/ -k "concurrent" -v
```

### Run with Markers

```bash
# Run only async tests
pytest tests/file-adapter/ -m asyncio -v

# Run only integration tests
pytest tests/file-adapter/test_integration.py -v
```

## Test Coverage Summary

| Component | Tests | Coverage |
|-----------|-------|----------|
| File Storage | 20+ | Storage backend, atomic writes, metadata |
| Chunking | 25+ | Fixed and semantic strategies |
| Metadata Store | 20+ | SQLite operations, multi-tenancy |
| File Processing | 30+ | Processors, service, validation, config handling |
| File Adapter | 30+ | Document formatting, filtering, content classification |
| File Retriever | 25+ | Vector search, collection management, config priority |
| Integration | 20+ | End-to-end workflows |
| **Chat with File Context** | **25+** | **Pipeline integration, context retrieval, file_ids** |
| **Chat Routes Integration** | **20+** | **HTTP endpoints, streaming, multi-file support** |
| **Multiple File Retrieval** | **15+** | **Multiple file_ids, filtering, aggregation** |
| **File Types Full Pipeline** | **11+** | **MD, TXT, PDF, DOCX, CSV, JSON, HTML, PNG, JPEG, vision service** |

**Total**: 241+ test cases

## Test Requirements

### Dependencies

All test dependencies are included in the default dependencies:
- `pytest>=8.3.5`
- `pytest-asyncio>=1.1.0` (for async tests)

### Additional Requirements

Some processors may require additional dependencies:
- `pypdf>=6.0.0` - PDF processing
- `python-docx>=1.2.0` - DOCX processing
- `pandas>=2.3.3` - CSV processing
- `beautifulsoup4>=4.14.1` - HTML processing
- `docling>=2.58.0` - Advanced document processing (optional)

## Test Patterns

### Async Tests

```python
@pytest.mark.asyncio
async def test_async_operation():
    result = await some_async_function()
    assert result is not None
```

### Fixtures

```python
@pytest_asyncio.fixture
async def service(tmp_path):
    service = FileProcessingService(config)
    yield service
    # Cleanup
    service.metadata_store.close()
```

### Temporary Files

```python
def test_with_temp_files(tmp_path):
    # tmp_path is automatically cleaned up
    test_file = tmp_path / "test.txt"
    test_file.write_text("content")
```

### Error Testing

```python
def test_error_handling():
    with pytest.raises(ValueError, match="error message"):
        function_that_should_fail()
```

## Common Test Scenarios

### Testing File Upload

```python
result = await service.process_file(
    file_data=b"content",
    filename="test.txt",
    mime_type="text/plain",
    api_key="test_key"
)

assert result["status"] == "completed"
assert result["chunk_count"] > 0
```

### Testing Multi-tenancy

```python
# Upload with different API keys
await service.process_file(..., api_key="tenant_1")
await service.process_file(..., api_key="tenant_2")

# Verify isolation
files_1 = await service.list_files("tenant_1")
files_2 = await service.list_files("tenant_2")

assert len(files_1) == 1
assert len(files_2) == 1
```

### Testing Concurrent Operations

```python
async def upload(index):
    return await service.process_file(...)

results = await asyncio.gather(*[upload(i) for i in range(10)])
assert all(r["status"] == "completed" for r in results)
```

## Troubleshooting

### Tests Fail with Database Locked

SQLite may have issues with concurrent access. The metadata store tests use separate database files per test via the `tmp_path` fixture.

### Tests Fail with Import Errors

Ensure you're running tests from the `server` directory:
```bash
cd server
pytest tests/file-adapter/
```

### Tests Fail with Missing Dependencies

Install required dependencies:
```bash
pip install -e ".[minimal]"  # Core dependencies
```

### Async Test Warnings

If you see deprecation warnings about event loops, ensure you have `pytest-asyncio>=1.1.0` installed.

## Continuous Integration

These tests can be integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run File Adapter Tests
  run: |
    cd server
    pytest tests/file-adapter/ \
      --cov=services/file_storage \
      --cov=services/file_processing \
      --cov=services/file_metadata \
      --cov-report=xml \
      -v
```

## Adding New Tests

When adding new tests:

1. Follow the existing naming convention: `test_<feature>_<scenario>`
2. Add docstrings explaining what the test validates
3. Use appropriate fixtures for setup/teardown
4. Group related tests in the same file
5. Add async marker for async tests: `@pytest.mark.asyncio`
6. Update this README if adding new test modules

## Performance Benchmarks

Some tests include performance checks:
- Large file processing (1MB+)
- Concurrent uploads (10-20 files)
- System under load (20+ operations)

These can be used as baseline benchmarks for performance optimization.

#### `test_chat_with_file_context.py`
Tests for chat integration with file context:
- Processing context file_ids storage
- Context retrieval step passing file_ids to retriever
- File retriever handling multiple file_ids
- File filtering by file_ids
- Adapter routing (file-document-qa vs others)
- API key ownership validation with file context
- Backward compatibility with single file_id
- Chat service passing file_ids through pipeline
- Streaming chat with file_ids

**Coverage**: Chat integration with file uploads (NEW)

#### `test_chat_routes_with_files.py`
Integration tests for /v1/chat endpoint with file_ids:
- Chat with single file context
- Chat with multiple file contexts
- Streaming chat with file context
- Chat without file context (normal operation)
- Empty file_ids handling
- Invalid file_id handling
- Multi-tenancy file context isolation
- Complete workflow: upload → chat → delete
- Request schema validation
- Performance testing with file context

**Coverage**: HTTP chat routes with file integration (NEW)

#### `test_file_retriever_multiple_files.py`
Tests for multiple file_ids support in FileVectorRetriever:
- Getting collections for multiple file_ids
- Collection name override behavior
- Empty vs None file_ids handling
- Non-existent file_ids handling
- Post-filtering with multiple file_ids
- Single file_id filter_metadata usage
- Backward compatibility with single file_id
- Mixed existing/non-existing file_ids
- Result aggregation across collections

**Coverage**: Multiple file querying functionality (NEW)

#### `test_file_types_full_pipeline.py`
Full pipeline integration tests for each supported file type:
- Markdown (.md) - full upload → process → query → chat → delete cycle
- Plain text (.txt) - text extraction and chunking verification
- PDF (.pdf) - PDF processor with reportlab-generated test files
- DOCX (.docx) - Word document processing with python-docx
- CSV (.csv) - structured data handling
- JSON (.json) - JSON parsing and indexing
- HTML (.html) - HTML text extraction
- PNG images (.png) - vision service integration and OCR
- JPEG images (.jpg) - vision service with different image format
- Unsupported file type handling
- Oversized file rejection

**Purpose**: These tests simulate actual client usage through the Node API, testing the complete server-side pipeline for each file type. Particularly useful for debugging vision service integration issues with images.

**Coverage**: End-to-end file type processing with vision service (NEW)

## Future Test Additions

Potential areas for additional test coverage:

- [x] PDF processor tests with actual PDF files ✓ (NEW)
- [x] DOCX processor tests with actual DOCX files ✓ (NEW)
- [x] CSV processor tests with various CSV formats ✓ (NEW)
- [x] Image processor tests with vision service ✓ (NEW)
- [ ] Vector store integration tests (requires Chroma/Qdrant)
- [x] File retriever tests ✓
- [x] File adapter tests ✓
- [x] Configuration handling tests ✓
- [x] Chat integration with file context ✓ (NEW)
- [x] Multiple file_ids support ✓ (NEW)
- [x] API endpoint tests (FastAPI integration) ✓ (NEW)
- [x] Full pipeline tests for all file types ✓ (NEW)
- [ ] DuckDB path tests for structured data
- [ ] S3 storage backend tests (when implemented)
- [ ] Multi-page PDF processing tests
- [ ] Large image file handling tests
- [ ] Vision service error handling tests

## Contributing

When contributing tests:

1. Ensure all tests pass locally
2. Add tests for new features
3. Maintain or improve coverage
4. Follow existing patterns and conventions
5. Update documentation as needed
