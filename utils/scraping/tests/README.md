# Test Files for Firecrawl URL Extractor

This directory contains test files to help you test the `firecrawl-url-extractor.py` script.

## Files

- **`test-website.html`** - A comprehensive test HTML file with multiple internal links
- **`test-local-server.py`** - A simple HTTP server to serve the test HTML locally
- **`README.md`** - This file

## Test HTML Features

The `test-website.html` file includes:

- **Navigation Links**: Main menu with common website sections
- **Blog Links**: Nested blog structure with dates and categories
- **Documentation Links**: API docs, guides, and examples
- **Support Links**: Help center, knowledge base, community
- **Product Links**: Software, services, consulting
- **Company Links**: Team, history, careers, press
- **Legal Links**: Privacy policy, terms of service
- **Resource Links**: Downloads, whitepapers, webinars
- **Deep Nested Links**: Multi-level URL structures
- **JavaScript-Generated Links**: Dynamic content created after page load
- **External Links**: These should NOT be extracted (for testing filtering)

## Testing Locally

### Option 1: Use the Python HTTP Server

1. Navigate to the tests directory:
   ```bash
   cd tests
   ```

2. Start the local server:
   ```bash
   python test-local-server.py
   ```

3. Open your browser and go to:
   ```
   http://localhost:8000/test-website.html
   ```

4. The server will show you all available HTML files and their URLs.

### Option 2: Use Python's Built-in Server

1. Navigate to the tests directory:
   ```bash
   cd tests
   ```

2. Start Python's built-in HTTP server:
   ```bash
   python -m http.server 8000
   ```

3. Open your browser and go to:
   ```
   http://localhost:8000/test-website.html
   ```

## Testing with URL Extractor Scripts

You can test both the `url-extractor.py` (traditional crawling) and `firecrawl-url-extractor.py` (Firecrawl-based) scripts with the test HTML.

### Testing with Traditional URL Extractor

The `url-extractor.py` script crawls websites starting from a sitemap or single URL:

```bash
# Extract URLs from the test website (single URL mode)
python url-extractor.py --url http://localhost:8000/test-website.html --output test-urls-traditional.json

# Test with different crawling parameters
python url-extractor.py --url http://localhost:8000/test-website.html --max-depth 2 --delay 0.5 --output test-urls-depth2.json

# Test conservative crawling
python url-extractor.py --url http://localhost:8000/test-website.html --max-depth 1 --delay 1.0 --output test-urls-conservative.json
```

### Testing with Firecrawl URL Extractor

The `firecrawl-url-extractor.py` script uses Firecrawl for more advanced web scraping:

```bash
# Basic test
python firecrawl-url-extractor.py --url http://localhost:8000/test-website.html --output test-results.json

# Test with different parameters
python firecrawl-url-extractor.py --url http://localhost:8000/test-website.html --max-depth 1 --output test-depth1.json

# Test page-limited crawling
python firecrawl-url-extractor.py --url http://localhost:8000/test-website.html --max-pages 20 --output test-limited.json

# Test with delay between requests
python firecrawl-url-extractor.py --url http://localhost:8000/test-website.html --delay 0.5 --output test-delayed.json
```

### Comparing Both Extractors

You can compare the results from both extractors:

```bash
# Extract with traditional method
python url-extractor.py --url http://localhost:8000/test-website.html --output test-traditional.json

# Extract with Firecrawl
python firecrawl-url-extractor.py --url http://localhost:8000/test-website.html --output test-firecrawl.json

# Compare the results
echo "Traditional extractor found:"
jq length test-traditional.json
echo "Firecrawl extractor found:"
jq length test-firecrawl.json
```

## Testing with Docling Crawler

After extracting URLs with the Firecrawl extractor, you can test the `docling-crawler.py` script to convert the HTML pages to markdown:

### Convert Single Test Page
```bash
# Convert the test HTML page directly to markdown
python docling-crawler.py --url http://localhost:8000/test-website.html ./test-output --filename test-website.md
```

### Convert Extracted URLs to Markdown
```bash
# First extract URLs
python firecrawl-url-extractor.py --url http://localhost:8000/test-website.html --output test-urls.json

# Then convert all extracted URLs to markdown
python docling-crawler.py test-urls.json ./test-output

# Or process with custom settings
python docling-crawler.py test-urls.json ./test-output --max-concurrent 3 --max-retries 2
```

