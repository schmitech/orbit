# Firecrawl Intent Template System

This directory contains the template system for the Firecrawl intent retriever adapter, which enables natural language queries to be translated into web scraping requests using Firecrawl.

## Overview

The Firecrawl intent adapter allows users to scrape web content using natural language queries. It supports both the cloud Firecrawl API and self-hosted Firecrawl deployments, providing a unified interface for web scraping through ORBIT's intent-based retrieval system.

## Architecture

The adapter follows the same architecture as other intent retrievers:

1. **Template Matching**: Natural language queries are matched against predefined templates using vector similarity
2. **Parameter Extraction**: URL and format parameters are extracted from the query using LLM
3. **API Translation**: Parameters are translated into Firecrawl API requests
4. **Response Formatting**: Scraped content is formatted into context documents

## Features

- **Dual Deployment Support**: Works with both cloud API and self-hosted Firecrawl
- **Format Flexibility**: Supports markdown, HTML, and text output formats
- **Fresh Content**: Always fetches fresh content (no local caching)
- **Error Handling**: Robust error handling for invalid URLs and API failures
- **Template-Based**: Uses configurable templates for different scraping scenarios

## Configuration

### Cloud API Setup

For cloud API usage, set the following in your adapter configuration:

```yaml
config:
  base_url: "https://api.firecrawl.dev/v1"
  auth:
    type: "bearer_token"
    token_env: "FIRECRAWL_API_KEY"
    header_name: "Authorization"
    token_prefix: "Bearer"
```

Set your API key in the environment:
```bash
export FIRECRAWL_API_KEY="your-api-key-here"
```

### Self-Hosted Setup

For self-hosted Firecrawl, set the base URL to your instance:

```yaml
config:
  base_url: "http://your-firecrawl-instance:3000/v1"
  # No authentication needed for self-hosted
```

## Template Structure

### Domain Configuration (`firecrawl_domain.yaml`)

Defines the web scraping domain with:
- **Entities**: url, webpage, content, format
- **Parameters**: url (required), formats (optional)
- **Vocabulary**: Synonyms and related terms
- **Intent Patterns**: Common query patterns

### Template Library (`firecrawl_templates.yaml`)

Contains 10 predefined templates for common scraping scenarios:

1. **Basic Scraping**: Simple URL scraping in markdown format
2. **Format-Specific**: Scraping with specific output formats
3. **Content Reading**: Reading webpage content
4. **Article Extraction**: Extracting article content
5. **Blog Content**: Fetching blog posts
6. **Documentation**: Scraping documentation
7. **News Content**: Extracting news articles
8. **Homepage Scraping**: Scraping website homepages
9. **Text Extraction**: Plain text content extraction
10. **HTML Source**: HTML source code scraping

## Usage Examples

### Basic Scraping
```
Query: "scrape https://example.com"
Result: Scrapes content from the URL in markdown format
```

### Format-Specific Scraping
```
Query: "scrape https://example.com as markdown and html"
Result: Scrapes content in both markdown and HTML formats
```

### Article Extraction
```
Query: "extract article from https://news.com/story"
Result: Extracts article content from the news story
```

### Documentation Scraping
```
Query: "scrape documentation from https://docs.api.com/guide"
Result: Scrapes documentation content from the API guide
```

## Parameter Extraction

The adapter extracts the following parameters from natural language queries:

### Required Parameters
- **url**: The URL to scrape (must start with http:// or https://)

### Optional Parameters
- **formats**: Array of desired output formats
  - Allowed values: `["markdown", "html", "text"]`
  - Default: `["markdown"]`

## Response Format

Successful scraping returns a context document with:

```json
{
  "content": "Formatted scraped content...",
  "metadata": {
    "source": "firecrawl",
    "template_id": "scrape_url_basic",
    "query_intent": "Scrape content from a URL in markdown format",
    "parameters_used": {"url": "https://example.com"},
    "similarity": 0.85,
    "result_count": 1,
    "scraped_url": "https://example.com",
    "scrape_success": true,
    "page_metadata": {
      "title": "Example Page",
      "description": "An example webpage",
      "author": "Example Author",
      "language": "en"
    }
  },
  "confidence": 0.85
}
```

## Error Handling

The adapter handles various error scenarios:

- **Invalid URLs**: Parameter validation ensures URLs start with http:// or https://
- **Missing URL**: Queries without URLs are rejected
- **API Failures**: Network and API errors are caught and reported
- **Unsupported Formats**: Invalid formats fall back to default markdown
- **Scraping Failures**: Failed scraping attempts return error messages

## Testing

Use the provided test queries in `examples/web-scraping/test_queries.md` to verify the adapter functionality. The test file includes:

- Basic scraping queries
- Format-specific requests
- Content type variations
- Error case examples
- Expected parameter extraction

## Dependencies

The Firecrawl intent adapter requires:

- `httpx`: For HTTP requests to Firecrawl API
- `firecrawl-py`: Optional, for direct Firecrawl client usage
- ORBIT's intent system components

## Performance Optimization

### Large Content Handling

Wikipedia articles and documentation pages can be very large (50KB-500KB+). To handle this efficiently:

#### Current Behavior
- Full content returned in single response
- May exceed LLM context limits
- Can slow down response times

#### Recommended Enhancements

See `docs/roadmap/adapters/firecrawl-content-chunking-plan.md` for detailed implementation plan.

**Phase 1: Intelligent Chunking**
```yaml
config:
  enable_chunking: true
  max_chunk_size: 4000  # tokens (~16KB)
  chunk_overlap: 200    # overlap between chunks
```

**Phase 2: Redis Cache Integration**
```yaml
config:
  enable_cache: true
  cache_ttl: 3600  # 1 hour for Wikipedia articles
  redis:
    host: "localhost"
    port: 6379
    db: 0
```

**Phase 3: Chunk Ranking**
```yaml
config:
  enable_chunk_ranking: true
  max_chunks_returned: 3  # Return top 3 relevant chunks
```

### Benefits of Chunking + Caching

1. **Reduced Context Usage**: 75-90% reduction in LLM context size
2. **Faster Response Times**: Cached chunks retrieved in <10ms
3. **Better Relevance**: Return only relevant sections of large documents
4. **Cost Optimization**: Process fewer tokens through LLM
5. **Scalability**: Handle any document size efficiently

### Cache Strategy

The adapter can leverage Redis for efficient content caching:

- **Cache Key Format**: `firecrawl:chunks:{url_hash}`
- **TTL Configuration**:
  - News articles: 1 hour
  - Wikipedia: 24 hours
  - Official docs: 7 days
- **Invalidation**: Automatic expiry + manual refresh option
- **Storage Format**: Compressed JSON chunks with metadata

### Integration with Existing Stores

ORBIT provides several storage options that can be used with this adapter:

1. **Redis** (Recommended for caching)
   - Fast retrieval (<10ms)
   - TTL support
   - Automatic eviction
   - Configured in `config/stores.yaml`

2. **ChromaDB** (For template matching)
   - Already used for intent matching
   - Could store document embeddings for similarity search

3. **Qdrant/Pinecone** (For advanced search)
   - Could enable semantic search across cached content
   - Find similar sections across multiple documents

## Troubleshooting

### Common Issues

1. **Authentication Errors**: Ensure API key is set correctly for cloud usage
2. **URL Validation**: URLs must start with http:// or https://
3. **Format Errors**: Only markdown, html, and text formats are supported
4. **Network Issues**: Check connectivity to Firecrawl API endpoint
5. **Large Content Timeouts**: Wikipedia pages may take 30-60s to scrape
6. **Memory Issues**: Large articles may consume significant memory without chunking

### Debug Mode

Enable verbose logging to see detailed parameter extraction and API calls:

```yaml
config:
  verbose: true
```

### Performance Issues

If experiencing slow responses with large content:

1. Enable chunking to reduce context size
2. Enable Redis caching for frequently accessed content
3. Adjust timeout values in adapter config
4. Consider pre-caching common topics

## Future Enhancements

Potential improvements for the knowledge retrieval system:

1. **Semantic Chunking**: Split by topics, not just headers
2. **Cross-Document Search**: Find related information across multiple sources
3. **Content Summarization**: Generate summaries before chunking
4. **Multi-Source Aggregation**: Combine information from multiple URLs
5. **Update Detection**: Monitor source changes and invalidate cache
6. **Query Expansion**: Automatically expand queries to related topics
7. **Source Diversity**: Include multiple sources per topic (Wikipedia + official docs)

## Contributing

To add new templates:

1. Define the template in `firecrawl_templates.yaml`
2. Add natural language examples
3. Specify required parameters
4. Test with queries in `test_queries.md`
5. Update documentation as needed

To add new knowledge sources:

1. Identify authoritative, reliable sources
2. Test content extraction quality
3. Determine appropriate cache TTL
4. Document source in templates
5. Add test queries

## License

This template system is part of the ORBIT project and follows the same licensing terms.
