# File Adapter System Guide

## Overview

The File Adapter System enables uploading, processing, and querying various file formats through ORBIT's retrieval infrastructure. It supports multiple file types including PDF, DOCX, CSV, TXT, HTML, Markdown, JSON, images, audio, and more using both lightweight and advanced document understanding libraries.

## Features

- **Multi-format Support**: PDF, DOCX, PPTX, XLSX, TXT, CSV, JSON, HTML, Markdown, images (PNG, JPEG, TIFF), audio (WAV, MP3), and WebVTT
- **Intelligent Chunking**: Fixed-size and semantic chunking strategies
- **Advanced Document Understanding**: IBM Docling for layout-aware parsing, table extraction, OCR, and ASR
- **Dual-Path Processing**:
  - Vector stores for unstructured documents (PDF, DOCX, TXT, HTML, images with OCR)
  - DuckDB for structured data (CSV, Parquet) with SQL-like queries
- **Semantic Search**: Natural language queries over file content
- **Storage Backend**: Filesystem (with S3-compatible abstraction for future migration)

## Architecture

### Storage Layer

Files are stored in an organized directory structure:
```
uploads/
  {api_key}/
    {file_id}/
      {filename}                    # Actual file
      {filename}.metadata.json     # Metadata sidecar
```

### Processing Pipeline

1. **Upload**: File uploaded via API
2. **Validation**: File type and size validation
3. **Storage**: File saved to storage backend
4. **Extraction**: Text and metadata extracted using format-specific processors
   - **Basic processors**: pypdf, python-docx, pandas for common formats
   - **Advanced processor**: IBM Docling for complex documents, images, and audio
5. **Chunking**: Content chunked using configured strategy
6. **Indexing**: Chunks indexed in vector store or DuckDB
7. **Metadata**: Processing status tracked in SQLite

### Dual-Path Strategy

#### Path 1: Vector Store (Unstructured Documents)
- Files: PDF, DOCX, TXT, HTML, MD, images, audio
- Processing: Text extraction → Chunking → Embedding → Vector store
- Query: Semantic search over chunks
- Use case: Document Q&A

#### Path 2: DuckDB (Structured Data)  
- Files: CSV, Parquet
- Processing: Load into DuckDB table
- Query: SQL-like queries via intent templates
- Use case: Data exploration and analysis

## Supported Libraries

### Basic Processors (Fast & Lightweight)
- **pypdf 6.0.0+**: PDF text extraction
- **python-docx**: Microsoft Word documents
- **pandas**: CSV and structured data
- **BeautifulSoup**: HTML parsing
- Standard library: Plain text, JSON

### Advanced Processor (IBM Docling)
- **Document formats**: PDF, DOCX, PPTX, XLSX, HTML
- **Layout understanding**: Page structure, reading order, tables
- **Specialized features**:
  - OCR for scanned documents and images
  - ASR (Automatic Speech Recognition) for audio
  - Advanced table extraction
  - Formula and code detection
- **Additional formats**: Images (PNG, JPEG, TIFF), audio (WAV, MP3), WebVTT

Docling is registered as a fallback processor and automatically handles complex documents that require advanced understanding.

## API Endpoints

### Upload File

```bash
curl -X POST "http://localhost:3000/api/files/upload" \
  -H "X-API-Key: your-api-key" \
  -F "file=@document.pdf"
```

Response:
```json
{
  "file_id": "uuid",
  "filename": "document.pdf",
  "mime_type": "application/pdf",
  "file_size": 123456,
  "status": "completed",
  "chunk_count": 15,
  "message": "File uploaded and processed successfully"
}
```

### List Files

```bash
curl -X GET "http://localhost:3000/api/files" \
  -H "X-API-Key: your-api-key"
```

Response:
```json
[
  {
    "file_id": "uuid",
    "filename": "document.pdf",
    "mime_type": "application/pdf",
    "file_size": 123456,
    "upload_timestamp": "2024-01-01T00:00:00",
    "processing_status": "completed",
    "chunk_count": 15,
    "storage_type": "vector"
  }
]
```

### Get File Info

```bash
curl -X GET "http://localhost:3000/api/files/{file_id}" \
  -H "X-API-Key: your-api-key"
```