### Test with Different Docling Settings
```bash
# Conservative settings for testing
python docling-crawler.py test-urls.json ./test-output --max-concurrent 2 --max-retries 3

# Faster processing (use with caution)
python docling-crawler.py test-urls.json ./test-output --max-concurrent 10 --max-retries 1
```

### Complete Testing Workflows

#### Workflow 1: Firecrawl + Docling Pipeline
```bash
# 1. Start the test server
cd tests
python test-local-server.py

# 2. In another terminal, extract URLs with Firecrawl
python firecrawl-url-extractor.py --url http://localhost:8000/test-website.html --output test-urls-firecrawl.json

# 3. Convert to markdown
python docling-crawler.py test-urls-firecrawl.json ./test-markdown-firecrawl

# 4. Check the results
ls -la ./test-markdown-firecrawl/
cat ./test-markdown-firecrawl/*.md | head -20
```

#### Workflow 2: Traditional + Docling Pipeline
```bash
# 1. Start the test server
cd tests
python test-local-server.py

# 2. In another terminal, extract URLs with traditional extractor
python url-extractor.py --url http://localhost:8000/test-website.html --output test-urls-traditional.json

# 3. Convert to markdown
python docling-crawler.py test-urls-traditional.json ./test-markdown-traditional

# 4. Check the results
ls -la ./test-markdown-traditional/
cat ./test-markdown-traditional/*.md | head -20
```

#### Workflow 3: Compare Both Extractors
```bash
# 1. Start the test server
cd tests
python test-local-server.py

# 2. Extract URLs with both methods
python url-extractor.py --url http://localhost:8000/test-website.html --output test-urls-traditional.json
python firecrawl-url-extractor.py --url http://localhost:8000/test-website.html --output test-urls-firecrawl.json

# 3. Compare URL extraction results
echo "Traditional extractor found:"
jq length test-urls-traditional.json
echo "Firecrawl extractor found:"
jq length test-urls-firecrawl.json

# 4. Convert both to markdown for comparison
python docling-crawler.py test-urls-traditional.json ./test-markdown-traditional
python docling-crawler.py test-urls-firecrawl.json ./test-markdown-firecrawl

# 5. Compare markdown outputs
echo "Traditional markdown files:"
ls -la ./test-markdown-traditional/
echo "Firecrawl markdown files:"
ls -la ./test-markdown-firecrawl/
```

## Expected Results

The extractor should:

✅ **Extract** internal links like:
- `about.html`
- `services.html`
- `blog/index.html`
- `docs/api.html`
- `support/help.html`
- `products/software-suite.html`
- `blog/2024/01/winter-update.html`

❌ **NOT extract** external links like:
- `https://www.google.com`
- `https://github.com`
- `https://stackoverflow.com`

## Testing JavaScript-Rendered Content

The test HTML includes JavaScript that creates additional links after the page loads. This tests Firecrawl's ability to handle JavaScript-rendered content:

- `dynamic/page1.html`
- `dynamic/page2.html`
- `dynamic/page3.html`

## Notes

- All links in the test HTML are fictional and for testing purposes only
- The HTML includes various link structures to test different crawling scenarios
- External links are clearly marked and should be filtered out by the extractor
- The file includes CSS styling to make it look like a real website
- JavaScript-generated content tests modern web scraping capabilities

## Requirements and Dependencies

Before testing, ensure you have the required dependencies installed:

```bash
# Install from the main requirements.txt
pip install -r requirements.txt

# Or install specific packages for testing
pip install firecrawl-py python-dotenv docling torch beautifulsoup4 lxml
```

**Note**: The `docling-crawler.py` script requires PyTorch, which may have specific installation requirements depending on your system. See the main `INSTALL.md` file for detailed PyTorch installation instructions.

## Troubleshooting

- If port 8000 is in use, the test server will suggest an alternative port
- Make sure you have the required dependencies installed (`firecrawl-py`, `python-dotenv`, `docling`, `torch`)
- Ensure your Firecrawl API key is set via environment variable or command line argument
- The local server only serves files from the tests directory for security
- For PyTorch installation issues, check the main project's `INSTALL.md` file
- Memory issues with docling: reduce `--max-concurrent` value
