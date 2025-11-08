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

ORBIT now supports **four chunking strategies**, each optimized for different use cases:

#### FixedSizeChunker (Default: Character-based)
```python
from services.file_processing.chunking import FixedSizeChunker

# Character-based (default)
chunker = FixedSizeChunker(chunk_size=1000, overlap=200)
chunks = chunker.chunk_text(text, file_id, metadata)

# Token-based (optional)
chunker = FixedSizeChunker(chunk_size=2048, overlap=200, use_tokens=True, tokenizer="gpt2")
chunks = chunker.chunk_text(text, file_id, metadata)
```

**Best for:**
- Plain text files
- CSV data
- Simple documents
- When you need consistent chunk sizes
- Fast processing requirements

**Characteristics:**
- Character-based (default) or token-based (optional)
- Fast and simple
- May split sentences/paragraphs
- Good for structured data
- Token-based mode provides better LLM context window accuracy

#### SemanticChunker
```python
from services.file_processing.chunking import SemanticChunker

# Simple mode (default)
chunker = SemanticChunker(chunk_size=10, overlap=2)
chunks = chunker.chunk_text(text, file_id, metadata)

# Advanced mode (optional, requires sentence-transformers)
chunker = SemanticChunker(
    chunk_size=10,
    overlap=2,
    use_advanced=True,
    model_name="all-MiniLM-L6-v2",
    threshold=0.8,
    similarity_window=3,
    min_sentences_per_chunk=1,
    min_characters_per_sentence=24,
    skip_window=0,  # 0=disabled, >0=enabled for skip-and-merge
    chunk_size_tokens=None  # Optional token limit
)
chunks = chunker.chunk_text(text, file_id, metadata)
```

**Best for:**
- PDFs with paragraphs
- Word documents
- Text with natural language
- When semantic coherence matters
- Q&A applications

**Characteristics:**
- Sentence-based (e.g., 10 sentences)
- Respects sentence boundaries
- Improved sentence splitting (Cython-optimized if available)
- Advanced mode: Savitzky-Golay filtering, window-based similarity, skip-and-merge
- Better for Q&A and semantic search
- Uses sentence-transformers (optional, for advanced mode)

**Advanced Parameters:**
- `threshold`: Similarity threshold (0-1) for semantic boundary detection
- `similarity_window`: Number of sentences to consider for similarity calculation
- `min_sentences_per_chunk`: Minimum sentences per chunk
- `min_characters_per_sentence`: Minimum characters per sentence (prevents fragmentation)
- `skip_window`: Number of groups to skip when merging (0=disabled)
- `filter_window`: Window length for Savitzky-Golay filter (requires scipy)
- `filter_polyorder`: Polynomial order for Savitzky-Golay filter
- `filter_tolerance`: Tolerance for Savitzky-Golay filter
- `chunk_size_tokens`: Optional token-based size limit

#### TokenChunker
```python
from services.file_processing.chunking import TokenChunker

chunker = TokenChunker(chunk_size=2048, overlap=200, tokenizer="gpt2")
chunks = chunker.chunk_text(text, file_id, metadata)
```

**Best for:**
- All text file types
- When accurate token counts are critical
- LLM context window management
- When you need token-based chunking without structure awareness

**Characteristics:**
- Token-based chunking (not character-based)
- More accurate for LLM context windows than character-based
- Supports various tokenizers (gpt2, tiktoken, character fallback)
- Fast and simple
- May split sentences/paragraphs

#### RecursiveChunker (Recommended Default)
```python
from services.file_processing.chunking import RecursiveChunker

# Default: paragraphs → sentences → words
chunker = RecursiveChunker(chunk_size=2048, min_characters_per_chunk=24)
chunks = chunker.chunk_text(text, file_id, metadata)

# Custom rules
from services.file_processing.chunking import RecursiveRules, RecursiveLevel

custom_rules = RecursiveRules([
    RecursiveLevel(delimiters=["\n\n"], include_delim="prev"),  # Paragraphs
    RecursiveLevel(delimiters=[". "], include_delim="prev"),     # Sentences
    RecursiveLevel(whitespace=True),                             # Words
])
chunker = RecursiveChunker(chunk_size=2048, rules=custom_rules)
chunks = chunker.chunk_text(text, file_id, metadata)
```

