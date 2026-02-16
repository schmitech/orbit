#!/usr/bin/env python3
"""
URL Extractor for Website Crawling

This script extracts URLs from a website starting with its sitemap XML file.
It recursively visits pages and collects all internal links, saving them to a JSON file
in a format suitable for further processing by the QA pipeline.

Features:
- Respects robots.txt compliance
- Implements polite crawling with configurable delays
- Handles rate limiting with exponential backoff
- Depth-limited crawling to prevent infinite recursion
- Automatic URL deduplication
- Converts URLs to consistent file naming scheme for markdown output

Requirements:
- Python 3.7+
- beautifulsoup4
- requests
- Install with: pip install -r requirements.txt

Usage:
------
Basic usage (crawl default OCCSC website):
    python url-extractor.py

Extract from specific sitemap:
    python url-extractor.py --sitemap https://example.com/sitemap.xml --output urls.json

Extract from single URL (crawl from that page):
    python url-extractor.py --url https://example.com/some-page --output urls.json

With custom crawling parameters:
    python url-extractor.py --delay 2.0 --max-pages 50 --max-depth 2

Command-line Arguments:
----------------------
--sitemap URL     : URL of the sitemap XML file
--url URL         : Single URL to start crawling from (alternative to sitemap)
--output FILE     : Output JSON file path (default: occsc_urls.json)
--delay SECONDS   : Base delay between requests in seconds (default: 1.0)
--max-pages NUM   : Maximum number of pages to process (default: 100)
--max-depth NUM   : Maximum crawl depth from initial URLs (default: 3)

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

Pipeline Integration:
--------------------
This is step 1 of the QA generation pipeline:
1. url-extractor.py     -> Extract URLs from website
2. docling-crawler.py   -> Convert pages to markdown
3. google_question_extractor.py -> Generate QA pairs

Use pipeline_orchestrator.py to run all steps automatically.

Notes:
------
- The script filters out non-HTML content (images, PDFs, etc.)
- Currently configured for occsc.org domain (modify line 303 for other domains)
- Implements adaptive delays to avoid overloading servers
- Respects rate limiting (HTTP 429) with exponential backoff
- Can start from either a sitemap XML or a single URL

Author: QA Pipeline Contributors
License: MIT
"""

import json
import argparse
import random
import time
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import requests
from urllib.robotparser import RobotFileParser