### Query File

```bash
curl -X POST "http://localhost:3000/api/files/{file_id}/query" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is this document about?", "max_results": 5}'
```

Response:
```json
{
  "file_id": "uuid",
  "filename": "document.pdf",
  "results": [
    {
      "content": "chunk text...",
      "metadata": {
        "chunk_id": "...",
        "chunk_index": 0,
        "confidence": 0.95
      }
    }
  ]
}
```

### Delete File

```bash
curl -X DELETE "http://localhost:3000/api/files/{file_id}" \
  -H "X-API-Key: your-api-key"
```

Response:
```json
{
  "message": "File deleted successfully",
  "file_id": "uuid"
}
```

### Delete All Files

Delete all files for an API key:

```bash
curl -X DELETE "http://localhost:3000/api/files" \
  -H "X-API-Key: your-api-key"
```

Response:
```json
{
  "message": "Deleted 5 file(s)",
  "deleted_count": 5,
  "errors": null
}
```

This endpoint deletes all files, chunks, and vector store entries for the specified API key. Useful for cleanup and testing.

## Configuration

Configure the file adapter in `config/adapters.yaml`:

```yaml
- name: "file-document-qa"
  enabled: true
  type: "retriever"
  datasource: "file"
  adapter: "file"
  
  config:
    # Storage
    storage_backend: "filesystem"
    storage_root: "./uploads"
    max_file_size: 52428800  # 50MB
    
    # Chunking
    chunking_strategy: "semantic"  # or "fixed"
    chunk_size: 1000
    chunk_overlap: 200
    
    # Vector store
    vector_store: "chroma"
    collection_prefix: "files_"
    
    # Supported types
    supported_types:
      - "application/pdf"
      - "text/plain"
      - "text/markdown"
      - "text/csv"
      - "application/json"
      - "text/html"
      - "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
      - "application/vnd.openxmlformats-officedocument.presentationml.presentation"
      - "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
      - "image/png"
      - "image/jpeg"
      - "image/tiff"
      - "audio/wav"
      - "audio/mpeg"
      - "text/vtt"
      
    # Q&A
    confidence_threshold: 0.3
    max_results: 5
    return_results: 3
    
    # DuckDB
    enable_duckdb_path: true
    duckdb_store: "duckdb"
```

## Supported File Types

| Type | MIME Type | Processor | Path | Notes |
|------|-----------|-----------|------|-------|
| PDF | `application/pdf` | pypdf/docling | Vector | Layout-aware parsing with Docling |
| DOCX | `application/...docx` | python-docx/docling | Vector | Structure preservation |
| PPTX | `application/...pptx` | docling | Vector | Slide content extraction |
| XLSX | `application/...xlsx` | docling | Vector | Cell-level parsing |
| TXT | `text/plain` | Text | Vector | Plain text |
| Markdown | `text/markdown` | Text | Vector | Plain text |
| CSV | `text/csv` | pandas/docling | DuckDB/Vector | Dual-path support |
| JSON | `application/json` | JSON | Vector | Structured data |
| HTML | `text/html` | BeautifulSoup/docling | Vector | Advanced parsing |
| PNG/JPEG/TIFF | `image/*` | docling | Vector | OCR support |
| WAV/MP3 | `audio/*` | docling | Vector | ASR support |
| VTT | `text/vtt` | docling | Vector | Caption parsing |

## Processor Selection Strategy

The system intelligently selects the best processor for each file:

1. **Format-specific processors** are tried first (fast, lightweight)
   - Example: pypdf for PDFs, python-docx for DOCX
2. **Docling processor** is used as fallback (advanced features)
   - Complex layouts, OCR for images, ASR for audio
   - Automatically handles formats without specific processors

This ensures optimal performance while supporting advanced features when needed.

## Chunking Strategies

### Fixed-Size Chunking

- Splits text into fixed-size chunks with overlap
- Fast and simple
- May split sentences

Configuration:
```yaml
chunking_strategy: "fixed"
chunk_size: 1000
chunk_overlap: 200
```

### Semantic Chunking

- Sentence-boundary aware
- Better coherence
- Uses sentence-transformers (if available)

