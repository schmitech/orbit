#!/usr/bin/env python3
"""
Unified Web Scraper - Multiple Backend Support

This script provides a unified interface for web scraping using multiple backends:
- Trafilatura (free, fast article extraction)
- Docling (free, local processing, good for documents)
- Playwright (free, handles JavaScript, browser automation)
- Jina Reader (free tier, API-based, simple)
- Firecrawl (paid API, advanced features, best for complex sites)

Features:
- Intelligent backend selection with cost optimization
- Automatic fallback chain from free to paid backends
- Unified output format (markdown with frontmatter)
- Progress tracking and statistics for all backends
- Cost-aware processing (prefers free backends when possible)

Usage:
------
# Auto mode - tries free backends first, falls back to paid
python unified-scraper.py urls.json ./output

# Fast article extraction (free)
python unified-scraper.py urls.json ./output --backend trafilatura

# JavaScript-heavy sites (free)
python unified-scraper.py urls.json ./output --backend playwright

# Simple API-based scraping (free tier)
python unified-scraper.py urls.json ./output --backend jina

# Advanced features (paid)
python unified-scraper.py urls.json ./output --backend firecrawl --screenshots --mobile

# Custom fallback chain
python unified-scraper.py urls.json ./output --fallback-chain trafilatura,playwright,firecrawl
"""

import asyncio
import json
import os
import argparse
import time
import hashlib
import random
from pathlib import Path
from typing import List, Dict, Optional, Any
from urllib.parse import urlparse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Try importing all backends
TRAFILATURA_AVAILABLE = False
DOCLING_AVAILABLE = False
PLAYWRIGHT_AVAILABLE = False
JINA_AVAILABLE = False
FIRECRAWL_AVAILABLE = False

try:
    import trafilatura
    TRAFILATURA_AVAILABLE = True
except ImportError:
    print("⚠ Trafilatura not available. Install with: pip install trafilatura")

try:
    from docling.document_converter import DocumentConverter
    DOCLING_AVAILABLE = True
except ImportError:
    print("⚠ Docling not available. Install with: pip install docling")

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    print("⚠ Playwright not available. Install with: pip install playwright && playwright install")

try:
    import aiohttp
    JINA_AVAILABLE = True
except ImportError:
    print("⚠ Jina Reader not available. Install with: pip install aiohttp")

try:
    from firecrawl import AsyncFirecrawlApp
    import base64
    FIRECRAWL_AVAILABLE = True
except ImportError:
    print("⚠ Firecrawl not available. Install with: pip install firecrawl-py")