class SitemapUrlExtractor:
    """
    Extracts URLs from a website starting with its sitemap.
    
    This class handles the crawling process, respecting robots.txt and
    implementing polite delays between requests to avoid overloading the server.
    """
    
    def __init__(self, sitemap_url, output_file, config=None):
        """
        Initialize the URL extractor.
        
        Args:
            sitemap_url (str): URL of the sitemap XML file
            output_file (str): Path to save the output JSON file
            config (dict, optional): Configuration options to override defaults

            Example:
            
            python url-extractor.py --sitemap https://example.com/sitemap.xml --output urls.json --delay 2.0 --max-pages 200
        """
        self.sitemap_url = sitemap_url
        self.output_file = output_file
        
        # Default configuration
        self.config = {
            'request_delay': 1.0,  # Base delay between requests in seconds
            'jitter': 0.5,         # Random jitter factor (0.5 means ±50% of delay)
            'politeness': 1.2,     # Politeness factor to multiply delay
            'max_retries': 3,      # Maximum number of retries for failed requests
            'timeout': 30,         # Request timeout in seconds
            'user_agent': 'Mozilla/5.0 (compatible; OccscUrlExtractor/1.0; +https://example.org/bot)',
            'verify_ssl': True,    # Verify SSL certificates
            'max_depth': 3         # Maximum crawl depth from initial URLs
        }
        
        # Override with user config if provided
        if config:
            self.config.update(config)
        
        # Initialize session
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.config['user_agent'],
            'Accept-Language': 'en-CA, fr-CA;q=0.8',
            'Accept-Encoding': 'gzip',
            'Connection': 'keep-alive',
        })
        
        # Track processed URLs and results
        self.processed_urls = set()
        self.url_entries = []
        self.url_depths = {}  # Track depth of each URL
        
        # Parse base domain for later use
        parsed_url = urlparse(sitemap_url)
        self.base_domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
    
    def check_robots_txt(self):
        """
        Check robots.txt for crawl permissions.
        
        Returns:
            RobotFileParser: Parser with robots.txt rules, or None if error
        """
        robots_url = f"{self.base_domain}/robots.txt"
        try:
            response = self.session.get(robots_url, timeout=self.config['timeout'])
            parser = RobotFileParser()
            parser.parse(response.text.splitlines())
            return parser
        except Exception as e:
            print(f"Error checking robots.txt: {e}")
            return None
    
    def adaptive_delay(self):
        """
        Implement an adaptive delay between requests.
        
        This adds a randomized delay to avoid predictable request patterns
        and reduce server load.
        """
        base_delay = self.config['request_delay']
        jitter = base_delay * self.config['jitter']
        actual_delay = base_delay * self.config['politeness'] + random.uniform(-jitter, jitter)
        time.sleep(max(0.5, actual_delay))  # Never less than 0.5s
    
    def process_sitemap(self, sitemap_url=None, is_nested=False):
        """
        Process the sitemap and extract page URLs. Handles both regular sitemaps
        and sitemap index files that contain references to other sitemaps.
        
        Args:
            sitemap_url (str, optional): URL of the sitemap to process. Uses self.sitemap_url if not provided.
            is_nested (bool): Whether this is a nested sitemap call
            
        Returns:
            list: List of URLs found in the sitemap(s)
        """
        if sitemap_url is None:
            sitemap_url = self.sitemap_url
            
        print(f"{'  ' if is_nested else ''}Processing sitemap: {sitemap_url}")
        
        # Check robots.txt (only for the initial sitemap)
        if not is_nested:
            robots = self.check_robots_txt()
            if robots and not robots.can_fetch(self.config['user_agent'], sitemap_url):
                print(f"ERROR: Cannot crawl {sitemap_url} per robots.txt")
                return []
        
        # Apply delay for nested sitemaps
        if is_nested:
            self.adaptive_delay()
        
        # Get sitemap content with retry logic
        for attempt in range(self.config['max_retries']):
            try:
                response = self.session.get(sitemap_url, timeout=self.config['timeout'])
                if response.status_code == 429:  # Too Many Requests
                    backoff = 2 ** attempt + random.uniform(0, 1)
                    print(f"Rate limited. Backing off for {backoff:.2f} seconds")
                    time.sleep(backoff)
                    continue
                break
            except Exception as e:
                print(f"Error fetching sitemap (attempt {attempt+1}): {e}")
                time.sleep(2 ** attempt)
        
        if not hasattr(response, 'status_code') or response.status_code != 200:
            print(f"Failed to fetch sitemap: {getattr(response, 'status_code', 'Unknown error')}")
            return []
        
        # Parse sitemap (XML document)
        soup = BeautifulSoup(response.content, 'xml')
        
        # Check if this is a sitemap index (contains other sitemaps)
        sitemap_entries = soup.find_all('sitemap')
        if sitemap_entries:
            print(f"{'  ' if is_nested else ''}Found sitemap index with {len(sitemap_entries)} nested sitemaps")
            all_urls = []
            for sitemap_entry in sitemap_entries:
                nested_loc = sitemap_entry.find('loc')
                if nested_loc:
                    nested_sitemap_url = nested_loc.text.strip()
                    # Recursively process nested sitemap
                    nested_urls = self.process_sitemap(nested_sitemap_url, is_nested=True)
                    all_urls.extend(nested_urls)
            return list(set(all_urls))  # Remove duplicates
        
        # Regular sitemap - extract all URLs
        urls = []
        for loc in soup.find_all('loc'):
            url = loc.text.strip()
            # Filter out image URLs and only include actual pages
            if not url.endswith(('.jpg', '.png', '.webp', '.svg', '.gif')):
                urls.append(url)
        
        print(f"{'  ' if is_nested else ''}Found {len(urls)} URLs in sitemap")
        return list(set(urls))  # Remove duplicates
    
    def extract_urls_from_page(self, url, current_depth=0):
        """
        Extract all URLs from a single page.
        
        Args:
            url (str): URL of the page to process
            current_depth (int): Current crawl depth
            
        Returns:
            list: List of URLs found on the page
        """
        if url in self.processed_urls:
            return []
        
        # Check depth limit
        if current_depth > self.config['max_depth']:
            print(f"  Skipping {url} - max depth {self.config['max_depth']} reached")
            return []
        
        self.processed_urls.add(url)
        
        # Apply adaptive delay
        self.adaptive_delay()
        
        try:
            # Get page content with retry logic
            for attempt in range(self.config['max_retries']):
                try:
                    response = self.session.get(url, timeout=self.config['timeout'])
                    if response.status_code == 429:  # Too Many Requests
                        backoff = 2 ** attempt + random.uniform(0, 1)
                        print(f"Rate limited. Backing off for {backoff:.2f} seconds")
                        time.sleep(backoff)
                        continue
                    break
                except Exception as e:
                    print(f"Error fetching page (attempt {attempt+1}): {e}")
                    if attempt < self.config['max_retries'] - 1:
                        time.sleep(2 ** attempt)
                    else:
                        return []
            
            if response.status_code != 200:
                print(f"Failed to fetch {url}: {response.status_code}")
                return []
            
            # Parse the HTML content
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract all links
            links = []
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                # Convert relative URLs to absolute
                absolute_url = urljoin(url, href)
                
                # Only include URLs from the same domain
                if urlparse(absolute_url).netloc in ['occsc.org', 'www.occsc.org']:
                    # Filter out anchors, query parameters, etc.
                    parsed = urlparse(absolute_url)
                    clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                    
                    # Filter out non-HTML content
                    if not clean_url.endswith(('.jpg', '.png', '.webp', '.svg', '.gif', '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.css', '.js')):
                        links.append(clean_url)
            
            return list(set(links))  # Remove duplicates
            
        except Exception as e:
            print(f"Error processing {url}: {e}")
            return []
    
    def create_url_entry(self, url):
        """
        Create a JSON entry for a URL.
        
        Args:
            url (str): URL to create an entry for
            
        Returns:
            dict: Entry with file_name and url fields
        """
        # Extract the path and create a filename
        path = urlparse(url).path.strip('/')
        if not path:
            file_name = "home.md"
        else:
            # Replace slashes with hyphens and add .md extension
            file_name = path.replace('/', '-')
            if not file_name.endswith('.md'):
                file_name += '.md'
        
        return {
            "file_name": file_name,
            "url": url
        }
    
    def process_all_pages(self, initial_urls):
        """
        Process all pages and extract URLs recursively with depth tracking.
        
        Args:
            initial_urls (list): Initial list of URLs to process
        """
        # Initialize URLs with depth 0
        to_process = [(url, 0) for url in initial_urls]
        all_urls = set(initial_urls)
        
        # Set initial depths
        for url in initial_urls:
            self.url_depths[url] = 0
        
        print(f"Starting with {len(to_process)} URLs from sitemap")
        print(f"Max crawl depth set to: {self.config['max_depth']}")
        
        while to_process:
            current_url, current_depth = to_process.pop(0)
            print(f"Processing: {current_url} (depth: {current_depth}, {len(to_process)} remaining in queue)")
            
            # Extract URLs from the page
            page_urls = self.extract_urls_from_page(current_url, current_depth)
            
            # Add the current URL to results
            self.url_entries.append(self.create_url_entry(current_url))
            
            # Add new URLs to the processing queue with incremented depth
            next_depth = current_depth + 1
            for url in page_urls:
                if url not in all_urls and next_depth <= self.config['max_depth']:
                    all_urls.add(url)
                    self.url_depths[url] = next_depth
                    to_process.append((url, next_depth))
                    print(f"  Found new URL at depth {next_depth}: {url}")
        
        print(f"Processed {len(self.processed_urls)} pages, found {len(self.url_entries)} unique URLs")
    
    def save_results(self):
        """
        Save results to JSON file.
        """
        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(self.url_entries, f, indent=4, ensure_ascii=False)
        
        print(f"Saved {len(self.url_entries)} URL entries to {self.output_file}")

