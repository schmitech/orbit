# File Adapter System Implementation Plan

## Overview

Implement a production-ready file adapter system that enables document upload, intelligent chunking, vector indexing, and Q&A capabilities. The system uses hybrid storage (local filesystem with S3-compatible abstraction layer), supports multiple file formats (PDF, DOCX, CSV, TXT, HTML, Markdown, JSON), and integrates with ORBIT's existing vector store infrastructure.

## Architecture Alignment

### Storage Strategy (Hybrid Approach)

- **Phase 1**: Local filesystem storage with clean abstraction layer
- **Storage abstraction interface**: `FileStorageBackend` supporting put/get/list/delete operations
- **Future-ready**: Design allows seamless migration to MinIO/S3 without adapter code changes
- **File organization**: `uploads/{api_key}/{file_id}/` structure for isolation and access control

### Integration Pattern (Dual-Path Strategy)

**Path 1: Vector Store Integration (Unstructured Documents)**

- Files like PDF, DOCX, TXT, HTML, MD chunked and indexed into vector stores (Chroma, Pinecone, Qdrant, etc.)
- Leverage existing `BaseVectorStore` infrastructure (`server/vector_stores/base/base_vector_store.py`)
- Uses QA adapter for question-answering over chunked content
- Chunks stored with rich metadata: `file_id`, `filename`, `chunk_index`, `page_number`, etc.

**Path 2: DuckDB Direct Query (Structured Data)**

- CSV, Parquet, TSV files loaded directly into DuckDB for SQL-based querying
- Leverage existing `DuckDBStore` (`server/vector_stores/implementations/duckdb_store.py`)
- Uses Intent-based semantic adapter with template matching (like PostgreSQL/SQLite intent adapters)
- Templates define common query patterns for data exploration, aggregation, filtering
- Enables natural language → SQL translation for tabular data

### Adapter Pattern

- `FileAdapter` extends `DocumentAdapter` (`server/adapters/base.py`)
- Registered with `ADAPTER_REGISTRY` following existing patterns
- Configuration via `config/adapters.yaml` with file-specific settings
- No dedicated file datasource needed - adapter manages file operations directly

## Implementation Phases

### Phase 1: Core Infrastructure (Foundation)

#### 1.1 Storage Abstraction Layer

**Location**: `server/services/file_storage/`

Create pluggable storage backend:

```python
# server/services/file_storage/base_storage.py
class FileStorageBackend(ABC):
    @abstractmethod
    async def put_file(self, file_data: bytes, key: str, metadata: Dict) -> str
    
    @abstractmethod
    async def get_file(self, key: str) -> bytes
    
    @abstractmethod
    async def delete_file(self, key: str) -> bool
    
    @abstractmethod
    async def list_files(self, prefix: str) -> List[str]
    
    @abstractmethod
    async def get_metadata(self, key: str) -> Dict[str, Any]

# server/services/file_storage/filesystem_storage.py
class FilesystemStorage(FileStorageBackend):
    """Local filesystem implementation with organized structure"""
    # uploads/{api_key}/{file_id}/{filename}
    # Includes metadata sidecar files (JSON)

# server/services/file_storage/s3_storage.py (Future)
class S3Storage(FileStorageBackend):
    """S3-compatible storage (MinIO/AWS S3/etc.)"""
    # Will be implemented in Phase 4
```

**Key Features**:

- Atomic writes with temp files
- Metadata stored as JSON sidecar files
- Automatic directory creation
- Path validation and sanitization
- File size limits and validation

#### 1.2 File Processing Pipeline

**Location**: `server/services/file_processing/`

Build modular file processor supporting multiple formats:

```python
# server/services/file_processing/base_processor.py
class FileProcessor(ABC):
    @abstractmethod
    async def extract_text(self, file_data: bytes) -> str
    
    @abstractmethod
    async def extract_metadata(self, file_data: bytes) -> Dict[str, Any]
    
    @abstractmethod
    def supports_mime_type(self, mime_type: str) -> bool

# Implementations:
# - text_processor.py (TXT, MD, plaintext)
# - pdf_processor.py (PDF via PyPDF2 or pdfplumber)
# - docx_processor.py (DOCX via python-docx)
# - csv_processor.py (CSV via pandas/csv)
# - json_processor.py (JSON structured data)
# - html_processor.py (HTML via BeautifulSoup)
```

