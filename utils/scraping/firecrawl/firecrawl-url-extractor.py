#!/usr/bin/env python3
"""
URL Extractor using Firecrawl

This script extracts URLs from a website starting with a given URL.
It uses Firecrawl to fetch pages and extract links, which can be more
effective for modern JavaScript-heavy websites.

Features:
- Uses Firecrawl for robust, JS-rendered page scraping
- Depth-limited crawling to control scope
- Page limit to control total number of URLs extracted
- Automatic URL deduplication
- Converts URLs to consistent file naming scheme for markdown output
- Fast mode for cached scraping (up to 500% faster)
- Rate limiting with configurable delay between requests

Requirements:
- Python 3.7+
- firecrawl-py
- python-dotenv
- Install with: pip install firecrawl-py python-dotenv

Usage:
------
python firecrawl-url-extractor.py --url https://example.com --output urls.json

With custom crawling parameters:
    python firecrawl-url-extractor.py --url https://example.com --max-pages 50 --max-depth 2 --delay 1.5

With fast mode for cached scraping (up to 500% faster):
    python firecrawl-url-extractor.py --url https://example.com --fast-mode --max-age-hours 2

Command-line Arguments:
----------------------
--url URL           : Single URL to start crawling from (required)
--output FILE       : Output JSON file path (default: firecrawl_urls.json)
--max-pages NUM     : Maximum number of pages to process (default: 100)
--max-depth NUM     : Maximum crawl depth from initial URLs (default: 2)
--delay SECONDS     : Delay between requests to avoid rate limiting (default: 0)
--fast-mode         : Enable fast scraping using cached data (up to 500% faster)
--max-age-hours NUM : Max age for cached data in hours when using fast mode (default: 1)
--api-key KEY       : Firecrawl API key (can also be set via FIRECRAWL_API_KEY env var)

Output Format:
-------------
The script generates a JSON file with the following structure:
[
    {
        "file_name": "page-name.md",
        "url": "https://example.com/page-name"
    },
    ...
]
"""

