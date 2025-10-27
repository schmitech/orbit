#!/usr/bin/env python3
"""
HTTP Request Template Creator

This tool helps you create HTTP intent templates for REST APIs.
It can generate templates from natural language examples using AI.
"""

import argparse
import yaml
import json
import sys
import os
import asyncio
from typing import List, Dict, Any, Optional
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class HTTPTemplateCreator:
    """Creates HTTP intent templates from natural language examples."""

    def __init__(self, api_name: str, base_url: str, inference_client=None):
        """
        Initialize the template creator.

        Args:
            api_name: Name of the API (e.g., 'github', 'stripe')
            base_url: Base URL of the API
            inference_client: Optional inference client for AI-powered generation
        """
        self.api_name = api_name
        self.base_url = base_url
        self.inference_client = inference_client
        self.templates = []

    async def create_template_from_examples(
        self,
        examples: List[str],
        endpoint: str,
        http_method: str = "GET",
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a template from natural language examples.

        Args:
            examples: List of natural language query examples
            endpoint: API endpoint template (e.g., "/users/{username}/repos")
            http_method: HTTP method (GET, POST, etc.)
            description: Template description

        Returns:
            Template dictionary
        """
        # Generate template ID from endpoint
        template_id = self._generate_template_id(endpoint, http_method)

        # Extract parameters from endpoint
        parameters = self._extract_parameters_from_endpoint(endpoint)

        # If AI is available, enhance the template
        if self.inference_client and description is None:
            description = await self._generate_description(examples, endpoint)

        # Build template
        template = {
            'id': template_id,
            'version': '1.0.0',
            'description': description or f'{http_method} request to {endpoint}',
            'http_method': http_method.upper(),
            'endpoint_template': endpoint,
            'parameters': parameters,
            'nl_examples': examples[:10],  # Limit to 10 examples
            'result_format': 'list',
            'tags': [self.api_name.lower(), http_method.lower()],
        }

        # Add headers for common APIs
        headers = self._get_common_headers()
        if headers:
            template['headers'] = headers

        # Add query params if GET request
        if http_method.upper() == 'GET':
            query_params = self._extract_query_params(parameters)
            if query_params:
                template['query_params'] = query_params

        # Add semantic tags
        semantic_tags = self._generate_semantic_tags(endpoint, examples)
        if semantic_tags:
            template['semantic_tags'] = semantic_tags

        return template

    def _generate_template_id(self, endpoint: str, method: str) -> str:
        """Generate a template ID from endpoint and method."""
        # Remove leading slash and convert to snake_case
        parts = endpoint.strip('/').replace('{', '').replace('}', '').split('/')
        id_parts = [method.lower()] + parts
        return '_'.join(id_parts)

    def _extract_parameters_from_endpoint(self, endpoint: str) -> List[Dict[str, Any]]:
        """Extract parameter definitions from endpoint template."""
        import re

        parameters = []
        # Find all {param} patterns
        param_pattern = r'\{(\w+)\}'
        matches = re.findall(param_pattern, endpoint)

        for param_name in matches:
            param = {
                'name': param_name,
                'type': 'string',  # Default type
                'required': True,
                'description': f'{param_name.replace("_", " ").title()}',
                'location': 'path',
                'example': f'example_{param_name}'
            }
            parameters.append(param)

        return parameters

    def _extract_query_params(self, parameters: List[Dict]) -> Dict[str, str]:
        """Extract query parameters for GET requests."""
        query_params = {}

        # Add common query parameters
        common_params = {
            'limit': '{{limit}}',
            'offset': '{{offset}}',
            'page': '{{page}}',
            'per_page': '{{per_page}}',
            'sort': '{{sort}}',
        }

        # Check if any path parameters suggest pagination
        param_names = [p['name'] for p in parameters]
        if any('list' in p or 'all' in p for p in param_names):
            query_params.update(common_params)

        return query_params

    def _get_common_headers(self) -> Dict[str, str]:
        """Get common headers for the API."""
        headers = {}

        # API-specific headers
        if 'github' in self.api_name.lower():
            headers['Accept'] = 'application/vnd.github.v3+json'
        elif 'stripe' in self.api_name.lower():
            headers['Stripe-Version'] = '2023-10-16'

        return headers

    def _generate_semantic_tags(self, endpoint: str, examples: List[str]) -> Dict[str, Any]:
        """Generate semantic tags for the template."""
        tags = {}

        # Determine action from endpoint and examples
        endpoint_lower = endpoint.lower()
        examples_text = ' '.join(examples).lower()

        # Action detection
        if any(word in examples_text for word in ['list', 'show', 'get', 'find', 'all']):
            tags['action'] = 'list'
        elif any(word in examples_text for word in ['create', 'add', 'new']):
            tags['action'] = 'create'
        elif any(word in examples_text for word in ['update', 'modify', 'change']):
            tags['action'] = 'update'
        elif any(word in examples_text for word in ['delete', 'remove']):
            tags['action'] = 'delete'
        else:
            tags['action'] = 'retrieve'

        # Entity detection
        entities = []
        common_entities = ['user', 'repo', 'repository', 'issue', 'comment', 'file', 'commit']
        for entity in common_entities:
            if entity in endpoint_lower or entity in examples_text:
                entities.append(entity)

        if entities:
            tags['primary_entity'] = entities[0]
            if len(entities) > 1:
                tags['secondary_entity'] = entities[1]

        return tags

    async def _generate_description(self, examples: List[str], endpoint: str) -> str:
        """Generate template description using AI."""
        if not self.inference_client:
            return f'API request to {endpoint}'

        try:
            prompt = f"""Based on these natural language queries and API endpoint, create a clear, concise description (one sentence) of what this API template does:

Queries:
{chr(10).join(f'- {ex}' for ex in examples[:5])}

API Endpoint: {endpoint}

Description:"""

            description = await self.inference_client.generate(prompt)
            return description.strip().strip('"')
        except Exception as e:
            print(f"Warning: Could not generate description: {e}")
            return f'API request to {endpoint}'

    def add_template(self, template: Dict[str, Any]):
        """Add a template to the collection."""
        self.templates.append(template)

    def save_templates(self, output_path: str):
        """Save templates to YAML file."""
        output = {
            'templates': self.templates
        }

        with open(output_path, 'w') as f:
            yaml.dump(output, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

        print(f"✓ Saved {len(self.templates)} templates to {output_path}")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Create HTTP intent templates for REST APIs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create template from examples
  python create_request_template.py \\
      --api-name github \\
      --base-url "https://api.github.com" \\
      --requests examples/github-api/test_requests.md \\
      --output examples/github-api/templates/github_templates.yaml

  # Interactive mode
  python create_request_template.py \\
      --api-name myapi \\
      --base-url "https://api.example.com" \\
      --interactive
        """
    )

    parser.add_argument('--api-name', required=True, help='API name (e.g., github, stripe)')
    parser.add_argument('--base-url', required=True, help='Base URL of the API')
    parser.add_argument('--requests', help='Path to file with natural language examples')
    parser.add_argument('--output', help='Output YAML file path')
    parser.add_argument('--interactive', action='store_true', help='Interactive mode')
    parser.add_argument('--use-ai', action='store_true', help='Use AI for description generation')
    parser.add_argument('--inference-provider', default='openai', help='Inference provider (default: openai)')

    args = parser.parse_args()

    # Initialize inference client if AI is requested
    inference_client = None
    if args.use_ai:
        try:
            from inference.pipeline.providers import UnifiedProviderFactory as ProviderFactory
            import yaml

            # Load config
            config_path = Path(__file__).parent.parent.parent / 'config' / 'config.yaml'
            with open(config_path) as f:
                config = yaml.safe_load(f)

            inference_client = ProviderFactory.create_provider_by_name(args.inference_provider, config)
            await inference_client.initialize()
            print(f"✓ Initialized {args.inference_provider} for AI-powered generation")
        except Exception as e:
            print(f"Warning: Could not initialize AI client: {e}")
            print("Continuing without AI assistance...")

    # Create template creator
    creator = HTTPTemplateCreator(args.api_name, args.base_url, inference_client)

    if args.interactive:
        print(f"\nHTTP Template Creator - {args.api_name}")
        print("=" * 50)
        print("\nEnter template details (or 'done' to finish):\n")

        while True:
            endpoint = input("Endpoint template (e.g., /users/{username}/repos) [or 'done']: ").strip()
            if endpoint.lower() == 'done':
                break

            method = input("HTTP method (GET/POST/PUT/DELETE) [GET]: ").strip().upper() or 'GET'
            description = input("Description [optional]: ").strip() or None

            print("\nEnter natural language examples (one per line, empty line to finish):")
            examples = []
            while True:
                example = input("  Example: ").strip()
                if not example:
                    break
                examples.append(example)

            if not examples:
                print("Error: At least one example is required")
                continue

            print("\nGenerating template...")
            template = await creator.create_template_from_examples(
                examples, endpoint, method, description
            )
            creator.add_template(template)
            print(f"✓ Added template: {template['id']}")
            print()

    elif args.requests:
        # Parse requests file
        print(f"Reading examples from {args.requests}...")
        templates_data = parse_requests_file(args.requests)

        for tpl_data in templates_data:
            print(f"\nGenerating template for {tpl_data['endpoint']}...")
            template = await creator.create_template_from_examples(
                tpl_data['examples'],
                tpl_data['endpoint'],
                tpl_data.get('method', 'GET'),
                tpl_data.get('description')
            )
            creator.add_template(template)
            print(f"✓ Created template: {template['id']}")

    else:
        parser.error("Either --requests or --interactive must be specified")

    # Save templates
    if creator.templates:
        output_path = args.output or f'{args.api_name}_templates.yaml'
        creator.save_templates(output_path)
        print(f"\n✓ Successfully created {len(creator.templates)} templates!")
        print(f"\nNext steps:")
        print(f"1. Review the templates in {output_path}")
        print(f"2. Create a domain configuration file")
        print(f"3. Add the adapter to config/adapters.yaml")
        print(f"4. Test with: python test_adapter_loading.py --adapter-name <name>")
    else:
        print("No templates created.")

    # Close inference client
    if inference_client:
        await inference_client.close()