def main():
    """
    Main entry point for the script.
    
    Parses command line arguments and runs the URL extraction process.
    """
    parser = argparse.ArgumentParser(
        description='Extract URLs from a website starting with its sitemap or a single URL.',
        epilog="""
Examples:
  # Extract from sitemap
  python url-extractor.py --sitemap https://company.org/page-sitemap.xml --output occsc_urls.json
  
  # Extract from single URL
  python url-extractor.py --url https://company.org/some-page --output urls.json
  
  # With custom settings
  python url-extractor.py --delay 2.0 --max-pages 200
        """
    )
    
    parser.add_argument(
        '--output', 
        default='occsc_urls.json', 
        help='Output JSON file (default: occsc_urls.json)'
    )
    
    parser.add_argument(
        '--sitemap', 
        default=None, 
        help='URL of the sitemap XML file'
    )
    
    parser.add_argument(
        '--url',
        default=None,
        help='Single URL to start crawling from (alternative to sitemap)'
    )
    
    parser.add_argument(
        '--delay', 
        type=float, 
        default=1.0, 
        help='Base delay between requests in seconds (default: 1.0)'
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
        default=3,
        help='Maximum crawl depth from initial URLs (default: 3)'
    )
    
    args = parser.parse_args()
    
    # Validate input - must provide either sitemap or url
    if not args.sitemap and not args.url:
        # Default to sitemap if neither provided
        args.sitemap = 'https://company.org/page-sitemap.xml'
    elif args.sitemap and args.url:
        parser.error("Please provide either --sitemap or --url, not both")
    
    # Create custom config
    config = {
        'request_delay': args.delay,
        'max_pages': args.max_pages,
        'max_depth': args.max_depth
    }
    
    # Determine which URL to use for initialization
    init_url = args.sitemap if args.sitemap else args.url
    
    # Initialize extractor
    extractor = SitemapUrlExtractor(init_url, args.output, config)
    
    if args.url:
        # Process single URL and crawl from there
        print(f"Starting crawl from single URL: {args.url}")
        initial_urls = [args.url]
    else:
        # Process sitemap to get initial URLs
        initial_urls = extractor.process_sitemap()
    
    if initial_urls:
        # Process all pages to extract URLs
        extractor.process_all_pages(initial_urls)
        # Save results
        extractor.save_results()
    else:
        print("No valid URLs found")

if __name__ == "__main__":
    main()