# File Adapter Architecture

The **File Adapter System** extends ORBIT's retrieval capabilities to provide **specialized handling of uploaded file content**. Built on top of the existing vector retriever architecture, it offers file-specific optimizations, metadata handling, and content formatting for various document types.

## Architecture Overview

```
BaseRetriever (abstract base for all retrievers)
└── AbstractVectorRetriever (database-agnostic vector functionality)
    └── ChromaRetriever (ChromaDB-specific implementation)
        └── QAChromaRetriever (QA domain specialization)
            └── FileChromaRetriever (File-specific specialization)
                ├── ChromaFileAdapter (File content formatting & filtering)
                ├── FileService (Upload processing & storage)
                └── File Routes (API endpoints)
```

## Key Components

### ✅ Core File System Components

| Component | Purpose | Location | Features |
|-----------|---------|----------|----------|
| **FileChromaRetriever** | File-specialized retriever | `implementations/file/` | File-specific thresholds, boost algorithms |
| **ChromaFileAdapter** | File content adapter | `adapters/file/` | CSV parsing, metadata handling, content formatting |
| **FileService** | Upload processing | `services/` | Multi-format support, chunking, vector storage |
| **File Routes** | API endpoints | `routes/` | Upload, info, delete, batch operations |

### 🎯 Supported File Types

| File Type | Extensions | Processing | Special Features |
|-----------|------------|------------|------------------|
| **CSV** | `.csv` | Header detection, row parsing | Structured data boost, column analysis |
| **Excel** | `.xlsx`, `.xls` | Sheet extraction | Multi-sheet support, formula handling |
| **PDF** | `.pdf` | Text extraction via `pypdf` | Page-aware chunking, metadata preservation |
| **Word** | `.docx`, `.doc` | Content extraction via `docx2python` | Style preservation, section detection |
| **Text** | `.txt`, `.md` | Direct processing | Markdown formatting support |
| **JSON** | `.json` | Structure-aware parsing | Nested object handling |

## File Adapter Architecture Details

### FileChromaRetriever

```python
class FileChromaRetriever(QAChromaRetriever):
    """
    File-specialized ChromaDB retriever that extends QAChromaRetriever.
    Provides file-specific confidence thresholds and enhancement algorithms.
    """
    
    # File-specific configuration
    confidence_threshold: float = 0.2        # Lower threshold for file content
    distance_scaling_factor: float = 150.0   # Optimized for file similarities
    include_file_metadata: bool = True        # Add file context
    boost_file_uploads: bool = True          # Boost uploaded content
    file_content_weight: float = 1.5         # Weight factor for files
    metadata_weight: float = 0.8             # Metadata importance
```

**Key Features:**
- **Lower Confidence Threshold**: File content often has lower embedding similarity but high relevance
- **Enhanced Metadata Integration**: Includes filename, upload time, file type in responses
- **File-Specific Boosting**: Prioritizes recently uploaded files and exact matches
- **Content Type Recognition**: Different handling for structured vs. unstructured data

### ChromaFileAdapter

```python
class ChromaFileAdapter(DocumentAdapter):
    """
    Adapter for uploaded file content, optimized for CSV and structured data.
    Handles content formatting and file-specific ranking.
    """
    
    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        # CSV-specific formatting with column detection
        # PDF context with page information  
        # File metadata integration
        
    def extract_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        # High-confidence file content summaries
        # Structured data previews
        # File-specific direct responses
        
    def apply_domain_specific_filtering(self, context_items, query):
        # File content term matching
        # Filename relevance boosting
        # Upload recency scoring
```

**Special Capabilities:**
- **CSV Intelligence**: Automatically detects headers, provides row/column counts
- **Structured Data Handling**: Special formatting for spreadsheets and databases
- **File Context**: Adds source file information to all responses
- **Content Type Classification**: Different processing for different file types

## Configuration Examples

### Basic File Adapter Setup

```yaml
# config.yaml
adapters:
  - name: "file-vector"
    type: "retriever"
    datasource: "chroma"
    adapter: "file"
    implementation: "retrievers.implementations.file.FileChromaRetriever"
    config:
      confidence_threshold: 0.2              # Lower for file content
      distance_scaling_factor: 150.0         # Optimized scaling
      max_results: 10
      return_results: 5
      # File-specific settings
      include_file_metadata: true             # Add file context
      boost_file_uploads: true               # Prioritize uploads
      file_content_weight: 1.5               # Boost factor
      metadata_weight: 0.8                   # Metadata importance

file_upload:
  enabled: true
  max_size_mb: 10
  max_files_per_batch: 10
  allowed_extensions:
    - ".txt"
    - ".pdf" 
    - ".docx"
    - ".xlsx"
    - ".csv"
    - ".md"
    - ".json"
  upload_directory: "uploads"
  save_to_disk: true
  auto_store_in_vector_db: true
  chunk_size: 1000
  chunk_overlap: 200
  require_api_key: true
```

