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

#!/usr/bin/env python3

# Print immediately to verify script starts
print("🔄 Starting template generator script...", flush=True)

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
import random
import time

print("✅ Basic imports complete", flush=True)

from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

print("✅ Path configured", flush=True)

# Load environment variables from .env file (two levels up in parent Orbit directory)
load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env")

print("✅ Environment loaded", flush=True)

print("🔄 Importing UnifiedProviderFactory (this may take a moment)...", flush=True)
from server.inference.pipeline.providers.unified_provider_factory import UnifiedProviderFactory
print("✅ UnifiedProviderFactory imported", flush=True)

# Configure logging with console output and flushing
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
# Force flush after each log message
for handler in logging.root.handlers:
    handler.flush = lambda: sys.stdout.flush()

logger = logging.getLogger(__name__)


# Built-in SQL dialect configurations
SQL_DIALECTS = {
    'sqlite': {
        'parameter_style': 'qmark',
        'placeholder': '?',
        'supports_limit_offset': True,
        'supports_returning': False,
        'supports_cte': True,
        'supports_window_functions': True,
        'string_concat_operator': '||',
        'boolean_literals': '0/1',
        'date_format_function': 'strftime',
        'instructions': [
            "Use SQLite-compatible SQL syntax",
            "Use LIMIT and OFFSET for pagination",
            "Use || for string concatenation",
            "Use strftime() for date formatting",
            "Use 0/1 for boolean values",
            "Use AUTOINCREMENT for auto-incrementing IDs"
        ]
    },
    'postgres': {
        'parameter_style': 'pyformat',
        'placeholder': '%(name)s',
        'supports_limit_offset': True,
        'supports_returning': True,
        'supports_cte': True,
        'supports_window_functions': True,
        'string_concat_operator': '||',
        'boolean_literals': 'true/false',
        'date_format_function': 'TO_CHAR',
        'instructions': [
            "Use PostgreSQL-compatible SQL syntax",
            "Use LIMIT and OFFSET for pagination",
            "Support RETURNING clause for INSERT/UPDATE/DELETE",
            "Use || for string concatenation",
            "Use TO_CHAR() for date formatting",
            "Use true/false for boolean values",
            "Use SERIAL or BIGSERIAL for auto-incrementing IDs"
        ]
    },
    'mysql': {
        'parameter_style': 'format',
        'placeholder': '%s',
        'supports_limit_offset': True,
        'supports_returning': False,
        'supports_cte': True,  # MySQL 8.0+
        'supports_window_functions': True,  # MySQL 8.0+
        'string_concat_operator': 'CONCAT()',
        'boolean_literals': '0/1',
        'date_format_function': 'DATE_FORMAT',
        'instructions': [
            "Use MySQL-compatible SQL syntax",
            "Use LIMIT and OFFSET for pagination",
            "Use CONCAT() for string concatenation",
            "Use DATE_FORMAT() for date formatting",
            "Use 0/1 for boolean values",
            "Use AUTO_INCREMENT for auto-incrementing IDs",
            "Use backticks for quoting identifiers if needed"
        ]
    },
    'mariadb': {
        'parameter_style': 'format',
        'placeholder': '%s',
        'supports_limit_offset': True,
        'supports_returning': True,  # MariaDB 10.5+
        'supports_cte': True,
        'supports_window_functions': True,
        'string_concat_operator': 'CONCAT()',
        'boolean_literals': '0/1',
        'date_format_function': 'DATE_FORMAT',
        'instructions': [
            "Use MariaDB-compatible SQL syntax",
            "Use LIMIT and OFFSET for pagination",
            "Use CONCAT() for string concatenation",
            "Use DATE_FORMAT() for date formatting",
            "Use 0/1 for boolean values",
            "Support RETURNING clause (MariaDB 10.5+)",
            "Use AUTO_INCREMENT for auto-incrementing IDs"
        ]
    },
    'oracle': {
        'parameter_style': 'named',
        'placeholder': ':param_name',
        'supports_limit_offset': False,
        'supports_returning': True,
        'supports_cte': True,
        'supports_window_functions': True,
        'string_concat_operator': '||',
        'boolean_literals': '0/1',
        'date_format_function': 'TO_CHAR',
        'instructions': [
            "Use Oracle-compatible SQL syntax",
            "Use ROWNUM or ROW_NUMBER() OVER() for pagination (no LIMIT)",
            "Use || for string concatenation",
            "Use TO_CHAR() for date formatting",
            "Use 0/1 for boolean values (no native boolean type)",
            "Use RETURNING clause for INSERT/UPDATE/DELETE",
            "Use SEQUENCE for auto-incrementing IDs"
        ]
    },
    'sqlserver': {
        'parameter_style': 'qmark',
        'placeholder': '?',
        'supports_limit_offset': True,  # SQL Server 2012+
        'supports_returning': True,  # OUTPUT clause
        'supports_cte': True,
        'supports_window_functions': True,
        'string_concat_operator': '+',
        'boolean_literals': '0/1',
        'date_format_function': 'FORMAT',
        'instructions': [
            "Use SQL Server (T-SQL) compatible syntax",
            "Use OFFSET/FETCH NEXT for pagination (SQL Server 2012+)",
            "Use + for string concatenation",
            "Use FORMAT() or CONVERT() for date formatting",
            "Use 0/1 or BIT type for boolean values",
            "Use OUTPUT clause instead of RETURNING",
            "Use IDENTITY for auto-incrementing IDs",
            "Use square brackets for quoting identifiers if needed"
        ]
    }
}