**Required Dependencies** (add to `install/dependencies.toml`):

```toml
"PyPDF2>=3.0.0",          # PDF processing
"python-docx>=1.1.0",     # DOCX processing
"pandas>=2.0.0",          # CSV/Excel processing
"beautifulsoup4>=4.12.0", # HTML processing
"python-magic>=0.4.27",   # MIME type detection
"filetype>=1.2.0"         # File type identification
```

#### 1.3 Chunking Strategies

**Location**: `server/services/file_processing/chunking/`

Implement fixed-size and semantic chunking:

```python
# server/services/file_processing/chunking/base_chunker.py
class TextChunker(ABC):
    @abstractmethod
    def chunk_text(self, text: str, metadata: Dict) -> List[Chunk]

# server/services/file_processing/chunking/fixed_chunker.py
class FixedSizeChunker(TextChunker):
    """Fixed-size chunking with overlap"""
    def __init__(self, chunk_size: int = 1000, overlap: int = 200)

# server/services/file_processing/chunking/semantic_chunker.py
class SemanticChunker(TextChunker):
    """Sentence-boundary aware chunking using sentence-transformers"""
    # Uses existing sentence-transformers from torch profile
    # Splits on sentence boundaries, respects semantic units
```

**Chunk Model**:

```python
@dataclass
class Chunk:
    chunk_id: str           # Unique ID: {file_id}_{chunk_idx}
    file_id: str
    text: str
    chunk_index: int
    metadata: Dict[str, Any]  # file_name, page_number, section, etc.
    embedding: Optional[List[float]] = None
```

#### 1.4 File Metadata Store

**Location**: `server/services/file_metadata/`

Track uploaded files and their processing status:

```python
# server/services/file_metadata/metadata_store.py
class FileMetadataStore:
    """Tracks file uploads, processing status, and chunk references"""
    # Uses SQLite (orbit.db) with new tables:
    # - uploaded_files: file_id, api_key, filename, mime_type, size, 
    #                   upload_time, processing_status, storage_key
    # - file_chunks: chunk_id, file_id, chunk_index, vector_store_id, 
    #                collection_name, processing_time
```

**Schema** (add to `orbit.db`):

```sql
CREATE TABLE uploaded_files (
    file_id TEXT PRIMARY KEY,
    api_key TEXT NOT NULL,
    filename TEXT NOT NULL,
    mime_type TEXT,
    file_size INTEGER,
    upload_timestamp TEXT,
    processing_status TEXT,  -- 'pending', 'processing', 'completed', 'failed'
    storage_key TEXT,
    chunk_count INTEGER,
    vector_store TEXT,
    collection_name TEXT,
    metadata TEXT  -- JSON
);

CREATE TABLE file_chunks (
    chunk_id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    chunk_index INTEGER,
    vector_store_id TEXT,
    collection_name TEXT,
    chunk_metadata TEXT,  -- JSON
    created_at TEXT,
    FOREIGN KEY (file_id) REFERENCES uploaded_files(file_id)
);
```

### Phase 2: File Adapter Implementation

#### 2.1 Core File Adapter

**Location**: `server/adapters/file/adapter.py` (update existing)

Enhance existing FileAdapter with full processing pipeline:

```python
class FileAdapter(DocumentAdapter):
    def __init__(self, config: Dict[str, Any] = None, **kwargs):
        super().__init__(config=config, **kwargs)
        
        # Initialize services
        self.storage = self._init_storage_backend()
        self.metadata_store = FileMetadataStore()
        self.processor_registry = FileProcessorRegistry()
        self.chunker = self._init_chunker()
        self.vector_store = self._init_vector_store()
        
    async def upload_and_process_file(
        self, 
        file_data: bytes, 
        filename: str,
        api_key: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Main entry point for file processing"""
        # 1. Detect file type
        # 2. Store file
        # 3. Extract text and metadata
        # 4. Chunk content
        # 5. Generate embeddings
        # 6. Store chunks in vector store
        # 7. Update metadata store
        # 8. Return processing result
    
    # Implement DocumentAdapter interface methods:
    # - format_document()
    # - extract_direct_answer()
    # - apply_domain_specific_filtering()
```

