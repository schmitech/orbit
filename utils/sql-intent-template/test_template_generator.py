#!/usr/bin/env python3
"""
Test script for the template generator

This script provides test functions to validate the template generator functionality.
It includes both basic unit tests and full pipeline tests.

USAGE:
    # Run the test script directly
    python utils/test_template_generator.py

    # Or import and run specific tests
    from utils.test_template_generator import test_basic_generation
    asyncio.run(test_basic_generation())

TESTS INCLUDED:
    1. test_basic_generation() - Tests basic template generation with sample queries
    2. test_full_pipeline() - Tests the complete pipeline with actual files

REQUIREMENTS:
    - Ollama running locally (or other configured inference provider)
    - Config files present (config/config.yaml)
    - For full pipeline test: PostgreSQL example files

WHAT IT TESTS:
    - Query analysis functionality
    - SQL template generation
    - Template validation
    - File I/O operations
    - Schema parsing

OUTPUT:
    - Console output showing test progress
    - Generated test_generated_templates.yaml file
    - Validation results for each template

NOTES:
    - The basic test uses a hardcoded schema for simplicity
    - The full pipeline test requires actual schema and query files
    - Uncomment the full pipeline test call in main() to run it
    - Tests are designed to work with default Ollama configuration
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from utils.template_generator import TemplateGenerator


async def test_basic_generation():
    """Test basic template generation with a few queries"""
    
    # Sample queries to test
    test_queries = [
        "Show me orders from John Smith",
        "What did customer 123 order?",
        "Find orders over $500",
        "Show me all pending orders",
        "How much did we sell on 2025-07-22?",
        "Who are our top 10 customers?",
        "Find orders from New York customers",
        "Show me orders paid with credit card"
    ]
    
    # Initialize generator (using ollama by default)
    generator = TemplateGenerator(
        config_path="config/config.yaml",
        provider="ollama"
    )
    
    # Initialize inference client
    await generator.initialize()
    
    # Manually set a simple schema for testing
    generator.schema = {
        'customers': {
            'name': 'customers',
            'columns': [
                {'name': 'id', 'type': 'SERIAL', 'nullable': False},
                {'name': 'name', 'type': 'VARCHAR(255)', 'nullable': False},
                {'name': 'email', 'type': 'VARCHAR(255)', 'nullable': False},
                {'name': 'city', 'type': 'VARCHAR(100)', 'nullable': True},
                {'name': 'country', 'type': 'VARCHAR(100)', 'nullable': True},
            ]
        },
        'orders': {
            'name': 'orders',
            'columns': [
                {'name': 'id', 'type': 'SERIAL', 'nullable': False},
                {'name': 'customer_id', 'type': 'INTEGER', 'nullable': False},
                {'name': 'order_date', 'type': 'DATE', 'nullable': False},
                {'name': 'total', 'type': 'DECIMAL(10,2)', 'nullable': False},
                {'name': 'status', 'type': 'VARCHAR(50)', 'nullable': True},
                {'name': 'payment_method', 'type': 'VARCHAR(50)', 'nullable': True},
            ],
            'foreign_keys': [
                {
                    'column': 'customer_id',
                    'references_table': 'customers',
                    'references_column': 'id'
                }
            ]
        }
    }
    
    print("Testing query analysis...")
    # Test analyzing individual queries
    for query in test_queries[:3]:
        print(f"\nAnalyzing: {query}")
        analysis = await generator.analyze_query(query)
        print(f"Analysis: {analysis}")
    
    print("\n" + "="*50 + "\n")
    print("Testing template generation...")
    
    # Generate templates for all test queries
    templates = await generator.generate_templates(test_queries)
    
    print(f"\nGenerated {len(templates)} templates:")
    for i, template in enumerate(templates):
        print(f"\nTemplate {i+1}: {template.get('id', 'unknown')}")
        print(f"Description: {template.get('description', 'N/A')}")
        print(f"SQL: {template.get('sql', 'N/A')[:100]}...")
        print(f"Parameters: {[p['name'] for p in template.get('parameters', [])]}")
        print(f"Examples: {len(template.get('nl_examples', []))}")
        
        # Validate template
        errors = generator.validate_template(template)
        if errors:
            print(f"Validation errors: {errors}")
        else:
            print("✓ Valid template")
    
    # Save templates to a test file
    output_path = "test_generated_templates.yaml"
    generator.save_templates(templates, output_path)
    print(f"\nTemplates saved to: {output_path}")


async def test_full_pipeline():
    """Test the full pipeline with actual files"""
    print("\nTesting full pipeline with PostgreSQL example...")
    
    schema_path = "examples/postgres/customer-order.sql"
    queries_path = "examples/postgres/test/test_queries.md"
    domain_path = "examples/postgres/customer_order_domain.yaml"
    output_path = "examples/postgres/generated_templates.yaml"
    
    # Check if files exist
    for path in [schema_path, queries_path]:
        if not Path(path).exists():
            print(f"Error: Required file not found: {path}")
            return
    
    # Run the generator
    from utils.template_generator import main
    
    # Simulate command line arguments
    sys.argv = [
        'template_generator.py',
        '--schema', schema_path,
        '--queries', queries_path,
        '--output', output_path,
        '--limit', '20',  # Limit to 20 queries for testing
        '--provider', 'ollama'
    ]
    
    if Path(domain_path).exists():
        sys.argv.extend(['--domain', domain_path])
    
    await main()


if __name__ == '__main__':
    print("Template Generator Test Suite")
    print("============================\n")
    
    # Run basic test
    print("1. Running basic generation test...")
    asyncio.run(test_basic_generation())
    
    # Uncomment to run full pipeline test
    # print("\n2. Running full pipeline test...")
    # asyncio.run(test_full_pipeline())
    
    print("\nTest complete!")