class TemplateGenerator:
    """Generates SQL templates from natural language queries using AI"""
    
    def __init__(self, config_path: str = "../../config/config.yaml", provider: str = None):
        """Initialize the template generator
        
        Args:
            config_path: Path to the main configuration file
            provider: Inference provider to use (e.g., 'ollama', 'openai', 'anthropic')
                     If None, will be read from config.yaml
        """
        self.config = self._load_config(config_path)
        self.provider = provider or self.config.get('general', {}).get('inference_provider', 'ollama')
        self.inference_client = None
        self.schema = {}
        self.domain_config = {}
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)

        # Process imports (like adapters.yaml, inference.yaml, etc.)
        config = self._process_imports(config, config_file.parent)

        # Process environment variables (${VAR_NAME} syntax)
        config = self._process_env_vars(config)

        return config

    def _process_imports(self, config: Dict[str, Any], config_dir: Path) -> Dict[str, Any]:
        """Process import statements in config (e.g., import: adapters.yaml)"""
        if not isinstance(config, dict):
            return config

        # Collect all import statements
        import_files = []
        keys_to_remove = []

        for key, value in config.items():
            if key == 'import':
                if isinstance(value, str):
                    import_files.append(value)
                elif isinstance(value, list):
                    import_files.extend(value)
                keys_to_remove.append(key)

        # Remove all import keys from config
        for key in keys_to_remove:
            del config[key]

        # Load and merge each imported file
        for import_file in import_files:
            import_path = config_dir / import_file
            try:
                with open(import_path, 'r') as f:
                    imported_config = yaml.safe_load(f)
                    logger.info(f"Successfully imported configuration from {import_path}")

                    # Recursively process imports in the imported file
                    imported_config = self._process_imports(imported_config, config_dir)

                    # Merge the imported config into the main config
                    config = self._merge_configs(config, imported_config)

            except FileNotFoundError:
                logger.warning(f"Import file not found: {import_path}")
            except Exception as e:
                logger.warning(f"Error loading import file {import_path}: {str(e)}")

        return config

    def _merge_configs(self, main_config: Dict[str, Any], imported_config: Dict[str, Any]) -> Dict[str, Any]:
        """Merge imported config into main config, with main config taking precedence"""
        result = main_config.copy()

        for key, value in imported_config.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Recursively merge nested dictionaries
                result[key] = self._merge_configs(result[key], value)
            elif key not in result:
                # Add new keys from imported config
                result[key] = value

        return result

    def _process_env_vars(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Process environment variables in config values (format: ${ENV_VAR_NAME})"""
        def replace_env_vars(value):
            if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                env_var_name = value[2:-1]
                env_value = os.environ.get(env_var_name)
                if env_value is not None:
                    return env_value
                else:
                    logger.warning(f"Environment variable {env_var_name} not found")
                    return ""
            return value

        def process_dict(d):
            result = {}
            for k, v in d.items():
                if isinstance(v, dict):
                    result[k] = process_dict(v)
                elif isinstance(v, list):
                    result[k] = [process_dict(item) if isinstance(item, dict) else replace_env_vars(item) for item in v]
                else:
                    result[k] = replace_env_vars(v)
            return result

        return process_dict(config)

    async def initialize(self):
        """Initialize the inference client"""
        logger.info(f"🔧 Initializing inference provider: {self.provider}")

        # Show the model being used
        model = "default"
        if self.provider in self.config.get('inference', {}):
            model = self.config.get('inference', {}).get(self.provider, {}).get('model', 'default')

        logger.info(f"📦 Using model: {model}")

        self.inference_client = UnifiedProviderFactory.create_provider_by_name(self.provider, self.config)
        await self.inference_client.initialize()
        logger.info(f"✅ Inference client initialized successfully")
        sys.stdout.flush()
    
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
        
        # Find CREATE TABLE statements (with optional IF NOT EXISTS)
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

                # Skip standalone constraint definitions (lines that START with constraint keywords)
                line_upper = line.upper()
                if line_upper.startswith('PRIMARY KEY') or line_upper.startswith('FOREIGN KEY') or line_upper.startswith('CHECK') or line_upper.startswith('CONSTRAINT'):
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
        sys.stdout.flush()
        return tables
    
    def load_domain_config(self, domain_config_path: str):
        """Load domain configuration if available"""
        if Path(domain_config_path).exists():
            with open(domain_config_path, 'r') as f:
                self.domain_config = yaml.safe_load(f)
            logger.info("Loaded domain configuration")

            # Extract SQL dialect type and load built-in configuration
            sql_dialect = self.domain_config.get('sql_dialect', {})
            dialect_type = sql_dialect.get('type', 'postgres').lower()

            if dialect_type in SQL_DIALECTS:
                self.sql_dialect = SQL_DIALECTS[dialect_type]
                self.sql_dialect_type = dialect_type
                logger.info(f"SQL Dialect: {dialect_type}")
                logger.info(f"  - Parameter style: {self.sql_dialect['parameter_style']}")
                logger.info(f"  - Placeholder: {self.sql_dialect['placeholder']}")
                sys.stdout.flush()
            else:
                logger.warning(f"Unknown SQL dialect '{dialect_type}', defaulting to postgres")
                self.sql_dialect = SQL_DIALECTS['postgres']
                self.sql_dialect_type = 'postgres'
                sys.stdout.flush()
        else:
            logger.warning(f"Domain config not found at: {domain_config_path}")
            self.sql_dialect = SQL_DIALECTS['postgres']
            self.sql_dialect_type = 'postgres'
            sys.stdout.flush()
    
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
        sys.stdout.flush()
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

        # Add rate limiting and retry logic
        max_retries = 3
        response = None

        for attempt in range(max_retries):
            try:
                # Add random delay to avoid rate limiting (0.5-2 seconds)
                delay = random.uniform(0.5, 2.0)
                await asyncio.sleep(delay)

                response = await self.inference_client.generate(prompt)
                break  # Success, exit retry loop

            except Exception as e:
                error_msg = str(e)
                is_rate_limit_error = '500' in error_msg or 'Internal Server Error' in error_msg or 'rate limit' in error_msg.lower()

                if is_rate_limit_error and attempt < max_retries - 1:
                    # Exponential backoff with jitter
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"   ⚠️  Rate limited (attempt {attempt + 1}/{max_retries}), retrying in {wait_time:.1f}s...")
                    sys.stdout.flush()
                    await asyncio.sleep(wait_time)
                else:
                    # Either not a rate limit error, or we've exhausted retries
                    logger.error(f"   ❌ Error analyzing query after {attempt + 1} attempts: {error_msg}")
                    sys.stdout.flush()
                    raise
        
        # Extract JSON from response
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                # Log successful analysis with key details
                intent = analysis.get('intent', 'unknown')
                entity = analysis.get('primary_entity', 'unknown')
                filters = len(analysis.get('filters', []))
                aggregations = len(analysis.get('aggregations', []))
                logger.debug(f"   📊 Analysis: {intent} {entity} (filters: {filters}, aggregations: {aggregations})")
                return analysis
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

        # Get SQL dialect configuration (defaults to postgres if not set)
        dialect_config = getattr(self, 'sql_dialect', SQL_DIALECTS['postgres'])
        dialect_type = getattr(self, 'sql_dialect_type', 'postgres')

        placeholder = dialect_config['placeholder']
        dialect_instructions = dialect_config['instructions']

        prompt = f"""Generate a parameterized SQL template for this query analysis.

Database Schema:
{schema_summary}

Original Query: "{query}"

Query Analysis:
{json.dumps(analysis, indent=2)}

SQL Dialect: {dialect_type.upper()}
Parameter Placeholder: {placeholder}

Generate a SQL template that:
1. Uses {placeholder} placeholders for dynamic values
2. Properly joins tables when needed
3. Includes appropriate WHERE clauses
4. Handles aggregations if needed
5. Is optimized for {dialect_type.upper()}

{dialect_type.upper()}-specific requirements:
{chr(10).join(f"  - {instruction}" for instruction in dialect_instructions)}

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
            "required": false,
            "default": <actual_value_NOT_null>
        }}
    ],
    "nl_examples": [
        "Example query 1",
        "Example query 2"
    ],
    "result_format": "table|summary"
}}

