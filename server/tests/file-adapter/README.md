# File Adapter Test Suite

Comprehensive test suite for the ORBIT File Adapter System.

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

**Coverage**: File processing pipeline (Phase 1.2 & Phase 2)

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

# Integration tests only
pytest tests/file-adapter/test_integration.py -v
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
| File Processing | 25+ | Processors, service, validation |
| Integration | 20+ | End-to-end workflows |

**Total**: 110+ test cases

## Test Requirements

### Dependencies

All test dependencies are included in the `minimal` profile:
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

## Future Test Additions

Potential areas for additional test coverage:

- [ ] PDF processor tests with actual PDF files
- [ ] DOCX processor tests with actual DOCX files
- [ ] CSV processor tests with various CSV formats
- [ ] Vector store integration tests (requires Chroma/Qdrant)
- [ ] File retriever tests
- [ ] API endpoint tests (FastAPI integration)
- [ ] DuckDB path tests for structured data
- [ ] S3 storage backend tests (when implemented)

## Contributing

When contributing tests:

1. Ensure all tests pass locally
2. Add tests for new features
3. Maintain or improve coverage
4. Follow existing patterns and conventions
5. Update documentation as needed

## License

These tests are part of the ORBIT project and follow the same license.