import asyncio
import json
import os
import argparse
from urllib.parse import urlparse, urljoin
from firecrawl import AsyncFirecrawlApp
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class FirecrawlUrlExtractor:
    """
    Extracts URLs from a website using Firecrawl's link extraction capabilities.
    """
    
    def __init__(self, api_key: str, config: dict = None):
        """
        Initialize the Firecrawl URL extractor.
        
        Args:
            api_key (str): Your Firecrawl API key.
            config (dict, optional): Configuration options.
        """
        self.app = AsyncFirecrawlApp(api_key=api_key)
        self.config = {
            'max_depth': 2,
            'max_pages': 100,
            'delay': 0,  # Delay in seconds between requests
            'fast_mode': False,  # Enable fast scraping with cached data
            'max_age_hours': 1,  # Max age for cached data in hours (used with fast_mode)
        }
        if config:
            self.config.update(config)
        
        self.processed_urls = set()
        self.url_entries = []
        self.discovered_links = set()  # Track all discovered links
        self.base_domain = None
        self.output_file = None  # Store output file path for real-time saving

    def create_url_entry(self, url: str) -> dict:
        """
        Create a JSON entry for a URL with a generated filename.
        
        Args:
            url (str): The URL to create an entry for.
            
        Returns:
            dict: An entry with "file_name" and "url" keys.
        """
        path = urlparse(url).path.strip('/')
        if not path:
            file_name = "home.md"
        else:
            file_name = path.replace('/', '-')
            if not file_name.endswith('.md'):
                file_name += '.md'
        
        return {
            "file_name": file_name,
            "url": url
        }

    async def extract_links(self, url: str) -> list:
        """
        Scrape a URL with Firecrawl to extract all unique links.
        This version uses the correct Firecrawl API parameters.
        """
        print(f"  -> Scraping for links: {url}")
        try:
            # Build parameters for scraping
            scrape_params = {
                'formats': ['links'],
                'only_main_content': True  # Fixed: underscore version
            }
            
            # Add max_age parameter if fast mode is enabled
            if self.config.get('fast_mode'):
                max_age_ms = int(self.config.get('max_age_hours', 1) * 3600000)  # Convert hours to milliseconds
                scrape_params['max_age'] = max_age_ms  # Confirmed: underscore version works
                print(f"    -> Using fast mode with max age: {self.config.get('max_age_hours')} hours")

            response = await self.app.v1.scrape_url(url, **scrape_params)
            print(f"    -> Response type: {type(response)}")
            
            if response and hasattr(response, 'links'):
                links = response.links
                print(f"    -> Found {len(links)} links in response.links")
                if links:
                    print(f"    -> Sample links: {links[:3]}")
                return links
            elif response and hasattr(response, 'data') and hasattr(response.data, 'links'):
                links = response.data.links
                print(f"    -> Found {len(links)} links in response.data.links")
                if links:
                    print(f"    -> Sample links: {links[:3]}")
                return links
            else:
                print(f"    -> No links found. Response attributes: {dir(response) if response else 'None'}")
                return []
        except Exception as e:
            print(f"  ✗ Error scraping {url}: {e}")
            return []

    async def crawl(self, start_urls: list):
        """
        Crawl a website starting from a list of URLs.
        
        Args:
            start_urls (list): A list of URLs to begin crawling from.
        """
        if not start_urls:
            return
            
        self.base_domain = urlparse(start_urls[0]).netloc
        
        queue = [(url, 0) for url in start_urls]
        visited = set(start_urls)

        head = 0
        while head < len(queue) and len(self.url_entries) < self.config['max_pages']:
            current_url, depth = queue[head]
            head += 1

            if depth > self.config['max_depth']:
                print(f"  Skipping {current_url} - max depth reached.")
                continue

            # Add current URL to the results
            if current_url not in self.processed_urls:
                self.url_entries.append(self.create_url_entry(current_url))
                self.processed_urls.add(current_url)
                self.discovered_links.add(current_url)  # Add to discovered links
                print(f"[{len(self.url_entries)}/{self.config['max_pages']}] Added: {current_url} (depth: {depth})")

            # Add delay if configured (rate limiting)
            if self.config['delay'] > 0:
                await asyncio.sleep(self.config['delay'])
            
            # Extract links from the page
            links = await self.extract_links(current_url)
            
            for link in links:
                absolute_link = urljoin(current_url, link)
                parsed_link = urlparse(absolute_link)
                
                # Clean URL by removing query params and fragments
                clean_link = f"{parsed_link.scheme}://{parsed_link.netloc}{parsed_link.path}"

                # Check if it's a valid, new, in-domain URL
                if (parsed_link.scheme in ['http', 'https'] and
                    parsed_link.netloc == self.base_domain and
                    clean_link not in visited and
                    not clean_link.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.pdf', '.zip', '.css', '.js', '.xml'))):
                    
                    if len(queue) < self.config['max_pages'] * 5: # Prevent queue from growing excessively
                        visited.add(clean_link)
                        queue.append((clean_link, depth + 1))
                        self.discovered_links.add(clean_link)  # Add to discovered links
            
            # Save discovered links in real-time after each page
            if self.output_file:
                self.save_discovered_links()
                print(f"    -> Progress: {len(self.discovered_links)} total links discovered so far")

    def save_discovered_links(self):
        """
        Save all discovered links to the JSON file in real-time.
        """
        if not self.output_file:
            return
            
        # Convert discovered links to URL entries
        all_entries = []
        for url in sorted(self.discovered_links):
            all_entries.append(self.create_url_entry(url))
        
        # Save to file
        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(all_entries, f, indent=4, ensure_ascii=False)
        print(f"    -> Saved {len(all_entries)} discovered links to {self.output_file}")

    def save_results(self, output_file: str):
        """
        Save the extracted URL entries to a JSON file.
        
        Args:
            output_file (str): The path to the output JSON file.
        """
        self.output_file = output_file  # Store for real-time saving
        self.save_discovered_links()
        print(f"\n✓ Final save: {len(self.discovered_links)} discovered links to {output_file}")


async def main():
    """
    Main entry point for the script.
    """
    parser = argparse.ArgumentParser(
        description='Extract URLs from a website using Firecrawl.',
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Example:
  python firecrawl-url-extractor.py --url https://example.com --output urls.json
"""
    )
    parser.add_argument(
        '--url',
        required=True,
        help='Single URL to start crawling from'
    )
    parser.add_argument(
        '--output', 
        default='firecrawl_urls.json', 
        help='Output JSON file (default: firecrawl_urls.json)'
    )
    parser.add_argument(
        '--max-pages', 
        type=int, 
        default=100, 
        help='Maximum number of pages to process (default: 100)'
    )
    parser.add_argument(
        '--max-depth',
        type=int,
        default=2,
        help='Maximum crawl depth from initial URLs (default: 2)'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=0,
        help='Delay in seconds between requests to avoid rate limiting (default: 0)'
    )
    parser.add_argument(
        '--fast-mode',
        action='store_true',
        help='Enable fast scraping mode using cached data (up to 500%% faster)'
    )
    parser.add_argument(
        '--max-age-hours',
        type=float,
        default=1,
        help='Max age for cached data in hours when using fast mode (default: 1)'
    )
    parser.add_argument('--api-key', help='Firecrawl API key (or set FIRECRAWL_API_KEY)')

    args = parser.parse_args()

    api_key = args.api_key or os.getenv('FIRECRAWL_API_KEY')
    if not api_key:
        raise ValueError("No Firecrawl API key provided. Use --api-key or set FIRECRAWL_API_KEY.")

    config = {
        'max_pages': args.max_pages,
        'max_depth': args.max_depth,
        'delay': args.delay,
        'fast_mode': args.fast_mode,
        'max_age_hours': args.max_age_hours
    }

    extractor = FirecrawlUrlExtractor(api_key, config)
    print(f"Starting crawl from: {args.url}")
    print(f"Max pages: {config['max_pages']}, Max depth: {config['max_depth']}, Delay: {config['delay']}s")
    if config['fast_mode']:
        print(f"Fast mode: ENABLED (max age: {config['max_age_hours']} hours)")
    print("-" * 40)
    
    # Set output file BEFORE crawling to enable real-time saving
    extractor.output_file = args.output
    
    await extractor.crawl([args.url])
    extractor.save_results(args.output)

if __name__ == "__main__":
    asyncio.run(main())