CRITICAL REQUIREMENT - Parameter Defaults:
- Parameters MUST have actual default values, NEVER use null
- For pagination: {{"name": "limit", "type": "integer", "default": 100, "required": false}}
- For pagination: {{"name": "offset", "type": "integer", "default": 0, "required": false}}
- For text search: {{"default": "", "required": false}} OR {{"required": true}} (no default)
- For numeric filters: provide sensible default OR make required=true
- For booleans: {{"default": false}} or {{"default": true}}
- For dates: {{"default": ""}} OR {{"required": true}}

Example CORRECT parameters:
[
    {{"name": "limit", "type": "integer", "description": "Max records", "required": false, "default": 100}},
    {{"name": "offset", "type": "integer", "description": "Skip records", "required": false, "default": 0}},
    {{"name": "search_term", "type": "string", "description": "Search text", "required": true}}
]

JSON Response:"""

        # Add rate limiting and retry logic
        max_retries = 3
        response = None

        for attempt in range(max_retries):
            try:
                # Add random delay to avoid rate limiting (0.5-2 seconds)
                delay = random.uniform(0.5, 2.0)
                await asyncio.sleep(delay)

                response = await self.inference_client.generate(prompt)
                break  # Success, exit retry loop

            except Exception as e:
                error_msg = str(e)
                is_rate_limit_error = '500' in error_msg or 'Internal Server Error' in error_msg or 'rate limit' in error_msg.lower()

                if is_rate_limit_error and attempt < max_retries - 1:
                    # Exponential backoff with jitter
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"   ⚠️  Rate limited (attempt {attempt + 1}/{max_retries}), retrying in {wait_time:.1f}s...")
                    sys.stdout.flush()
                    await asyncio.sleep(wait_time)
                else:
                    # Either not a rate limit error, or we've exhausted retries
                    logger.error(f"   ❌ Error generating template after {attempt + 1} attempts: {error_msg}")
                    sys.stdout.flush()
                    raise

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

                # Post-process: Fix any null defaults in parameters
                self._fix_parameter_defaults(template)

                # Log successful template generation
                template_id = template.get('id', 'unknown')
                param_count = len(template.get('parameters', []))
                example_count = len(template.get('nl_examples', []))
                logger.debug(f"   🎯 Generated template: {template_id} ({param_count} params, {example_count} examples)")

                return template
            else:
                logger.error(f"No JSON found in SQL template response for query: {query}")
                return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse SQL template JSON for query: {query}, error: {e}")
            return None

    def _fix_parameter_defaults(self, template: Dict[str, Any]) -> None:
        """Fix null defaults in template parameters.

        This post-processing method ensures no parameters have null defaults,
        which can cause binding errors in SQLite and other databases.

        Args:
            template: Template dictionary to fix (modified in place)
        """
        if 'parameters' not in template or not template['parameters']:
            return

        fixed_count = 0
        for param in template['parameters']:
            if 'default' not in param:
                continue

            # Skip if already has a non-null default
            if param['default'] is not None:
                continue

            # Fix based on parameter type and name
            param_name = param.get('name', '').lower()
            param_type = param.get('type', 'string').lower()

            # Common pagination parameters
            if param_name == 'limit':
                param['default'] = 100
                fixed_count += 1
                logger.debug(f"Fixed null default for 'limit' parameter -> 100")
            elif param_name == 'offset':
                param['default'] = 0
                fixed_count += 1
                logger.debug(f"Fixed null default for 'offset' parameter -> 0")

            # Type-based defaults
            elif param_type == 'integer':
                # For integer types, either make required or provide sensible default
                if 'max' in param_name or 'limit' in param_name:
                    param['default'] = 100
                elif 'min' in param_name or 'offset' in param_name or 'skip' in param_name:
                    param['default'] = 0
                else:
                    # For other integers, make them required instead of providing arbitrary default
                    param['required'] = True
                    del param['default']
                fixed_count += 1
                logger.debug(f"Fixed null default for integer parameter '{param_name}'")

            elif param_type == 'string' or param_type == 'text':
                # For string types, use empty string or make required
                if 'search' in param_name or 'term' in param_name or 'query' in param_name:
                    # Search terms should typically be required
                    param['required'] = True
                    del param['default']
                else:
                    # Other strings can default to empty
                    param['default'] = ""
                fixed_count += 1
                logger.debug(f"Fixed null default for string parameter '{param_name}'")

            elif param_type == 'boolean' or param_type == 'bool':
                param['default'] = False
                fixed_count += 1
                logger.debug(f"Fixed null default for boolean parameter '{param_name}' -> False")

            elif param_type == 'date' or param_type == 'datetime' or param_type == 'timestamp':
                # Date parameters are usually filters, so make them required
                param['required'] = True
                del param['default']
                fixed_count += 1
                logger.debug(f"Fixed null default for date parameter '{param_name}' -> required")

            elif param_type == 'decimal' or param_type == 'float' or param_type == 'numeric':
                # Numeric filters should usually be required
                param['required'] = True
                del param['default']
                fixed_count += 1
                logger.debug(f"Fixed null default for numeric parameter '{param_name}' -> required")

        if fixed_count > 0:
            logger.info(f"Fixed {fixed_count} null default(s) in template '{template.get('id', 'unknown')}'")

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
        import time
        start_time = time.time()
        
        # Analyze all queries
        logger.info(f"🔍 Analyzing {len(queries)} queries...")
        logger.info("=" * 60)
        sys.stdout.flush()

        analyses = []
        successful_analyses = 0

        for i, query in enumerate(queries):
            query_start = time.time()

            # Show progress for every query
            logger.info(f"📝 [{i+1}/{len(queries)}] Analyzing: \"{query[:60]}{'...' if len(query) > 60 else ''}\"")
            sys.stdout.flush()

            analysis = await self.analyze_query(query)
            analyses.append(analysis)

            if analysis:
                successful_analyses += 1
                query_time = time.time() - query_start
                logger.info(f"   ✅ Complete ({query_time:.1f}s) - {successful_analyses}/{i+1} successful")
            else:
                logger.warning(f"   ⚠️  Analysis failed")
            sys.stdout.flush()
        
        analysis_time = time.time() - start_time
        logger.info("=" * 60)
        logger.info(f"✅ Query analysis complete: {successful_analyses}/{len(queries)} successful ({analysis_time:.1f}s)")
        sys.stdout.flush()

        # Group similar queries
        logger.info("🔄 Grouping similar queries...")
        sys.stdout.flush()
        group_start = time.time()
        grouped = self.group_similar_queries(queries, analyses)
        group_time = time.time() - group_start
        logger.info(f"✅ Grouped into {len(grouped)} template categories ({group_time:.1f}s)")
        sys.stdout.flush()

        # Generate templates for each group
        logger.info("🏗️  Generating SQL templates...")
        logger.info("=" * 60)
        sys.stdout.flush()
        template_start = time.time()
        templates = []

        for i, (group_key, group_queries) in enumerate(grouped.items()):
            group_gen_start = time.time()
            logger.info(f"📋 Template {i+1}/{len(grouped)}: {group_key} ({len(group_queries)} queries)")
            sys.stdout.flush()

            # Use the first query as representative
            repr_query, repr_analysis = group_queries[0]
            logger.info(f"   🎯 Representative query: \"{repr_query[:60]}{'...' if len(repr_query) > 60 else ''}\"")
            sys.stdout.flush()

            template = await self.generate_sql_template(repr_query, repr_analysis)
            if template:
                # Add all example queries from the group
                all_examples = [q for q, _ in group_queries[:10]]  # Limit to 10 examples
                template['nl_examples'] = all_examples

                templates.append(template)
                group_gen_time = time.time() - group_gen_start
                logger.info(f"   ✅ Template generated: {template.get('id', 'unknown')} ({group_gen_time:.1f}s)")
                logger.info(f"   📊 Parameters: {len(template.get('parameters', []))}, Examples: {len(all_examples)}")
            else:
                group_gen_time = time.time() - group_gen_start
                logger.warning(f"   ❌ Template generation failed ({group_gen_time:.1f}s)")

            logger.info("-" * 40)
            sys.stdout.flush()
        
        total_time = time.time() - start_time
        template_time = time.time() - template_start
        logger.info("=" * 60)
        logger.info(f"🎉 Template generation complete!")
        logger.info(f"📈 Generated {len(templates)} templates from {len(queries)} queries")
        logger.info(f"⏱️  Total time: {total_time:.1f}s (Analysis: {analysis_time:.1f}s, Templates: {template_time:.1f}s)")
        sys.stdout.flush()

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

    def generate_domain_config(self, domain_name: str = None, domain_type: str = "general") -> Dict[str, Any]:
        """Generate domain configuration file from schema

        Args:
            domain_name: Name of the domain (default: inferred from schema)
            domain_type: Type of domain (general, ecommerce, security, etc.)

        Returns:
            Domain configuration dictionary
        """
        if not self.schema:
            raise ValueError("Schema must be parsed before generating domain config")

        # Infer domain name from tables if not provided
        if not domain_name:
            table_names = list(self.schema.keys())
            domain_name = " ".join(table_names).replace("_", " ").title()

        logger.info(f"Generating domain configuration: {domain_name}")

        # Create domain config structure
        domain_config = {
            'domain_name': domain_name,
            'description': f"{domain_name} database schema",
            'domain_type': domain_type,
            'semantic_types': self._generate_semantic_types(),
            'vocabulary': self._generate_vocabulary(),
            'entities': {},
            'fields': {},
            'relationships': self._generate_relationships(),
            'query_patterns': [],
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'generator_version': '1.0.0',
                'auto_generated': True
            }
        }

        # Generate entities and fields
        for table_name, table_info in self.schema.items():
            # Create entity
            entity = self._generate_entity(table_name, table_info)
            domain_config['entities'][table_name] = entity

            # Create fields for this entity
            domain_config['fields'][table_name] = self._generate_fields(table_name, table_info)

        return domain_config

    def _generate_semantic_types(self) -> Dict[str, Any]:
        """Generate semantic type definitions based on schema"""
        semantic_types = {}

        # Scan all columns to detect semantic types
        all_columns = []
        for table_info in self.schema.values():
            all_columns.extend(table_info['columns'])

        # Common semantic patterns
        patterns = {
            'email_address': {
                'description': 'Email address',
                'patterns': ['email', 'mail', 'contact'],
                'regex_patterns': [r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b']
            },
            'phone_number': {
                'description': 'Phone number',
                'patterns': ['phone', 'tel', 'mobile', 'cell'],
                'regex_patterns': [r'\b(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})\b']
            },
            'date_value': {
                'description': 'Date values in various formats',
                'patterns': ['date', 'day', 'time', 'when', 'on', 'created', 'updated'],
                'regex_patterns': [r'\b\d{4}-\d{2}-\d{2}\b', r'\b\d{2}/\d{2}/\d{4}\b']
            },
            'monetary_amount': {
                'description': 'Currency amounts',
                'patterns': ['amount', 'total', 'price', 'cost', 'sum', 'balance'],
                'regex_patterns': [r'\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)']
            },
            'identifier': {
                'description': 'Unique identifier',
                'patterns': ['id', 'identifier', 'key'],
                'regex_patterns': [r'\b(\d+)\b']
            },
            'status_value': {
                'description': 'Status or state',
                'patterns': ['status', 'state', 'condition', 'stage'],
                'enum_values': ['active', 'inactive', 'pending', 'completed', 'cancelled']
            }
        }

        # Only include semantic types that match columns in schema
        for sem_type, definition in patterns.items():
            for col in all_columns:
                col_name = col['name'].lower()
                if any(pattern in col_name for pattern in definition['patterns']):
                    semantic_types[sem_type] = definition
                    break

        return semantic_types

    def _generate_vocabulary(self) -> Dict[str, Any]:
        """Generate vocabulary for NLU"""
        return {
            'entity_synonyms': {},
            'action_verbs': {
                'find': ['show', 'list', 'get', 'find', 'display', 'retrieve', 'lookup', 'search', 'view'],
                'filter': ['filter', 'only', 'just', 'where', 'with', 'having', 'containing'],
                'count': ['count', 'number of', 'how many', 'total', 'sum'],
                'sort': ['sort', 'order', 'arrange', 'rank']
            },
            'field_synonyms': {}
        }

    def _generate_entity(self, table_name: str, table_info: Dict[str, Any]) -> Dict[str, Any]:
        """Generate entity definition from table"""
        # Detect entity type based on naming patterns
        entity_type = 'primary'
        if any(word in table_name.lower() for word in ['audit', 'log', 'transaction', 'history']):
            entity_type = 'transaction'
        elif any(word in table_name.lower() for word in ['lookup', 'ref', 'category', 'type']):
            entity_type = 'reference'

        # Find primary key
        primary_key = None
        for col in table_info['columns']:
            col_name_lower = col['name'].lower()
            if 'id' in col_name_lower and col_name_lower == f"{table_name}_id".lower() or col_name_lower == 'id':
                primary_key = col['name']
                break

        # Find display name field (name, title, etc.)
        display_name_field = None
        for col in table_info['columns']:
            col_name_lower = col['name'].lower()
            if col_name_lower in ['name', 'title', 'username', 'email']:
                display_name_field = col['name']
                break

        # Determine searchable fields (text columns)
        searchable_fields = []
        common_filters = []
        for col in table_info['columns']:
            col_type_lower = col['type'].lower()
            if any(t in col_type_lower for t in ['varchar', 'text', 'char']):
                searchable_fields.append(col['name'])
            if any(word in col['name'].lower() for word in ['status', 'type', 'category', 'id', 'date', 'active']):
                common_filters.append(col['name'])

        # Default sort field (created_at, updated_at, id)
        default_sort_field = primary_key
        for col in table_info['columns']:
            if 'created' in col['name'].lower():
                default_sort_field = col['name']
                break

        return {
            'name': table_name,
            'entity_type': entity_type,
            'table_name': table_name,
            'description': f"{table_name.replace('_', ' ').title()} entity",
            'primary_key': primary_key or 'id',
            'display_name_field': display_name_field,
            'searchable_fields': searchable_fields,
            'common_filters': common_filters,
            'default_sort_field': default_sort_field,
            'default_sort_order': 'DESC' if entity_type == 'transaction' else 'ASC'
        }

    def _generate_fields(self, table_name: str, table_info: Dict[str, Any]) -> Dict[str, Any]:
        """Generate field definitions for entity"""
        fields = {}

        for col in table_info['columns']:
            # Map SQL types to domain types
            col_type_lower = col['type'].lower()
            if any(t in col_type_lower for t in ['int', 'serial', 'bigint']):
                data_type = 'integer'
            elif any(t in col_type_lower for t in ['varchar', 'text', 'char']):
                data_type = 'string'
            elif any(t in col_type_lower for t in ['decimal', 'numeric', 'float', 'real']):
                data_type = 'decimal'
            elif any(t in col_type_lower for t in ['date']):
                data_type = 'date'
            elif any(t in col_type_lower for t in ['timestamp', 'datetime']):
                data_type = 'datetime'
            elif any(t in col_type_lower for t in ['bool']):
                data_type = 'boolean'
            else:
                data_type = 'string'

            # Detect semantic type
            semantic_type = self._infer_semantic_type(col['name'])

            # Determine if field is required
            required = not col.get('nullable', True)

            # Determine field capabilities
            col_name_lower = col['name'].lower()
            searchable = data_type == 'string' and 'id' not in col_name_lower
            filterable = True
            sortable = True

            # Calculate summary priority (1-10, higher = more important)
            priority = 5
            if 'id' in col_name_lower:
                priority = 10
            elif col_name_lower in ['name', 'title', 'username', 'email']:
                priority = 9
            elif col_name_lower in ['status', 'type', 'category']:
                priority = 8
            elif 'date' in col_name_lower:
                priority = 7

            fields[col['name']] = {
                'name': col['name'],
                'data_type': data_type,
                'db_column': col['name'],
                'description': f"{col['name'].replace('_', ' ').title()}",
                'required': required,
                'searchable': searchable,
                'filterable': filterable,
                'sortable': sortable,
                'semantic_type': semantic_type,
                'summary_priority': priority
            }

        return fields

    def _infer_semantic_type(self, column_name: str) -> Optional[str]:
        """Infer semantic type from column name"""
        col_lower = column_name.lower()

        if 'email' in col_lower or 'mail' in col_lower:
            return 'email_address'
        elif 'phone' in col_lower or 'tel' in col_lower or 'mobile' in col_lower:
            return 'phone_number'
        elif 'date' in col_lower or 'time' in col_lower or 'created' in col_lower or 'updated' in col_lower:
            return 'date_value'
        elif any(word in col_lower for word in ['amount', 'price', 'cost', 'total', 'balance']):
            return 'monetary_amount'
        elif 'status' in col_lower or 'state' in col_lower:
            return 'status_value'
        elif col_lower.endswith('_id') or col_lower == 'id':
            return 'identifier'

        return None

    def _generate_relationships(self) -> List[Dict[str, Any]]:
        """Generate relationship definitions from foreign keys"""
        relationships = []

        for table_name, table_info in self.schema.items():
            if 'foreign_keys' not in table_info:
                continue

            for fk in table_info['foreign_keys']:
                # Many-to-one relationship
                relationships.append({
                    'name': f"{table_name}_{fk['references_table']}",
                    'from_entity': table_name,
                    'to_entity': fk['references_table'],
                    'relation_type': 'many_to_one',
                    'from_field': fk['column'],
                    'to_field': fk['references_column'],
                    'join_type': 'LEFT',
                    'description': f"{table_name.replace('_', ' ').title()} belongs to {fk['references_table'].replace('_', ' ').title()}"
                })

                # Inverse one-to-many relationship
                relationships.append({
                    'name': f"{fk['references_table']}_{table_name}",
                    'from_entity': fk['references_table'],
                    'to_entity': table_name,
                    'relation_type': 'one_to_many',
                    'from_field': fk['references_column'],
                    'to_field': fk['column'],
                    'join_type': 'LEFT',
                    'description': f"{fk['references_table'].replace('_', ' ').title()} has many {table_name.replace('_', ' ').title()}"
                })

        return relationships

    def save_domain_config(self, domain_config: Dict[str, Any], output_path: str):
        """Save domain configuration to YAML file

        Args:
            domain_config: Domain configuration dictionary
            output_path: Path to output YAML file
        """
        with open(output_path, 'w') as f:
            yaml.dump(domain_config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

        logger.info(f"Saved domain configuration to: {output_path}")


async def main():
    """Main function"""
    import time
    overall_start = time.time()
    
    parser = argparse.ArgumentParser(description='Generate SQL templates from test queries')
    parser.add_argument('--schema', required=True, help='Path to SQL schema file')
    parser.add_argument('--queries', required=True, help='Path to test queries file')
    parser.add_argument('--output', required=True, help='Path to output YAML file')
    parser.add_argument('--domain', help='Path to domain configuration file')
    parser.add_argument('--config', default='../../config/config.yaml', help='Path to main config file')
    parser.add_argument('--provider', help='Inference provider to use (default: from config.yaml)')
    parser.add_argument('--limit', type=int, help='Limit number of queries to process')
    parser.add_argument('--generate-domain', action='store_true', help='Generate domain configuration file from schema')
    parser.add_argument('--domain-output', help='Path to output domain configuration file (default: <schema>_domain.yaml)')
    parser.add_argument('--domain-name', help='Name for the domain (default: inferred from schema)')
    parser.add_argument('--domain-type', default='general', help='Type of domain (general, ecommerce, security, etc.)')

    args = parser.parse_args()

    logger.info("🚀 Starting SQL Template Generator")
    logger.info("=" * 60)
    sys.stdout.flush()

    # Create generator
    logger.info("⚙️  Initializing template generator...")
    sys.stdout.flush()
    init_start = time.time()
    generator = TemplateGenerator(args.config, args.provider)
    await generator.initialize()
    init_time = time.time() - init_start
    logger.info(f"✅ Generator initialized ({init_time:.1f}s)")
    sys.stdout.flush()

    # Parse schema
    logger.info("📋 Parsing database schema...")
    sys.stdout.flush()
    schema_start = time.time()
    generator.parse_schema(args.schema)
    schema_time = time.time() - schema_start
    logger.info(f"✅ Schema parsed: {len(generator.schema)} tables ({schema_time:.1f}s)")
    sys.stdout.flush()

    # Generate domain config if requested
    if args.generate_domain:
        # Determine output path
        if args.domain_output:
            domain_output_path = args.domain_output
        else:
            schema_base = Path(args.schema).stem
            domain_output_path = f"{schema_base}_domain.yaml"

        logger.info(f"🏗️  Generating domain configuration: {domain_output_path}")
        sys.stdout.flush()
        domain_start = time.time()
        domain_config = generator.generate_domain_config(args.domain_name, args.domain_type)
        generator.save_domain_config(domain_config, domain_output_path)
        domain_time = time.time() - domain_start
        logger.info(f"✅ Domain configuration saved ({domain_time:.1f}s)")
        sys.stdout.flush()

    # Load domain config if provided
    if args.domain:
        logger.info(f"📖 Loading domain configuration: {args.domain}")
        sys.stdout.flush()
        generator.load_domain_config(args.domain)

    # Parse test queries
    logger.info("📝 Parsing test queries...")
    sys.stdout.flush()
    query_start = time.time()
    queries = generator.parse_test_queries(args.queries)
    query_time = time.time() - query_start
    logger.info(f"✅ Parsed {len(queries)} queries ({query_time:.1f}s)")
    sys.stdout.flush()

    # Limit queries if requested
    if args.limit:
        queries = queries[:args.limit]
        logger.info(f"🔢 Limited to {len(queries)} queries")
        sys.stdout.flush()

    # Generate templates
    logger.info("🎯 Starting template generation process...")
    sys.stdout.flush()
    templates = await generator.generate_templates(queries)

    # Save templates
    logger.info("💾 Saving templates...")
    sys.stdout.flush()
    save_start = time.time()
    generator.save_templates(templates, args.output)
    save_time = time.time() - save_start
    logger.info(f"✅ Templates saved to: {args.output} ({save_time:.1f}s)")
    sys.stdout.flush()

    total_time = time.time() - overall_start
    logger.info("=" * 60)
    logger.info("🎉 Template generation complete!")
    logger.info(f"⏱️  Total execution time: {total_time:.1f}s")
    logger.info(f"📊 Generated {len(templates)} templates from {len(queries)} queries")
    logger.info(f"📁 Output file: {args.output}")
    if args.generate_domain:
        logger.info(f"📁 Domain config: {domain_output_path}")
    sys.stdout.flush()


if __name__ == '__main__':
    asyncio.run(main())