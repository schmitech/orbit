# Firecrawl Template Pipeline

A web crawler templating engine that generates intent-based templates for grounded responses from specific URLs.

## Overview

This pipeline transforms a website (via sitemap or crawling) into a set of **Firecrawl intent templates** that enable:
- **Grounded responses**: Each query maps to a specific, authoritative URL
- **Semantic matching**: Natural language queries are matched to relevant content
- **Efficient retrieval**: Only scrapes when user query matches (no bulk scraping at query time)
- **Quality control**: LLM-generated questions cover natural query variations

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         TEMPLATE PIPELINE                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   INPUT                    PROCESSING                    OUTPUT          │
│   ─────                    ──────────                    ──────          │
│                                                                          │
│   Sitemap.xml    ┌──────────────────────┐                               │
│       or    ──── │  URL Extraction      │                               │
│   Single URL     │  (url-extractor.py)  │                               │
│                  └──────────┬───────────┘                               │
│                             │                                            │
│                             ▼                                            │
│                  ┌──────────────────────┐                               │
│                  │  Content Sampling    │     urls.json                 │
│                  │  (Firecrawl API)     │ ─────────────────────────►    │
│                  └──────────┬───────────┘                               │
│                             │                                            │
│                             ▼                                            │
│                  ┌──────────────────────┐                               │
│                  │  NL Example Gen      │                               │
│                  │  (Ollama/OpenAI)     │                               │
│                  └──────────┬───────────┘                               │
│                             │                                            │
│                             ▼                                            │
│                  ┌──────────────────────┐     firecrawl_templates.yaml  │
│                  │  Template Builder    │ ─────────────────────────►    │
│                  │                      │                               │
│                  └──────────────────────┘     firecrawl_domain.yaml     │
│                                          ─────────────────────────►     │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

1. **Python 3.7+** with required packages:
   ```bash
   pip install aiohttp pyyaml requests beautifulsoup4
   ```

2. **Ollama** running locally (or OpenAI API key):
   ```bash
   # Start Ollama
   ollama serve

   # Pull a model
   ollama pull llama3.2
   ```

3. **Firecrawl API key** (optional, for content sampling):
   ```bash
   export FIRECRAWL_API_KEY="your-api-key"
   ```

### Basic Usage

```bash
# Navigate to the scraping directory
cd utils/scraping

# From a sitemap (recommended)
python template_pipeline.py --sitemap https://company.com/sitemap.xml --output ./templates/

# From a single URL (will crawl)
python template_pipeline.py --url https://company.com --output ./templates/ --max-depth 2

# From existing urls.json
python template_pipeline.py --urls-file urls.json --output ./templates/
```

## Pipeline Components

### 1. URL Extractor (`url-extractor.py`)

Extracts URLs from a website:

```bash
# From sitemap
python url-extractor.py --sitemap https://company.com/sitemap.xml --output urls.json

# From single URL with crawling
python url-extractor.py --url https://company.com/page --output urls.json --max-depth 2
```

**Output (`urls.json`):**
```json
[
    {"file_name": "services-consulting.md", "url": "https://company.com/services/consulting"},
    {"file_name": "about-team.md", "url": "https://company.com/about/team"},
    ...
]
```

### 2. Template Generator (`template_generator.py`)

Generates intent templates from URLs:

```bash
# Basic usage
python template_generator.py --input urls.json --output templates.yaml

# With OpenAI
python template_generator.py --input urls.json --output templates.yaml --use-openai

# With more examples
python template_generator.py --input urls.json --output templates.yaml --examples 7
```

**Output (`firecrawl_templates.yaml`):**
```yaml
templates:
  - id: "company_services_consulting"
    description: "Information about consulting services"
    semantic_type: "services"
    nl_examples:
      - "What consulting services do you offer?"
      - "Tell me about your consulting options"
      - "How can you help with consulting?"
      - "Consulting services information"
      - "I need consulting help"
    url_mapping:
      url: "https://company.com/services/consulting"
    formats: ["markdown"]
    timeout: 45
```

### 3. Pipeline Orchestrator (`template_pipeline.py`)

Runs the complete pipeline:

```bash
# Full pipeline with all options
python template_pipeline.py \
    --sitemap https://company.com/sitemap.xml \
    --output ./templates/ \
    --domain "company_kb" \
    --examples 5 \
    --max-pages 50 \
    --delay 1.0 \
    --verbose
```

## Command-Line Options

### `template_pipeline.py`

| Option | Description | Default |
|--------|-------------|---------|
| `--sitemap URL` | Sitemap XML URL to extract URLs from | - |
| `--url URL` | Single URL to start crawling from | - |
| `--urls-file FILE` | Existing JSON file with URLs | - |
| `--output DIR` | Output directory | `./templates` |
| `--max-pages N` | Maximum pages to extract | 100 |
| `--max-depth N` | Maximum crawl depth | 3 |
| `--examples N` | NL examples per template | 5 |
| `--domain NAME` | Domain name for templates | auto-detected |
| `--limit N` | Limit number of templates | all |
| `--use-openai` | Use OpenAI instead of Ollama | false |
| `--delay SECONDS` | Delay between requests | 0.5 |
| `--concurrent N` | Concurrent requests | 3 |
| `--timeout SECONDS` | Request timeout | 60 |
| `--quick` | Skip content scraping | false |
| `--no-cache` | Disable caching | false |
| `--verbose` | Verbose output | false |

