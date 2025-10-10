# Installation Guide for QA Pipeline

## Quick Start

For most systems:
```bash
pip install -r requirements.txt
```

## Mac Installation (Apple Silicon & Intel)

Due to PyTorch dependencies in docling, Mac users should follow these steps:

### ⚠️ Python 3.13 Users
PyTorch doesn't yet support Python 3.13. You have three options:

1. **Use Python 3.11 or 3.12** (Recommended)
2. **Skip docling** and use the minimal installation
3. **Use the pipeline without docling** (provide markdown files directly)

### Option 1: Install with Python 3.11/3.12 (Recommended)

```bash
# Install Python 3.11 or 3.12 using homebrew
brew install python@3.11
# or
brew install python@3.12

# Create virtual environment with Python 3.11/3.12
python3.11 -m venv venv
source venv/bin/activate

# Now install PyTorch
pip install torch torchvision

# Install remaining dependencies
pip install -r requirements.txt
```

### Option 2: Use conda/mamba (Alternative)

If you encounter issues with pip, use conda:

```bash
# Create new environment
conda create -n qa-pipeline python=3.10
conda activate qa-pipeline

# Install PyTorch
conda install pytorch torchvision -c pytorch

# Install remaining packages
pip install -r requirements.txt
```

### Option 3: Minimal installation (Without docling)

If you only need URL extraction and QA generation (without docling):

```bash
# Create minimal requirements file
cat > requirements-minimal.txt << EOF
aiohttp>=3.12.15
nest-asyncio>=1.6.0
beautifulsoup4>=4.13.4
requests>=2.31.0
python-dotenv==1.0.0
google-generativeai>=0.3.0
markdown>=3.4.0
EOF

pip install -r requirements-minimal.txt
```

Note: Without docling, you'll need to provide markdown files directly for the QA generation step.

## Troubleshooting

### Playwright backend fails: "BrowserType.launch: Executable doesn't exist .../ms-playwright"

Playwright Python needs browser binaries downloaded once per machine/user.

Fix:

```bash
# Ensure playwright is installed
pip install playwright

# Then download browsers (Chromium is enough for this repo)
python -m playwright install chromium
# or
playwright install chromium
```

Notes:
- If you use a virtualenv, run the install command inside it.
- macOS default cache is `~/Library/Caches/ms-playwright`. You can override with `PLAYWRIGHT_BROWSERS_PATH`.
- If corporate proxies block downloads, you can try launching the system Chrome with the scraper (no download) by ensuring Google Chrome is installed; the scraper will attempt this fallback automatically.
- Linux servers may also require dependencies: `python -m playwright install --with-deps`.

### Error: "Cannot install docling because these package versions have conflicting dependencies"

**Solution**: Install PyTorch separately first:
```bash
pip install torch
pip install docling
pip install -r requirements.txt
```

### Error: "No module named 'torch'"

**Solution**: Install PyTorch for your system:
```bash
# Check your Python version
python --version

# Install appropriate PyTorch
pip install torch torchvision
```

### Error: SSL Certificate issues

**Solution**: Update certificates:
```bash
pip install --upgrade certifi
```

### Error: Memory issues on M1/M2/M3 Macs

**Solution**: Set memory limits:
```bash
export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.7
```

## Verifying Installation

Test each component:

```bash
# Test URL extractor (no special dependencies)
python url-extractor.py --help

# Test docling crawler (requires torch/docling)
python docling-crawler.py --help

# Test QA generator (requires google-generativeai)
python google_question_extractor.py --help

# Test pipeline orchestrator
python pipeline_orchestrator.py --help
```

## Environment Variables

Create a `.env` file for the Google Gemini API:

```bash
echo "GOOGLE_API_KEY=your_api_key_here" > .env
```

Get your API key from: https://makersuite.google.com/app/apikey

## Running the Pipeline

After successful installation:

```bash
# Run complete pipeline
python pipeline_orchestrator.py --sitemap https://example.com/sitemap.xml

# Or run individual components
python url-extractor.py --sitemap https://example.com/sitemap.xml
python docling-crawler.py urls.json ./docs
python google_question_extractor.py --input ./docs --output qa_pairs.json
```

## Docker Alternative

If you continue having issues, consider using Docker:

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch first
RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Copy and install requirements
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY *.py ./

CMD ["python", "pipeline_orchestrator.py"]
```

Build and run:
```bash
docker build -t qa-pipeline .
docker run -v $(pwd)/output:/app/output qa-pipeline
```
