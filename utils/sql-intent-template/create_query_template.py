#!/usr/bin/env python3
"""
Test Queries Template Generator

DESCRIPTION:
    Creates a starter markdown template for test queries based on your
    database schema. This gives you a structured starting point to write
    natural language queries for template generation.

    While it doesn't automatically generate the queries themselves (you need
    domain knowledge for that), it creates organized sections based on your
    database tables and suggests query categories.

USAGE:
    python create_query_template.py --schema <schema.sql> --output <queries.md>

ARGUMENTS:
    --schema FILE    Path to SQL schema file
    --output FILE    Path to output markdown file (default: test_queries.md)

EXAMPLES:
    # Create template from contact schema
    python create_query_template.py --schema examples/contact.sql

    # Specify output file
    python create_query_template.py \
      --schema examples/ecommerce.sql \
      --output examples/ecommerce_queries.md

OUTPUT:
    Creates a markdown file with:
    - Title and description
    - Sections for each database table
    - Suggested query categories (search, filter, count, etc.)
    - Placeholder lines ready for you to fill in
    - Examples showing expected format

WORKFLOW:
    1. Parse schema to extract table names and columns
    2. Create organized sections for each table
    3. Add common query patterns for each entity type
    4. Save markdown template
    5. YOU manually fill in the actual query examples

NEXT STEPS:
    1. Run this script to generate template
    2. Open generated markdown file
    3. Replace placeholder queries with real examples
    4. Aim for 10-50+ queries per table
    5. Use with generate_templates.sh

SEE ALSO:
    - examples/contact_test_queries.md - Simple example
    - examples/classified-data_test_queries.md - Complex example
    - generate_templates.sh - Uses these query files

AUTHOR:
    SQL Intent Template Generator v1.0.0
"""

import re
import argparse
from pathlib import Path
from typing import Dict, List, Any

def parse_schema(schema_path: str) -> Dict[str, Any]:
    """Parse SQL schema to extract tables and columns"""
    with open(schema_path, 'r') as f:
        schema_sql = f.read()

    tables = {}

    # Find CREATE TABLE statements
    table_pattern = r'CREATE TABLE(?:\s+IF NOT EXISTS)?\s+(\w+)\s*\((.*?)\);'
    matches = re.findall(table_pattern, schema_sql, re.IGNORECASE | re.DOTALL)

    for table_name, table_def in matches:
        columns = []

        # Parse column definitions
        lines = table_def.strip().split('\n')
        for line in lines:
            line = line.strip().rstrip(',')
            if not line or line.startswith('--'):
                continue

            # Skip constraint definitions
            line_upper = line.upper()
            if line_upper.startswith('PRIMARY KEY') or line_upper.startswith('FOREIGN KEY') or \
               line_upper.startswith('CHECK') or line_upper.startswith('CONSTRAINT'):
                continue

            # Parse column name and type
            parts = line.split()
            if len(parts) >= 2:
                col_name = parts[0]
                col_type = parts[1]
                columns.append({'name': col_name, 'type': col_type})

        tables[table_name] = {
            'name': table_name,
            'columns': columns
        }

    return tables

