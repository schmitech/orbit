#!/usr/bin/env python3
"""
Firecrawl Template Generator

This script generates Firecrawl intent templates from a list of URLs. It combines
URL extraction, content sampling, and LLM-based question generation to produce
production-ready YAML templates for the IntentFirecrawlRetriever.

The generated templates enable grounded responses by mapping natural language
queries to specific, authoritative URLs.

Pipeline Integration:
--------------------
This is the bridge between URL discovery and intent-based retrieval:

1. url-extractor.py OR firecrawl-scraper.py -> Extract URLs from website
2. template_generator.py -> Generate intent templates (YOU ARE HERE)
3. IntentFirecrawlRetriever -> Use templates for grounded retrieval

Features:
---------
1. Reads URLs from JSON file (output from url-extractor.py)
2. Samples content from each URL using Firecrawl API
3. Generates natural language examples (nl_examples) using Ollama
4. Produces YAML templates compatible with IntentFirecrawlRetriever
5. Supports batch processing with rate limiting
6. Caching to avoid redundant API calls
7. Semantic type categorization based on URL patterns
8. Configurable number of nl_examples per template

Requirements:
------------
- Python 3.7+
- aiohttp, pyyaml, requests
- Running Ollama instance OR OpenAI API key
- Firecrawl API key (for content sampling)
- A config.yaml file with LLM settings

Usage:
------
Basic usage:
    python template_generator.py --input urls.json --output templates.yaml

With custom settings:
    python template_generator.py --input urls.json --output templates.yaml \\
        --examples 5 --delay 1.0 --domain "company_knowledge_base"

Using OpenAI instead of Ollama:
    python template_generator.py --input urls.json --output templates.yaml --use-openai

Process specific URLs only:
    python template_generator.py --input urls.json --output templates.yaml --limit 10

Command-line Arguments:
----------------------
--input, -i       : Input JSON file with URLs (from url-extractor.py)
--output, -o      : Output YAML file for templates (default: firecrawl_templates.yaml)
--examples, -e    : Number of nl_examples per template (default: 5)
--delay           : Delay between API calls in seconds (default: 0.5)
--limit           : Maximum number of URLs to process (default: all)
--domain          : Domain name for the template collection (default: auto-detected)
--use-openai      : Use OpenAI API instead of Ollama for question generation
--no-cache        : Skip cache and regenerate all templates
--skip-scrape     : Skip scraping, use cached/placeholder content
--timeout         : Request timeout in seconds (default: 60)
--concurrent      : Maximum concurrent requests (default: 3)
--semantic-types  : JSON file with custom semantic type mappings
--verbose, -v     : Enable verbose output

Output Format:
-------------
Generates a YAML file with this structure:

templates:
  - id: "company_services_consulting"
    description: "Information about consulting services"
    semantic_type: "services"
    nl_examples:
      - "What consulting services do you offer?"
      - "Tell me about your consulting options"
      - "How can you help with consulting?"
    url_mapping:
      url: "https://company.com/services/consulting"
    formats: ["markdown"]
    timeout: 45

Author: Orbit Pipeline Contributors
License: MIT
"""

import asyncio
import aiohttp
import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlparse
import yaml

# Try to import OpenAI for optional support
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Load configuration
def load_config() -> Dict[str, Any]:
    """Load configuration from config.yaml."""
    config_paths = [
        Path('config.yaml'),
        Path(__file__).parent / 'config.yaml',
        Path(__file__).parent.parent.parent / 'config.yaml',
    ]

    for config_path in config_paths:
        if config_path.exists():
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)

    return {}

CONFIG = load_config()

# Ollama settings (from config or defaults)
OLLAMA_CONFIG = CONFIG.get('ollama', {})
OLLAMA_BASE_URL = OLLAMA_CONFIG.get('base_url', 'http://localhost:11434')
OLLAMA_MODEL = OLLAMA_CONFIG.get('model', 'llama3.2')
OLLAMA_TEMPERATURE = OLLAMA_CONFIG.get('temperature', 0.3)
OLLAMA_NUM_CTX = OLLAMA_CONFIG.get('num_ctx', 8192)

