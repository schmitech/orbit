#!/usr/bin/env python3
"""
GraphQL Template Generator

This script generates intent-based templates from GraphQL operations.
It can parse GraphQL queries/mutations and create YAML templates with
parameter definitions, natural language examples, and semantic tags.

Usage:
    python create_graphql_template.py --help

    # From a GraphQL file
    python create_graphql_template.py \\
        --api-name spacex \\
        --base-url "https://spacex-production.up.railway.app/graphql" \\
        --graphql queries.graphql \\
        --output templates/spacex_templates.yaml

    # Interactive mode
    python create_graphql_template.py \\
        --api-name myapi \\
        --base-url "https://api.example.com/graphql" \\
        --interactive
"""

import argparse
import re
import yaml
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime


# GraphQL type to Python/template type mapping
GRAPHQL_TYPE_MAP = {
    'Int': 'integer',
    'Float': 'float',
    'String': 'string',
    'Boolean': 'boolean',
    'ID': 'string',
}


def parse_graphql_operation(graphql_text: str) -> Dict[str, Any]:
    """
    Parse a GraphQL operation (query or mutation) and extract metadata.

    Args:
        graphql_text: The GraphQL operation text

    Returns:
        Dictionary with operation metadata
    """
    result = {
        'operation_type': None,
        'operation_name': None,
        'variables': [],
        'fields': [],
        'raw_query': graphql_text.strip()
    }

    # Detect operation type and name
    # Pattern: query|mutation OperationName($var: Type)
    operation_pattern = r'(query|mutation)\s+(\w+)?\s*(\([^)]*\))?\s*\{'
    match = re.search(operation_pattern, graphql_text, re.IGNORECASE)

    if match:
        result['operation_type'] = match.group(1).lower()
        result['operation_name'] = match.group(2)

        # Extract variables if present
        if match.group(3):
            variables_str = match.group(3).strip('()')
            result['variables'] = parse_graphql_variables(variables_str)
    else:
        # Assume query if no explicit type
        result['operation_type'] = 'query'

    # Extract top-level fields
    result['fields'] = extract_top_level_fields(graphql_text)

    return result


def parse_graphql_variables(variables_str: str) -> List[Dict[str, Any]]:
    """
    Parse GraphQL variable definitions.

    Args:
        variables_str: String like "$limit: Int, $id: ID!"

    Returns:
        List of variable definitions
    """
    variables = []

    # Pattern: $varName: Type(!) (= defaultValue)?
    var_pattern = r'\$(\w+)\s*:\s*(\[?\w+\]?!?)\s*(?:=\s*([^,)]+))?'

    for match in re.finditer(var_pattern, variables_str):
        var_name = match.group(1)
        graphql_type = match.group(2)
        default_value = match.group(3)

        # Determine if required (has !)
        required = graphql_type.endswith('!')
        base_type = graphql_type.rstrip('!')

        # Check if it's a list type
        is_list = base_type.startswith('[') and base_type.endswith(']')
        if is_list:
            base_type = base_type.strip('[]')

        # Map to template type
        template_type = GRAPHQL_TYPE_MAP.get(base_type, 'string')

        variable = {
            'name': var_name,
            'type': template_type,
            'graphql_type': graphql_type,
            'required': required,
            'location': 'variable'
        }

        if default_value:
            # Parse default value
            default_value = default_value.strip()
            if template_type == 'integer':
                variable['default'] = int(default_value)
            elif template_type == 'float':
                variable['default'] = float(default_value)
            elif template_type == 'boolean':
                variable['default'] = default_value.lower() == 'true'
            else:
                variable['default'] = default_value.strip('"\'')

        variables.append(variable)

    return variables


def extract_top_level_fields(graphql_text: str) -> List[str]:
    """
    Extract top-level field names from a GraphQL operation.

    Args:
        graphql_text: The GraphQL operation text

    Returns:
        List of top-level field names
    """
    fields = []

    # Find the main query body (after the opening brace)
    # This is a simplified extraction - handles common cases
    brace_count = 0
    in_query = False
    current_field = ''

    for char in graphql_text:
        if char == '{':
            brace_count += 1
            if brace_count == 1:
                in_query = True
                continue
            elif brace_count == 2 and current_field:
                fields.append(current_field.strip().split('(')[0])
                current_field = ''
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                break
            elif brace_count == 1 and current_field:
                fields.append(current_field.strip().split('(')[0])
                current_field = ''
        elif in_query and brace_count == 1:
            if char.isalnum() or char == '_':
                current_field += char
            elif current_field and char in ' (':
                fields.append(current_field.strip())
                current_field = ''

    return [f for f in fields if f]


