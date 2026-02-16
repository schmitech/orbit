#!/usr/bin/env python3
"""
GraphQL Adapter Loading Test

Tests that GraphQL intent adapters load correctly and can execute queries.
Useful for verifying configuration and template setup.

Usage:
    # List all GraphQL adapters
    python test_adapter_loading.py --list

    # Test adapter loading
    python test_adapter_loading.py --adapter-name intent-graphql-spacex

    # Test with a query
    python test_adapter_loading.py --adapter-name intent-graphql-spacex \\
        --query "Show me SpaceX launches"

    # Test against live API
    python test_adapter_loading.py --adapter-name intent-graphql-spacex \\
        --query "What rockets does SpaceX have?" --execute
"""

import argparse
import asyncio
import sys
import yaml
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config() -> Dict[str, Any]:
    """Load the main configuration."""
    config_paths = [
        Path('config/config.yaml'),
        Path('../config/config.yaml'),
        Path('../../config/config.yaml'),
    ]

    for config_path in config_paths:
        if config_path.exists():
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)

    raise FileNotFoundError("Could not find config.yaml")


def load_adapters_config() -> Dict[str, Any]:
    """Load the adapters configuration."""
    adapter_paths = [
        Path('config/adapters/intent.yaml'),
        Path('../config/adapters/intent.yaml'),
        Path('../../config/adapters/intent.yaml'),
    ]

    for adapter_path in adapter_paths:
        if adapter_path.exists():
            with open(adapter_path, 'r') as f:
                return yaml.safe_load(f)

    raise FileNotFoundError("Could not find adapters/intent.yaml")


def find_graphql_adapters(adapters_config: Dict) -> List[Dict]:
    """Find all GraphQL adapters in the configuration."""
    graphql_adapters = []

    for adapter in adapters_config.get('adapters', []):
        # Check if it's a GraphQL adapter
        implementation = adapter.get('implementation', '')
        if 'GraphQL' in implementation or 'graphql' in implementation.lower():
            graphql_adapters.append(adapter)

    return graphql_adapters


def get_adapter_by_name(adapters_config: Dict, name: str) -> Optional[Dict]:
    """Get a specific adapter by name."""
    for adapter in adapters_config.get('adapters', []):
        if adapter.get('name') == name:
            return adapter
    return None


def validate_adapter_config(adapter: Dict) -> List[str]:
    """Validate adapter configuration."""
    errors = []

    # Check required fields
    required_fields = ['name', 'type', 'implementation']
    for field in required_fields:
        if field not in adapter:
            errors.append(f"Missing required field: {field}")

    # Check config section
    config = adapter.get('config', {})
    if not config:
        errors.append("Missing 'config' section")
    else:
        # Check GraphQL-specific config
        if not config.get('domain_config_path'):
            errors.append("Missing domain_config_path in config")
        if not config.get('template_library_path'):
            errors.append("Missing template_library_path in config")
        if not config.get('base_url'):
            errors.append("Missing base_url in config")

    return errors


def check_file_exists(path: str) -> bool:
    """Check if a configuration file exists."""
    # Try multiple base paths
    base_paths = [Path('.'), Path('..'), Path('../..')]

    for base in base_paths:
        full_path = base / path
        if full_path.exists():
            return True

    return False


def load_templates(template_paths: List[str]) -> List[Dict]:
    """Load templates from the specified paths."""
    templates = []
    base_paths = [Path('.'), Path('..'), Path('../..')]

    for template_path in template_paths:
        for base in base_paths:
            full_path = base / template_path
            if full_path.exists():
                with open(full_path, 'r') as f:
                    data = yaml.safe_load(f)
                    templates.extend(data.get('templates', []))
                break

    return templates


async def test_adapter_initialization(adapter: Dict, config: Dict) -> bool:
    """
    Test that an adapter can be initialized.

    Returns True if successful.
    """
    try:
        # Dynamically import the retriever class
        implementation = adapter['implementation']
        module_path, class_name = implementation.rsplit('.', 1)

        # Add server to path if needed
        sys.path.insert(0, str(Path('server').absolute()))
        sys.path.insert(0, str(Path('../server').absolute()))
        sys.path.insert(0, str(Path('../../server').absolute()))

        import importlib
        module = importlib.import_module(module_path)
        retriever_class = getattr(module, class_name)

        print(f"✓ Successfully imported {class_name}")

        # Build configuration for retriever
        retriever_config = {
            **config,
            'adapter_config': adapter.get('config', {}),
            'embedding': config.get('embedding', {}),
            'inference': config.get('inference', {}),
        }

        # Add provider overrides
        if adapter.get('inference_provider'):
            retriever_config['inference_provider'] = adapter['inference_provider']
        if adapter.get('embedding_provider'):
            retriever_config['embedding']['provider'] = adapter['embedding_provider']

        # Create instance
        retriever = retriever_class(config=retriever_config)
        print("✓ Created retriever instance")

        # Initialize
        await retriever.initialize()
        print("✓ Retriever initialized successfully")

        # Clean up
        await retriever.close()

        return True

    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False
    except Exception as e:
        print(f"✗ Initialization error: {e}")
        logger.exception("Full error:")
        return False