**Best for:**
- **All file types** (PDF, DOCX, CSV, TXT, HTML, JSON, images, audio)
- Complex document structures
- Mixed content (structured + unstructured)
- When you need structure-aware chunking
- Default choice for first-time installations

**Characteristics:**
- Hierarchical splitting: paragraphs → sentences → words
- Respects document structure
- Token-aware (uses tokenizer if available)
- Handles structured data (CSV, JSON) via whitespace/character splitting
- Works well for natural language documents
- No required dependencies (character tokenizer fallback)
- Balanced complexity: more sophisticated than fixed, simpler than advanced semantic

### Dependencies and Fallback Behavior

All chunkers work **without any dependencies** thanks to graceful fallback:

**Optional Dependencies:**
- **chonkie** - Provides Cython-optimized sentence splitting (10-50x faster)
  - **Fallback:** Pure Python sentence splitting
  - **Install:** `pip install chonkie`
- **sentence-transformers** - Required for `SemanticChunker` advanced mode
  - **Fallback:** Simple mode (no similarity calculations)
  - **Install:** `pip install sentence-transformers`
- **scipy** - Required for Savitzky-Golay filtering in advanced semantic mode
  - **Fallback:** Simple threshold-based splitting
  - **Install:** `pip install scipy`
- **numpy** - Improves performance of similarity calculations
  - **Fallback:** Pure Python dot product calculations
  - **Install:** `pip install numpy`
- **tokenizers** (tiktoken, transformers) - For advanced tokenization
  - **Fallback:** Character-based tokenization
  - **Install:** `pip install tiktoken` or `pip install transformers`

**No installation required** for basic functionality - all chunkers work out of the box!

**Fallback Chain Example:**
```
SemanticChunker (advanced mode)
  ↓ (sentence-transformers missing)
SemanticChunker (simple mode)
  ↓ (chonkie missing)
Pure Python sentence splitting
  ✅ Always works
```

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

## Implementation Details

### Sentence Splitting

All chunkers use an improved sentence splitting algorithm that:
- Uses Cython-optimized splitting when `chonkie` is available (10-50x faster)
- Falls back to pure Python implementation automatically
- Handles multiple delimiters: `. `, `! `, `? `, `\n`
- Respects minimum sentence length to avoid fragmentation
- Includes delimiters in previous sentence (`include_delim="prev"`)
- Handles abbreviations (Dr., Mr., etc.) and edge cases

**Location:** `server/services/file_processing/chunking/utils.py`

**Example:**
```python
from services.file_processing.chunking.utils import split_sentences

sentences = split_sentences(
    text="Dr. Smith went to the store. He bought milk.",
    delimiters=[". ", "! ", "? ", "\n"],
    include_delim="prev",
    min_characters_per_sentence=12
)
# Result: ["Dr. Smith went to the store. ", "He bought milk."]
```

### Token Estimation Fallback

When tokenizer operations fail, chunkers use intelligent fallback:
- **Estimation heuristic:** ~4 characters per token (English text average)
- **Graceful degradation:** Character-based chunking if token operations fail
- **No exceptions thrown:** Warnings logged, processing continues
- **Automatic recovery:** Falls back to FixedSizeChunker if needed

**Example:**
```python
# If tokenizer.decode() fails:
try:
    chunk_text = tokenizer.decode(token_slice)
except Exception:
    # Fallback: estimate characters from tokens
    estimated_chars = len(token_slice) * 4  # ~4 chars per token
    chunk_text = text[start:start + estimated_chars]
```

This ensures robustness even with corrupted tokenizers or encoding issues.

### Recursive Splitting Strategy

RecursiveChunker uses a hierarchical approach:

1. **Level 1 (Paragraphs):** Split by `\n\n` or `\n\n\n`
2. **Level 2 (Sentences):** Split by `. `, `! `, `? `, `\n`
3. **Level 3 (Words):** Split by whitespace

**Merging Logic:**
- Merges short splits into larger chunks
- Respects `chunk_size` token limits
- Preserves delimiters with previous segment
- Handles edge cases (no punctuation, very long sentences)

**Dynamic Word Grouping:**
- Estimates ~1.3 tokens per word
- Calculates `words_per_chunk = chunk_size / 1.3`
- Groups words accordingly to respect token limits

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

## File Chunking Strategy Comparison