#### 2.2 File Retriever

**Location**: `server/retrievers/implementations/file/`

Create file-aware retriever for Q&A:

```python
# server/retrievers/implementations/file/file_retriever.py
class FileRetriever(AbstractVectorRetriever):
    """Retriever for querying uploaded files"""
    
    async def get_relevant_context(self, query: str, **kwargs) -> List[Dict]:
        # 1. Generate query embedding
        # 2. Search vector store for relevant chunks
        # 3. Enrich results with file metadata
        # 4. Group by file if needed
        # 5. Apply file-specific filtering
        # 6. Return formatted context
```

#### 2.3 Configuration

**Location**: `config/adapters.yaml`

Add file adapter configuration:

```yaml
- name: "file-document-qa"
  enabled: true
  type: "retriever"
  datasource: "file"  # Special marker
  adapter: "file"
  implementation: "adapters.file.adapter.FileAdapter"
  
  # Provider overrides
  inference_provider: "ollama"
  embedding_provider: "ollama"
  
  config:
    # Storage configuration
    storage_backend: "filesystem"  # or "s3" in future
    storage_root: "./uploads"
    max_file_size: 52428800  # 50MB
    
    # Processing configuration
    chunking_strategy: "semantic"  # or "fixed"
    chunk_size: 1000
    chunk_overlap: 200
    
    # Vector store integration
    vector_store: "chroma"  # References stores.yaml
    collection_prefix: "files_"
    
    # Supported file types
    supported_types:
      - "application/pdf"
      - "text/plain"
      - "text/markdown"
      - "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
      - "text/csv"
      - "application/json"
      - "text/html"
    
    # Q&A settings
    confidence_threshold: 0.3
    max_results: 5
    return_results: 3
```

### Phase 3: API Endpoints

#### 3.1 File Upload & Management

**Location**: `server/routes/files.py` (new)

RESTful API for file operations:

```python
@router.post("/api/files/upload")
async def upload_file(
    file: UploadFile,
    api_key: str = Header(...),
    processing_options: Optional[Dict] = None
):
    """Upload and process a file"""

@router.get("/api/files/{file_id}")
async def get_file_info(file_id: str, api_key: str = Header(...)):
    """Get file metadata and processing status"""

@router.delete("/api/files/{file_id}")
async def delete_file(file_id: str, api_key: str = Header(...)):
    """Delete file and all associated chunks"""

@router.get("/api/files")
async def list_files(api_key: str = Header(...)):
    """List all files for an API key"""

@router.post("/api/files/{file_id}/query")
async def query_file(
    file_id: str,
    query: QueryRequest,
    api_key: str = Header(...)
):
    """Query a specific file"""
```

#### 3.2 Integration with Existing Chat Endpoint

**Location**: `server/routes/chat.py` (update)

Enable file-based queries through existing chat:

```python
# Add file context to chat requests
# Users can reference uploaded files in queries:
# "What does contract.pdf say about payment terms?"
# System resolves file references and queries appropriate collections
```

### Phase 4: Testing & Documentation

#### 4.1 Unit Tests

**Location**: `server/tests/test_file_adapter.py`

Comprehensive test coverage:

```python
# Test file processing pipeline
async def test_pdf_processing()
async def test_chunking_strategies()
async def test_vector_store_integration()

# Test storage backends
async def test_filesystem_storage()
async def test_metadata_store()

# Test retrieval
async def test_file_query()
async def test_multi_file_query()
```

#### 4.2 Integration Tests

**Location**: `server/tests/integration/test_file_workflow.py`

End-to-end workflows:

```python
async def test_upload_process_query_workflow()
async def test_multiple_file_types()
async def test_concurrent_uploads()
```

#### 4.3 Documentation

**Location**: `docs/file-adapter-guide.md` (new)

User-facing documentation:

