#!/usr/bin/env python3
"""
URL Extractor for OCCSC Website

This script extracts URLs from a website starting with its sitemap XML file.
It recursively visits pages and collects all internal links, saving them to a JSON file
in a format suitable for further processing.

Features:
- Respects robots.txt
- Implements polite crawling with configurable delays
- Handles rate limiting with exponential backoff
- Deduplicates URLs
- Converts URLs to a consistent file naming scheme

Author: Your Name
License: MIT
"""

import asyncio
import json
import os
import argparse
import re
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
            'verify_ssl': True     # Verify SSL certificates
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
    
    def process_sitemap(self):
        """
        Process the sitemap and extract page URLs.
        
        Returns:
            list: List of URLs found in the sitemap
        """
        print(f"Processing sitemap: {self.sitemap_url}")
        
        # Check robots.txt
        robots = self.check_robots_txt()
        if robots and not robots.can_fetch(self.config['user_agent'], self.sitemap_url):
            print(f"ERROR: Cannot crawl {self.sitemap_url} per robots.txt")
            return []
        
        # Get sitemap content with retry logic
        for attempt in range(self.config['max_retries']):
            try:
                response = self.session.get(self.sitemap_url, timeout=self.config['timeout'])
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
        
        # Parse sitemap
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract all URLs from the sitemap
        urls = []
        for loc in soup.find_all('loc'):
            url = loc.text.strip()
            # Filter out image URLs and only include actual pages
            if not url.endswith(('.jpg', '.png', '.webp', '.svg', '.gif')):
                urls.append(url)
        
        return list(set(urls))  # Remove duplicates
    
    def extract_urls_from_page(self, url):
        """
        Extract all URLs from a single page.
        
        Args:
            url (str): URL of the page to process
            
        Returns:
            list: List of URLs found on the page
        """
        if url in self.processed_urls:
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
        Process all pages and extract URLs recursively.
        
        Args:
            initial_urls (list): Initial list of URLs to process
        """
        to_process = list(initial_urls)
        all_urls = set(initial_urls)
        
        print(f"Starting with {len(to_process)} URLs from sitemap")
        
        while to_process:
            current_url = to_process.pop(0)
            print(f"Processing: {current_url} ({len(to_process)} remaining in queue)")
            
            # Extract URLs from the page
            page_urls = self.extract_urls_from_page(current_url)
            
            # Add the current URL to results
            self.url_entries.append(self.create_url_entry(current_url))
            
            # Add new URLs to the processing queue
            for url in page_urls:
                if url not in all_urls:
                    all_urls.add(url)
                    to_process.append(url)
                    print(f"  Found new URL: {url}")
        
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
        description='Extract URLs from a website starting with its sitemap.',
        epilog="""
Examples:
  python url-extractor.py --sitemap https://occsc.org/page-sitemap.xml --output occsc_urls.json
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
        default='https://occsc.org/page-sitemap.xml', 
        help='URL of the sitemap XML file (default: https://occsc.org/page-sitemap.xml)'
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
    
    args = parser.parse_args()
    
    # Create custom config
    config = {
        'request_delay': args.delay,
        'max_pages': args.max_pages
    }
    
    # Initialize extractor
    extractor = SitemapUrlExtractor(args.sitemap, args.output, config)
    
    # Process sitemap to get initial URLs
    initial_urls = extractor.process_sitemap()
    if initial_urls:
        # Process all pages to extract URLs
        extractor.process_all_pages(initial_urls)
        # Save results
        extractor.save_results()
    else:
        print("No valid URLs found in sitemap")

if __name__ == "__main__":
    main()