| Strategy | Best For | Unit | Structure Awareness | Speed | Dependencies | LLM Accuracy |
|----------|----------|------|-------------------|-------|--------------|--------------|
| **FixedSizeChunker** | Plain text, CSV, simple docs | Characters/Tokens | None | Fast | None | ⚠️ Character-based, ✅ Token-based |
| **SemanticChunker** | PDFs, DOCX, natural language | Sentences | Sentence boundaries | Medium | Optional (sentence-transformers) | ✅ |
| **TokenChunker** | All text types, LLM context | Tokens | None | Fast | Optional (tokenizers) | ✅ |
| **RecursiveChunker** ⭐ | **All file types (default)** | Tokens/Characters | Hierarchical (paragraphs→sentences→words) | Medium | None | ✅ |

⭐ **Recommended default** - Works best across all file types (PDF, DOCX, CSV, TXT, HTML, JSON, images, audio)

### Detailed Strategy Comparison

| Feature | FixedSize | Semantic | Token | Recursive |
|---------|-----------|----------|-------|-----------|
| **Works for CSV/JSON** | ✅ | ⚠️ | ✅ | ✅ |
| **Works for PDF/DOCX** | ✅ | ✅ | ✅ | ✅ |
| **Respects sentences** | ❌ | ✅ | ❌ | ✅ |
| **Respects paragraphs** | ❌ | ⚠️ | ❌ | ✅ |
| **Token-aware** | Optional | Optional | ✅ | ✅ |
| **LLM context accuracy** | ⚠️/✅ | ✅ | ✅ | ✅ |
| **Complexity** | Low | Medium/High | Low | Medium |
| **Speed** | Fast | Medium | Fast | Medium |
| **Required deps** | None | Optional | Optional | None |
| **Default recommended** | ❌ | ❌ | ❌ | ✅ |

## System Comparison Table

| Feature | File Chunking | Web Content Chunking |
|---------|---------------|---------------------|
| **Unit** | Characters/Sentences/Tokens | Tokens |
| **Structure** | Flat/Hierarchical | Hierarchical (tree) |
| **Awareness** | Sentence/paragraph/words | Markdown headers |
| **Output** | `Chunk` dataclass | Dictionary |
| **Use Case** | Uploaded files | Scraped web pages |
| **Strategies** | Fixed, Semantic, Token, Recursive | Markdown structure |
| **Size Trigger** | Always chunks | Only if > max_tokens |
| **Hierarchy** | Optional (RecursiveChunker) | H1 > H2 > H3... |
| **Adapter** | File Adapter | Firecrawl Adapter |

## When to Use Which Strategy?

### File Chunking Strategy Selection

#### Use FixedSizeChunker When:
- ✅ Working with CSV or structured data
- ✅ Need consistent, predictable chunk sizes
- ✅ Processing speed is critical
- ✅ Simple plain text files
- ⚠️ Consider token-based mode (`use_tokens=True`) for better LLM accuracy

#### Use SemanticChunker When:
- ✅ Working with PDFs, DOCX, or natural language documents
- ✅ Semantic coherence is important
- ✅ Q&A applications where sentence boundaries matter
- ✅ Can use advanced mode with sentence-transformers for better results
- ❌ Not ideal for CSV or highly structured data

#### Use TokenChunker When:
- ✅ Need accurate token counts for LLM context windows
- ✅ Working with all text file types
- ✅ Token-based chunking is required
- ✅ Don't need structure awareness
- ❌ May split sentences/paragraphs mid-way

#### Use RecursiveChunker When (Recommended Default):
- ✅ **First-time installation** - Works best for all file types
- ✅ Need structure-aware chunking (paragraphs → sentences → words)
- ✅ Working with mixed content (structured + unstructured)
- ✅ Want best balance of structure awareness and simplicity
- ✅ Processing PDFs, DOCX, CSV, TXT, HTML, JSON, images, audio
- ✅ Default choice for general-purpose file processing

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
│ - 1000 chars/tokens  │    - 4000 tokens                 │
│ - 200 overlap       │    - Markdown H1-H6              │
│ - Character/token   │    - Section hierarchy           │
│                     │    - Smart overlap               │
│ SemanticChunker     │                                   │
│ - 10 sentences      │                                   │
│ - 2 sentence overlap│                                   │
│ - Advanced mode     │                                   │
│                     │                                   │
│ TokenChunker        │                                   │
│ - 2048 tokens       │                                   │
│ - Token-based       │                                   │
│                     │                                   │
│ RecursiveChunker ⭐ │                                   │
│ - 2048 tokens       │                                   │
│ - Hierarchical      │                                   │
│ - Default strategy  │                                   │
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

