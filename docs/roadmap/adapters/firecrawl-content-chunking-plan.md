# Firecrawl Content Chunking & Caching Strategy

## Problem Statement

Wikipedia articles and documentation pages can be very large (50KB-500KB+), which can:
- Exceed LLM context limits when combined with other system prompts
- Slow down response times
- Increase processing costs
- Reduce relevance (user may only need specific sections)

## Current Implementation

The current Firecrawl retriever (`intent_firecrawl_retriever.py`) returns full page content in a single response:

```python
def _format_firecrawl_results(self, results: List[Dict], template: Dict) -> str:
    # Returns entire markdown content
    if 'markdown' in result and result['markdown']:
        lines.append(f"\nMarkdown Content:\n{result['markdown']}")
```

## Proposed Solutions

### Option 1: Intelligent Chunking (Recommended)

Split large content into semantic chunks based on document structure:

#### Implementation Strategy

1. **Parse Markdown Structure**
   - Split by headers (# H1, ## H2, ### H3)
   - Preserve hierarchy and context
   - Maintain semantic relationships

2. **Chunk Sizing**
   - Target chunk size: 2,000-4,000 tokens (~8KB-16KB)
   - Include header hierarchy in each chunk for context
   - Add overlap between chunks (200-500 tokens)

3. **Metadata Preservation**
   - Store document structure map
   - Track chunk positions and relationships
   - Include section titles in chunk metadata

#### Code Structure

```python
class ContentChunker:
    def __init__(self, max_chunk_size: int = 4000, overlap: int = 200):
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap

    def chunk_markdown(self, content: str, metadata: Dict) -> List[Dict]:
        """
        Chunk markdown content by sections.

        Returns:
            List of chunks with metadata:
            [
                {
                    "chunk_id": "doc_1_chunk_0",
                    "content": "...",
                    "section": "Introduction",
                    "hierarchy": ["Web Scraping", "Introduction"],
                    "position": 0,
                    "total_chunks": 5,
                    "overlap_with_prev": True,
                    "overlap_with_next": True
                }
            ]
        """
        pass
```

### Option 2: Redis Cache with Time-Based Expiry

Cache full content in Redis with chunking metadata for fast retrieval:

#### Implementation Strategy

1. **Cache Key Structure**
   ```
   firecrawl:content:{url_hash}:full
   firecrawl:content:{url_hash}:chunks
   firecrawl:content:{url_hash}:metadata
   ```

2. **Storage Format**
   ```python
   # Full content
   redis.set(
       f"firecrawl:content:{url_hash}:full",
       json.dumps({"markdown": "...", "metadata": {...}}),
       ex=3600  # 1 hour expiry
   )

   # Chunked content
   redis.hset(
       f"firecrawl:content:{url_hash}:chunks",
       mapping={
           "chunk_0": json.dumps({"content": "...", "metadata": {...}}),
           "chunk_1": json.dumps({"content": "...", "metadata": {...}}),
           # ...
       }
   )
   redis.expire(f"firecrawl:content:{url_hash}:chunks", 3600)
   ```

3. **Retrieval Strategy**
   ```python
   # Check cache first
   cached_chunks = redis.hgetall(f"firecrawl:content:{url_hash}:chunks")
   if cached_chunks:
       return [json.loads(chunk) for chunk in cached_chunks.values()]

   # If not cached, scrape and chunk
   content = await scrape_url(url)
   chunks = chunker.chunk_markdown(content)

   # Store in cache
   for i, chunk in enumerate(chunks):
       redis.hset(
           f"firecrawl:content:{url_hash}:chunks",
           f"chunk_{i}",
           json.dumps(chunk)
       )
   ```

4. **Cache Invalidation**
   - Time-based: 1 hour for news, 24 hours for Wikipedia
   - Manual invalidation: Force refresh via parameter
   - Size-based eviction: LRU policy

### Option 3: Hybrid Approach (Best Solution)

Combine chunking with Redis caching for optimal performance:

#### Workflow

1. **Query received**: "Tell me about web scraping"
2. **Check Redis cache**:
   - Key: `firecrawl:chunks:hash(wikipedia.org/wiki/Web_scraping)`
   - If found: Return cached chunks
3. **If not cached**:
   - Scrape content via Firecrawl
   - Chunk content intelligently
   - Store chunks in Redis (1 hour TTL)
   - Return chunks
4. **LLM Processing**:
   - Rank chunks by relevance to query
   - Return top 2-3 most relevant chunks
   - Include chunk navigation metadata

## Implementation Plan

### Phase 1: Basic Chunking (Immediate)

```python
# Add to intent_firecrawl_retriever.py

from typing import List, Dict, Any
import hashlib
import re

class IntentFirecrawlRetriever(IntentHTTPRetriever):

    def __init__(self, config: Dict[str, Any], **kwargs):
        super().__init__(config=config, **kwargs)

        # Chunking configuration
        self.enable_chunking = self.intent_config.get('enable_chunking', True)
        self.max_chunk_size = self.intent_config.get('max_chunk_size', 4000)
        self.chunk_overlap = self.intent_config.get('chunk_overlap', 200)

    def _chunk_content(self, markdown: str, metadata: Dict) -> List[Dict]:
        """
        Chunk markdown content by sections.
        """
        if not self.enable_chunking:
            return [{"content": markdown, "chunk_id": 0, "total_chunks": 1}]

        # Split by top-level headers
        sections = re.split(r'\n(?=#+\s)', markdown)

        chunks = []
        current_chunk = ""
        chunk_id = 0

        for section in sections:
            # Estimate token count (rough: 1 token ≈ 4 chars)
            if len(current_chunk) + len(section) > self.max_chunk_size * 4:
                if current_chunk:
                    chunks.append({
                        "content": current_chunk,
                        "chunk_id": chunk_id,
                        "metadata": metadata
                    })
                    chunk_id += 1
                current_chunk = section
            else:
                current_chunk += "\n" + section if current_chunk else section

        # Add remaining content
        if current_chunk:
            chunks.append({
                "content": current_chunk,
                "chunk_id": chunk_id,
                "metadata": metadata
            })

        # Add total_chunks to all chunks
        for chunk in chunks:
            chunk["total_chunks"] = len(chunks)

        return chunks

    def _format_firecrawl_results(self, results: List[Dict], template: Dict) -> str:
        """
        Format with chunking support.
        """
        if not results:
            return "No content was scraped."

        result = results[0]

        # Get markdown content
        if 'markdown' in result and result['markdown']:
            content = result['markdown']

            # Chunk if enabled
            if self.enable_chunking and len(content) > self.max_chunk_size * 4:
                chunks = self._chunk_content(content, result.get('metadata', {}))

                # Format chunked response
                lines = [
                    f"Successfully scraped and chunked content from: {result.get('url', 'Unknown')}",
                    f"Total chunks: {len(chunks)}",
                    "",
                    "=" * 60,
                    "CHUNK 1 (Showing first chunk - full content cached for follow-up queries)",
                    "=" * 60,
                    chunks[0]["content"]
                ]

                return "\n".join(lines)
            else:
                # Return full content if small enough
                return content

        return "No markdown content available."
```

### Phase 2: Redis Cache Integration (Next Sprint)

```python
# Add Redis cache support

import redis.asyncio as redis
import json

class IntentFirecrawlRetriever(IntentHTTPRetriever):

    def __init__(self, config: Dict[str, Any], **kwargs):
        super().__init__(config=config, **kwargs)

        # Redis cache configuration
        self.enable_cache = self.intent_config.get('enable_cache', False)
        self.cache_ttl = self.intent_config.get('cache_ttl', 3600)  # 1 hour

        if self.enable_cache:
            redis_config = self.intent_config.get('redis', {})
            self.redis_client = redis.Redis(
                host=redis_config.get('host', 'localhost'),
                port=redis_config.get('port', 6379),
                db=redis_config.get('db', 0),
                decode_responses=True
            )

    async def _get_cached_chunks(self, url: str) -> Optional[List[Dict]]:
        """Retrieve cached chunks from Redis."""
        if not self.enable_cache:
            return None

        try:
            url_hash = hashlib.md5(url.encode()).hexdigest()
            cache_key = f"firecrawl:chunks:{url_hash}"

            cached_data = await self.redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Cache retrieval failed: {e}")

        return None

    async def _cache_chunks(self, url: str, chunks: List[Dict]):
        """Store chunks in Redis cache."""
        if not self.enable_cache:
            return

        try:
            url_hash = hashlib.md5(url.encode()).hexdigest()
            cache_key = f"firecrawl:chunks:{url_hash}"

            await self.redis_client.setex(
                cache_key,
                self.cache_ttl,
                json.dumps(chunks)
            )
        except Exception as e:
            logger.warning(f"Cache storage failed: {e}")
```

### Phase 3: Intelligent Chunk Ranking (Future Enhancement)

Use embedding similarity to rank chunks by relevance to the query:

```python
async def _rank_chunks(self, chunks: List[Dict], query: str) -> List[Dict]:
    """
    Rank chunks by relevance to query using embeddings.
    """
    if not chunks or len(chunks) == 1:
        return chunks

    # Get query embedding
    query_embedding = await self.embedding_provider.embed([query])

    # Get chunk embeddings
    chunk_texts = [chunk["content"][:500] for chunk in chunks]  # First 500 chars
    chunk_embeddings = await self.embedding_provider.embed(chunk_texts)

    # Calculate similarities
    from numpy import dot
    from numpy.linalg import norm

    similarities = []
    for i, chunk_emb in enumerate(chunk_embeddings):
        sim = dot(query_embedding[0], chunk_emb) / (norm(query_embedding[0]) * norm(chunk_emb))
        chunks[i]["relevance_score"] = float(sim)
        similarities.append((i, sim))

    # Sort by relevance
    similarities.sort(key=lambda x: x[1], reverse=True)

    # Return top 3 most relevant chunks
    top_chunks = [chunks[i] for i, _ in similarities[:3]]

    return top_chunks
```

## Configuration Example

Add to `config/adapters.yaml`:

```yaml
- name: "intent-firecrawl-webscrape"
  enabled: true
  type: "retriever"
  datasource: "http"
  adapter: "intent"
  implementation: "retrievers.implementations.intent.IntentFirecrawlRetriever"
  config:
    # ... existing config ...

    # Chunking configuration
    enable_chunking: true
    max_chunk_size: 4000  # tokens
    chunk_overlap: 200    # tokens

    # Redis cache configuration (Phase 2)
    enable_cache: true
    cache_ttl: 3600  # 1 hour for Wikipedia
    redis:
      host: "localhost"
      port: 6379
      db: 0

    # Chunk ranking (Phase 3)
    enable_chunk_ranking: true
    max_chunks_returned: 3
```

## Benefits

1. **Reduced Context Usage**: 75-90% reduction in context size
2. **Faster Response Times**: Cached chunks retrieved in <10ms
3. **Better Relevance**: Only return relevant sections
4. **Cost Optimization**: Fewer tokens processed by LLM
5. **Improved User Experience**: Focused, relevant answers

## Performance Metrics

Expected improvements:

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Average Response Size | 50KB | 10KB | 80% reduction |
| Cache Hit Rate | 0% | 60-80% | - |
| Response Time | 2-5s | 0.5-2s | 60% faster |
| Context Window Usage | 40% | 8% | 80% reduction |
| Cost per Query | $0.02 | $0.004 | 80% reduction |

## Migration Path

1. **Week 1**: Implement basic chunking (Phase 1)
2. **Week 2**: Add Redis caching (Phase 2)
3. **Week 3**: Implement chunk ranking (Phase 3)
4. **Week 4**: Performance testing and optimization

## Testing Strategy

1. Test with small content (<5KB): Should return full content
2. Test with medium content (10-30KB): Should return 2-3 chunks
3. Test with large content (50KB+): Should return top 3 relevant chunks
4. Test cache hit rates with repeated queries
5. Test cache invalidation and refresh

## Monitoring

Track these metrics:

- Cache hit/miss rates
- Average chunk sizes
- Chunks per document
- Query response times
- Context window usage
- Content freshness (cache age)
