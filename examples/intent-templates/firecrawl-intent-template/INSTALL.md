# Firecrawl Adapter Installation

## Install Firecrawl Python SDK

The Firecrawl adapter requires the `firecrawl-py` package:

```bash
# Activate ORBIT virtual environment
source venv/bin/activate

# Install firecrawl-py
pip install firecrawl-py

# Verify installation
python -c "from firecrawl import FirecrawlApp; print('✓ firecrawl-py installed')"
```

## Set API Key

Get your API key from [firecrawl.dev](https://firecrawl.dev) and add it to your `.env` file in the project root:

```bash
# Add to .env file in project root
echo "FIRECRAWL_API_KEY=your-api-key-here" >> .env
```

Or set as environment variable (optional):

```bash
export FIRECRAWL_API_KEY="your-api-key-here"
```

The test script will automatically load the API key from `.env` in the project root directory.

## Test Installation

Run the Python test script:

```bash
python utils/firecrawl-intent-template/test_firecrawl_api.py
```

**Expected output:**
```
✓ API key found
✓ Firecrawl client initialized
✓ Test 1 PASSED
✓ Test 2 PASSED
✓ Test 3 PASSED
🎉 All tests passed!
```

## Usage in ORBIT

Once installed, the adapter will automatically use the firecrawl-py package via httpx in the retriever implementation.

## Troubleshooting

### Import Error: No module named 'firecrawl'

**Solution:**
```bash
source venv/bin/activate
pip install firecrawl-py
```

### API Key Not Found

**Solution:**
```bash
export FIRECRAWL_API_KEY="your-key"
# Or add to .env file
```

### Connection Errors

**Check:**
1. Internet connectivity
2. Firecrawl service status
3. API key validity
4. Account credits/limits

## Package Information

- **Package**: `firecrawl-py`
- **PyPI**: https://pypi.org/project/firecrawl-py/
- **GitHub**: https://github.com/mendableai/firecrawl
- **Docs**: https://docs.firecrawl.dev/