Configuration:
```yaml
chunking_strategy: "semantic"
chunk_size: 10  # sentences
chunk_overlap: 2
```

## Query Examples

### Querying a PDF Document

```bash
curl -X POST "http://localhost:3000/api/files/{file_id}/query" \
  -H "X-API-Key: key" \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the main conclusions in this document?"}'
```

### Querying CSV Data

CSV files are loaded into DuckDB for SQL-like querying:

```bash
curl -X POST "http://localhost:3000/api/files/{csv_file_id}/query" \
  -H "X-API-Key: key" \
  -d '{"query": "What are the total sales by region?"}'
```

This translates to intent-based SQL queries using templates.

### Querying Images with Text

Images are processed with OCR:

```bash
curl -X POST "http://localhost:3000/api/files/{image_id}/query" \
  -H "X-API-Key: key" \
  -d '{"query": "What text is visible in this image?"}'
```

### Querying Audio Files

Audio files use ASR for transcription:

```bash
curl -X POST "http://localhost:3000/api/files/{audio_id}/query" \
  -H "X-API-Key: key" \
  -d '{"query": "What was discussed in this recording?"}'
```

## Integration with Chat

Files can be referenced in chat queries:

```
"What does contract.pdf say about payment terms?"
"What are the trends in sales_data.csv?"
"What text is in image.png?"
"What was discussed in meeting_audio.wav?"
```

The system resolves file references and queries appropriate collections.

## Storage Abstraction

The system uses a pluggable storage backend:

- **FilesystemStorage** (current): Local filesystem storage
- **S3Storage** (future): S3-compatible storage (MinIO, AWS S3, etc.)

To switch backends, update configuration:
```yaml
storage_backend: "s3"  # instead of "filesystem"
```

## Metadata Store

File metadata is stored in the main backend database (SQLite `orbit.db` or MongoDB, configured via `internal_services.backend` in `config.yaml`):

- `uploaded_files`: File metadata and processing status
- `file_chunks`: Chunk references and vector store mappings

This enables:
- File tracking and lifecycle management
- Chunk cleanup on file deletion
- Multi-tenancy via API key isolation
- Processing status monitoring
- Unified database backend (no separate `files.db`)

## Installation Notes

### NumPy Compatibility

The system uses NumPy 1.x (`numpy<2.0`) for compatibility with PyTorch and transformers. This is configured in `install/dependencies.toml`:

```toml
"numpy<2.0.0",  # Pin to NumPy 1.x for compatibility
```

This prevents the NumPy 2.x compatibility issues that can cause server startup failures.

## Best Practices

### File Size
- Keep files under 50MB for optimal performance
- Larger files may take longer to process

### Chunk Size
- 1000 characters for fixed chunking
- 10 sentences for semantic chunking
- Adjust based on document structure

### Collection Naming
- Use `collection_prefix` to organize file collections
- Format: `{prefix}{api_key}_{timestamp}`

### Storage
- Use filesystem for development
- Plan for S3/MinIO in production
- Monitor disk usage with large volumes

## Troubleshooting

### File Processing Fails
- Check file format is supported
- Verify file size is within limits
- Check logs for processor errors

### No Results from Query
- Ensure file processing completed
- Verify chunks were indexed
- Check confidence threshold

### Storage Issues
- Monitor disk space
- Check storage backend configuration
- Verify write permissions

### Server Startup Issues
- Ensure NumPy version is compatible (should be < 2.0)
- Check virtual environment is activated
- Verify all dependencies installed correctly

## Future Enhancements

- [ ] S3/MinIO storage backend
- [ ] Additional formats (Excel with advanced features, PowerPoint)
- [ ] Advanced chunking (structure-aware, table-aware)
- [ ] Multi-document analysis
- [ ] Streaming processing for large files
- [ ] Document versioning and history
- [ ] Table extraction from PDFs
- [ ] Citation and source tracking
- [ ] Chart understanding (bar charts, line plots, etc.)
- [ ] Chemistry structure understanding

## See Also

- [Adapter Configuration](../adapter-configuration.md)
- [Vector Store Architecture](../vector_store_architecture.md)
- [Retriever Architecture](../../server/retrievers/README.md)