# Firecrawl settings
FIRECRAWL_API_KEY = os.getenv('FIRECRAWL_API_KEY', '')
FIRECRAWL_BASE_URL = os.getenv('FIRECRAWL_BASE_URL', 'https://api.firecrawl.dev/v1')

# Default semantic type mappings based on URL patterns
DEFAULT_SEMANTIC_TYPES = {
    # Services & Products
    r'/services?/': 'services',
    r'/products?/': 'products',
    r'/solutions?/': 'solutions',
    r'/offerings?/': 'offerings',
    r'/pricing': 'pricing',

    # Information
    r'/about': 'company_info',
    r'/team': 'team_info',
    r'/staff': 'team_info',
    r'/leadership': 'team_info',
    r'/contact': 'contact_info',
    r'/locations?': 'location_info',

    # Resources
    r'/blog': 'blog_content',
    r'/news': 'news_content',
    r'/articles?': 'article_content',
    r'/resources?': 'resources',
    r'/docs?': 'documentation',
    r'/documentation': 'documentation',
    r'/guides?': 'guides',
    r'/tutorials?': 'tutorials',
    r'/faq': 'faq',
    r'/help': 'help_content',

    # Legal & Policy
    r'/privacy': 'legal_info',
    r'/terms': 'legal_info',
    r'/policy': 'legal_info',
    r'/legal': 'legal_info',

    # Events & Programs
    r'/events?': 'events',
    r'/programs?': 'programs',
    r'/workshops?': 'workshops',
    r'/webinars?': 'webinars',
    r'/training': 'training',

    # Careers
    r'/careers?': 'careers',
    r'/jobs?': 'careers',
    r'/hiring': 'careers',

    # Default fallback
    r'.*': 'general_info'
}


