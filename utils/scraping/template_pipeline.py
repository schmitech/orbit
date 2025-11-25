#!/usr/bin/env python3
"""
Template Pipeline Orchestrator

This script orchestrates the complete pipeline from URL discovery to
Firecrawl intent template generation. It combines:
1. URL extraction (from sitemap or single URL)
2. Content sampling via Firecrawl
3. Question generation via LLM (Ollama/OpenAI)
4. Template YAML generation

This creates a robust web crawler templating engine that produces
grounded responses based on specific, authoritative URLs.

Pipeline Flow:
-------------
                    ┌─────────────────┐
                    │   Input Source  │
                    │ (sitemap/URL)   │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  URL Extraction │
                    │ (url-extractor) │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ Content Sampling│
                    │   (Firecrawl)   │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  NL Examples    │
                    │ Generation(LLM) │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ Template Output │
                    │     (YAML)      │
                    └─────────────────┘

Usage:
------
# From sitemap
python template_pipeline.py --sitemap https://company.com/sitemap.xml --output ./templates/

# From single URL (crawl)
python template_pipeline.py --url https://company.com --output ./templates/ --max-depth 2

# From existing urls.json
python template_pipeline.py --urls-file urls.json --output ./templates/

# Quick mode (skip scraping, use URL-based generation)
python template_pipeline.py --sitemap https://company.com/sitemap.xml --output ./templates/ --quick

# Full options
python template_pipeline.py \\
    --sitemap https://company.com/sitemap.xml \\
    --output ./templates/ \\
    --domain "company_kb" \\
    --examples 5 \\
    --max-pages 50 \\
    --delay 1.0 \\
    --use-openai \\
    --verbose

Output:
-------
The pipeline generates:
1. urls.json - Extracted URLs with file mappings
2. firecrawl_templates.yaml - Intent templates for retrieval
3. firecrawl_domain.yaml - Domain configuration (optional)

Author: Orbit Pipeline Contributors
License: MIT
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse
import yaml


class TemplatePipeline:
    """
    Orchestrates the complete template generation pipeline.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the pipeline.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.output_dir = Path(config['output_dir'])
        self.verbose = config.get('verbose', False)

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Paths for intermediate and final files
        self.urls_file = self.output_dir / 'urls.json'
        self.templates_file = self.output_dir / 'firecrawl_templates.yaml'
        self.domain_file = self.output_dir / 'firecrawl_domain.yaml'

        # Pipeline statistics
        self.stats = {
            'urls_extracted': 0,
            'templates_generated': 0,
            'start_time': None,
            'end_time': None
        }

    def log(self, message: str, level: str = 'info'):
        """Log a message."""
        prefix = {
            'info': '→',
            'success': '✓',
            'warning': '⚠️',
            'error': '✗',
            'step': '📋'
        }.get(level, '→')

        if level == 'step':
            print(f"\n{'=' * 60}")
            print(f"{prefix} {message}")
            print('=' * 60)
        else:
            print(f"{prefix} {message}")

    async def step1_extract_urls(self) -> bool:
        """
        Step 1: Extract URLs from source.

        Returns:
            True if successful
        """
        self.log("STEP 1: URL EXTRACTION", 'step')

        # If urls file already provided, skip extraction
        if self.config.get('urls_file'):
            source_file = Path(self.config['urls_file'])
            if source_file.exists():
                # Copy to output directory
                with open(source_file, 'r') as f:
                    urls = json.load(f)
                with open(self.urls_file, 'w') as f:
                    json.dump(urls, f, indent=2)
                self.stats['urls_extracted'] = len(urls)
                self.log(f"Using existing URLs file: {source_file} ({len(urls)} URLs)", 'success')
                return True

        # Determine extraction method
        sitemap = self.config.get('sitemap')
        url = self.config.get('url')

        if not sitemap and not url:
            self.log("No URL source provided (--sitemap or --url required)", 'error')
            return False

        # Build command for url-extractor.py
        script_dir = Path(__file__).parent
        extractor_script = script_dir / 'url-extractor.py'

        if not extractor_script.exists():
            self.log(f"url-extractor.py not found at {extractor_script}", 'error')
            return False

        cmd = [
            sys.executable,
            str(extractor_script),
            '--output', str(self.urls_file)
        ]

        if sitemap:
            cmd.extend(['--sitemap', sitemap])
            self.log(f"Extracting URLs from sitemap: {sitemap}")
        else:
            cmd.extend(['--url', url])
            self.log(f"Extracting URLs starting from: {url}")

        # Add optional parameters
        if self.config.get('max_pages'):
            cmd.extend(['--max-pages', str(self.config['max_pages'])])
        if self.config.get('max_depth'):
            cmd.extend(['--max-depth', str(self.config['max_depth'])])
        if self.config.get('delay'):
            cmd.extend(['--delay', str(self.config['delay'])])

        try:
            if self.verbose:
                self.log(f"Running: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=not self.verbose,
                text=True,
                timeout=600  # 10 minute timeout
            )

            if result.returncode != 0:
                self.log(f"URL extraction failed: {result.stderr}", 'error')
                return False

            # Count extracted URLs
            if self.urls_file.exists():
                with open(self.urls_file, 'r') as f:
                    urls = json.load(f)
                self.stats['urls_extracted'] = len(urls)
                self.log(f"Extracted {len(urls)} URLs", 'success')
                return True
            else:
                self.log("URLs file not created", 'error')
                return False

        except subprocess.TimeoutExpired:
            self.log("URL extraction timed out", 'error')
            return False
        except Exception as e:
            self.log(f"URL extraction error: {e}", 'error')
            return False

    async def step2_generate_templates(self) -> bool:
        """
        Step 2: Generate templates from URLs.

        Returns:
            True if successful
        """
        self.log("STEP 2: TEMPLATE GENERATION", 'step')

        if not self.urls_file.exists():
            self.log(f"URLs file not found: {self.urls_file}", 'error')
            return False

        # Import template generator
        try:
            from template_generator import TemplateGenerator
        except ImportError:
            # Try relative import
            script_dir = Path(__file__).parent
            sys.path.insert(0, str(script_dir))
            from template_generator import TemplateGenerator

        # Build config for generator
        gen_config = {
            'input': str(self.urls_file),
            'output': str(self.templates_file),
            'examples': self.config.get('examples', 5),
            'delay': self.config.get('delay', 0.5),
            'limit': self.config.get('limit'),
            'domain': self.config.get('domain'),
            'use_openai': self.config.get('use_openai', False),
            'no_cache': self.config.get('no_cache', False),
            'skip_scrape': self.config.get('quick', False),
            'timeout': self.config.get('timeout', 60),
            'concurrent': self.config.get('concurrent', 3),
            'verbose': self.verbose
        }

        self.log(f"Generating templates with {gen_config['examples']} examples each")
        if gen_config['use_openai']:
            self.log("Using OpenAI for question generation")
        else:
            self.log("Using Ollama for question generation")

        try:
            generator = TemplateGenerator(gen_config)
            await generator.initialize()
            templates = await generator.generate_templates()
            generator.save_templates(templates)
            generator.print_statistics()
            await generator.cleanup()

            self.stats['templates_generated'] = len(templates.get('templates', []))
            self.log(f"Generated {self.stats['templates_generated']} templates", 'success')
            return True

        except Exception as e:
            self.log(f"Template generation error: {e}", 'error')
            import traceback
            if self.verbose:
                traceback.print_exc()
            return False

    async def step3_generate_domain_config(self) -> bool:
        """
        Step 3: Generate domain configuration file.

        Returns:
            True if successful
        """
        self.log("STEP 3: DOMAIN CONFIGURATION", 'step')

        if not self.templates_file.exists():
            self.log("Templates file not found, skipping domain config", 'warning')
            return True

        try:
            # Load templates to analyze
            with open(self.templates_file, 'r') as f:
                templates_data = yaml.safe_load(f)

            templates = templates_data.get('templates', [])

            # Extract unique semantic types
            semantic_types = set()
            for template in templates:
                st = template.get('semantic_type', 'general_info')
                semantic_types.add(st)

            # Detect domain from URLs
            domain_name = self.config.get('domain')
            if not domain_name and templates:
                first_url = templates[0].get('url_mapping', {}).get('url', '')
                if first_url:
                    parsed = urlparse(first_url)
                    domain_name = parsed.netloc.replace('www.', '').replace('.', '_')

            domain_name = domain_name or 'web_knowledge_base'

            # Build domain config
            domain_config = {
                'domain_name': domain_name,
                'version': '1.0',
                'generated': time.strftime('%Y-%m-%d %H:%M:%S'),

                'semantic_types': [
                    {
                        'name': st,
                        'description': f"Content related to {st.replace('_', ' ')}"
                    }
                    for st in sorted(semantic_types)
                ],

                'capabilities': [
                    {'name': 'topic_retrieval', 'description': 'Retrieve information about specific topics'},
                    {'name': 'factual_lookup', 'description': 'Look up factual information'},
                    {'name': 'concept_explanation', 'description': 'Explain concepts and terms'}
                ],

                'query_patterns': [
                    'What is {topic}?',
                    'Tell me about {topic}',
                    'Explain {topic}',
                    '{topic} information',
                    'How does {topic} work?',
                    'I need help with {topic}'
                ],

                'source_preferences': {
                    'prefer_authoritative': True,
                    'content_format': 'markdown'
                }
            }

            # Save domain config
            with open(self.domain_file, 'w') as f:
                yaml.dump(domain_config, f, default_flow_style=False, allow_unicode=True)

            self.log(f"Generated domain config: {self.domain_file}", 'success')
            return True

        except Exception as e:
            self.log(f"Domain config generation error: {e}", 'warning')
            return True  # Non-critical step

    async def run(self) -> bool:
        """
        Run the complete pipeline.

        Returns:
            True if successful
        """
        self.stats['start_time'] = time.time()

        print("\n" + "=" * 60)
        print("🚀 FIRECRAWL TEMPLATE PIPELINE")
        print("=" * 60)
        print(f"Output directory: {self.output_dir}")
        print("=" * 60)

        # Step 1: URL Extraction
        if not await self.step1_extract_urls():
            return False

        # Step 2: Template Generation
        if not await self.step2_generate_templates():
            return False

        # Step 3: Domain Configuration (optional)
        await self.step3_generate_domain_config()

        self.stats['end_time'] = time.time()
        duration = self.stats['end_time'] - self.stats['start_time']

        # Print summary
        print("\n" + "=" * 60)
        print("✅ PIPELINE COMPLETE")
        print("=" * 60)
        print(f"URLs extracted:      {self.stats['urls_extracted']}")
        print(f"Templates generated: {self.stats['templates_generated']}")
        print(f"Duration:            {duration:.1f} seconds")
        print(f"\nOutput files:")
        print(f"  - {self.urls_file}")
        print(f"  - {self.templates_file}")
        if self.domain_file.exists():
            print(f"  - {self.domain_file}")
        print("=" * 60)

        # Print usage hint
        print("\n📖 Next Steps:")
        print("-" * 60)
        print("1. Review generated templates in:")
        print(f"   {self.templates_file}")
        print("\n2. Copy templates to your retriever config:")
        print(f"   cp {self.templates_file} config/adapters/templates/")
        print("\n3. Update your adapter config to use the templates")
        print("-" * 60)

        return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Template Pipeline - URL to Firecrawl Templates',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # From sitemap
  python template_pipeline.py --sitemap https://company.com/sitemap.xml --output ./templates/

  # From single URL
  python template_pipeline.py --url https://company.com --output ./templates/ --max-depth 2

  # From existing urls.json
  python template_pipeline.py --urls-file urls.json --output ./templates/

  # Quick mode (no scraping)
  python template_pipeline.py --sitemap https://company.com/sitemap.xml --output ./templates/ --quick