def parse_requests_file(file_path: str) -> List[Dict[str, Any]]:
    """
    Parse a markdown file with natural language examples.

    Expected format:
    ```markdown
    ## Category Name

    ### Template Description
    Endpoint: /path/to/{param}
    Method: GET

    1. "Example query one"
    2. "Example query two"
    ```
    """
    templates = []
    current_template = None

    with open(file_path, 'r') as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # New template section (### heading)
        if line.startswith('###'):
            if current_template and current_template.get('examples'):
                templates.append(current_template)

            description = line.lstrip('#').strip()
            current_template = {
                'description': description,
                'endpoint': None,
                'method': 'GET',
                'examples': []
            }

        # Endpoint definition
        elif line.startswith('Endpoint:') and current_template:
            current_template['endpoint'] = line.split(':', 1)[1].strip()

        # Method definition
        elif line.startswith('Method:') and current_template:
            current_template['method'] = line.split(':', 1)[1].strip().upper()

        # Example queries (numbered or bulleted)
        elif current_template and (line and line[0].isdigit() or line.startswith('-')):
            # Extract example text
            example = line.lstrip('0123456789.-) ').strip().strip('"\'')
            if example:
                current_template['examples'].append(example)

        i += 1

    # Add last template
    if current_template and current_template.get('examples') and current_template.get('endpoint'):
        templates.append(current_template)

    return templates


if __name__ == '__main__':
    asyncio.run(main())
