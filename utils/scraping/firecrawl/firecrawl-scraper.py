#!/usr/bin/env python3
"""
Advanced Firecrawl Web Scraper with Enhanced Features

This enhanced version includes additional features from the Firecrawl API:
- Structured data extraction using LLM
- Screenshot capture
- Link extraction
- Metadata preservation
- Custom actions (wait, click, scroll)
- Location-based scraping
- Mobile emulation
- Rate limiting with configurable delays
- Fast mode with cached data (up to 500% faster)
- Real-time progress tracking and saving

Usage:
------
# Basic scraping
python firecrawl-scraper.py urls.json ./output

# Extract structured data with custom schema
python firecrawl-scraper.py urls.json ./output --extract-schema schema.json

# Mobile scraping with screenshots
python firecrawl-scraper.py urls.json ./output --mobile --screenshots

# Location-specific scraping
python firecrawl-scraper.py urls.json ./output --country US --language en

# Optimized scraping with rate limiting and fast mode
python firecrawl-scraper.py urls.json ./output --delay 0.5 --fast-mode --max-age-hours 2

# Single URL with custom settings
python firecrawl-scraper.py --url https://example.com ./output --delay 1 --screenshots

# Save results as JSON instead of Markdown
python firecrawl-scraper.py urls.json ./output --output-format json

# Save results as JSONL (one JSON object per line)
python firecrawl-scraper.py urls.json ./output --output-format jsonl

# Aggregate all results into a single JSONL file
python firecrawl-scraper.py urls.json ./output --output-format jsonl --aggregate-jsonl --aggregate-jsonl-file all-results.jsonl
"""

