#!/usr/bin/env python3
"""
Automatic SQL Template Generator using AI

This script reads test queries and database schema to automatically generate
SQL templates for the Intent PostgreSQL retriever.

USAGE:
    python utils/template_generator.py --schema <schema_file> --queries <queries_file> --output <output_file> [options]

REQUIRED ARGUMENTS:
    --schema    Path to SQL schema file (e.g., examples/postgres/customer-order.sql)
    --queries   Path to test queries file (e.g., examples/postgres/test/test_queries.md)
    --output    Path to output YAML file for generated templates

OPTIONAL ARGUMENTS:
    --domain    Path to domain configuration file (provides additional context)
    --config    Path to main config file (default: config/config.yaml)
    --provider  Inference provider to use (default: ollama)
                Available: ollama, openai, anthropic, gemini, groq, etc.
    --limit     Limit number of queries to process (useful for testing)

EXAMPLES:
    # Basic usage with default settings
    python utils/template_generator.py \
        --schema examples/postgres/customer-order.sql \
        --queries examples/postgres/test/test_queries.md \
        --output examples/postgres/generated_templates.yaml

    # Use with domain config and specific provider
    python utils/template_generator.py \
        --schema examples/postgres/customer-order.sql \
        --queries examples/postgres/test/test_queries.md \
        --output examples/postgres/generated_templates.yaml \
        --domain examples/postgres/customer_order_domain.yaml \
        --provider anthropic

    # Test with limited queries
    python utils/template_generator.py \
        --schema examples/postgres/customer-order.sql \
        --queries examples/postgres/test/test_queries.md \
        --output test_templates.yaml \
        --limit 10

WORKFLOW:
    1. Parse SQL schema to understand database structure
    2. Extract test queries from markdown file
    3. Analyze each query using AI to understand intent
    4. Group similar queries together
    5. Generate SQL templates with parameters
    6. Validate generated templates
    7. Save to YAML file

OUTPUT FORMAT:
    The script generates a YAML file with templates in this format:
    
    templates:
      - id: template_id
        description: What this template does
        nl_examples: [list of example queries]
        parameters: [list of parameter definitions]
        sql_template: |
          SELECT ... FROM ... WHERE ...
        tags: [search tags]
        semantic_tags: {action, entities, qualifiers}

NOTES:
    - Always review generated templates before using in production
    - Templates are marked as approved: false by default
    - Ensure your inference provider is running (e.g., ollama serve)
    - The script requires proper database schema with CREATE TABLE statements
"""