### Advanced File Processing Configuration

```yaml
file_upload:
  # Security and Stability Controls
  security:
    rate_limiting:
      enabled: true
      max_uploads_per_minute: 10
      max_uploads_per_hour: 100
      block_duration_minutes: 15
    
    virus_scanning:
      enabled: false                        # Optional ClamAV integration
      
    content_validation:
      enabled: true
      max_empty_files: 0
      min_file_size_bytes: 10
      
  # Processing Controls  
  processing:
    timeout_seconds: 120                    # Upload processing timeout
    max_memory_mb: 500                      # Memory limit per upload
    parallel_processing: true               # Process multiple files concurrently
    
    # File type specific settings
    pdf:
      extract_images: false                 # Skip image extraction
      preserve_layout: true                 # Maintain document structure
      
    excel:
      include_formulas: false               # Extract formula results only
      sheet_limit: 10                       # Max sheets to process
      
    csv:
      delimiter_detection: true             # Auto-detect CSV format
      encoding_detection: true              # Auto-detect encoding
      sample_rows: 5                        # Rows for preview generation
```

## Usage Examples

### File Upload and Query

```python
# Upload a CSV file
upload_response = requests.post(
    "http://localhost:3000/files/upload",
    headers={
        "X-API-Key": "orbit_your_api_key",
        "X-Session-ID": "upload-session"
    },
    files={"file": open("employees.csv", "rb")},
    data={"metadata": json.dumps({
        "description": "Employee database",
        "category": "HR"
    })}
)

# Query the uploaded data using file adapter
query_response = requests.post(
    "http://localhost:3000/v1/chat",
    headers={
        "X-API-Key": "orbit_your_api_key", 
        "X-Session-ID": "query-session",
        "Content-Type": "application/json"
    },
    json={
        "jsonrpc": "2.0",
        "method": "tools/call", 
        "params": {
            "name": "chat",
            "arguments": {
                "messages": [{"role": "user", "content": "Who are the software engineers?"}],
                "adapter": "file-vector"  # Use file adapter
            }
        },
        "id": "file-query"
    }
)
```

### Programmatic File Adapter Usage

```python
from retrievers.implementations.file.file_chroma_retriever import FileChromaRetriever

# Configuration for file retriever
config = {
    "adapters": [{
        "name": "file-vector",
        "type": "retriever", 
        "datasource": "chroma",
        "adapter": "file",
        "config": {
            "confidence_threshold": 0.2,
            "include_file_metadata": True,
            "boost_file_uploads": True
        }
    }],
    "datasources": {
        "chroma": {
            "use_local": True,
            "db_path": "sample_db/chroma/chroma_db"
        }
    }
}

# Initialize file retriever
retriever = FileChromaRetriever(config=config)
await retriever.initialize()
await retriever.set_collection("uploaded_files")

# Query uploaded file content
results = await retriever.get_relevant_context(
    "What is John Doe's position?",
    api_key="orbit_your_api_key"
)

# Results include file metadata and enhanced context
for result in results:
    print(f"Source: {result.get('file_info', {}).get('filename', 'Unknown')}")
    print(f"Content: {result['content']}")
    print(f"Confidence: {result['confidence']}")
```

## Extending to Other Use Cases

### Creating Domain-Specific File Adapters

#### 1. Legal Document Adapter