### File Adapter Examples

#### PDF Upload (Recommended: RecursiveChunker)
```python
# User uploads research.pdf
from services.file_processing.chunking import RecursiveChunker

# Default recursive chunker (recommended)
chunker = RecursiveChunker(chunk_size=2048, min_characters_per_chunk=24)
chunks = chunker.chunk_text(pdf_text, file_id, metadata)

# Store in vector DB
for chunk in chunks:
    await vector_store.add_vectors([embedding], [chunk.chunk_id], [chunk.metadata])
```

#### CSV Upload (FixedSizeChunker)
```python
# User uploads data.csv
from services.file_processing.chunking import FixedSizeChunker

# Character-based for CSV
chunker = FixedSizeChunker(chunk_size=1000, overlap=200)
chunks = chunker.chunk_text(csv_text, file_id, metadata)
```

#### Natural Language Document (SemanticChunker)
```python
# User uploads document.docx
from services.file_processing.chunking import SemanticChunker

# Advanced semantic chunking with sentence-transformers
chunker = SemanticChunker(
    chunk_size=10,
    overlap=2,
    use_advanced=True,
    model_name="all-MiniLM-L6-v2"
)
chunks = chunker.chunk_text(docx_text, file_id, metadata)
```

#### Token-Aware Chunking (TokenChunker)
```python
# User uploads any text file, need accurate token counts
from services.file_processing.chunking import TokenChunker

chunker = TokenChunker(chunk_size=2048, overlap=200, tokenizer="gpt2")
chunks = chunker.chunk_text(text, file_id, metadata)
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

### File Chunking (Tested on ~5MB files)
- **Speed**:
  - FixedSizeChunker (char): ~5-10ms per 1000 chars
  - FixedSizeChunker (token): ~15-20ms per 1000 chars
  - SemanticChunker (simple): ~30-50ms per 1000 chars
  - SemanticChunker (advanced): ~150-250ms per 1000 chars (depends on model)
  - TokenChunker: ~12-18ms per 1000 chars
  - RecursiveChunker: ~25-40ms per 1000 chars
- **Memory**:
  - All chunkers (except advanced semantic): <100MB for files up to 10MB
  - Semantic (advanced): 100-500MB (due to embedding model)
- **Accuracy**: Deterministic (all strategies)
- **Token Accuracy**: TokenChunker and token-based FixedSizeChunker provide most accurate token counts
- **Test Coverage**: 76 tests, 100% passing

### Web Content Chunking
- **Speed**: ~100ms per 50KB markdown
- **Memory**: Low (streaming)
- **Cache Hit Rate**: 60-80% (after first scrape)
- **Context Reduction**: 75-90% (only relevant sections)
- **Cost Savings**: 80% (fewer tokens to LLM)

## Configuration

### Default Configuration (config.yaml)

```yaml
files:
  default_chunking_strategy: "recursive"  # Recommended default
  default_chunk_size: 2048  # Tokens (for recursive/token), characters (for fixed/semantic)
  default_chunk_overlap: 200

  # Optional tokenizer configuration
  tokenizer: null  # Options: "character" (default), "gpt2", "tiktoken", etc.
  use_tokens: false  # For fixed strategy: use token-based instead of character-based

  # Strategy-specific options
  chunking_options:
    # Recursive chunking options
    min_characters_per_chunk: 24

    # Semantic chunking options
    model_name: null  # e.g., "all-MiniLM-L6-v2"
    use_advanced: false  # Enable advanced semantic chunking
    threshold: 0.8  # Similarity threshold (0-1) for boundary detection
    similarity_window: 3  # Number of sentences for similarity calculation
    min_sentences_per_chunk: 1  # Minimum sentences per chunk
    min_characters_per_sentence: 24  # Minimum characters per sentence
    skip_window: 0  # Number of groups to skip when merging (0=disabled, >0=enabled)
    filter_window: 5  # Window length for Savitzky-Golay filter (requires scipy)
    filter_polyorder: 3  # Polynomial order for Savitzky-Golay filter
    filter_tolerance: 0.2  # Tolerance for Savitzky-Golay filter
    chunk_size_tokens: null  # Optional token-based chunk size limit
