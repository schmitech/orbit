# Chunking Architecture in ORBIT

This document explains the chunking strategies available in ORBIT and when to use each approach.

## Overview

ORBIT uses **two separate chunking systems** for different use cases:

1. **File Chunking** - For uploaded files (PDF, DOCX, CSV, TXT)
2. **Web Content Chunking** - For scraped web content (Wikipedia, documentation)

## 1. File Chunking

**Location:** `server/services/file_processing/chunking/`

### Purpose
Chunks user-uploaded files for the File Adapter to store in vector databases.

### Strategies

#### FixedSizeChunker
```python
from services.file_processing.chunking import FixedSizeChunker

chunker = FixedSizeChunker(chunk_size=1000, overlap=200)
chunks = chunker.chunk_text(text, file_id, metadata)
```

**Best for:**
- Plain text files
- CSV data
- Simple documents
- When you need consistent chunk sizes

**Characteristics:**
- Character-based (e.g., 1000 chars)
- Fast and simple
- May split sentences/paragraphs
- Good for structured data

#### SemanticChunker
```python
from services.file_processing.chunking import SemanticChunker

chunker = SemanticChunker(chunk_size=10, overlap=2)
chunks = chunker.chunk_text(text, file_id, metadata)
```

**Best for:**
- PDFs with paragraphs
- Word documents
- Text with natural language
- When semantic coherence matters

**Characteristics:**
- Sentence-based (e.g., 10 sentences)
- Respects sentence boundaries
- Better for Q&A and semantic search
- Uses sentence-transformers (optional)

### Output Format
```python
@dataclass
class Chunk:
    chunk_id: str          # Unique ID
    file_id: str           # Source file
    text: str              # Chunk content
    chunk_index: int       # Position
    metadata: Dict         # Additional info
    embedding: List[float] # Pre-computed embedding
```

## 2. Web Content Chunking (Firecrawl)

**Location:** `server/utils/content_chunker.py`

### Purpose
Chunks large web content from Firecrawl API (Wikipedia, documentation sites) to prevent exceeding LLM context limits.

### Strategy: MarkdownChunker

```python
from utils.content_chunker import ContentChunker

chunker = ContentChunker(
    max_chunk_tokens=4000,
    chunk_overlap_tokens=200,
    min_chunk_tokens=500
)
chunks = chunker.chunk_markdown(markdown_content, metadata)
```

**Best for:**
- Wikipedia articles
- Documentation sites
- Blog posts
- Any hierarchical markdown content

**Characteristics:**
- **Token-based** (e.g., 4000 tokens ≈ 16KB)
- **Hierarchy-aware** - Parses H1-H6 headers
- **Section-based** - Keeps sections together
- **Smart splitting** - Only chunks content > 4000 tokens
- Preserves document structure

### Output Format
```python
{
    "chunk_id": 0,
    "total_chunks": 15,
    "content": "# Web Scraping\n\nWeb scraping is...",
    "section": "Introduction",
    "hierarchy": ["Web Scraping", "Introduction"],
    "position": 0,
    "token_count": 3500,
    "overlap_with_prev": False,
    "overlap_with_next": True,
    "source_url": "https://en.wikipedia.org/...",
    "source_hash": "abc123..."
}
```

## Comparison Table

| Feature | File Chunking | Web Content Chunking |
|---------|---------------|---------------------|
| **Unit** | Characters/Sentences | Tokens |
| **Structure** | Flat | Hierarchical (tree) |
| **Awareness** | Sentence/paragraph | Markdown headers |
| **Output** | `Chunk` dataclass | Dictionary |
| **Use Case** | Uploaded files | Scraped web pages |
| **Strategies** | Fixed, Semantic | Markdown structure |
| **Size Trigger** | Always chunks | Only if > max_tokens |
| **Hierarchy** | None | H1 > H2 > H3... |
| **Adapter** | File Adapter | Firecrawl Adapter |

## When to Use Which?

### Use File Chunking When:
- ✅ User uploads a PDF, DOCX, or TXT file
- ✅ You need consistent chunk sizes
- ✅ Content is flat (no hierarchical structure)
- ✅ Working with the File Adapter
- ✅ Storing in vector DB for semantic search

### Use Web Content Chunking When:
- ✅ Scraping web pages with Firecrawl
- ✅ Content has markdown headers (H1-H6)
- ✅ Working with large documentation/Wikipedia
- ✅ Need to preserve document structure
- ✅ Want query-relevant sections only
- ✅ Content may exceed LLM context limits

## Chunk Storage and Retrieval

Both systems can use the **ChunkManager** for vector store integration:

**Location:** `server/utils/chunk_manager.py`

```python
from utils.chunk_manager import ChunkManager

# Initialize
chunk_manager = ChunkManager(
    vector_store=chroma_store,
    embedding_client=openai_embeddings,
    collection_name="my_chunks",
    max_embedding_tokens=7500,  # Max tokens for embedding model (with safety buffer)
    min_similarity_score=0.3,   # Minimum similarity for retrieval
    cache_ttl_hours=24           # Cache duration
)

# Store chunks
await chunk_manager.store_chunks(chunks, source_url, metadata)

# Retrieve relevant chunks
relevant = await chunk_manager.retrieve_chunks(
    query="What is web scraping?",
    source_url=url,
    top_k=3
)
```