def generate_template_id(operation_name: str, operation_type: str, fields: List[str]) -> str:
    """
    Generate a template ID from operation metadata.

    Args:
        operation_name: The GraphQL operation name
        operation_type: 'query' or 'mutation'
        fields: Top-level fields

    Returns:
        Template ID string
    """
    if operation_name:
        # Convert CamelCase to snake_case
        name = re.sub(r'(?<!^)(?=[A-Z])', '_', operation_name).lower()
        return name
    elif fields:
        return f"{operation_type}_{fields[0]}"
    else:
        return f"{operation_type}_template"


def generate_description(operation_name: str, operation_type: str, fields: List[str]) -> str:
    """
    Generate a human-readable description for the template.

    Args:
        operation_name: The GraphQL operation name
        operation_type: 'query' or 'mutation'
        fields: Top-level fields

    Returns:
        Description string
    """
    if operation_name:
        # Convert CamelCase to words
        words = re.sub(r'(?<!^)(?=[A-Z])', ' ', operation_name)
        return words
    elif fields:
        action = 'Get' if operation_type == 'query' else 'Execute'
        return f"{action} {fields[0]}"
    else:
        return f"GraphQL {operation_type}"


def generate_semantic_tags(operation_type: str, operation_name: str,
                          fields: List[str], variables: List[Dict]) -> Dict[str, Any]:
    """
    Generate semantic tags for template matching.

    Args:
        operation_type: 'query' or 'mutation'
        operation_name: Operation name
        fields: Top-level fields
        variables: Variable definitions

    Returns:
        Semantic tags dictionary
    """
    tags = {
        'action': 'query' if operation_type == 'query' else 'mutate',
        'primary_entity': fields[0] if fields else 'unknown',
        'qualifiers': []
    }

    # Infer action from operation name
    if operation_name:
        name_lower = operation_name.lower()
        if 'list' in name_lower or 'all' in name_lower:
            tags['action'] = 'list'
            tags['qualifiers'].append('multiple')
        elif 'get' in name_lower or 'find' in name_lower:
            tags['action'] = 'get'
        elif 'create' in name_lower or 'add' in name_lower:
            tags['action'] = 'create'
        elif 'update' in name_lower or 'edit' in name_lower:
            tags['action'] = 'update'
        elif 'delete' in name_lower or 'remove' in name_lower:
            tags['action'] = 'delete'
        elif 'latest' in name_lower or 'recent' in name_lower:
            tags['action'] = 'get'
            tags['qualifiers'].append('latest')

    # Add qualifiers based on variables
    for var in variables:
        if var['name'].lower() == 'id':
            tags['qualifiers'].append('by_id')
        elif var['name'].lower() == 'limit':
            tags['qualifiers'].append('paginated')
        elif var['name'].lower() in ('filter', 'where'):
            tags['qualifiers'].append('filterable')

    return tags