def generate_query_categories(table_name: str, columns: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Generate suggested query categories for a table"""
    categories = []

    # Basic search queries
    categories.append({
        'title': f'Basic {table_name.title()} Search',
        'count': 10,
        'examples': [
            f'"Show me all {table_name}"',
            f'"Find all {table_name}"',
            f'"List {table_name}"',
            f'"Get {table_name}"',
            f'"Display all {table_name}"'
        ]
    })

    # Search by each column
    for col in columns:
        col_name = col['name']
        col_type = col['type'].lower()

        # String columns
        if any(t in col_type for t in ['varchar', 'text', 'char']):
            categories.append({
                'title': f'Search by {col_name.replace("_", " ").title()}',
                'count': 5,
                'examples': [
                    f'"Find {table_name} with {col_name} John"',
                    f'"Show me {table_name} where {col_name} is example"',
                    f'"Get {table_name} by {col_name}"'
                ]
            })

        # Numeric columns
        elif any(t in col_type for t in ['int', 'serial', 'decimal', 'numeric']):
            if 'id' in col_name.lower():
                categories.append({
                    'title': f'Search by {col_name.replace("_", " ").title()}',
                    'count': 5,
                    'examples': [
                        f'"Find {table_name} with {col_name} 123"',
                        f'"Show me {table_name} {col_name} 456"',
                        f'"Get {table_name} by {col_name} 789"'
                    ]
                })
            else:
                categories.append({
                    'title': f'{col_name.replace("_", " ").title()} Range Queries',
                    'count': 5,
                    'examples': [
                        f'"Show me {table_name} with {col_name} over 100"',
                        f'"Find {table_name} where {col_name} is less than 50"',
                        f'"Get {table_name} with {col_name} between 10 and 100"'
                    ]
                })

        # Date columns
        elif any(t in col_type for t in ['date', 'timestamp', 'time']):
            categories.append({
                'title': f'Recent {table_name.title()} by {col_name.replace("_", " ").title()}',
                'count': 5,
                'examples': [
                    f'"Show me recent {table_name}"',
                    f'"Find {table_name} from today"',
                    f'"Get {table_name} from this week"'
                ]
            })

    # Count queries
    categories.append({
        'title': f'Count Queries',
        'count': 5,
        'examples': [
            f'"How many {table_name} do we have?"',
            f'"Count all {table_name}"',
            f'"Total number of {table_name}"'
        ]
    })

    # Statistical queries
    categories.append({
        'title': f'Statistics',
        'count': 5,
        'examples': [
            f'"Show me {table_name} statistics"',
            f'"Get {table_name} summary"',
            f'"What are the {table_name} metrics?"'
        ]
    })

    return categories

def create_markdown_template(tables: Dict[str, Any], domain_name: str = None) -> str:
    """Create markdown template with query sections"""

    if not domain_name:
        domain_name = " & ".join([t.title() for t in tables.keys()])

    md = f"""# {domain_name} - Test Queries

This document provides test queries for the {domain_name.lower()} database schema.
These queries will be used to generate SQL intent templates.

**INSTRUCTIONS:**
1. Replace the placeholder queries below with realistic natural language queries
2. Each query should be something a user would actually ask
3. Aim for variety - different phrasings, different filters, different use cases
4. Include edge cases and complex queries
5. Format: Number. "Query in quotes"

## Query Format Examples

```
1. "Show me all customers"
2. "Find orders from last week"
3. "How many products are in stock?"
```

---

"""

    # Add sections for each table
    for table_name, table_info in tables.items():
        md += f"\n## {table_name.title()} Queries\n\n"
        md += f"**Table:** `{table_name}`\n"
        md += f"**Columns:** {', '.join([c['name'] for c in table_info['columns']])}\n\n"

        # Generate categories
        categories = generate_query_categories(table_name, table_info['columns'])

        query_number = 1
        for category in categories:
            md += f"### {category['title']}\n"

            # Add example queries
            for i, example in enumerate(category['examples'][:3], 1):
                md += f"{query_number}. {example}\n"
                query_number += 1

            # Add placeholder queries
            remaining = category['count'] - 3
            if remaining > 0:
                md += f"{query_number}. \"[Add your query here]\"\n"
                query_number += 1
                if remaining > 1:
                    md += f"{query_number}. \"[Add your query here]\"\n"
                    query_number += 1
                if remaining > 2:
                    md += f"... (add {remaining - 2} more similar queries)\n"

            md += "\n"

    # Add complex queries section
    md += """
## Complex Multi-Criteria Queries

### Combining Multiple Filters
1. "[Add query combining multiple conditions]"
2. "[Add query with joins between tables]"
3. "[Add query with aggregations and grouping]"
... (add more complex queries)

### Advanced Analytics
1. "[Add analytical query]"
2. "[Add reporting query]"
3. "[Add trend analysis query]"
... (add more analytics queries)

---

## Tips for Writing Good Test Queries

1. **Be Natural**: Write how users would actually ask questions
2. **Be Specific**: Include actual values ("John Smith" not "NAME")
3. **Vary Phrasing**: Same intent, different words
4. **Include Edge Cases**: What about empty results? Large numbers?
5. **Think Use Cases**: What would real users want to know?

## What to Do Next

1. Fill in the placeholder queries above
2. Add more queries based on your domain knowledge
3. Review for variety and completeness
4. Run the template generator:
   ```bash
   ./generate_templates.sh \\
     --schema your_schema.sql \\
     --queries this_file.md \\
     --domain configs/your-config.yaml
   ```
"""

    return md

def main():
    parser = argparse.ArgumentParser(description='Create test queries template from schema')
    parser.add_argument('--schema', required=True, help='Path to SQL schema file')
    parser.add_argument('--output', default='test_queries.md', help='Output markdown file (default: test_queries.md)')
    parser.add_argument('--domain', help='Domain name for title (default: inferred from tables)')

    args = parser.parse_args()

    # Parse schema
    print(f"📋 Parsing schema: {args.schema}")
    tables = parse_schema(args.schema)

    if not tables:
        print("❌ No tables found in schema file")
        return 1

    print(f"✅ Found {len(tables)} tables: {', '.join(tables.keys())}")

    # Generate markdown
    print(f"📝 Generating query template...")
    markdown = create_markdown_template(tables, args.domain)

    # Save to file
    output_path = Path(args.output)
    with open(output_path, 'w') as f:
        f.write(markdown)

    print(f"✅ Template created: {output_path}")
    print(f"\n📖 Next steps:")
    print(f"   1. Open {output_path}")
    print(f"   2. Replace placeholder queries with real examples")
    print(f"   3. Add more queries based on your use cases")
    print(f"   4. Run template generator with this file")
    print(f"\n💡 Aim for 20-100+ queries for best results!")

    return 0

if __name__ == '__main__':
    exit(main())