"""
    )

    # Input source (mutually exclusive)
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument('--sitemap', type=str,
                              help='Sitemap XML URL to extract URLs from')
    source_group.add_argument('--url', type=str,
                              help='Single URL to start crawling from')
    source_group.add_argument('--urls-file', type=str,
                              help='Existing JSON file with URLs')

    # Output
    parser.add_argument('--output', '-o', type=str, default='./templates',
                        help='Output directory (default: ./templates)')

    # URL extraction options
    parser.add_argument('--max-pages', type=int, default=100,
                        help='Maximum pages to extract (default: 100)')
    parser.add_argument('--max-depth', type=int, default=3,
                        help='Maximum crawl depth (default: 3)')

    # Template generation options
    parser.add_argument('--examples', '-e', type=int, default=5,
                        help='NL examples per template (default: 5)')
    parser.add_argument('--domain', type=str,
                        help='Domain name for templates')
    parser.add_argument('--limit', type=int,
                        help='Limit number of templates to generate')

    # LLM options
    parser.add_argument('--use-openai', action='store_true',
                        help='Use OpenAI instead of Ollama')

    # Performance options
    parser.add_argument('--delay', type=float, default=0.5,
                        help='Delay between requests (default: 0.5)')
    parser.add_argument('--concurrent', type=int, default=3,
                        help='Concurrent requests (default: 3)')
    parser.add_argument('--timeout', type=int, default=60,
                        help='Request timeout (default: 60)')

    # Mode options
    parser.add_argument('--quick', action='store_true',
                        help='Quick mode - skip content scraping')
    parser.add_argument('--no-cache', action='store_true',
                        help='Disable caching')

    # Output options
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')

    args = parser.parse_args()

    # Validate input
    if not args.sitemap and not args.url and not args.urls_file:
        parser.error("One of --sitemap, --url, or --urls-file is required")

    # Build config
    config = {
        'sitemap': args.sitemap,
        'url': args.url,
        'urls_file': args.urls_file,
        'output_dir': args.output,
        'max_pages': args.max_pages,
        'max_depth': args.max_depth,
        'examples': args.examples,
        'domain': args.domain,
        'limit': args.limit,
        'use_openai': args.use_openai,
        'delay': args.delay,
        'concurrent': args.concurrent,
        'timeout': args.timeout,
        'quick': args.quick,
        'no_cache': args.no_cache,
        'verbose': args.verbose
    }

    # Run pipeline
    pipeline = TemplatePipeline(config)

    try:
        success = asyncio.run(pipeline.run())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Pipeline interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Pipeline error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