async def test_query_execution(adapter: Dict, config: Dict, query: str, execute: bool = False) -> bool:
    """
    Test query execution against the adapter.

    Args:
        adapter: Adapter configuration
        config: Main configuration
        query: Natural language query to test
        execute: If True, actually execute against the API
    """
    try:
        # Import and initialize retriever
        implementation = adapter['implementation']
        module_path, class_name = implementation.rsplit('.', 1)

        sys.path.insert(0, str(Path('server').absolute()))
        sys.path.insert(0, str(Path('../server').absolute()))
        sys.path.insert(0, str(Path('../../server').absolute()))

        import importlib
        module = importlib.import_module(module_path)
        retriever_class = getattr(module, class_name)

        retriever_config = {
            **config,
            'adapter_config': adapter.get('config', {}),
            'embedding': config.get('embedding', {}),
            'inference': config.get('inference', {}),
        }

        if adapter.get('inference_provider'):
            retriever_config['inference_provider'] = adapter['inference_provider']
        if adapter.get('embedding_provider'):
            retriever_config['embedding']['provider'] = adapter['embedding_provider']

        retriever = retriever_class(config=retriever_config)
        await retriever.initialize()

        print(f"\n📝 Query: \"{query}\"")
        print("-" * 50)

        if execute:
            # Actually execute the query
            results = await retriever.get_relevant_context(query)

            print("\n📊 Results:")
            for i, result in enumerate(results, 1):
                print(f"\nResult {i}:")
                print(f"  Confidence: {result.get('confidence', 0):.2%}")

                metadata = result.get('metadata', {})
                print(f"  Template: {metadata.get('template_id', 'N/A')}")
                print(f"  Parameters: {metadata.get('parameters_used', {})}")

                content = result.get('content', '')
                if len(content) > 500:
                    content = content[:500] + "..."
                print(f"\n  Content:\n{content}")
        else:
            # Just test template matching
            print("(Dry run - use --execute to run against live API)")

            # Test template matching only
            if hasattr(retriever, '_find_best_templates'):
                templates = await retriever._find_best_templates(query)

                if templates:
                    print(f"\n🎯 Matched {len(templates)} template(s):")
                    for t in templates[:3]:
                        template = t['template']
                        print(f"\n  Template: {template.get('id')}")
                        print(f"  Similarity: {t['similarity']:.2%}")
                        print(f"  Description: {template.get('description', 'N/A')}")
                else:
                    print("\n⚠️  No matching templates found")

        # Clean up
        await retriever.close()
        return True

    except Exception as e:
        print(f"✗ Query execution error: {e}")
        logger.exception("Full error:")
        return False


def list_adapters(adapters_config: Dict):
    """List all GraphQL adapters."""
    graphql_adapters = find_graphql_adapters(adapters_config)

    if not graphql_adapters:
        print("No GraphQL adapters found in configuration.")
        return

    print(f"\n📋 Found {len(graphql_adapters)} GraphQL adapter(s):\n")

    for adapter in graphql_adapters:
        name = adapter.get('name', 'unnamed')
        enabled = adapter.get('enabled', False)
        status = "✓ enabled" if enabled else "✗ disabled"
        implementation = adapter.get('implementation', 'N/A')

        print(f"  {name}")
        print(f"    Status: {status}")
        print(f"    Implementation: {implementation}")

        config = adapter.get('config', {})
        if config.get('base_url'):
            print(f"    Base URL: {config['base_url']}")
        if config.get('graphql_endpoint'):
            print(f"    Endpoint: {config['graphql_endpoint']}")

        print()


async def main():
    parser = argparse.ArgumentParser(
        description='Test GraphQL intent adapter loading and query execution'
    )

    parser.add_argument('--list', '-l', action='store_true',
                       help='List all GraphQL adapters')
    parser.add_argument('--adapter-name', '-a',
                       help='Name of adapter to test')
    parser.add_argument('--query', '-q',
                       help='Test query to execute')
    parser.add_argument('--execute', '-e', action='store_true',
                       help='Actually execute query against live API')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load configurations
    try:
        config = load_config()
        adapters_config = load_adapters_config()
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # List mode
    if args.list:
        list_adapters(adapters_config)
        return

    # Test specific adapter
    if args.adapter_name:
        adapter = get_adapter_by_name(adapters_config, args.adapter_name)
        if not adapter:
            print(f"Error: Adapter '{args.adapter_name}' not found", file=sys.stderr)
            print("\nAvailable GraphQL adapters:")
            for a in find_graphql_adapters(adapters_config):
                print(f"  - {a.get('name')}")
            sys.exit(1)

        print(f"\n🔍 Testing adapter: {args.adapter_name}")
        print("=" * 50)

        # Validate configuration
        print("\n📋 Validating configuration...")
        errors = validate_adapter_config(adapter)
        if errors:
            print("Configuration errors:")
            for error in errors:
                print(f"  ✗ {error}")
            sys.exit(1)
        print("✓ Configuration is valid")

        # Check file existence
        print("\n📁 Checking files...")
        config_section = adapter.get('config', {})

        domain_path = config_section.get('domain_config_path')
        if domain_path:
            if check_file_exists(domain_path):
                print(f"✓ Domain config found: {domain_path}")
            else:
                print(f"✗ Domain config not found: {domain_path}")

        template_paths = config_section.get('template_library_path', [])
        if isinstance(template_paths, str):
            template_paths = [template_paths]

        for tp in template_paths:
            if check_file_exists(tp):
                print(f"✓ Template library found: {tp}")
            else:
                print(f"✗ Template library not found: {tp}")

        # Load and count templates
        templates = load_templates(template_paths)
        print(f"\n📝 Found {len(templates)} template(s)")

        # Test query if provided
        if args.query:
            print("\n🧪 Testing query execution...")
            success = await test_query_execution(adapter, config, args.query, args.execute)
            if not success:
                sys.exit(1)
        else:
            # Just test initialization
            print("\n🧪 Testing adapter initialization...")
            success = await test_adapter_initialization(adapter, config)
            if not success:
                sys.exit(1)

        print("\n✅ All tests passed!")

    else:
        parser.print_help()


if __name__ == '__main__':
    asyncio.run(main())