import asyncio
import json
import os
import argparse
import time
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Any
from urllib.parse import urlparse
from firecrawl import AsyncFirecrawlApp
import base64
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class AdvancedFirecrawlScraper:
    """Enhanced Firecrawl scraper with advanced features."""
    
    def __init__(self, api_key: str, output_dir: str, config: Dict[str, Any]):
        """Initialize the advanced scraper with configuration."""
        self.api_key = api_key
        self.output_dir = Path(output_dir)
        self.cache_dir = Path(config.get('cache_dir', '.firecrawl_cache'))
        self.config = config
        self.request_delay = config.get('request_delay', 0)  # Delay between requests
        
        # Create directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Create screenshots directory if needed
        if config.get('screenshots'):
            self.screenshots_dir = self.output_dir / 'screenshots'
            self.screenshots_dir.mkdir(exist_ok=True)
        
        # Aggregate JSONL setup (single file for all results)
        self.aggregate_jsonl = (
            self.config.get('output_format') == 'jsonl' and self.config.get('aggregate_jsonl', False)
        )
        if self.aggregate_jsonl:
            self.aggregate_path = self.output_dir / self.config.get('aggregate_jsonl_file', 'results.jsonl')
            try:
                # Initialize/overwrite aggregate file at start of run
                with open(self.aggregate_path, 'w', encoding='utf-8') as _:
                    pass
            except Exception as e:
                print(f"Warning: Could not initialize aggregate JSONL file: {e}")
            # Async lock to prevent concurrent writes
            self.aggregate_lock = asyncio.Lock()

        # Initialize Firecrawl client
        self.app = AsyncFirecrawlApp(api_key=api_key)
        
        # Statistics
        self.stats = {
            'total': 0,
            'successful': 0,
            'failed': 0,
            'cached': 0,
            'screenshots': 0,
            'structured_data': 0,
            'errors': []
        }
        
        # Progress tracking for real-time saving
        self.progress_file = self.output_dir / 'scraping_progress.json'
    
    def build_scrape_params(self, url: str) -> Dict[str, Any]:
        """Build scrape parameters based on configuration."""
        params = {
            'formats': self.config.get('formats', ['markdown']),
            'timeout': self.config.get('timeout', 30000),
            'mobile': self.config.get('mobile', False)
        }
        
        # Add fast mode with max_age parameter
        if self.config.get('fast_mode'):
            max_age_ms = int(self.config.get('max_age_hours', 1) * 3600000)  # Convert hours to milliseconds
            params['max_age'] = max_age_ms
        
        # Add proxy if configured
        if self.config.get('proxy'):
            params['proxy'] = self.config['proxy']  # "basic", "stealth", or "auto"
        
        # Add location settings
        if self.config.get('country') or self.config.get('language'):
            params['location'] = {}
            if self.config.get('country'):
                params['location']['country'] = self.config['country']
            if self.config.get('language'):
                params['location']['language'] = self.config['language']
        
        # Add include/exclude tags (use snake_case for AsyncFirecrawlApp)
        if self.config.get('include_tags'):
            params['include_tags'] = self.config['include_tags']
        if self.config.get('exclude_tags'):
            params['exclude_tags'] = self.config['exclude_tags']
        
        # Add actions (wait, click, screenshot, etc.)
        actions = []
        
        # Wait for content to load
        if self.config.get('wait_time'):
            actions.append({
                'type': 'wait',
                'milliseconds': self.config['wait_time']
            })
        
        # Wait for specific selector
        if self.config.get('wait_for'):
            actions.append({
                'type': 'wait',
                'selector': self.config['wait_for']
            })
        
        # Take screenshot
        if self.config.get('screenshots'):
            actions.append({
                'type': 'screenshot',
                'fullPage': self.config.get('full_page_screenshot', True)
            })
        
        # Click elements
        if self.config.get('click_selectors'):
            for selector in self.config['click_selectors']:
                actions.append({
                    'type': 'click',
                    'selector': selector
                })
        
        # Scroll
        if self.config.get('scroll'):
            actions.append({
                'type': 'scroll',
                'direction': self.config.get('scroll_direction', 'down'),
                'amount': self.config.get('scroll_amount', 500)
            })
        
        if actions:
            params['actions'] = actions
        
        # Add structured data extraction
        if self.config.get('extract_schema'):
            params['json_options'] = {
                'schema': self.config['extract_schema'],
                'systemPrompt': self.config.get('extract_prompt', 
                    'Extract structured data according to the provided schema.')
            }
        
        return params
    
    def get_cache_path(self, url: str) -> Path:
        """Generate cache file path for a URL."""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return self.cache_dir / f"{url_hash}.json"
    
    def load_from_cache(self, url: str) -> Optional[Dict]:
        """Load cached response for a URL if available."""
        if not self.config.get('use_cache', True):
            return None
            
        cache_path = self.get_cache_path(url)
        if cache_path.exists():
            cache_age = time.time() - cache_path.stat().st_mtime
            max_age = self.config.get('cache_max_age', 7 * 24 * 3600)
            
            if cache_age < max_age:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        return None
    
    def save_to_cache(self, url: str, response: Dict):
        """Save response to cache."""
        if self.config.get('use_cache', True):
            cache_path = self.get_cache_path(url)
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(response, f, indent=2)
    
    async def scrape_url(self, url: str, max_retries: int = 3) -> Optional[Dict]:
        """Scrape a single URL with advanced features."""
        # Check cache first
        cached_response = self.load_from_cache(url)
        if cached_response:
            print(f"✓ Using cached content for: {url}")
            self.stats['cached'] += 1
            return cached_response
        
        # Build scrape parameters (without url since it's passed separately)
        params = self.build_scrape_params(url)
        
        # Retry logic
        for attempt in range(max_retries):
            try:
                print(f"→ Scraping: {url} (attempt {attempt + 1}/{max_retries})")
                
                # Add delay between requests if configured
                if self.request_delay > 0:
                    await asyncio.sleep(self.request_delay)
                
                # Perform scraping (pass url separately, other params as kwargs)
                response = await self.app.v1.scrape_url(url, **params)
                
                if response:
                    # Convert Pydantic model to dict
                    response_dict = dict(response)
                    
                    # Map new SDK fields back to the names expected by the script
                    if response_dict.get('extract'):
                        response_dict['jsonData'] = response_dict['extract']
                    elif response_dict.get('json_field'):
                        response_dict['jsonData'] = response_dict['json_field']
                    
                    # Handle metadata mapping if needed
                    if response_dict.get('metadata') and isinstance(response_dict['metadata'], dict):
                        # The script expects some fields at the top level in some places
                        pass

                    # Save to cache
                    self.save_to_cache(url, response_dict)
                    
                    print(f"✓ Successfully scraped: {url}")
                    return response_dict
                else:
                    print(f"⚠ No content returned for: {url}")
                    
            except Exception as e:
                error_msg = str(e)
                print(f"✗ Error scraping {url}: {error_msg}")
                
                if 'rate' in error_msg.lower() or '429' in error_msg:
                    wait_time = 2 ** attempt + 1
                    print(f"  Rate limited. Waiting {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                    continue
                
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"  Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    self.stats['errors'].append({
                        'url': url,
                        'error': error_msg
                    })
        
        return None
    
    async def process_and_save(self, url: str, file_name: str, max_retries: int = 3):
        """Process a URL and save all extracted content."""
        self.stats['total'] += 1
        
        # Scrape the URL
        response = await self.scrape_url(url, max_retries)
        
        if not response:
            print(f"✗ Failed to scrape: {url}")
            self.stats['failed'] += 1
            # Save progress even for failures
            self.save_progress()
            return
        
        # Determine output path based on desired format
        output_format = self.config.get('output_format', 'markdown')
        output_path = self.output_dir / file_name
        if output_format == 'json':
            expected_suffix = '.json'
        elif output_format == 'jsonl':
            expected_suffix = '.jsonl'
        else:
            expected_suffix = '.md'
        if output_path.suffix != expected_suffix:
            output_path = output_path.with_suffix(expected_suffix)

        # Save content in desired format
        if output_format in ('json', 'jsonl'):
            data = {
                'source': url,
                'scraped_with': 'firecrawl-scraper',
                'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            # Include metadata if present
            if 'metadata' in response:
                data['metadata'] = response['metadata']
            # Include available content fields
            for key in ['markdown', 'html', 'text']:
                if key in response:
                    data[key] = response[key]
            # Optional extra fields
            if 'links' in response:
                data['links'] = response['links']
            if 'jsonData' in response:
                data['jsonData'] = response['jsonData']

            if output_format == 'jsonl' and getattr(self, 'aggregate_jsonl', False):
                # Append line to aggregate JSONL file with a lock
                try:
                    async with self.aggregate_lock:
                        with open(self.aggregate_path, 'a', encoding='utf-8') as f:
                            f.write(json.dumps(data, ensure_ascii=False))
                            f.write('\n')
                    print(f"✓ Appended to JSONL aggregate: {self.aggregate_path}")
                except Exception as e:
                    print(f"✗ Failed writing to aggregate JSONL: {e}")
            else:
                with open(output_path, 'w', encoding='utf-8') as f:
                    if output_format == 'jsonl':
                        f.write(json.dumps(data, ensure_ascii=False))
                        f.write('\n')
                    else:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"✓ Saved {output_format.upper()}: {output_path}")
        else:
            # Default: Save markdown content
            if 'markdown' in response:
                with open(output_path, 'w', encoding='utf-8') as f:
                    # Add metadata header
                    f.write("---\n")
                    f.write(f"source: {url}\n")
                    f.write("scraped_with: firecrawl-scraper\n")
                    f.write(f"scraped_at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    
                    # Add metadata if present
                    if 'metadata' in response:
                        metadata = response['metadata']
                        if metadata.get('title'):
                            f.write(f"title: {metadata['title']}\n")
                        if metadata.get('description'):
                            f.write(f"description: {metadata['description']}\n")
                        if metadata.get('author'):
                            f.write(f"author: {metadata['author']}\n")
                    
                    f.write("---\n\n")
                    f.write(response['markdown'])
                
                print(f"✓ Saved markdown: {output_path}")
        
        # Save HTML if requested
        if 'html' in response and 'html' in self.config.get('formats', []):
            html_path = output_path.with_suffix('.html')
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(response['html'])
            print(f"✓ Saved HTML: {html_path}")
        
        # Save links if present
        if 'links' in response and response['links']:
            links_path = output_path.with_suffix('.links.json')
            with open(links_path, 'w', encoding='utf-8') as f:
                json.dump(response['links'], f, indent=2)
            print(f"✓ Saved {len(response['links'])} links: {links_path}")
        
        # Save screenshot if present
        if 'screenshot' in response:
            screenshot_data = response['screenshot']
            if isinstance(screenshot_data, str) and screenshot_data.startswith('data:image'):
                # Extract base64 data
                base64_data = screenshot_data.split(',')[1]
                image_data = base64.b64decode(base64_data)
                
                # Save screenshot
                screenshot_path = self.screenshots_dir / f"{output_path.stem}.png"
                with open(screenshot_path, 'wb') as f:
                    f.write(image_data)
                
                print(f"✓ Saved screenshot: {screenshot_path}")
                self.stats['screenshots'] += 1
        
        # Save structured data if present
        if 'jsonData' in response:
            json_path = output_path.with_suffix('.data.json')
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(response['jsonData'], f, indent=2)
            print(f"✓ Saved structured data: {json_path}")
            self.stats['structured_data'] += 1
        
        self.stats['successful'] += 1
        
        # Save progress in real-time
        self.save_progress()
    
    async def process_batch(self, urls_batch: List[Dict[str, str]], max_retries: int = 3):
        """Process a batch of URLs concurrently."""
        tasks = []
        
        for entry in urls_batch:
            url = entry['url']
            file_name = entry['file_name']
            task = self.process_and_save(url, file_name, max_retries)
            tasks.append(task)
        
        await asyncio.gather(*tasks)
    
    def print_statistics(self):
        """Print detailed scraping statistics."""
        print("\n" + "="*60)
        print("ADVANCED SCRAPING STATISTICS")
        print("="*60)
        print(f"Total URLs processed: {self.stats['total']}")
        print(f"Successfully scraped: {self.stats['successful']}")
        print(f"From cache: {self.stats['cached']}")
        print(f"Failed: {self.stats['failed']}")
        
        if self.stats['screenshots'] > 0:
            print(f"Screenshots captured: {self.stats['screenshots']}")
        
        if self.stats['structured_data'] > 0:
            print(f"Structured data extracted: {self.stats['structured_data']}")
        
        if self.stats['errors']:
            print("\nErrors encountered:")
            for error in self.stats['errors'][:5]:
                print(f"  - {error['url']}: {error['error'][:100]}")
            if len(self.stats['errors']) > 5:
                print(f"  ... and {len(self.stats['errors']) - 5} more errors")
        
        if self.stats['total'] > 0:
            success_rate = (self.stats['successful'] / self.stats['total']) * 100
            print(f"\nSuccess rate: {success_rate:.1f}%")
        print("="*60)
    
    def save_progress(self):
        """Save current progress to a JSON file for real-time tracking."""
        progress_data = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'statistics': self.stats.copy(),
            'completed_urls': self.stats['successful'] + self.stats['cached'],
            'total_processed': self.stats['total']
        }
        
        try:
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                json.dump(progress_data, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save progress file: {e}")

async def main(input_source: str, output_dir: str, args):
    """Main function to process URLs with advanced features."""
    # Get API key
    api_key = args.api_key or os.getenv('FIRECRAWL_API_KEY')
    if not api_key:
        raise ValueError("No Firecrawl API key provided. Use --api-key or set FIRECRAWL_API_KEY.")
    
    # Build configuration
    config = {
        'use_cache': not args.no_cache,
        'cache_max_age': args.cache_max_age * 3600,  # Convert hours to seconds
        'formats': args.formats,
        'timeout': args.timeout * 1000,  # Convert to milliseconds
        'mobile': args.mobile,
        'screenshots': args.screenshots,
        'full_page_screenshot': args.full_page_screenshot,
        'proxy': args.proxy,
        'country': args.country,
        'language': args.language,
        'wait_time': args.wait_time,
        'wait_for': args.wait_for,
        'scroll': args.scroll,
        'scroll_direction': args.scroll_direction,
        'scroll_amount': args.scroll_amount,
        'request_delay': args.delay,  # Add delay between requests
        'fast_mode': args.fast_mode,  # Enable fast mode
        'max_age_hours': args.max_age_hours,  # Max age for cached data
        'output_format': args.output_format,  # Desired storage format
        'aggregate_jsonl': args.aggregate_jsonl,
        'aggregate_jsonl_file': args.aggregate_jsonl_file
    }
    
    # Load include/exclude tags
    if args.include_tags:
        config['include_tags'] = args.include_tags.split(',')
    if args.exclude_tags:
        config['exclude_tags'] = args.exclude_tags.split(',')
    
    # Load click selectors
    if args.click:
        config['click_selectors'] = args.click.split(',')
    
    # Load extraction schema
    if args.extract_schema:
        with open(args.extract_schema, 'r') as f:
            config['extract_schema'] = json.load(f)
        if args.extract_prompt:
            config['extract_prompt'] = args.extract_prompt
    
    # Initialize scraper
    scraper = AdvancedFirecrawlScraper(api_key, output_dir, config)
    
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
            print(f"✓ Filtered out {original_count - len(urls)} image URLs.")
    
    print(f"Found {len(urls)} URL(s) to process")
    print("Configuration:")
    print(f"  - Formats: {config['formats']}")
    print(f"  - Output storage: {config['output_format']}")
    if config.get('output_format') == 'jsonl' and args.output_format == 'jsonl':
        if args.aggregate_jsonl:
            print(f"  - JSONL aggregation: ENABLED (file: {os.path.join(output_dir, args.aggregate_jsonl_file)})")
    print(f"  - Mobile: {config['mobile']}")
    print(f"  - Screenshots: {config['screenshots']}")
    print(f"  - Cache: {'enabled' if config['use_cache'] else 'disabled'}")
    if config.get('fast_mode'):
        print(f"  - Fast mode: ENABLED (max age: {config['max_age_hours']} hours)")
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
        await scraper.process_batch(batch, args.max_retries)
        
        if i + batch_size < len(urls):
            await asyncio.sleep(5)
    
    # Print statistics
    scraper.print_statistics()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Advanced Firecrawl web scraper with enhanced features',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Basic arguments
    parser.add_argument('input', help='JSON file or single URL')
    parser.add_argument('output_dir', help='Output directory')
    parser.add_argument('--url', action='store_true', help='Treat input as single URL')
    parser.add_argument('--filename', help='Output filename for single URL')
    parser.add_argument('--api-key', help='Firecrawl API key')
    
    # Processing options
    parser.add_argument('--batch-size', type=int, default=5, help='Batch size (default: 5)')
    parser.add_argument('--max-retries', type=int, default=3, help='Max retries (default: 3)')
    
    # Cache options
    parser.add_argument('--no-cache', action='store_true', help='Disable local cache')
    parser.add_argument('--cache-max-age', type=int, default=168, help='Cache max age in hours (default: 168)')
    
    # Performance options
    parser.add_argument('--delay', type=float, default=0, help='Delay between requests in seconds (default: 0)')
    parser.add_argument('--fast-mode', action='store_true', help='Enable fast mode using Firecrawl cached data')
    parser.add_argument('--max-age-hours', type=float, default=1, help='Max age for cached data in hours when using fast mode (default: 1)')
    
    # Content options
    parser.add_argument('--formats', nargs='+', default=['markdown'], 
                        choices=['markdown', 'html', 'text'],
                        help='Output formats (default: markdown)')
    parser.add_argument('--output-format', default='markdown', choices=['markdown', 'json', 'jsonl'],
                        help='Storage format for saved results (default: markdown)')
    parser.add_argument('--aggregate-jsonl', action='store_true',
                        help='Aggregate all results into a single JSONL file')
    parser.add_argument('--aggregate-jsonl-file', default='results.jsonl',
                        help='Filename for aggregated JSONL (relative to output_dir)')
    parser.add_argument('--timeout', type=int, default=30, help='Timeout in seconds (default: 30)')
    
    # Scraping behavior
    parser.add_argument('--mobile', action='store_true', help='Emulate mobile device')
    parser.add_argument('--proxy', choices=['basic', 'stealth', 'auto'],
                        help='Proxy type to use')
    
    # Location options
    parser.add_argument('--country', help='Country code (e.g., US, UK)')
    parser.add_argument('--language', help='Language code (e.g., en, fr)')
    
    # Tag filtering
    parser.add_argument('--include-tags', help='Comma-separated tags to include')
    parser.add_argument('--exclude-tags', help='Comma-separated tags to exclude')
    
    # Actions
    parser.add_argument('--wait-time', type=int, help='Wait time in milliseconds')
    parser.add_argument('--wait-for', help='CSS selector to wait for')
    parser.add_argument('--click', help='Comma-separated selectors to click')
    parser.add_argument('--scroll', action='store_true', help='Enable scrolling')
    parser.add_argument('--scroll-direction', default='down', choices=['up', 'down'],
                        help='Scroll direction')
    parser.add_argument('--scroll-amount', type=int, default=500, help='Scroll amount in pixels')
    
    # Screenshots
    parser.add_argument('--screenshots', action='store_true', help='Capture screenshots')
    parser.add_argument('--full-page-screenshot', action='store_true', default=True,
                        help='Capture full page screenshot')
    
    # Structured data extraction
    parser.add_argument('--extract-schema', help='JSON file with extraction schema')
    parser.add_argument('--extract-prompt', help='Custom prompt for extraction')
    
    args = parser.parse_args()
    
    # Run async main
    asyncio.run(main(args.input, args.output_dir, args))