class TemplateGenerator:
    """
    Generates Firecrawl intent templates from URLs.

    This class orchestrates the template generation process:
    1. Load URLs from input file
    2. Sample content from each URL
    3. Generate nl_examples using LLM
    4. Output YAML templates
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the template generator.

        Args:
            config: Configuration dictionary with settings
        """
        self.config = config
        self.input_file = Path(config['input'])
        self.output_file = Path(config['output'])
        self.num_examples = config.get('examples', 5)
        self.delay = config.get('delay', 0.5)
        self.limit = config.get('limit', None)
        self.domain_name = config.get('domain', None)
        self.use_openai = config.get('use_openai', False)
        self.no_cache = config.get('no_cache', False)
        self.skip_scrape = config.get('skip_scrape', False)
        self.timeout = config.get('timeout', 60)
        self.concurrent = config.get('concurrent', 3)
        self.verbose = config.get('verbose', False)

        # Load custom semantic types if provided
        self.semantic_types = DEFAULT_SEMANTIC_TYPES.copy()
        if config.get('semantic_types_file'):
            with open(config['semantic_types_file'], 'r') as f:
                custom_types = json.load(f)
                self.semantic_types.update(custom_types)

        # Cache directory
        self.cache_dir = Path(config.get('cache_dir', '.template_cache'))
        self.cache_dir.mkdir(exist_ok=True)

        # HTTP session (initialized in async context)
        self.session: Optional[aiohttp.ClientSession] = None

        # Semaphore for rate limiting
        self.semaphore = asyncio.Semaphore(self.concurrent)

        # Statistics
        self.stats = {
            'total_urls': 0,
            'processed': 0,
            'cached': 0,
            'failed': 0,
            'templates_generated': 0
        }

    async def initialize(self):
        """Initialize async resources."""
        connector = aiohttp.TCPConnector(limit=20, limit_per_host=5)
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        self.session = aiohttp.ClientSession(connector=connector, timeout=timeout)

        # Validate Firecrawl API key if we're going to scrape
        if not self.skip_scrape:
            if not FIRECRAWL_API_KEY:
                print("⚠️  Warning: FIRECRAWL_API_KEY not set. Content sampling will be limited.")
                print("   Set the environment variable or use --skip-scrape for cached content.")

    async def cleanup(self):
        """Cleanup async resources."""
        if self.session and not self.session.closed:
            await self.session.close()

    def get_cache_path(self, url: str, cache_type: str = 'content') -> Path:
        """Get cache file path for a URL."""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return self.cache_dir / f"{cache_type}_{url_hash}.json"

    def load_from_cache(self, url: str, cache_type: str = 'content') -> Optional[Dict]:
        """Load cached data for a URL."""
        if self.no_cache:
            return None

        cache_path = self.get_cache_path(url, cache_type)
        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def save_to_cache(self, url: str, data: Dict, cache_type: str = 'content'):
        """Save data to cache."""
        cache_path = self.get_cache_path(url, cache_type)
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def detect_semantic_type(self, url: str) -> str:
        """
        Detect semantic type based on URL patterns.

        Args:
            url: The URL to analyze

        Returns:
            Semantic type string
        """
        path = urlparse(url).path.lower()

        for pattern, semantic_type in self.semantic_types.items():
            if re.search(pattern, path):
                return semantic_type

        return 'general_info'

    def generate_template_id(self, url: str) -> str:
        """
        Generate a unique template ID from URL.

        Args:
            url: The URL to create ID from

        Returns:
            Snake_case template ID
        """
        parsed = urlparse(url)

        # Get domain name without TLD
        domain_parts = parsed.netloc.replace('www.', '').split('.')
        domain = domain_parts[0] if domain_parts else 'site'

        # Get path parts
        path = parsed.path.strip('/')
        if not path:
            return f"{domain}_home"

        # Convert path to snake_case ID
        path_parts = path.split('/')
        # Take last 2-3 meaningful parts
        meaningful_parts = [p for p in path_parts if p and not p.isdigit()][-3:]

        # Clean and join
        clean_parts = []
        for part in meaningful_parts:
            # Remove file extensions
            part = re.sub(r'\.[a-z]+$', '', part)
            # Convert to snake_case
            part = re.sub(r'[^a-z0-9]+', '_', part.lower())
            part = part.strip('_')
            if part:
                clean_parts.append(part)

        if clean_parts:
            return f"{domain}_{'_'.join(clean_parts)}"
        return f"{domain}_page"

    async def scrape_url_content(self, url: str) -> Optional[Dict]:
        """
        Scrape content from a URL using Firecrawl API.

        Args:
            url: URL to scrape

        Returns:
            Dictionary with scraped content and metadata
        """
        # Check cache first
        cached = self.load_from_cache(url, 'content')
        if cached:
            self.stats['cached'] += 1
            if self.verbose:
                print(f"  ↳ Using cached content for: {url}")
            return cached

        if self.skip_scrape:
            return {'url': url, 'title': '', 'description': '', 'content': ''}

        if not FIRECRAWL_API_KEY:
            return {'url': url, 'title': '', 'description': '', 'content': ''}

        async with self.semaphore:
            await asyncio.sleep(self.delay)

            try:
                headers = {
                    'Authorization': f'Bearer {FIRECRAWL_API_KEY}',
                    'Content-Type': 'application/json'
                }

                payload = {
                    'url': url,
                    'formats': ['markdown'],
                    'timeout': self.timeout * 1000
                }

                async with self.session.post(
                    f"{FIRECRAWL_BASE_URL}/scrape",
                    json=payload,
                    headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        result_data = data.get('data', {})

                        result = {
                            'url': url,
                            'title': result_data.get('metadata', {}).get('title', ''),
                            'description': result_data.get('metadata', {}).get('description', ''),
                            'content': result_data.get('markdown', '')[:8000],  # Limit content size
                            'metadata': result_data.get('metadata', {})
                        }

                        # Cache the result
                        self.save_to_cache(url, result, 'content')

                        if self.verbose:
                            print(f"  ✓ Scraped: {url}")

                        return result
                    else:
                        error_text = await response.text()
                        print(f"  ✗ Firecrawl error {response.status}: {error_text[:200]}")
                        return None

            except Exception as e:
                print(f"  ✗ Error scraping {url}: {e}")
                return None

    async def generate_nl_examples_ollama(self, url: str, content: Dict) -> List[str]:
        """
        Generate natural language examples using Ollama.

        Args:
            url: The URL being processed
            content: Scraped content dictionary

        Returns:
            List of natural language question examples
        """
        # Check cache
        cached = self.load_from_cache(url, 'examples')
        if cached and 'examples' in cached:
            if self.verbose:
                print(f"  ↳ Using cached examples for: {url}")
            return cached['examples']

        title = content.get('title', '')
        description = content.get('description', '')
        page_content = content.get('content', '')[:4000]  # Limit for context window

        # Build context from available information
        context_parts = []
        if title:
            context_parts.append(f"Page Title: {title}")
        if description:
            context_parts.append(f"Description: {description}")
        if page_content:
            context_parts.append(f"Content Preview:\n{page_content[:2000]}")

        context = '\n'.join(context_parts) if context_parts else f"URL: {url}"

        prompt = f"""You are generating natural language query examples for a Q&A system.
Given the following web page information, generate exactly {self.num_examples} different ways a user might ask about this content.

{context}

REQUIREMENTS:
1. Generate exactly {self.num_examples} questions/queries
2. Each should be a natural way someone would ask for this information
3. Include variety:
   - Direct questions: "What is...?", "How does...?"
   - Information requests: "Tell me about...", "I need information on..."
   - Explanation requests: "Explain...", "Can you describe...?"
4. Use specific terms from the content when relevant
5. Keep each query concise (under 15 words)
6. NO meta-references like "according to this page"

OUTPUT FORMAT:
Return a JSON array of strings, nothing else.
Example: ["What is X?", "Tell me about X", "How does X work?", "X information", "Explain X"]

JSON array:"""

        try:
            async with self.semaphore:
                await asyncio.sleep(self.delay)

                payload = {
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": OLLAMA_TEMPERATURE,
                        "num_ctx": OLLAMA_NUM_CTX,
                        "num_predict": 512
                    }
                }

                async with self.session.post(
                    f"{OLLAMA_BASE_URL}/api/generate",
                    json=payload
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        output = result.get('response', '').strip()

                        # Parse JSON array from output
                        examples = self._parse_examples_output(output)

                        if examples:
                            # Cache the results
                            self.save_to_cache(url, {'examples': examples}, 'examples')
                            return examples

            # Fallback: generate basic examples from title/URL
            return self._generate_fallback_examples(url, content)

        except Exception as e:
            print(f"  ✗ Error generating examples: {e}")
            return self._generate_fallback_examples(url, content)

    async def generate_nl_examples_openai(self, url: str, content: Dict) -> List[str]:
        """
        Generate natural language examples using OpenAI API.

        Args:
            url: The URL being processed
            content: Scraped content dictionary

        Returns:
            List of natural language question examples
        """
        if not OPENAI_AVAILABLE:
            print("  ⚠️  OpenAI not available, falling back to Ollama")
            return await self.generate_nl_examples_ollama(url, content)

        # Check cache
        cached = self.load_from_cache(url, 'examples')
        if cached and 'examples' in cached:
            return cached['examples']

        title = content.get('title', '')
        description = content.get('description', '')
        page_content = content.get('content', '')[:3000]

        context_parts = []
        if title:
            context_parts.append(f"Page Title: {title}")
        if description:
            context_parts.append(f"Description: {description}")
        if page_content:
            context_parts.append(f"Content Preview:\n{page_content[:1500]}")

        context = '\n'.join(context_parts) if context_parts else f"URL: {url}"

        try:
            client = openai.AsyncOpenAI()

            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You generate natural language query examples for a Q&A retrieval system. Output only a JSON array of strings."
                    },
                    {
                        "role": "user",
                        "content": f"""Generate exactly {self.num_examples} different ways a user might ask about this web page:

{context}

Requirements:
- Natural, conversational queries
- Include questions, requests, and statements
- Use specific terms from the content
- Keep each under 15 words
- No meta-references

Output: JSON array only, e.g., ["query1", "query2", ...]"""
                    }
                ],
                temperature=0.7,
                max_tokens=300
            )

            output = response.choices[0].message.content.strip()
            examples = self._parse_examples_output(output)

            if examples:
                self.save_to_cache(url, {'examples': examples}, 'examples')
                return examples

            return self._generate_fallback_examples(url, content)

        except Exception as e:
            print(f"  ✗ OpenAI error: {e}")
            return self._generate_fallback_examples(url, content)

    def _parse_examples_output(self, output: str) -> List[str]:
        """Parse LLM output to extract examples list."""
        try:
            # Try direct JSON parse
            examples = json.loads(output)
            if isinstance(examples, list):
                return [str(e).strip() for e in examples if e][:self.num_examples]
        except json.JSONDecodeError:
            pass

        # Try to extract JSON array from text
        json_match = re.search(r'\[.*?\]', output, re.DOTALL)
        if json_match:
            try:
                examples = json.loads(json_match.group())
                if isinstance(examples, list):
                    return [str(e).strip() for e in examples if e][:self.num_examples]
            except json.JSONDecodeError:
                pass

        # Fallback: parse numbered list
        lines = output.strip().split('\n')
        examples = []
        for line in lines:
            # Match numbered items or bullet points
            match = re.match(r'^\s*(?:\d+[.\)]\s*|[-*•]\s*)?["\']?(.+?)["\']?\s*$', line)
            if match:
                example = match.group(1).strip().strip('"\'')
                if example and len(example) > 5:
                    examples.append(example)

        return examples[:self.num_examples]

    def _generate_fallback_examples(self, url: str, content: Dict) -> List[str]:
        """Generate basic fallback examples when LLM fails."""
        title = content.get('title', '')
        path = urlparse(url).path.strip('/')

        # Extract topic from title or path
        if title:
            topic = title.split('|')[0].split('-')[0].strip()
        elif path:
            topic = path.split('/')[-1].replace('-', ' ').replace('_', ' ').title()
        else:
            topic = "this topic"

        return [
            f"What is {topic}?",
            f"Tell me about {topic}",
            f"{topic} information",
            f"Explain {topic}",
            f"I need help with {topic}"
        ][:self.num_examples]

    def generate_description(self, url: str, content: Dict) -> str:
        """Generate a description for the template."""
        title = content.get('title', '')
        description = content.get('description', '')

        if description and len(description) > 10:
            # Clean up description
            desc = description.split('.')[0].strip()
            if len(desc) > 100:
                desc = desc[:100] + '...'
            return desc

        if title:
            return f"Information about {title.split('|')[0].strip()}"

        path = urlparse(url).path.strip('/')
        if path:
            topic = path.split('/')[-1].replace('-', ' ').replace('_', ' ').title()
            return f"Information about {topic}"

        return "Web page information"

    async def process_url(self, url_entry: Dict) -> Optional[Dict]:
        """
        Process a single URL and generate its template.

        Args:
            url_entry: Dictionary with 'url' and optionally 'file_name'

        Returns:
            Template dictionary or None if failed
        """
        url = url_entry.get('url', '')
        if not url:
            return None

        self.stats['processed'] += 1

        if self.verbose:
            print(f"\n[{self.stats['processed']}/{self.stats['total_urls']}] Processing: {url}")

        # Step 1: Scrape content
        content = await self.scrape_url_content(url)
        if not content:
            self.stats['failed'] += 1
            # Use minimal content for template generation
            content = {'url': url, 'title': '', 'description': '', 'content': ''}

        # Step 2: Generate nl_examples
        if self.use_openai:
            examples = await self.generate_nl_examples_openai(url, content)
        else:
            examples = await self.generate_nl_examples_ollama(url, content)

        if not examples:
            self.stats['failed'] += 1
            return None

        # Step 3: Build template
        template = {
            'id': self.generate_template_id(url),
            'description': self.generate_description(url, content),
            'semantic_type': self.detect_semantic_type(url),
            'nl_examples': examples,
            'url_mapping': {
                'url': url
            },
            'formats': ['markdown'],
            'timeout': 45
        }

        self.stats['templates_generated'] += 1

        if self.verbose:
            print(f"  ✓ Generated template: {template['id']}")
            for ex in examples[:3]:
                print(f"    - {ex}")

        return template

    async def generate_templates(self) -> Dict[str, Any]:
        """
        Main method to generate all templates.

        Returns:
            Complete template configuration dictionary
        """
        # Load URLs
        with open(self.input_file, 'r', encoding='utf-8') as f:
            urls = json.load(f)

        if self.limit:
            urls = urls[:self.limit]

        self.stats['total_urls'] = len(urls)

        print(f"🚀 Starting template generation for {len(urls)} URLs")
        print(f"   Output: {self.output_file}")
        print(f"   Examples per template: {self.num_examples}")
        print(f"   LLM: {'OpenAI' if self.use_openai else 'Ollama'}")
        print("-" * 60)

        # Auto-detect domain name if not provided
        if not self.domain_name and urls:
            first_url = urls[0].get('url', '')
            parsed = urlparse(first_url)
            self.domain_name = parsed.netloc.replace('www.', '').replace('.', '_') + '_knowledge_base'

        # Process URLs
        templates = []
        for url_entry in urls:
            template = await self.process_url(url_entry)
            if template:
                templates.append(template)

        # Build final output
        output = {
            'templates': templates
        }

        return output

    def save_templates(self, templates: Dict[str, Any]):
        """Save templates to YAML file."""
        # Create output directory if needed
        self.output_file.parent.mkdir(parents=True, exist_ok=True)

        # Add header comment
        header = f"""# Firecrawl Intent Templates
# Generated by template_generator.py
# Domain: {self.domain_name}
# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}
# Total templates: {len(templates.get('templates', []))}
#
# Usage: These templates are used by IntentFirecrawlRetriever to map
# natural language queries to specific URLs for grounded responses.

"""

        with open(self.output_file, 'w', encoding='utf-8') as f:
            f.write(header)
            yaml.dump(templates, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        print(f"\n✅ Templates saved to: {self.output_file}")

    def print_statistics(self):
        """Print generation statistics."""
        print("\n" + "=" * 60)
        print("TEMPLATE GENERATION STATISTICS")
        print("=" * 60)
        print(f"Total URLs:          {self.stats['total_urls']}")
        print(f"Processed:           {self.stats['processed']}")
        print(f"From cache:          {self.stats['cached']}")
        print(f"Failed:              {self.stats['failed']}")
        print(f"Templates generated: {self.stats['templates_generated']}")

        if self.stats['total_urls'] > 0:
            success_rate = (self.stats['templates_generated'] / self.stats['total_urls']) * 100
            print(f"\nSuccess rate: {success_rate:.1f}%")
        print("=" * 60)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Generate Firecrawl intent templates from URLs',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--input', '-i', required=True,
                        help='Input JSON file with URLs')
    parser.add_argument('--output', '-o', default='firecrawl_templates.yaml',
                        help='Output YAML file (default: firecrawl_templates.yaml)')
    parser.add_argument('--examples', '-e', type=int, default=5,
                        help='Number of nl_examples per template (default: 5)')
    parser.add_argument('--delay', type=float, default=0.5,
                        help='Delay between API calls in seconds (default: 0.5)')
    parser.add_argument('--limit', type=int, default=None,
                        help='Maximum number of URLs to process')
    parser.add_argument('--domain', type=str, default=None,
                        help='Domain name for template collection')
    parser.add_argument('--use-openai', action='store_true',
                        help='Use OpenAI API instead of Ollama')
    parser.add_argument('--no-cache', action='store_true',
                        help='Skip cache and regenerate all')
    parser.add_argument('--skip-scrape', action='store_true',
                        help='Skip scraping, use cached content only')
    parser.add_argument('--timeout', type=int, default=60,
                        help='Request timeout in seconds (default: 60)')
    parser.add_argument('--concurrent', type=int, default=3,
                        help='Maximum concurrent requests (default: 3)')
    parser.add_argument('--semantic-types', type=str, default=None,
                        help='JSON file with custom semantic type mappings')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable verbose output')

    args = parser.parse_args()

    # Build config
    config = {
        'input': args.input,
        'output': args.output,
        'examples': args.examples,
        'delay': args.delay,
        'limit': args.limit,
        'domain': args.domain,
        'use_openai': args.use_openai,
        'no_cache': args.no_cache,
        'skip_scrape': args.skip_scrape,
        'timeout': args.timeout,
        'concurrent': args.concurrent,
        'semantic_types_file': args.semantic_types,
        'verbose': args.verbose
    }

    # Create generator and run
    generator = TemplateGenerator(config)

    try:
        await generator.initialize()
        templates = await generator.generate_templates()
        generator.save_templates(templates)
        generator.print_statistics()
    finally:
        await generator.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