def create_template_from_graphql(graphql_text: str,
                                 nl_examples: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Create a complete template from a GraphQL operation.

    Args:
        graphql_text: The GraphQL operation text
        nl_examples: Optional list of natural language examples

    Returns:
        Template dictionary
    """
    parsed = parse_graphql_operation(graphql_text)

    template_id = generate_template_id(
        parsed['operation_name'],
        parsed['operation_type'],
        parsed['fields']
    )

    template = {
        'id': template_id,
        'version': '1.0.0',
        'description': generate_description(
            parsed['operation_name'],
            parsed['operation_type'],
            parsed['fields']
        ),
        'category': f"{parsed['fields'][0]}_queries" if parsed['fields'] else 'general',
        'complexity': 'simple' if len(parsed['variables']) <= 2 else 'moderate',

        # GraphQL operation
        'graphql_type': parsed['operation_type'],
        'operation_name': parsed['operation_name'],
        'graphql_template': parsed['raw_query'],

        # Parameters from variables
        'parameters': parsed['variables'],

        # Natural language examples
        'nl_examples': nl_examples or [
            f"Execute {parsed['operation_name'] or 'GraphQL'} operation"
        ],

        # Semantic tags
        'semantic_tags': generate_semantic_tags(
            parsed['operation_type'],
            parsed['operation_name'],
            parsed['fields'],
            parsed['variables']
        ),

        # Response mapping (basic)
        'response_mapping': {
            'items_path': f"data.{parsed['fields'][0]}" if parsed['fields'] else 'data',
            'fields': []
        },

        # Display configuration
        'display_fields': [],
        'result_format': 'list',

        # Metadata
        'tags': [parsed['operation_type']] + parsed['fields'],
        'approved': False
    }

    return template


def parse_graphql_file(file_path: Path) -> List[Dict[str, Any]]:
    """
    Parse a file containing multiple GraphQL operations.

    Args:
        file_path: Path to the GraphQL file

    Returns:
        List of template dictionaries
    """
    templates = []

    with open(file_path, 'r') as f:
        content = f.read()

    # Split by operation (query/mutation)
    operation_pattern = r'(query|mutation)\s+\w*\s*(?:\([^)]*\))?\s*\{[^}]*(?:\{[^}]*\}[^}]*)*\}'

    for match in re.finditer(operation_pattern, content, re.DOTALL | re.IGNORECASE):
        graphql_text = match.group(0)
        template = create_template_from_graphql(graphql_text)
        templates.append(template)

    return templates


def interactive_mode(api_name: str, base_url: str) -> List[Dict[str, Any]]:
    """
    Interactive mode for creating templates.

    Args:
        api_name: Name of the API
        base_url: Base URL for the GraphQL endpoint

    Returns:
        List of created templates
    """
    templates = []

    print("\n=== GraphQL Template Generator ===")
    print(f"API: {api_name}")
    print(f"Endpoint: {base_url}")
    print("\nEnter GraphQL operations. Type 'done' when finished.")
    print("Enter multi-line operations, then press Enter twice to submit.\n")

    while True:
        print("-" * 40)
        print("Enter GraphQL operation (or 'done' to finish):")

        lines = []
        empty_count = 0

        while True:
            try:
                line = input()
            except EOFError:
                break

            if line.strip().lower() == 'done':
                return templates

            if not line.strip():
                empty_count += 1
                if empty_count >= 2:
                    break
            else:
                empty_count = 0
                lines.append(line)

        if not lines:
            continue

        graphql_text = '\n'.join(lines)

        # Get natural language examples
        print("\nEnter natural language examples (one per line, empty line to finish):")
        nl_examples = []
        while True:
            example = input().strip()
            if not example:
                break
            nl_examples.append(example)

        # Create template
        template = create_template_from_graphql(graphql_text, nl_examples or None)
        templates.append(template)

        print(f"\n✓ Created template: {template['id']}")

    return templates


def generate_template_library(templates: List[Dict[str, Any]], api_name: str) -> Dict[str, Any]:
    """
    Generate a complete template library document.

    Args:
        templates: List of template dictionaries
        api_name: Name of the API

    Returns:
        Template library dictionary
    """
    return {
        'status': 'generated',
        'generated_at': datetime.now().isoformat(),
        'generator_version': '1.0.0',
        'api_name': api_name,
        'total_templates': len(templates),
        'templates': templates
    }


def main():
    parser = argparse.ArgumentParser(
        description='Generate intent-based templates from GraphQL operations'
    )

    parser.add_argument('--api-name', required=True,
                       help='Name of the API (e.g., spacex, github)')
    parser.add_argument('--base-url', required=True,
                       help='GraphQL endpoint URL')
    parser.add_argument('--graphql', '-g',
                       help='Path to GraphQL file containing operations')
    parser.add_argument('--output', '-o',
                       help='Output YAML file path')
    parser.add_argument('--interactive', '-i', action='store_true',
                       help='Interactive mode for entering operations')

    args = parser.parse_args()

    templates = []

    if args.graphql:
        graphql_path = Path(args.graphql)
        if not graphql_path.exists():
            print(f"Error: GraphQL file not found: {graphql_path}", file=sys.stderr)
            sys.exit(1)

        print(f"Parsing GraphQL file: {graphql_path}")
        templates = parse_graphql_file(graphql_path)
        print(f"Found {len(templates)} operations")

    elif args.interactive:
        templates = interactive_mode(args.api_name, args.base_url)

    else:
        parser.print_help()
        sys.exit(1)

    if not templates:
        print("No templates generated.", file=sys.stderr)
        sys.exit(1)

    # Generate template library
    library = generate_template_library(templates, args.api_name)

    # Output
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            yaml.dump(library, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

        print(f"\n✓ Template library saved to: {output_path}")
        print(f"  Total templates: {len(templates)}")
    else:
        # Print to stdout
        print("\n" + "=" * 40)
        print(yaml.dump(library, default_flow_style=False, sort_keys=False, allow_unicode=True))


if __name__ == '__main__':
    main()