```python
from retrievers.adapters.file.chroma_file_adapter import ChromaFileAdapter

class LegalFileAdapter(ChromaFileAdapter):
    """Specialized adapter for legal documents"""
    
    def __init__(self, config: Dict[str, Any] = None, **kwargs):
        super().__init__(config=config, **kwargs)
        self.legal_terms = ["contract", "agreement", "clause", "provision"]
        self.citation_patterns = [r"\d+\s+[A-Z]\.\w+\.\s+\d+", r"§\s*\d+"]
    
    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        item = super().format_document(raw_doc, metadata)
        
        # Legal document enhancements
        if metadata.get('mime_type') == 'application/pdf':
            # Extract legal citations
            citations = self._extract_citations(raw_doc)
            item['legal_citations'] = citations
            
            # Identify document type
            doc_type = self._classify_legal_document(raw_doc)
            item['legal_document_type'] = doc_type
            
            # Enhanced content with legal context
            item['content'] = f"Legal Document: {doc_type}\nCitations: {citations}\n\nContent:\n{raw_doc}"
        
        return item
    
    def apply_domain_specific_filtering(self, context_items, query):
        enhanced_items = super().apply_domain_specific_filtering(context_items, query)
        
        # Legal-specific boosting
        for item in enhanced_items:
            # Boost items containing legal terms
            content_lower = item.get('content', '').lower()
            legal_term_matches = sum(1 for term in self.legal_terms if term in content_lower)
            if legal_term_matches > 0:
                item['confidence'] *= (1.0 + legal_term_matches * 0.15)
                item['legal_relevance'] = f"{legal_term_matches} legal terms matched"
        
        return enhanced_items
    
    def _extract_citations(self, text: str) -> List[str]:
        """Extract legal citations from text"""
        import re
        citations = []
        for pattern in self.citation_patterns:
            citations.extend(re.findall(pattern, text))
        return citations
    
    def _classify_legal_document(self, text: str) -> str:
        """Classify type of legal document"""
        text_lower = text.lower()
        if "employment agreement" in text_lower:
            return "Employment Contract"
        elif "lease" in text_lower:
            return "Lease Agreement"
        elif "confidentiality" in text_lower or "nda" in text_lower:
            return "Non-Disclosure Agreement"
        else:
            return "Legal Document"
```

#### 2. Medical Records Adapter

```python
class MedicalFileAdapter(ChromaFileAdapter):
    """Specialized adapter for medical records"""
    
    def __init__(self, config: Dict[str, Any] = None, **kwargs):
        super().__init__(config=config, **kwargs)
        self.medical_terms = ["diagnosis", "treatment", "medication", "symptom"]
        self.sensitive_fields = ["patient_id", "ssn", "dob"]
    
    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        item = super().format_document(raw_doc, metadata)
        
        # Medical record enhancements
        if self._is_medical_record(metadata):
            # Extract medical entities
            entities = self._extract_medical_entities(raw_doc)
            item['medical_entities'] = entities
            
            # Privacy protection
            sanitized_content = self._sanitize_sensitive_data(raw_doc)
            item['content'] = sanitized_content
            
            # Medical classification
            record_type = self._classify_medical_record(raw_doc)
            item['medical_record_type'] = record_type
        
        return item
    
    def _sanitize_sensitive_data(self, text: str) -> str:
        """Remove or mask sensitive medical information"""
        import re
        # Mask patient IDs, SSNs, etc.
        text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[REDACTED-SSN]', text)
        text = re.sub(r'\bPT\d+\b', '[PATIENT-ID]', text)
        return text
```

#### 3. Financial Documents Adapter

```python
class FinancialFileAdapter(ChromaFileAdapter):
    """Specialized adapter for financial documents"""
    
    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        item = super().format_document(raw_doc, metadata)
        
        # Financial document processing
        if self._is_financial_document(metadata):
            # Extract financial figures
            amounts = self._extract_financial_amounts(raw_doc)
            item['financial_amounts'] = amounts
            
            # Detect financial document type
            doc_type = self._classify_financial_document(raw_doc)
            item['financial_document_type'] = doc_type
            
            # Enhanced content with financial context
            item['content'] = f"Financial Document: {doc_type}\nKey Amounts: {amounts}\n\nContent:\n{raw_doc}"
        
        return item
    
    def _extract_financial_amounts(self, text: str) -> List[str]:
        """Extract monetary amounts from text"""
        import re
        # Match currency amounts
        pattern = r'\$[\d,]+\.?\d*|\b\d+\.\d{2}\b'
        return re.findall(pattern, text)
```

### Creating Multi-Database File Adapters

#### File Adapter for Pinecone