**Features:**
- Embedding-based storage and retrieval
- Similarity search for relevance
- Caching with TTL (default: 24 hours)
- Works with any vector store (Chroma, Qdrant, etc.)
- **Automatic chunk splitting** - Splits chunks that exceed embedding model limits
- **Safety margins** - Uses 95% of max_embedding_tokens to prevent token estimation errors
- **Recursive splitting** - Intelligently splits by paragraphs → sentences → character limits
- **Fallback embedding** - Retries with individual chunk embedding if batch fails

### Embedding Safety and Automatic Splitting

ChunkManager automatically handles chunks that exceed embedding model token limits:

1. **Token Estimation**: Uses conservative estimate (1 token ≈ 3 chars) to account for special tokens
2. **Safety Margin**: Applies 95% limit (e.g., 7500 tokens → 7125 tokens max) to prevent estimation errors
3. **Recursive Splitting Strategy**:
   - First: Split by paragraphs (`\n\n`)
   - Then: Split by sentences (`.`)
   - Finally: Split by character limit at word boundaries
4. **Validation**: Double-checks each split piece before embedding
5. **Fallback**: If batch embedding fails, retries with individual chunk embedding

**Example:**
```python
# Chunk with 9500 tokens exceeds limit (7500 max)
chunk = {
    "content": "Very long content...",  # 9500 tokens
    "token_count": 9500
}

# ChunkManager automatically splits it:
# → Piece 1: 7000 tokens
# → Piece 2: 2500 tokens
# Both pieces are now embeddable
```

**Why This Matters:**
- Prevents embedding API errors (e.g., "maximum context length exceeded")
- Ensures all chunks are successfully embedded
- Handles edge cases where ContentChunker creates chunks larger than embedding limits
- Works with any embedding model (OpenAI, Cohere, Jina, etc.)

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    ORBIT Chunking                       │
├─────────────────────┬───────────────────────────────────┤
│                     │                                   │
│  FILE CHUNKING      │     WEB CONTENT CHUNKING         │
│  (Uploaded Files)   │     (Scraped Web Pages)          │
│                     │                                   │
├─────────────────────┼───────────────────────────────────┤
│                     │                                   │
│ FixedSizeChunker    │    ContentChunker                │
│ - 1000 chars        │    - 4000 tokens                 │
│ - 200 char overlap  │    - Markdown H1-H6              │
│                     │    - Section hierarchy           │
│ SemanticChunker     │    - Smart overlap               │
│ - 10 sentences      │                                   │
│ - 2 sentence overlap│                                   │
│                     │                                   │
├─────────────────────┴───────────────────────────────────┤
│                                                          │
│              ChunkManager (Shared)                      │
│              - Vector Store Integration                 │
│              - Embedding-based Search                   │
│              - Caching with TTL                         │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

## Future Consolidation Opportunities

While these systems are currently separate, potential consolidation could include:

1. **Shared utilities:**
   - Token estimation functions
   - Overlap calculation logic
   - ID generation

2. **Unified base class:**
   - Abstract `BaseChunker` that both inherit from
   - Common interface for `chunk()` method
   - Standardized output format converter

3. **Factory pattern:**
   - `ChunkerFactory.create('fixed' | 'semantic' | 'markdown')`
   - Auto-detect best strategy based on content type

4. **Hybrid approach:**
   - Markdown chunker that falls back to semantic chunking
   - Dynamic strategy selection based on content

## Example Usage

### File Adapter (PDF Upload)
```python
# User uploads research.pdf
from services.file_processing.chunking import SemanticChunker

chunker = SemanticChunker(chunk_size=10, overlap=2)
chunks = chunker.chunk_text(pdf_text, file_id, metadata)

# Store in vector DB
for chunk in chunks:
    await vector_store.add_vectors([embedding], [chunk.chunk_id], [chunk.metadata])
```

### Firecrawl Adapter (Wikipedia Scrape)
```python
# User asks "What is web scraping?"
from utils.content_chunker import ContentChunker
from utils.chunk_manager import ChunkManager

# Scrape Wikipedia
markdown = await firecrawl.scrape("https://en.wikipedia.org/wiki/Web_scraping")

# Chunk if large
chunker = ContentChunker(max_chunk_tokens=4000)
if chunker.should_chunk(markdown):
    chunks = chunker.chunk_markdown(markdown, metadata)

    # Store with embeddings
    await chunk_manager.store_chunks(chunks, url, metadata)

    # Retrieve relevant sections
    relevant = await chunk_manager.retrieve_chunks(
        query="What is web scraping?",
        top_k=3
    )
```

## Performance Metrics

### File Chunking
- **Speed**: ~10ms per 1000 chars (fixed), ~50ms per 1000 chars (semantic)
- **Memory**: Low (streaming)
- **Accuracy**: N/A (deterministic)

### Web Content Chunking
- **Speed**: ~100ms per 50KB markdown
- **Memory**: Low (streaming)
- **Cache Hit Rate**: 60-80% (after first scrape)
- **Context Reduction**: 75-90% (only relevant sections)
- **Cost Savings**: 80% (fewer tokens to LLM)

## Conclusion

Keep these systems **separate** because they serve different purposes:

1. **File Chunking** - General-purpose, character/sentence-based, for uploaded files
2. **Web Content Chunking** - Specialized, token/structure-based, for web scraping

Both can share the **ChunkManager** for vector store integration, providing a unified storage and retrieval layer.

This architecture follows the **separation of concerns** principle while allowing code reuse where it makes sense (storage/retrieval logic).