- Upload file examples
- Supported formats
- Chunking strategies
- Query patterns
- Configuration options
- API reference

Update existing docs:

- `docs/adapter-configuration.md`: Add file adapter section
- `docs/README.md`: Add file adapter to feature list

## File Structure

```
server/
├── adapters/
│   └── file/
│       ├── __init__.py
│       └── adapter.py (enhanced)
├── services/
│   ├── file_storage/
│   │   ├── __init__.py
│   │   ├── base_storage.py
│   │   ├── filesystem_storage.py
│   │   └── s3_storage.py (future)
│   ├── file_processing/
│   │   ├── __init__.py
│   │   ├── base_processor.py
│   │   ├── text_processor.py
│   │   ├── pdf_processor.py
│   │   ├── docx_processor.py
│   │   ├── csv_processor.py
│   │   ├── json_processor.py
│   │   ├── html_processor.py
│   │   └── chunking/
│   │       ├── __init__.py
│   │       ├── base_chunker.py
│   │       ├── fixed_chunker.py
│   │       └── semantic_chunker.py
│   └── file_metadata/
│       ├── __init__.py
│       └── metadata_store.py
├── retrievers/
│   └── implementations/
│       └── file/
│           ├── __init__.py
│           └── file_retriever.py
├── routes/
│   └── files.py (new)
└── tests/
    ├── test_file_adapter.py
    ├── test_file_storage.py
    ├── test_file_processing.py
    └── integration/
        └── test_file_workflow.py

docs/
└── file-adapter-guide.md (new)

config/
└── adapters.yaml (update)

install/
└── dependencies.toml (update)
```

## Key Design Decisions

### 1. Why Hybrid Storage?

- **Immediate value**: Filesystem storage works out-of-box, no external dependencies
- **Production ready**: Clean abstraction enables S3/MinIO migration without code changes
- **Cost effective**: Local storage for development/testing, object storage for production
- **Flexibility**: Users choose based on scale and infrastructure

### 2. Why Vector Store Integration?

- **Leverage existing infrastructure**: No new storage system to maintain
- **Unified retrieval**: Files become first-class citizens in ORBIT's retrieval pipeline
- **Multi-modal queries**: Users can query files + databases + APIs in single request
- **Proven scalability**: Vector stores already handle millions of embeddings

### 3. Why Semantic Chunking?

- **Better retrieval**: Respects sentence/paragraph boundaries for coherent chunks
- **Existing dependencies**: sentence-transformers already in torch profile
- **Quality vs. Speed**: Fixed chunking as fallback for speed-critical scenarios
- **User choice**: Configuration allows switching based on use case

### 4. File Metadata Tracking

- **Audit trail**: Track all uploads, processing status, chunk references
- **Lifecycle management**: Enable file deletion with cascade to chunks
- **Multi-tenancy**: API key isolation built into storage and metadata
- **Debugging**: Processing status helps troubleshoot issues

## Migration Path to MinIO/S3 (Future - Phase 5+)

When ready for object storage:

1. **Implement S3Storage class**: Drop-in replacement for FilesystemStorage
2. **Update configuration**: Change `storage_backend: "s3"` in adapters.yaml
3. **Add connection params**: MinIO/S3 credentials in config
4. **Data migration script**: Copy existing files from filesystem to object storage
5. **Update metadata**: Point storage_key to new S3 locations

**Zero adapter code changes required** - abstraction layer handles everything.

## Success Metrics

- Upload and process 10+ file formats
- Sub-second chunking for typical documents (< 100 pages)
- Retrieval latency comparable to existing vector retrievers (< 500ms)
- Support 1000+ files per API key
- Comprehensive test coverage (>80%)
- Production-ready error handling and logging

## Next Steps After Implementation

- **Phase 5**: Add MinIO/S3 storage backend
- **Phase 6**: Support additional formats (Excel, PowerPoint, images with OCR)
- **Phase 7**: Advanced chunking (structure-aware, table-aware)
- **Phase 8**: Multi-document analysis and comparison
- **Phase 9**: Streaming processing for large files
- **Phase 10**: Document versioning and history