```python
from retrievers.implementations.file.file_chroma_retriever import FileChromaRetriever
from retrievers.implementations.pinecone_retriever import PineconeRetriever

class FilePineconeRetriever(PineconeRetriever):
    """File-specialized Pinecone retriever"""
    
    def __init__(self, config: Dict[str, Any], **kwargs):
        # Get file-specific adapter config
        adapter_config = self._get_file_adapter_config(config)
        
        # Initialize with Pinecone-specific settings
        super().__init__(config=config, **kwargs)
        
        # File-specific overrides
        if adapter_config:
            self.confidence_threshold = adapter_config.get('confidence_threshold', 0.2)
            self.include_file_metadata = adapter_config.get('include_file_metadata', True)
            self.boost_file_uploads = adapter_config.get('boost_file_uploads', True)
    
    async def initialize(self) -> None:
        """Initialize with file domain adapter"""
        await super().initialize()
        
        # Create file adapter for Pinecone
        from retrievers.adapters.registry import ADAPTER_REGISTRY
        self.domain_adapter = ADAPTER_REGISTRY.create(
            adapter_type='retriever',
            datasource='pinecone',
            adapter_name='file',
            config=self.config
        )
```

#### Configuration for Multi-Database File Support

```yaml
adapters:
  # ChromaDB file adapter
  - name: "file-chroma"
    type: "retriever"
    datasource: "chroma"
    adapter: "file"
    implementation: "retrievers.implementations.file.FileChromaRetriever"
    config:
      confidence_threshold: 0.2
      
  # Pinecone file adapter  
  - name: "file-pinecone"
    type: "retriever"
    datasource: "pinecone"
    adapter: "file"
    implementation: "retrievers.implementations.file.FilePineconeRetriever"
    config:
      confidence_threshold: 0.3
      
  # Milvus file adapter
  - name: "file-milvus"
    type: "retriever"
    datasource: "milvus"  
    adapter: "file"
    implementation: "retrievers.implementations.file.FileMilvusRetriever"
    config:
      confidence_threshold: 0.25
```

## File Processing Pipeline

### Upload → Storage → Retrieval Flow

```
1. File Upload (via API)
   ├── File validation (size, type, content)
   ├── Virus scanning (optional)
   └── Rate limiting check

2. Content Processing
   ├── Text extraction (PDF, Word, Excel)
   ├── Encoding detection
   ├── Content chunking
   └── Metadata extraction

3. Vector Storage
   ├── Embedding generation
   ├── Vector database storage
   ├── Metadata indexing
   └── File reference tracking

4. Query Processing  
   ├── File adapter selection
   ├── Vector similarity search
   ├── File-specific ranking
   └── Response formatting
```

### Content Processing Details

```python
# FileService processing pipeline
class FileService:
    async def process_file(self, file_data: bytes, filename: str) -> Dict[str, Any]:
        """Complete file processing pipeline"""
        
        # 1. Content extraction
        content = await self._extract_content(file_data, filename)
        
        # 2. Chunking for vector storage
        chunks = self._chunk_content(content)
        
        # 3. Metadata generation
        metadata = self._generate_metadata(filename, file_data, content)
        
        # 4. Vector storage
        if self.auto_store_in_vector_db:
            storage_result = await self._store_in_vector_db(content, metadata)
        
        # 5. File tracking
        file_record = await self._save_file_record(filename, metadata)
        
        return {
            "file_id": file_record["file_id"],
            "chunks_stored": len(chunks),
            "metadata": metadata,
            "storage_result": storage_result
        }
```

## API Endpoints

### File Upload Endpoints

```python
# File upload routes
POST /files/upload              # Single file upload
POST /files/upload/batch        # Multiple file upload  
GET  /files/info/{file_id}      # File information
DELETE /files/{file_id}         # Delete file
GET  /files/status              # Service status

# Query endpoints with file adapter
POST /v1/chat                   # Chat with adapter parameter
```

### Example API Calls

```bash
# Upload a CSV file
curl -X POST "http://localhost:3000/files/upload" \
  -H "X-API-Key: orbit_your_key" \
  -H "X-Session-ID: upload-session" \
  -F "file=@employees.csv" \
  -F "metadata={\"category\": \"HR\"}"

# Query using file adapter
curl -X POST "http://localhost:3000/v1/chat" \
  -H "X-API-Key: orbit_your_key" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "chat", 
      "arguments": {
        "messages": [{"role": "user", "content": "Show me all engineers"}],
        "adapter": "file-vector"
      }
    },
    "id": "file-query"
  }'
```

## Testing and Validation

### Test Suite Example

```bash
#!/bin/bash
# File adapter test suite

# Test 1: Upload CSV file
echo "Testing CSV upload..."
curl -X POST "$SERVER_URL/files/upload" \
  -H "X-API-Key: $API_KEY" \
  -F "file=@test_employees.csv"

# Test 2: Query specific employee
echo "Testing employee lookup..."
curl -X POST "$SERVER_URL/v1/chat" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "chat", "arguments": {"messages": [{"role": "user", "content": "Who is John Doe?"}], "adapter": "file-vector"}}, "id": "test"}'

# Test 3: Department search
echo "Testing department search..."
curl -X POST "$SERVER_URL/v1/chat" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "chat", "arguments": {"messages": [{"role": "user", "content": "Show me all engineers"}], "adapter": "file-vector"}}, "id": "test"}'
```