class UnifiedScraper:
    """Unified scraper that can use either Docling or Firecrawl backend."""
    
    def __init__(self, output_dir: str, config: Dict[str, Any]):
        """Initialize the unified scraper with configuration."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.config = config
        self.backend = config.get('backend', 'auto')
        
        # Initialize backends based on availability and configuration
        self.docling_converter = None
        self.firecrawl_app = None
        self.playwright_browser = None
        
        # Define fallback chain
        if config.get('fallback_chain'):
            self.fallback_chain = config['fallback_chain']
        else:
            # Default: free backends first, then paid
            self.fallback_chain = ['trafilatura', 'docling', 'playwright', 'jina', 'firecrawl']
        
        # Initialize available backends
        self.available_backends = []
        
        if TRAFILATURA_AVAILABLE:
            self.available_backends.append('trafilatura')
            print("✓ Trafilatura backend available (free, fast articles)")
        
        if DOCLING_AVAILABLE:
            self.docling_converter = DocumentConverter()
            self.available_backends.append('docling')
            print("✓ Docling backend initialized (free, documents)")
        
        if PLAYWRIGHT_AVAILABLE:
            self.available_backends.append('playwright')
            print("✓ Playwright backend available (free, JavaScript support)")
        
        if JINA_AVAILABLE:
            self.available_backends.append('jina')
            print("✓ Jina Reader backend available (free tier, API)")
        
        if FIRECRAWL_AVAILABLE:
            api_key = config.get('firecrawl_api_key') or os.getenv('FIRECRAWL_API_KEY')
            if api_key:
                self.firecrawl_app = AsyncFirecrawlApp(api_key=api_key)
                self.available_backends.append('firecrawl')
                print("✓ Firecrawl backend initialized (paid, advanced features)")
            else:
                print("⚠ Firecrawl API key not found. Set FIRECRAWL_API_KEY or use --firecrawl-api-key")
        
        # Cache directory for both backends
        self.cache_dir = Path(config.get('cache_dir', '.unified_cache'))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Statistics tracking
        self.stats = {
            'total': 0,
            'successful': 0,
            'failed': 0,
            'trafilatura_success': 0,
            'docling_success': 0,
            'playwright_success': 0,
            'jina_success': 0,
            'firecrawl_success': 0,
            'fallback_used': 0,
            'from_cache': 0,
            'errors': []
        }
        
        # Progress file
        self.progress_file = self.output_dir / 'scraping_progress.json'
    
    def get_cache_path(self, url: str, backend: str) -> Path:
        """Generate cache file path for a URL and backend."""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return self.cache_dir / f"{backend}_{url_hash}.json"
    
    def load_from_cache(self, url: str, backend: str) -> Optional[Dict]:
        """Load cached response for a URL if available."""
        if not self.config.get('use_cache', True):
            return None
        
        cache_path = self.get_cache_path(url, backend)
        if cache_path.exists():
            cache_age = time.time() - cache_path.stat().st_mtime
            max_age = self.config.get('cache_max_age', 7 * 24 * 3600)
            
            if cache_age < max_age:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        return None
    
    def save_to_cache(self, url: str, backend: str, content: Dict):
        """Save content to cache."""
        if self.config.get('use_cache', True):
            cache_path = self.get_cache_path(url, backend)
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(content, f, indent=2)
    
    async def scrape_with_trafilatura(self, url: str, max_retries: int = 3) -> Optional[Dict]:
        """Scrape using Trafilatura (free, fast article extraction)."""
        if not TRAFILATURA_AVAILABLE:
            return None
        
        # Check cache
        cached = self.load_from_cache(url, 'trafilatura')
        if cached:
            print(f"  ✓ Using cached Trafilatura content for: {url}")
            self.stats['from_cache'] += 1
            return cached
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    backoff = 2 ** attempt + random.uniform(0, 1)
                    print(f"  Retrying Trafilatura after {backoff:.1f}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(backoff)
                
                # Download and extract with Trafilatura
                downloaded = await asyncio.to_thread(trafilatura.fetch_url, url)
                if not downloaded:
                    continue
                
                extracted = await asyncio.to_thread(
                    trafilatura.extract, 
                    downloaded, 
                    output_format='markdown',
                    include_comments=False,
                    include_tables=True
                )
                
                if extracted and len(extracted.strip()) > 100:
                    content = {
                        'markdown': extracted,
                        'backend': 'trafilatura',
                        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    # Extract title from markdown
                    lines = extracted.split('\n')
                    for line in lines[:5]:
                        if line.strip().startswith('#'):
                            content['title'] = line.strip('#').strip()
                            break
                    
                    self.save_to_cache(url, 'trafilatura', content)
                    return content
                    
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"  ✗ Trafilatura failed for {url}: {str(e)[:100]}")
                    
        return None

    async def scrape_with_docling(self, url: str, max_retries: int = 3) -> Optional[Dict]:
        """Scrape using Docling (free, local processing)."""
        if not self.docling_converter:
            return None
        
        # Check cache
        cached = self.load_from_cache(url, 'docling')
        if cached:
            print(f"  ✓ Using cached Docling content for: {url}")
            self.stats['from_cache'] += 1
            return cached
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    backoff = 2 ** attempt + random.uniform(0, 1)
                    print(f"  Retrying Docling after {backoff:.1f}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(backoff)
                
                # Convert using Docling
                result = await asyncio.to_thread(self.docling_converter.convert, url)
                
                if result and result.document:
                    content = {
                        'markdown': result.document.export_to_markdown(),
                        'backend': 'docling',
                        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    # Extract title if possible
                    markdown_lines = content['markdown'].split('\n')
                    for line in markdown_lines[:10]:
                        if line.strip().startswith('#'):
                            content['title'] = line.strip('#').strip()
                            break
                    
                    self.save_to_cache(url, 'docling', content)
                    return content
                    
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"  ✗ Docling failed for {url}: {str(e)[:100]}")
                    
        return None
    
    async def scrape_with_firecrawl(self, url: str, max_retries: int = 3) -> Optional[Dict]:
        """Scrape using Firecrawl (paid API, advanced features)."""
        if not self.firecrawl_app:
            return None
        
        # Check cache
        cached = self.load_from_cache(url, 'firecrawl')
        if cached:
            print(f"  ✓ Using cached Firecrawl content for: {url}")
            self.stats['from_cache'] += 1
            return cached
        
        # Build Firecrawl parameters
        params = {
            'formats': ['markdown'],
            'timeout': self.config.get('timeout', 30000),
            'mobile': self.config.get('mobile', False)
        }
        
        # Add screenshots if requested
        if self.config.get('screenshots'):
            params['actions'] = [{'type': 'screenshot', 'fullPage': True}]
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    backoff = 2 ** attempt + random.uniform(0, 1)
                    print(f"  Retrying Firecrawl after {backoff:.1f}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(backoff)
                
                # Add delay if configured
                if self.config.get('request_delay', 0) > 0:
                    await asyncio.sleep(self.config['request_delay'])
                
                # Scrape with Firecrawl
                response = await self.firecrawl_app.v1.scrape_url(url, **params)
                
                if response:
                    response_dict = dict(response)
                    content = {
                        'markdown': response_dict.get('markdown', ''),
                        'backend': 'firecrawl',
                        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    # Add metadata if available
                    if 'metadata' in response_dict:
                        content['title'] = response_dict['metadata'].get('title')
                        content['description'] = response_dict['metadata'].get('description')
                    
                    # Add screenshot if available
                    if 'screenshot' in response_dict:
                        content['screenshot'] = response_dict['screenshot']
                    
                    self.save_to_cache(url, 'firecrawl', content)
                    return content
                    
            except Exception as e:
                error_msg = str(e)
                if 'rate' in error_msg.lower() or '429' in error_msg:
                    wait_time = 2 ** (attempt + 1)
                    print(f"  ⚠ Rate limited. Waiting {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                    
                if attempt == max_retries - 1:
                    print(f"  ✗ Firecrawl failed for {url}: {error_msg[:100]}")
                    
        return None
    
    async def scrape_with_playwright(self, url: str, max_retries: int = 3) -> Optional[Dict]:
        """Scrape using Playwright (free, handles JavaScript)."""
        if not PLAYWRIGHT_AVAILABLE:
            return None
        
        # Check cache
        cached = self.load_from_cache(url, 'playwright')
        if cached:
            print(f"  ✓ Using cached Playwright content for: {url}")
            self.stats['from_cache'] += 1
            return cached
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    backoff = 2 ** attempt + random.uniform(0, 1)
                    print(f"  Retrying Playwright after {backoff:.1f}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(backoff)
                
                async with async_playwright() as p:
                    # Try to launch bundled Chromium; on failure, attempt system Chrome channel
                    try:
                        browser = await p.chromium.launch(headless=True)
                    except Exception as launch_err:
                        err_msg = str(launch_err)
                        if 'Executable doesn\'t exist' in err_msg or 'executable doesn\'t exist' in err_msg.lower():
                            print("  ⚠ Playwright browsers not installed. Run: `python -m playwright install chromium` (or `playwright install chromium`) and retry.")
                            print("    Falling back to system Chrome channel if available...")
                            try:
                                browser = await p.chromium.launch(channel="chrome", headless=True)
                            except Exception:
                                # Re-raise original error to keep context for final attempt handling
                                raise launch_err
                        else:
                            # If it's a different error, propagate
                            raise
                    context = await browser.new_context(
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    )
                    page = await context.new_page()
                    
                    # Navigate to page
                    await page.goto(url, timeout=30000, wait_until='networkidle')
                    
                    # Wait for content to load
                    await page.wait_for_timeout(2000)
                    
                    # Get page content
                    title = await page.title()
                    
                    # Remove navigation, ads, etc.
                    await page.evaluate("""
                        // Remove common unwanted elements
                        const selectors = ['nav', 'header', 'footer', '.advertisement', '.ad', '.sidebar', '.menu'];
                        selectors.forEach(sel => {
                            document.querySelectorAll(sel).forEach(el => el.remove());
                        });
                    """)
                    
                    # Get main content
                    content_selector = 'main, article, .content, .post, .entry, #content, #main'
                    main_content = await page.query_selector(content_selector)
                    
                    if main_content:
                        text_content = await main_content.inner_text()
                    else:
                        text_content = await page.evaluate('document.body.innerText')
                    
                    await browser.close()
                    
                    if text_content and len(text_content.strip()) > 100:
                        # Convert to simple markdown
                        markdown_content = self._text_to_markdown(text_content, title)
                        
                        content = {
                            'markdown': markdown_content,
                            'title': title,
                            'backend': 'playwright',
                            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                        }
                        
                        self.save_to_cache(url, 'playwright', content)
                        return content
                    
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"  ✗ Playwright failed for {url}: {str(e)[:100]}")
                    
        return None
    
    async def scrape_with_jina(self, url: str, max_retries: int = 3) -> Optional[Dict]:
        """Scrape using Jina Reader API (free tier, simple API)."""
        if not JINA_AVAILABLE:
            return None
        
        # Check cache
        cached = self.load_from_cache(url, 'jina')
        if cached:
            print(f"  ✓ Using cached Jina content for: {url}")
            self.stats['from_cache'] += 1
            return cached
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    backoff = 2 ** attempt + random.uniform(0, 1)
                    print(f"  Retrying Jina after {backoff:.1f}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(backoff)
                
                # Add delay if configured
                if self.config.get('request_delay', 0) > 0:
                    await asyncio.sleep(self.config['request_delay'])
                
                # Use Jina Reader API
                jina_url = f"https://r.jina.ai/{url}"
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(jina_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        if response.status == 200:
                            markdown_content = await response.text()
                            
                            if markdown_content and len(markdown_content.strip()) > 100:
                                content = {
                                    'markdown': markdown_content,
                                    'backend': 'jina',
                                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                                }
                                
                                # Extract title from markdown
                                lines = markdown_content.split('\n')
                                for line in lines[:10]:
                                    if line.strip().startswith('#'):
                                        content['title'] = line.strip('#').strip()
                                        break
                                
                                self.save_to_cache(url, 'jina', content)
                                return content
                        else:
                            print(f"  ⚠ Jina API returned status {response.status}")
                    
            except Exception as e:
                error_msg = str(e)
                if 'rate' in error_msg.lower() or '429' in error_msg:
                    wait_time = 2 ** (attempt + 1)
                    print(f"  ⚠ Rate limited. Waiting {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                    
                if attempt == max_retries - 1:
                    print(f"  ✗ Jina failed for {url}: {error_msg[:100]}")
                    
        return None
    
    def _text_to_markdown(self, text: str, title: str = None) -> str:
        """Convert plain text to simple markdown format."""
        lines = text.split('\n')
        markdown_lines = []
        
        # Add title if provided
        if title:
            markdown_lines.append(f"# {title}\n")
        
        # Process text lines
        for line in lines:
            line = line.strip()
            if not line:
                markdown_lines.append("")
                continue
                
            # Simple heuristics for formatting
            if len(line) < 100 and not line.endswith('.') and not line.endswith(':'):
                # Likely a heading
                markdown_lines.append(f"## {line}")
            else:
                # Regular paragraph
                markdown_lines.append(line)
        
        return '\n'.join(markdown_lines)
    
    async def scrape_url(self, url: str) -> Optional[Dict]:
        """Scrape a URL using configured backend with intelligent fallback."""
        content = None
        
        # Define backend methods
        backend_methods = {
            'trafilatura': self.scrape_with_trafilatura,
            'docling': self.scrape_with_docling,
            'playwright': self.scrape_with_playwright,
            'jina': self.scrape_with_jina,
            'firecrawl': self.scrape_with_firecrawl
        }
        
        if self.backend in backend_methods:
            # Single backend mode
            method = backend_methods[self.backend]
            backend_name = self.backend.title()
            cost_info = "(free)" if self.backend != 'firecrawl' else "(paid)"
            
            print(f"→ Scraping with {backend_name} {cost_info}: {url}")
            content = await method(url)
            
            if content:
                self.stats[f'{self.backend}_success'] += 1
                print(f"  ✓ Success with {backend_name}")
                
        else:  # auto mode - try fallback chain
            print(f"→ Auto mode - trying backends in order: {url}")
            
            # Filter fallback chain to only available backends
            available_chain = [b for b in self.fallback_chain if b in self.available_backends]
            
            for i, backend_name in enumerate(available_chain):
                if backend_name not in backend_methods:
                    continue
                    
                cost_info = "(free)" if backend_name != 'firecrawl' else "(paid)"
                
                if i == 0:
                    print(f"  Trying {backend_name.title()} {cost_info}")
                else:
                    print(f"  ⟲ Falling back to {backend_name.title()} {cost_info}")
                
                method = backend_methods[backend_name]
                content = await method(url)
                
                if content:
                    self.stats[f'{backend_name}_success'] += 1
                    if i > 0:
                        self.stats['fallback_used'] += 1
                    print(f"  ✓ Success with {backend_name.title()}")
                    break
                else:
                    print(f"  ✗ {backend_name.title()} failed")
        
        return content
    
    async def process_and_save(self, url: str, file_name: str):
        """Process a URL and save the content."""
        self.stats['total'] += 1
        
        # Scrape the URL
        content = await self.scrape_url(url)
        
        if not content:
            print(f"✗ Failed to scrape: {url}")
            self.stats['failed'] += 1
            self.stats['errors'].append({'url': url, 'error': 'All backends failed'})
            self.save_progress()
            return
        
        # Prepare output file
        output_path = self.output_dir / file_name
        if not output_path.suffix:
            output_path = output_path.with_suffix('.md')
        
        # Save markdown with frontmatter
        with open(output_path, 'w', encoding='utf-8') as f:
            # Write frontmatter
            f.write("---\n")
            f.write(f"source: {url}\n")
            f.write("scraped_with: unified-scraper\n")
            f.write(f"backend: {content['backend']}\n")
            f.write(f"scraped_at: {content['timestamp']}\n")
            
            if content.get('title'):
                f.write(f"title: {content['title']}\n")
            if content.get('description'):
                f.write(f"description: {content['description']}\n")
                
            f.write("---\n\n")
            
            # Write markdown content
            f.write(content['markdown'])
        
        # Save screenshot if available (Firecrawl only)
        if content.get('screenshot'):
            screenshots_dir = self.output_dir / 'screenshots'
            screenshots_dir.mkdir(exist_ok=True)
            
            screenshot_data = content['screenshot']
            if isinstance(screenshot_data, str) and screenshot_data.startswith('data:image'):
                base64_data = screenshot_data.split(',')[1]
                image_data = base64.b64decode(base64_data)
                
                screenshot_path = screenshots_dir / f"{output_path.stem}.png"
                with open(screenshot_path, 'wb') as f:
                    f.write(image_data)
                print(f"  ✓ Saved screenshot: {screenshot_path}")
        
        print(f"✓ Saved: {output_path} (via {content['backend']})")
        self.stats['successful'] += 1
        self.save_progress()
    
    async def process_batch(self, urls_batch: List[Dict[str, str]]):
        """Process a batch of URLs concurrently."""
        tasks = []
        for entry in urls_batch:
            url = entry['url']
            file_name = entry['file_name']
            task = self.process_and_save(url, file_name)
            tasks.append(task)
        
        await asyncio.gather(*tasks)
    
    def save_progress(self):
        """Save current progress to file."""
        progress_data = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'statistics': self.stats,
            'backend_config': {
                'primary': self.backend,
                'docling_available': bool(self.docling_converter),
                'firecrawl_available': bool(self.firecrawl_app)
            }
        }
        
        try:
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                json.dump(progress_data, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save progress: {e}")
    
    def print_statistics(self):
        """Print detailed statistics."""
        print("\n" + "="*60)
        print("SCRAPING STATISTICS")
        print("="*60)
        print(f"Total URLs processed: {self.stats['total']}")
        print(f"Successfully scraped: {self.stats['successful']}")
        print(f"Failed: {self.stats['failed']}")
        print(f"From cache: {self.stats['from_cache']}")
        
        # Show backend-specific successes
        backend_stats = []
        for backend in ['trafilatura', 'docling', 'playwright', 'jina', 'firecrawl']:
            count = self.stats.get(f'{backend}_success', 0)
            if count > 0:
                cost_info = "(free)" if backend != 'firecrawl' else "(paid)"
                backend_stats.append(f"{backend.title()} {cost_info}: {count}")
        
        if backend_stats:
            print("Backend successes:")
            for stat in backend_stats:
                print(f"  - {stat}")
        
        if self.stats['fallback_used'] > 0:
            print(f"Fallbacks used: {self.stats['fallback_used']}")
        
        # Cost estimation
        firecrawl_count = self.stats.get('firecrawl_success', 0)
        jina_count = self.stats.get('jina_success', 0)  # Jina has free tier
        
        if firecrawl_count > 0 or jina_count > 0:
            print("\nCost estimation:")
            if firecrawl_count > 0:
                estimated_cost = firecrawl_count * 0.01  # $0.01 per scrape estimate
                print(f"  Firecrawl cost: ~${estimated_cost:.2f}")
            if jina_count > 0:
                if jina_count <= 1000:  # Assuming 1000 free requests per month
                    print(f"  Jina Reader: Free tier ({jina_count} requests)")
                else:
                    excess = jina_count - 1000
                    print(f"  Jina Reader: Free tier + ${excess * 0.002:.2f} for {excess} excess")
            
            free_count = sum(self.stats.get(f'{b}_success', 0) for b in ['trafilatura', 'docling', 'playwright'])
            if free_count > 0:
                saved_amount = free_count * 0.01
                print(f"  Saved by free backends: ~${saved_amount:.2f}")
        
        if self.stats['errors']:
            print("\nErrors encountered:")
            for error in self.stats['errors'][:5]:
                print(f"  - {error['url']}: {error['error']}")
            if len(self.stats['errors']) > 5:
                print(f"  ... and {len(self.stats['errors']) - 5} more")
        
        print("="*60)


async def main(input_source: str, output_dir: str, args):
    """Main function to coordinate scraping."""
    
    # Build configuration
    config = {
        'backend': args.backend,
        'auto_fallback': args.auto_fallback,
        'use_cache': not args.no_cache,
        'cache_max_age': args.cache_max_age * 3600,
        'request_delay': args.delay,
        'timeout': args.timeout * 1000,
        'mobile': args.mobile,
        'screenshots': args.screenshots,
        'firecrawl_api_key': args.firecrawl_api_key
    }
    
    # Handle custom fallback chain
    if args.fallback_chain:
        config['fallback_chain'] = [b.strip() for b in args.fallback_chain.split(',')]
    
    # Check backend availability
    backend_availability = {
        'trafilatura': TRAFILATURA_AVAILABLE,
        'docling': DOCLING_AVAILABLE,
        'playwright': PLAYWRIGHT_AVAILABLE,
        'jina': JINA_AVAILABLE,
        'firecrawl': FIRECRAWL_AVAILABLE
    }
    
    if config['backend'] != 'auto':
        if not backend_availability.get(config['backend'], False):
            backend_install = {
                'trafilatura': 'pip install trafilatura',
                'docling': 'pip install docling',
                'playwright': 'pip install playwright && playwright install',
                'jina': 'pip install aiohttp (already installed)',
                'firecrawl': 'pip install firecrawl-py'
            }
            print(f"Error: {config['backend'].title()} backend requested but not available.")
            print(f"Install with: {backend_install.get(config['backend'], 'Unknown backend')}")
            return
    
    if config['backend'] == 'auto':
        available_backends = [name for name, available in backend_availability.items() if available]
        if not available_backends:
            print("Error: No backends available. Install at least one backend.")
            print("Recommended: pip install trafilatura (fast and free)")
            return
        
        print(f"Available backends: {', '.join(available_backends)}")
        
        # Special case: if only Firecrawl is available, warn about costs
        if available_backends == ['firecrawl']:
            print("Warning: Only Firecrawl available - this will cost money for API calls")
        elif 'firecrawl' not in available_backends:
            print("Info: Using free backends only (no Firecrawl API key)")
        
        # If only paid backends available, confirm
        free_backends = [b for b in available_backends if b != 'firecrawl']
        if not free_backends:
            response = input("Only paid backends available. Continue? (y/N): ")
            if response.lower() != 'y':
                return
    
    # Initialize scraper
    scraper = UnifiedScraper(output_dir, config)
    
    # Prepare URLs
    if args.url:
        # Single URL mode
        url = input_source
        print(f"Processing single URL: {url}")
        
        if args.filename:
            filename = args.filename
        else:
            parsed = urlparse(url)
            path_parts = parsed.path.strip('/').split('/')
            if path_parts and path_parts[-1]:
                filename = path_parts[-1].replace('.html', '') + '.md'
            else:
                filename = parsed.netloc.replace('.', '_') + '.md'
        
        urls = [{"url": url, "file_name": filename}]
    else:
        # Load URLs from JSON
        print(f"Loading URLs from: {input_source}")
        with open(input_source, 'r') as f:
            urls = json.load(f)
        
        # Filter out image URLs
        original_count = len(urls)
        image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg')
        urls = [u for u in urls if not u['url'].lower().endswith(image_extensions)]
        
        if original_count != len(urls):
            print(f"✓ Filtered out {original_count - len(urls)} image URLs")
    
    print(f"Found {len(urls)} URL(s) to process")
    print("Configuration:")
    print(f"  - Backend: {config['backend']}")
    print(f"  - Auto-fallback: {config['auto_fallback']}")
    print(f"  - Cache: {'enabled' if config['use_cache'] else 'disabled'}")
    if config.get('request_delay'):
        print(f"  - Request delay: {config['request_delay']}s")
    print("-" * 60)
    
    # Process URLs in batches
    batch_size = args.batch_size
    
    for i in range(0, len(urls), batch_size):
        batch = urls[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(urls) + batch_size - 1) // batch_size
        
        print(f"\nProcessing batch {batch_num}/{total_batches} ({len(batch)} URLs)")
        await scraper.process_batch(batch)
        
        if i + batch_size < len(urls):
            await asyncio.sleep(2)
    
    # Print statistics
    scraper.print_statistics()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Unified web scraper with Docling and Firecrawl backends',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Basic arguments
    parser.add_argument('input', help='JSON file or single URL')
    parser.add_argument('output_dir', help='Output directory')
    parser.add_argument('--url', action='store_true', help='Treat input as single URL')
    parser.add_argument('--filename', help='Output filename for single URL')
    
    # Backend selection
    parser.add_argument('--backend', choices=['auto', 'trafilatura', 'docling', 'playwright', 'jina', 'firecrawl'], 
                        default='auto', help='Backend to use (default: auto - tries free backends first)')
    parser.add_argument('--fallback-chain', help='Custom fallback order (comma-separated): trafilatura,docling,playwright,jina,firecrawl')
    parser.add_argument('--auto-fallback', action='store_true', default=True,
                        help='Automatically fallback through available backends (default: True)')
    parser.add_argument('--firecrawl-api-key', help='Firecrawl API key (or set FIRECRAWL_API_KEY env var)')
    
    # Processing options
    parser.add_argument('--batch-size', type=int, default=5, help='Batch size (default: 5)')
    parser.add_argument('--delay', type=float, default=0, help='Delay between requests in seconds')
    parser.add_argument('--timeout', type=int, default=30, help='Timeout in seconds (default: 30)')
    
    # Cache options
    parser.add_argument('--no-cache', action='store_true', help='Disable cache')
    parser.add_argument('--cache-max-age', type=int, default=168, help='Cache max age in hours (default: 168)')
    
    # Firecrawl-specific options
    parser.add_argument('--mobile', action='store_true', help='Emulate mobile device (Firecrawl only)')
    parser.add_argument('--screenshots', action='store_true', help='Capture screenshots (Firecrawl only)')
    
    args = parser.parse_args()
    
    # Run async main
    asyncio.run(main(args.input, args.output_dir, args))