```

### Per-Adapter Override

Adapters can override global settings in `adapters.yaml`:

```yaml
adapters:
  - name: "file-document-qa"
    config:
      chunking_strategy: "semantic"  # Override default
      chunk_size: 10
      chunk_overlap: 2
      chunking_options:
        use_advanced: true
        model_name: "all-MiniLM-L6-v2"
        threshold: 0.8
        similarity_window: 3
```

## Troubleshooting

### "Token decoding failed" warnings
**Cause:** Tokenizer compatibility issue or corrupted encoding
**Solution:** Chunker automatically falls back to character estimation. No action needed.
**To fix:** Install compatible tokenizer: `pip install tiktoken` or use `tokenizer="character"`

### SemanticChunker advanced mode not working
**Cause:** sentence-transformers not installed
**Solution:** Install with `pip install sentence-transformers`
**Alternative:** Use `use_advanced=False` for simple mode (no dependencies)

### Savitzky-Golay filtering not working
**Cause:** scipy not installed
**Solution:** Install with `pip install scipy`
**Alternative:** Advanced mode will fall back to simple threshold-based splitting

### Chunks too large/small
**Adjust:**
- FixedSizeChunker: `chunk_size` parameter (characters or tokens)
- SemanticChunker: `chunk_size` (number of sentences) or `chunk_size_tokens` (token limit)
- TokenChunker: `chunk_size` (number of tokens)
- RecursiveChunker: `chunk_size` and `min_characters_per_chunk`

### RecursiveChunker creates uneven chunks
**Expected behavior:** Respects document structure (paragraphs, sentences)
**If problematic:** Switch to FixedSizeChunker or TokenChunker for uniform sizes

### Empty chunks or missing content
**Cause:** Text only contains delimiters or whitespace
**Solution:** All chunkers handle this gracefully and return empty list or valid chunks

### Very slow performance
**Possible causes:**
- SemanticChunker in advanced mode with large model
- Very large files (>50MB)
- Sentence-transformers model not cached

**Solutions:**
- Use simple mode: `use_advanced=False`
- Switch to FixedSizeChunker or TokenChunker for speed
- Reduce `chunk_size` to process smaller pieces
- Install chonkie for Cython optimizations: `pip install chonkie`

### "Chunk size must be positive" error
**Cause:** Invalid configuration parameters
**Solution:** Ensure `chunk_size > 0` and `overlap < chunk_size`

## Recent Improvements (2025-01-08)

A comprehensive review and bug fix session resulted in:
- ✅ **5 critical bugs fixed:**
  1. Sentence splitting logic bug (utils.py)
  2. Hardcoded whitespace split size (recursive_chunker.py)
  3. Fragile string join logic (recursive_chunker.py)
  4. Incorrect token-to-character fallback (token_chunker.py)
  5. Incorrect token-to-character fallback (fixed_chunker.py)
- ✅ **28 new tests added** (76 total tests, 100% passing)
- ✅ **Enhanced edge case handling** (empty text, special characters, very long sentences)
- ✅ **Improved large file performance testing** (tested up to 5MB files)
- ✅ **Better fallback behavior** for tokenizer failures

See `CHUNKING_REVIEW_REPORT.md` for full details on:
- Implementation quality assessment (8.5/10 confidence)
- Medium/low priority optimizations
- Performance expectations
- Security & safety considerations
- Migration & rollback plan

## Conclusion

Keep these systems **separate** because they serve different purposes:

1. **File Chunking** - General-purpose, multiple strategies (fixed, semantic, token, recursive), for uploaded files
2. **Web Content Chunking** - Specialized, token/structure-based, for web scraping

### Recommended Default Strategy

**RecursiveChunker** is recommended as the default strategy because:
- ✅ Works best for **all file types** (PDF, DOCX, CSV, TXT, HTML, JSON, images, audio)
- ✅ Respects document structure (paragraphs → sentences → words)
- ✅ Token-aware for accurate LLM context window management
- ✅ No required dependencies (character tokenizer fallback)
- ✅ Balanced complexity: sophisticated enough for quality, simple enough for performance
- ✅ Production-ready with comprehensive test coverage

Both systems can share the **ChunkManager** for vector store integration, providing a unified storage and retrieval layer.

This architecture follows the **separation of concerns** principle while allowing code reuse where it makes sense (storage/retrieval logic).