## Performance Considerations

### File Processing Optimization

| Aspect | Recommendation | Implementation |
|--------|---------------|----------------|
| **Memory Usage** | Streaming processing | Process files in chunks |
| **Upload Speed** | Parallel processing | Handle multiple files concurrently |
| **Storage Efficiency** | Deduplication | Check file hashes before storing |
| **Query Performance** | Optimized embeddings | Use file-specific embedding strategies |

### Scaling Considerations

```yaml
# Production file upload configuration
file_upload:
  processing:
    max_concurrent_uploads: 5         # Limit concurrent processing
    worker_pool_size: 10              # Background processing workers
    chunk_batch_size: 50              # Vector storage batch size
    memory_limit_mb: 1000             # Per-upload memory limit
    
  storage:
    vector_batch_size: 100            # Batch vector operations
    cleanup_interval_hours: 24        # Clean up temporary files
    max_storage_size_gb: 100          # Total storage limit
```

## Security Considerations

### File Upload Security

```yaml
file_upload:
  security:
    # File validation
    allowed_extensions: [".pdf", ".docx", ".csv", ".txt"]
    max_size_mb: 10
    scan_for_malware: true
    
    # Content validation  
    validate_file_content: true
    reject_suspicious_files: true
    
    # Access control
    require_api_key: true
    rate_limiting: true
    audit_uploads: true
    
    # Data protection
    encrypt_at_rest: true
    sanitize_sensitive_data: true
    retention_policy_days: 90
```

## Integration with Existing Systems

### With Document Management Systems

```python
from retrievers.implementations.file.file_chroma_retriever import FileChromaRetriever

class DocumentManagementFileAdapter(FileChromaRetriever):
    """Integration with document management systems"""
    
    def __init__(self, config, dm_client=None):
        super().__init__(config)
        self.dm_client = dm_client  # Document management client
    
    async def sync_documents(self):
        """Sync with external document management system"""
        documents = await self.dm_client.get_recent_documents()
        for doc in documents:
            # Download and process document
            content = await self.dm_client.download(doc.id)
            await self.process_external_document(content, doc.metadata)
```

### With Data Lakes and Warehouses

```python
class DataLakeFileAdapter(FileChromaRetriever):
    """Integration with data lakes"""
    
    async def sync_from_s3(self, bucket: str, prefix: str):
        """Sync files from S3 data lake"""
        import boto3
        
        s3 = boto3.client('s3')
        objects = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        
        for obj in objects.get('Contents', []):
            if self._is_supported_file(obj['Key']):
                # Download and process
                content = s3.get_object(Bucket=bucket, Key=obj['Key'])
                await self.process_s3_object(content, obj)
```

## Migration and Deployment

### Migrating from Basic to File Adapter

```python
# Migration script
async def migrate_to_file_adapter():
    """Migrate existing documents to file adapter format"""
    
    # 1. Initialize file retriever
    file_retriever = FileChromaRetriever(config)
    await file_retriever.initialize()
    
    # 2. Migrate existing documents
    existing_docs = await get_existing_documents()
    for doc in existing_docs:
        # Add file metadata
        enhanced_metadata = add_file_metadata(doc.metadata)
        
        # Re-index with file adapter
        await file_retriever.store_document(doc.content, enhanced_metadata)
    
    # 3. Update configuration
    update_adapter_config("file-vector")
```

## Design Principles

**📁 File-First Design**: Optimized specifically for uploaded file content
**🔧 Extensible Architecture**: Easy to add new file types and processing logic  
**🛡️ Security by Default**: Built-in protections for file uploads and processing
**⚡ Performance Optimized**: Efficient processing and storage of file content
**🔄 Standards Compliant**: Works with existing ORBIT retriever patterns

## Future Extensions

### Planned Enhancements

1. **Advanced File Types**: PowerPoint, images with OCR, audio transcription
2. **Multi-Modal Support**: Image + text processing, document layout analysis  
3. **Real-Time Sync**: Watch folders, webhook integration
4. **Advanced Analytics**: File usage statistics, content insights
5. **Collaboration Features**: Shared files, team collections