### `template_generator.py`

| Option | Description | Default |
|--------|-------------|---------|
| `--input FILE` | Input JSON file with URLs | required |
| `--output FILE` | Output YAML file | `firecrawl_templates.yaml` |
| `--examples N` | NL examples per template | 5 |
| `--delay SECONDS` | Delay between API calls | 0.5 |
| `--limit N` | Max URLs to process | all |
| `--domain NAME` | Domain name | auto-detected |
| `--use-openai` | Use OpenAI API | false |
| `--no-cache` | Skip cache | false |
| `--skip-scrape` | Skip scraping | false |
| `--semantic-types FILE` | Custom semantic type mappings | - |
| `--verbose` | Verbose output | false |

## Configuration

### Ollama Configuration (`config.yaml`)

```yaml
ollama:
  base_url: "http://localhost:11434"
  model: "llama3.2"
  temperature: 0.3
  num_ctx: 8192
```

### Environment Variables

```bash
# Firecrawl API (for content sampling)
export FIRECRAWL_API_KEY="fc-xxxxx"
export FIRECRAWL_BASE_URL="https://api.firecrawl.dev/v1"  # or self-hosted

# OpenAI (if using --use-openai)
export OPENAI_API_KEY="sk-xxxxx"
```

### Custom Semantic Types

Create a JSON file with URL pattern → semantic type mappings:

```json
{
    "/products/": "product_catalog",
    "/support/": "customer_support",
    "/api/": "api_documentation"
}
```

Use with: `--semantic-types custom_types.json`

## Integration with IntentFirecrawlRetriever

After generating templates, integrate them with the retriever:

### 1. Copy Templates

```bash
cp templates/firecrawl_templates.yaml config/adapters/templates/
```

### 2. Update Adapter Config

In your adapter configuration (e.g., `config/adapters/firecrawl.yaml`):

```yaml
adapter:
  type: intent_firecrawl
  templates_file: templates/firecrawl_templates.yaml

  # Optional settings
  confidence_threshold: 0.7
  enable_chunking: true
  max_chunk_tokens: 4000
```

### 3. Query the System

```python
# The retriever will now match natural language queries to templates
query = "What consulting services do you offer?"
# → Matches template with highest nl_examples similarity
# → Scrapes https://company.com/services/consulting
# → Returns grounded response
```

## Best Practices

### 1. URL Selection

- **Start with sitemaps**: They provide curated, important URLs
- **Limit crawl depth**: Deeper pages often have less unique content
- **Filter by path patterns**: Focus on content-rich sections

### 2. NL Examples Quality

- **More is better**: 5-7 examples per template improves matching
- **Diverse phrasing**: Include questions, statements, and requests
- **Domain-specific terms**: Use terminology your users would use

### 3. Performance

- **Use caching**: Avoid redundant API calls during development
- **Rate limiting**: Respect server limits with `--delay`
- **Quick mode**: Use `--quick` for rapid iteration without scraping

### 4. Maintenance

- **Version control templates**: Track changes over time
- **Periodic regeneration**: Update templates when content changes
- **Manual review**: Check generated examples for quality

## Troubleshooting

### Common Issues

**"Ollama connection failed"**
```bash
# Ensure Ollama is running
ollama serve

# Check the model is available
ollama list
```

**"No URLs extracted"**
```bash
# Check sitemap URL is accessible
curl https://company.com/sitemap.xml

# Try with verbose mode
python template_pipeline.py --sitemap URL --verbose
```

**"Template generation slow"**
```bash
# Use quick mode for testing
python template_pipeline.py --sitemap URL --quick

# Reduce concurrent requests if rate limited
python template_pipeline.py --sitemap URL --concurrent 1 --delay 2
```

**"Poor nl_examples quality"**
```bash
# Increase examples count
python template_generator.py --input urls.json --examples 7

# Try OpenAI for better quality
python template_generator.py --input urls.json --use-openai
```

## Example Workflow

```bash
# 1. Extract URLs from company website
python url-extractor.py \
    --sitemap https://acme.com/sitemap.xml \
    --output acme_urls.json \
    --max-pages 50

# 2. Generate templates (development - quick mode)
python template_generator.py \
    --input acme_urls.json \
    --output acme_templates.yaml \
    --quick \
    --verbose

# 3. Review and refine templates
# (manually edit acme_templates.yaml if needed)

# 4. Regenerate with full content sampling
python template_generator.py \
    --input acme_urls.json \
    --output acme_templates.yaml \
    --examples 5

# 5. Copy to production config
cp acme_templates.yaml ../config/adapters/templates/firecrawl_templates.yaml

# 6. Test queries against the retriever
# (use your application's query interface)
```

## File Structure

```
utils/scraping/
├── template_pipeline.py       # Main orchestrator
├── template_generator.py      # Template generation logic
├── url-extractor.py          # URL extraction from sitemaps
├── TEMPLATE_PIPELINE_README.md  # This documentation
├── .template_cache/          # Cache directory (auto-created)
│   ├── content_*.json        # Cached page content
│   └── examples_*.json       # Cached NL examples
└── config.yaml               # Ollama/LLM configuration
```

## Output Files

After running the pipeline:

```
./templates/
├── urls.json                 # Extracted URLs
├── firecrawl_templates.yaml  # Intent templates
└── firecrawl_domain.yaml     # Domain configuration
```