import asyncio
import json
import yaml
import re
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import argparse
import sys
import os

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from server.inference.pipeline.providers.provider_factory import ProviderFactory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TemplateGenerator:
    """Generates SQL templates from natural language queries using AI"""
    
    def __init__(self, config_path: str = "config/config.yaml", provider: str = "ollama"):
        """Initialize the template generator
        
        Args:
            config_path: Path to the main configuration file
            provider: Inference provider to use (e.g., 'ollama', 'openai', 'anthropic')
        """
        self.config = self._load_config(config_path)
        self.provider = provider
        self.inference_client = None
        self.schema = {}
        self.domain_config = {}
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
            
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    
    async def initialize(self):
        """Initialize the inference client"""
        logger.info(f"Initializing inference provider: {self.provider}")
        self.inference_client = ProviderFactory.create_provider(self.config, self.provider)
        await self.inference_client.initialize()
        logger.info("Inference client initialized")
    
    def parse_schema(self, schema_path: str) -> Dict[str, Any]:
        """Parse SQL schema file to extract table structure
        
        Args:
            schema_path: Path to SQL schema file
            
        Returns:
            Dictionary containing table definitions
        """
        logger.info(f"Parsing schema from: {schema_path}")
        
        with open(schema_path, 'r') as f:
            schema_sql = f.read()
        
        # Extract table definitions
        tables = {}
        
        # Find CREATE TABLE statements
        table_pattern = r'CREATE TABLE (\w+)\s*\((.*?)\);'
        matches = re.findall(table_pattern, schema_sql, re.IGNORECASE | re.DOTALL)
        
        for table_name, table_def in matches:
            columns = []
            
            # Parse column definitions
            lines = table_def.strip().split('\n')
            for line in lines:
                line = line.strip().rstrip(',')
                if not line or line.startswith('--'):
                    continue
                    
                # Skip constraints
                if any(keyword in line.upper() for keyword in ['PRIMARY KEY', 'FOREIGN KEY', 'CHECK', 'UNIQUE']):
                    continue
                
                # Parse column name and type
                parts = line.split()
                if len(parts) >= 2:
                    col_name = parts[0]
                    col_type = parts[1]
                    columns.append({
                        'name': col_name,
                        'type': col_type,
                        'nullable': 'NOT NULL' not in line.upper()
                    })
            
            tables[table_name] = {
                'name': table_name,
                'columns': columns
            }
        
        # Find foreign key relationships
        fk_pattern = r'FOREIGN KEY\s*\((\w+)\)\s*REFERENCES\s*(\w+)\s*\((\w+)\)'
        fk_matches = re.findall(fk_pattern, schema_sql, re.IGNORECASE)
        
        for fk_col, ref_table, ref_col in fk_matches:
            # Find which table this FK belongs to
            for table_name, table_info in tables.items():
                if any(col['name'] == fk_col for col in table_info['columns']):
                    if 'foreign_keys' not in table_info:
                        table_info['foreign_keys'] = []
                    table_info['foreign_keys'].append({
                        'column': fk_col,
                        'references_table': ref_table,
                        'references_column': ref_col
                    })
        
        self.schema = tables
        logger.info(f"Parsed {len(tables)} tables from schema")
        return tables
    
    def load_domain_config(self, domain_config_path: str):
        """Load domain configuration if available"""
        if Path(domain_config_path).exists():
            with open(domain_config_path, 'r') as f:
                self.domain_config = yaml.safe_load(f)
            logger.info("Loaded domain configuration")
        else:
            logger.warning(f"Domain config not found at: {domain_config_path}")
    
    def parse_test_queries(self, test_file_path: str) -> List[str]:
        """Parse test queries from markdown file
        
        Args:
            test_file_path: Path to test queries markdown file
            
        Returns:
            List of test queries
        """
        logger.info(f"Parsing test queries from: {test_file_path}")
        
        with open(test_file_path, 'r') as f:
            content = f.read()
        
        # Extract queries (lines that start with a number and contain quotes)
        query_pattern = r'^\d+\.\s*"([^"]+)"'
        queries = re.findall(query_pattern, content, re.MULTILINE)
        
        # Also extract queries without numbers
        additional_pattern = r'^"([^"]+)"'
        additional_queries = re.findall(additional_pattern, content, re.MULTILINE)
        
        # Extract queries from the "Other Queries" section
        other_queries = []
        lines = content.split('\n')
        in_other_section = False
        for line in lines:
            if '### Other Queries' in line:
                in_other_section = True
                continue
            if in_other_section and line.strip() and not line.startswith('#'):
                # Clean up the line
                query = line.strip()
                if query and not query.startswith('"'):
                    other_queries.append(query)
        
        all_queries = queries + additional_queries + other_queries
        
        # Remove duplicates while preserving order
        seen = set()
        unique_queries = []
        for q in all_queries:
            if q not in seen:
                seen.add(q)
                unique_queries.append(q)
        
        logger.info(f"Found {len(unique_queries)} unique queries")
        return unique_queries
    
    async def analyze_query(self, query: str) -> Dict[str, Any]:
        """Analyze a natural language query to extract intent and parameters
        
        Args:
            query: Natural language query
            
        Returns:
            Dictionary containing query analysis
        """
        schema_summary = self._create_schema_summary()
        
        prompt = f"""Analyze this natural language query and extract its intent and parameters.

Database Schema:
{schema_summary}

Query: "{query}"

Provide a JSON response with:
1. intent: The main action (find, calculate, filter, etc.)
2. primary_entity: The main entity being queried (customer, order, etc.)
3. secondary_entity: Any related entity (if applicable)
4. filters: List of filter conditions with field and value
5. aggregations: Any aggregation functions needed (sum, count, avg, etc.)
6. time_range: Any time-based filters
7. order_by: Sorting requirements
8. limit: Result limit if specified

Example response:
{{
    "intent": "find",
    "primary_entity": "order",
    "secondary_entity": "customer",
    "filters": [
        {{"field": "customer_name", "operator": "like", "value": "John Doe"}},
        {{"field": "order_date", "operator": ">=", "value": "last_week"}}
    ],
    "aggregations": [],
    "time_range": {{"period": "last_week", "field": "order_date"}},
    "order_by": [{{"field": "order_date", "direction": "DESC"}}],
    "limit": null
}}

JSON Response:"""

        response = await self.inference_client.generate(prompt)
        
        # Extract JSON from response
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                logger.error(f"No JSON found in response for query: {query}")
                return {}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON for query: {query}, error: {e}")
            return {}
    
    def _create_schema_summary(self) -> str:
        """Create a summary of the database schema"""
        summary = []
        for table_name, table_info in self.schema.items():
            cols = [f"{c['name']} ({c['type']})" for c in table_info['columns']]
            summary.append(f"{table_name}: {', '.join(cols[:5])}...")
            
            if 'foreign_keys' in table_info:
                for fk in table_info['foreign_keys']:
                    summary.append(f"  FK: {fk['column']} -> {fk['references_table']}.{fk['references_column']}")
        
        return '\n'.join(summary)
    
    async def generate_sql_template(self, query: str, analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Generate SQL template from query analysis
        
        Args:
            query: Original natural language query
            analysis: Query analysis results
            
        Returns:
            SQL template dictionary or None if generation fails
        """
        if not analysis:
            return None
        
        schema_summary = self._create_schema_summary()
        
        prompt = f"""Generate a parameterized SQL template for this query analysis.

Database Schema:
{schema_summary}

Original Query: "{query}"

Query Analysis:
{json.dumps(analysis, indent=2)}

Generate a SQL template that:
1. Uses %(parameter_name)s placeholders for dynamic values
2. Properly joins tables when needed
3. Includes appropriate WHERE clauses
4. Handles aggregations if needed
5. Is optimized for PostgreSQL

Also provide:
1. List of parameters with their types and descriptions
2. A template ID (snake_case)
3. A description of what the template does
4. 3-5 example natural language queries this template would match

Response format:
{{
    "id": "template_id",
    "description": "What this template does",
    "sql": "SELECT ... FROM ... WHERE ...",
    "parameters": [
        {{
            "name": "param_name",
            "type": "string|integer|date|decimal",
            "description": "Parameter description",
            "required": true,
            "default": null
        }}
    ],
    "nl_examples": [
        "Example query 1",
        "Example query 2"
    ],
    "result_format": "table|summary"
}}

JSON Response:"""

        response = await self.inference_client.generate(prompt)
        
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                template = json.loads(json_match.group())
                
                # Add additional metadata
                template['version'] = "1.0.0"
                template['approved'] = False  # Requires manual review
                template['created_at'] = datetime.now().isoformat()
                template['created_by'] = "template_generator"
                
                # Add semantic tags based on analysis
                template['semantic_tags'] = {
                    'action': analysis.get('intent', 'find'),
                    'primary_entity': analysis.get('primary_entity', ''),
                    'secondary_entity': analysis.get('secondary_entity', ''),
                    'qualifiers': []
                }
                
                # Add tags for better matching
                tags = [analysis.get('intent', ''), analysis.get('primary_entity', '')]
                if analysis.get('secondary_entity'):
                    tags.append(analysis['secondary_entity'])
                if analysis.get('aggregations'):
                    tags.extend(analysis['aggregations'])
                template['tags'] = [t for t in tags if t]
                
                return template
            else:
                logger.error(f"No JSON found in SQL template response for query: {query}")
                return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse SQL template JSON for query: {query}, error: {e}")
            return None
    
    def group_similar_queries(self, queries: List[str], analyses: List[Dict[str, Any]]) -> Dict[str, List[Tuple[str, Dict]]]:
        """Group similar queries that can use the same template
        
        Args:
            queries: List of natural language queries
            analyses: List of query analyses
            
        Returns:
            Dictionary mapping template keys to lists of (query, analysis) tuples
        """
        groups = {}
        
        for query, analysis in zip(queries, analyses):
            if not analysis:
                continue
            
            # Create a key based on intent and entities
            key = f"{analysis.get('intent', 'unknown')}_{analysis.get('primary_entity', 'unknown')}"
            if analysis.get('secondary_entity'):
                key += f"_{analysis['secondary_entity']}"
            
            # Add aggregation info to key
            if analysis.get('aggregations'):
                key += f"_{'_'.join(sorted(analysis['aggregations']))}"
            
            if key not in groups:
                groups[key] = []
            groups[key].append((query, analysis))
        
        logger.info(f"Grouped queries into {len(groups)} template categories")
        return groups
    
    async def generate_templates(self, queries: List[str]) -> List[Dict[str, Any]]:
        """Generate SQL templates for a list of queries
        
        Args:
            queries: List of natural language queries
            
        Returns:
            List of generated SQL templates
        """
        # Analyze all queries
        logger.info("Analyzing queries...")
        analyses = []
        for i, query in enumerate(queries):
            if i % 10 == 0:
                logger.info(f"Analyzing query {i+1}/{len(queries)}")
            analysis = await self.analyze_query(query)
            analyses.append(analysis)
        
        # Group similar queries
        grouped = self.group_similar_queries(queries, analyses)
        
        # Generate templates for each group
        templates = []
        for group_key, group_queries in grouped.items():
            logger.info(f"Generating template for group: {group_key} ({len(group_queries)} queries)")
            
            # Use the first query as representative
            repr_query, repr_analysis = group_queries[0]
            
            template = await self.generate_sql_template(repr_query, repr_analysis)
            if template:
                # Add all example queries from the group
                all_examples = [q for q, _ in group_queries[:10]]  # Limit to 10 examples
                template['nl_examples'] = all_examples
                
                templates.append(template)
        
        logger.info(f"Generated {len(templates)} templates")
        return templates
    
    def validate_template(self, template: Dict[str, Any]) -> List[str]:
        """Validate a generated template
        
        Args:
            template: Template to validate
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        # Check required fields
        required_fields = ['id', 'description', 'sql', 'parameters', 'nl_examples']
        for field in required_fields:
            if field not in template:
                errors.append(f"Missing required field: {field}")
        
        # Validate SQL
        if 'sql' in template:
            sql = template['sql']
            if not sql.strip():
                errors.append("SQL template is empty")
            elif sql.count('%(') != sql.count(')s'):
                errors.append("Mismatched parameter placeholders in SQL")
        
        # Validate parameters
        if 'parameters' in template:
            param_names = {p['name'] for p in template['parameters'] if 'name' in p}
            
            # Check if all SQL parameters are defined
            if 'sql' in template:
                sql_params = re.findall(r'%\((\w+)\)s', template['sql'])
                for sql_param in sql_params:
                    if sql_param not in param_names:
                        errors.append(f"SQL parameter '{sql_param}' not defined in parameters list")
        
        return errors
    
    def save_templates(self, templates: List[Dict[str, Any]], output_path: str):
        """Save generated templates to YAML file
        
        Args:
            templates: List of templates to save
            output_path: Path to output YAML file
        """
        # Validate templates
        valid_templates = []
        for template in templates:
            errors = self.validate_template(template)
            if errors:
                logger.warning(f"Template '{template.get('id', 'unknown')}' has validation errors: {errors}")
                template['validation_errors'] = errors
            valid_templates.append(template)
        
        # Create output structure
        output = {
            'generated_at': datetime.now().isoformat(),
            'generator_version': '1.0.0',
            'total_templates': len(valid_templates),
            'templates': valid_templates
        }
        
        # Save to file
        with open(output_path, 'w') as f:
            yaml.dump(output, f, default_flow_style=False, sort_keys=False)
        
        logger.info(f"Saved {len(valid_templates)} templates to: {output_path}")


async def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Generate SQL templates from test queries')
    parser.add_argument('--schema', required=True, help='Path to SQL schema file')
    parser.add_argument('--queries', required=True, help='Path to test queries file')
    parser.add_argument('--output', required=True, help='Path to output YAML file')
    parser.add_argument('--domain', help='Path to domain configuration file')
    parser.add_argument('--config', default='config/config.yaml', help='Path to main config file')
    parser.add_argument('--provider', default='ollama', help='Inference provider to use')
    parser.add_argument('--limit', type=int, help='Limit number of queries to process')
    
    args = parser.parse_args()
    
    # Create generator
    generator = TemplateGenerator(args.config, args.provider)
    await generator.initialize()
    
    # Parse schema
    generator.parse_schema(args.schema)
    
    # Load domain config if provided
    if args.domain:
        generator.load_domain_config(args.domain)
    
    # Parse test queries
    queries = generator.parse_test_queries(args.queries)
    
    # Limit queries if requested
    if args.limit:
        queries = queries[:args.limit]
        logger.info(f"Limited to {len(queries)} queries")
    
    # Generate templates
    templates = await generator.generate_templates(queries)
    
    # Save templates
    generator.save_templates(templates, args.output)
    
    logger.info("Template generation complete!")


if __name__ == '__main__':
    asyncio.run(main())