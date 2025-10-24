#!/usr/bin/env python3
"""
Test HTTP Adapter Loading

This script tests that HTTP adapters can be loaded correctly and
queries can be executed against them.
"""

import argparse
import asyncio
import sys
import yaml
from pathlib import Path
from typing import Dict, Any

# Add parent directories to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'server'))


async def test_adapter_loading(adapter_name: str, test_query: str = None):
    """
    Test loading and querying an HTTP adapter.

    Args:
        adapter_name: Name of the adapter to test
        test_query: Optional test query to execute
    """
    try:
        print(f"\n{'=' * 60}")
        print(f"Testing HTTP Adapter: {adapter_name}")
        print(f"{'=' * 60}\n")

        # Load configuration
        config_path = Path(__file__).parent.parent.parent / 'config' / 'config.yaml'
        print(f"📂 Loading configuration from: {config_path}")

        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        # Load adapters configuration
        adapters_path = Path(__file__).parent.parent.parent / 'config' / 'adapters.yaml'
        print(f"📂 Loading adapters from: {adapters_path}")

        with open(adapters_path, 'r') as f:
            adapters_config = yaml.safe_load(f)

        # Find the adapter
        adapter_config = None
        for adapter in adapters_config.get('adapters', []):
            if adapter['name'] == adapter_name:
                adapter_config = adapter
                break

        if not adapter_config:
            print(f"❌ Error: Adapter '{adapter_name}' not found in adapters.yaml")
            return False

        if not adapter_config.get('enabled', False):
            print(f"⚠️  Warning: Adapter '{adapter_name}' is disabled")
            print("   Enable it in config/adapters.yaml to use it")
            return False

        print(f"✓ Found adapter configuration")
        print(f"   Type: {adapter_config.get('type')}")
        print(f"   Implementation: {adapter_config.get('implementation')}")

        # Check domain and template files
        adapter_specific_config = adapter_config.get('config', {})
        domain_config_path = adapter_specific_config.get('domain_config_path')
        template_library_paths = adapter_specific_config.get('template_library_path', [])

        if domain_config_path:
            domain_path = Path(__file__).parent.parent.parent / domain_config_path
            if domain_path.exists():
                print(f"✓ Domain config found: {domain_config_path}")
            else:
                print(f"❌ Domain config not found: {domain_path}")
                return False

        if isinstance(template_library_paths, list):
            for template_path in template_library_paths:
                full_path = Path(__file__).parent.parent.parent / template_path
                if full_path.exists():
                    with open(full_path, 'r') as f:
                        templates = yaml.safe_load(f)
                        template_count = len(templates.get('templates', []))
                    print(f"✓ Template library found: {template_path} ({template_count} templates)")
                else:
                    print(f"❌ Template library not found: {full_path}")
                    return False

        # Try to import the retriever class
        print("\n📦 Testing retriever class import...")
        implementation = adapter_config.get('implementation')

        try:
            module_path, class_name = implementation.rsplit('.', 1)
            module = __import__(module_path, fromlist=[class_name])
            retriever_class = getattr(module, class_name)
            print(f"✓ Successfully imported {class_name}")
        except Exception as e:
            print(f"❌ Error importing retriever class: {e}")
            return False

        # Try to initialize the adapter
        print("\n🔧 Testing adapter initialization...")

        try:
            # Merge adapter-specific config with global config
            merged_config = config.copy()
            merged_config['adapter_config'] = adapter_specific_config
            merged_config['inference_provider'] = adapter_config.get('inference_provider')
            merged_config['embedding'] = {
                'provider': adapter_config.get('embedding_provider', config.get('embedding', {}).get('provider'))
            }

            # Create retriever instance
            retriever = retriever_class(config=merged_config)
            print(f"✓ Created retriever instance")

            # Initialize the retriever
            print("   Initializing retriever (this may take a moment)...")
            await retriever.initialize()
            print(f"✓ Retriever initialized successfully")

            # Execute test query if provided
            if test_query:
                print(f"\n🔍 Executing test query...")
                print(f"   Query: \"{test_query}\"")

                results = await retriever.get_relevant_context(test_query)

                print(f"\n📊 Results:")
                print(f"   Found {len(results)} results")

                for i, result in enumerate(results, 1):
                    print(f"\n   Result {i}:")
                    print(f"   Confidence: {result.get('confidence', 0):.2%}")

                    metadata = result.get('metadata', {})
                    if 'template_id' in metadata:
                        print(f"   Template: {metadata['template_id']}")
                    if 'parameters_used' in metadata:
                        print(f"   Parameters: {metadata['parameters_used']}")

                    content = result.get('content', '')
                    if len(content) > 500:
                        print(f"   Content: {content[:500]}...")
                    else:
                        print(f"   Content: {content}")

            # Clean up
            await retriever.close()
            print(f"\n✓ Retriever closed successfully")

            print(f"\n{'=' * 60}")
            print(f"✅ Adapter '{adapter_name}' is working correctly!")
            print(f"{'=' * 60}\n")

            return True

        except Exception as e:
            print(f"❌ Error initializing or testing adapter: {e}")
            import traceback
            traceback.print_exc()
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def list_http_adapters():
    """List all HTTP adapters in the configuration."""
    try:
        adapters_path = Path(__file__).parent.parent.parent / 'config' / 'adapters.yaml'

        with open(adapters_path, 'r') as f:
            adapters_config = yaml.safe_load(f)

        http_adapters = [
            adapter for adapter in adapters_config.get('adapters', [])
            if adapter.get('datasource') == 'http' or 'HTTP' in adapter.get('implementation', '')
        ]

        print("\n📋 Available HTTP Adapters:")
        print("=" * 60)

        for adapter in http_adapters:
            name = adapter['name']
            enabled = "✓" if adapter.get('enabled', False) else "✗"
            implementation = adapter.get('implementation', 'Unknown')

            print(f"\n{enabled} {name}")
            print(f"   Implementation: {implementation}")
            print(f"   Enabled: {adapter.get('enabled', False)}")

            config = adapter.get('config', {})
            if 'base_url' in config:
                print(f"   Base URL: {config['base_url']}")

        print()

    except Exception as e:
        print(f"❌ Error listing adapters: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Test HTTP adapter loading and configuration',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all HTTP adapters
  python test_adapter_loading.py --list

  # Test adapter loading
  python test_adapter_loading.py --adapter-name intent-http-github

  # Test adapter with a query
  python test_adapter_loading.py \\
      --adapter-name intent-http-github \\
      --query "Show me repositories for octocat"
        """
    )

    parser.add_argument('--adapter-name', help='Name of the adapter to test')
    parser.add_argument('--query', help='Test query to execute')
    parser.add_argument('--list', action='store_true', help='List all HTTP adapters')

    args = parser.parse_args()

    if args.list:
        asyncio.run(list_http_adapters())
    elif args.adapter_name:
        success = asyncio.run(test_adapter_loading(args.adapter_name, args.query))
        sys.exit(0 if success else 1)
    else:
        parser.error("Either --list or --adapter-name must be specified")


if __name__ == '__main__':
    main()
