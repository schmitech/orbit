#!/usr/bin/env python3
"""
Test Queries Template Generator - AI-Powered Version

DESCRIPTION:
    Creates a comprehensive markdown template for test queries based on your
    database schema using AI. Generates rich, varied queries including:
    - Basic search and filter queries
    - Advanced analytical queries
    - Business intelligence queries
    - Time-series analysis
    - Comparative analysis
    - Cohort analysis
    - Multi-table join queries

USAGE:
    python create_query_template.py --schema <schema.sql> --output <queries.md> [--config <config.yaml>] [--provider <provider>]

ARGUMENTS:
    --schema FILE    Path to SQL schema file
    --output FILE    Path to output markdown file (default: test_queries.md)
    --domain NAME    Domain name for title (optional)
    --config FILE    Path to config file (default: ../../config/config.yaml)
    --provider NAME  Inference provider to use (default: from config)

EXAMPLES:
    # Create template from schema
    python create_query_template.py --schema examples/customer-order.sql

    # Specify output file and provider
    python create_query_template.py \
      --schema examples/ecommerce.sql \
      --output examples/ecommerce_queries.md \
      --provider ollama

AUTHOR:
    SQL Intent Template Generator v3.0.0 (AI-Powered)
"""

import re
import asyncio
import argparse
import sys
import os
import json
import yaml
import logging
from pathlib import Path
from typing import Dict, List, Any, Tuple
from collections import defaultdict
from dotenv import load_dotenv

# Add parent directory to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))
# Add server directory to path so that adapters can be imported
sys.path.append(str(project_root / "server"))

# Load environment variables
load_dotenv(dotenv_path=project_root / ".env")

from server.inference.pipeline.providers.unified_provider_factory import UnifiedProviderFactory

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def parse_schema(schema_path: str) -> Dict[str, Any]:
    """Parse SQL schema to extract tables, columns, and relationships
    
    Handles:
    - Quoted identifiers (e.g., "table_name", `table_name`)
    - Schema-qualified names (e.g., schema.table)
    - Composite primary/foreign keys
    - Multi-line constraints
    - Various SQL dialects
    """
    with open(schema_path, 'r') as f:
        schema_sql = f.read()

    tables = {}
    relationships = defaultdict(list)  # table -> [(foreign_table, foreign_key_col, local_col)]

    # Find CREATE TABLE statements - more flexible pattern
    # Handles: CREATE TABLE, CREATE TABLE IF NOT EXISTS, schema.table, quoted names
    table_pattern = r'CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+(?:[\w"]+\.)?([\w"]+)\s*\((.*?)\);'
    matches = re.findall(table_pattern, schema_sql, re.IGNORECASE | re.DOTALL)

    for table_name, table_def in matches:
        # Clean table name (remove quotes, schema prefix)
        table_name = table_name.strip('"\'`').split('.')[-1]
        columns = []
        primary_key = None

        # Parse column definitions - handle multi-line
        # Split by comma but be careful with nested parentheses
        table_def_clean = table_def.strip()
        
        # Extract all column definitions and constraints
        lines = []
        current_line = ""
        paren_depth = 0
        
        for char in table_def_clean:
            if char == '(':
                paren_depth += 1
                current_line += char
            elif char == ')':
                paren_depth -= 1
                current_line += char
            elif char == ',' and paren_depth == 0:
                if current_line.strip():
                    lines.append(current_line.strip())
                current_line = ""
            else:
                current_line += char
        
        if current_line.strip():
            lines.append(current_line.strip())
        
        for line in lines:
            line = line.strip().rstrip(',')
            if not line or line.startswith('--'):
                continue

            line_upper = line.upper()
            
            # Detect PRIMARY KEY (handles composite keys)
            if 'PRIMARY KEY' in line_upper:
                pk_match = re.search(r'PRIMARY\s+KEY\s*\(([^)]+)\)', line_upper, re.IGNORECASE)
                if pk_match:
                    pk_cols = [c.strip().strip('"\'`') for c in pk_match.group(1).split(',')]
                    primary_key = pk_cols[0] if pk_cols else None
                continue

            # Detect FOREIGN KEY relationships (more flexible pattern)
            fk_patterns = [
                r'FOREIGN\s+KEY\s*\(([^)]+)\)\s+REFERENCES\s+(?:[\w"]+\.)?([\w"]+)\s*\(([^)]+)\)',
                r'(\w+)\s+REFERENCES\s+(?:[\w"]+\.)?([\w"]+)\s*\(([^)]+)\)',
            ]
            
            for fk_pattern in fk_patterns:
                fk_match = re.search(fk_pattern, line_upper, re.IGNORECASE)
                if fk_match:
                    local_col = fk_match.group(1).strip().strip('"\'`')
                    foreign_table = fk_match.group(2).strip().strip('"\'`').split('.')[-1]
                    foreign_col = fk_match.group(3).strip().strip('"\'`')
                    relationships[table_name].append((foreign_table, foreign_col, local_col))
                    break
            
            if any(keyword in line_upper for keyword in ['FOREIGN KEY', 'CHECK', 'CONSTRAINT', 'UNIQUE', 'REFERENCES']):
                continue

            # Parse column name and type - handle quoted names and schema qualifiers
            # Extract column name (first word, may be quoted)
            col_match = re.match(r'^(["\']?[\w]+["\']?)\s+', line)
            if col_match:
                col_name = col_match.group(1).strip('"\'`')
                # Extract type (next word, may have parameters like VARCHAR(255))
                type_match = re.search(r'\s+([A-Z]+\w*(?:\([^)]+\))?)', line, re.IGNORECASE)
                if type_match:
                    col_type = type_match.group(1)
                columns.append({'name': col_name, 'type': col_type})

        tables[table_name] = {
            'name': table_name,
            'columns': columns,
            'primary_key': primary_key,
            'relationships': relationships[table_name]
        }

    return tables

def detect_column_semantics(col_name: str, col_type: str) -> Dict[str, Any]:
    """Detect semantic meaning of columns using both name patterns and data types
    
    Uses:
    - Column name patterns (keywords, abbreviations)
    - Data type information
    - Type constraints (e.g., VARCHAR length hints at content)
    """
    col_lower = col_name.lower()
    col_type_lower = col_type.lower()
    
    # Extract base type (remove parameters like VARCHAR(255))
    base_type = re.sub(r'\([^)]+\)', '', col_type_lower).strip()
    
    semantics = {
        'is_id': False,
        'is_amount': False,
        'is_price': False,
        'is_revenue': False,
        'is_status': False,
        'is_date': False,
        'is_email': False,
        'is_phone': False,
        'is_location': False,
        'is_country': False,
        'is_city': False,
        'is_name': False,
        'is_category': False,
        'is_type': False,
        'is_quantity': False,
        'is_percentage': False,
        'is_rating': False,
        'is_boolean': False,
        'is_text': False,
        'is_numeric': False,
    }
    
    # Data type based detection (more reliable than name patterns)
    if any(term in base_type for term in ['date', 'timestamp', 'time', 'datetime']):
        semantics['is_date'] = True
    elif any(term in base_type for term in ['int', 'integer', 'serial', 'bigint', 'smallint']):
        semantics['is_numeric'] = True
        if 'id' in col_lower or col_lower.endswith('_id') or col_lower.endswith('id'):
            semantics['is_id'] = True
    elif any(term in base_type for term in ['decimal', 'numeric', 'float', 'double', 'real', 'money']):
        semantics['is_numeric'] = True
        semantics['is_amount'] = True  # Numeric types are often amounts
    elif any(term in base_type for term in ['varchar', 'text', 'char', 'string']):
        semantics['is_text'] = True
    elif any(term in base_type for term in ['bool', 'boolean', 'bit']):
        semantics['is_boolean'] = True
    elif 'enum' in base_type:
        # Enum types are often status/type fields
        semantics['is_status'] = True
    
    # Name pattern detection (supplements type-based detection)
    # ID detection
    if 'id' in col_lower or col_lower.endswith('_id') or col_lower.endswith('id'):
        semantics['is_id'] = True
    
    # Financial columns (name-based, supplements type detection)
    if any(term in col_lower for term in ['amount', 'total', 'sum', 'value', 'cost', 'price', 'fee', 'charge', 'payment', 'paid']):
        if 'price' in col_lower:
            semantics['is_price'] = True
        elif any(term in col_lower for term in ['revenue', 'sales', 'income']):
            semantics['is_revenue'] = True
        else:
            semantics['is_amount'] = True
    
    # Status/enum columns
    if any(term in col_lower for term in ['status', 'state', 'stage', 'phase']):
        semantics['is_status'] = True
    elif 'type' in col_lower and not semantics['is_status']:
        semantics['is_type'] = True
    
    # Contact columns (type-based hints: VARCHAR with specific lengths)
    if 'email' in col_lower or (semantics['is_text'] and '@' in col_name):
        semantics['is_email'] = True
    if any(term in col_lower for term in ['phone', 'tel', 'mobile', 'cell']):
        semantics['is_phone'] = True
    
    # Location columns
    if 'country' in col_lower:
        semantics['is_country'] = True
    if 'city' in col_lower:
        semantics['is_city'] = True
    if any(term in col_lower for term in ['address', 'location', 'region', 'state', 'zip', 'postal', 'province']):
        semantics['is_location'] = True
    
    # Name columns
    if any(term in col_lower for term in ['name', 'title', 'label', 'full_name']):
        semantics['is_name'] = True
    
    # Category columns
    if 'category' in col_lower or 'cat' in col_lower:
        semantics['is_category'] = True
    
    # Quantity columns
    if any(term in col_lower for term in ['quantity', 'qty', 'count', 'num', 'number']):
        if not semantics['is_id']:  # Don't mark ID columns as quantity
            semantics['is_quantity'] = True
    
    # Percentage columns
    if any(term in col_lower for term in ['percent', 'pct', 'percentage', 'rate']):
        semantics['is_percentage'] = True
    
    # Rating columns
    if any(term in col_lower for term in ['rating', 'score', 'rank', 'grade']):
        semantics['is_rating'] = True
    
    return semantics

def get_entity_label(table_name: str) -> str:
    """Convert table name to human-readable entity label"""
    # Remove common prefixes/suffixes
    label = table_name.replace('_', ' ').title()
    # Handle plural forms
    if label.endswith('s'):
        return label
    return label


class QueryGenerator:
    """AI-powered query generator using LLM"""
    
    def __init__(self, config_path: str = "../../config/config.yaml", provider: str = None):
        """Initialize the query generator
        
        Args:
            config_path: Path to the main configuration file
            provider: Inference provider to use (e.g., 'ollama', 'openai', 'anthropic')
                     If None, will be read from config.yaml
        """
        self.config = self._load_config(config_path)
        self.provider = provider or self.config.get('general', {}).get('inference_provider', 'ollama')
        self.inference_client = None
        
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

        import_files = []
        keys_to_remove = []

        for key, value in config.items():
            if key == 'import':
                if isinstance(value, str):
                    import_files.append(value)
                elif isinstance(value, list):
                    import_files.extend(value)
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del config[key]

        for import_file in import_files:
            import_path = config_dir / import_file
            try:
                with open(import_path, 'r') as f:
                    imported_config = yaml.safe_load(f)
                    imported_config = self._process_imports(imported_config, config_dir)
                    config = self._merge_configs(config, imported_config)
            except FileNotFoundError:
                logger.warning(f"Import file not found: {import_path}")
            except Exception as e:
                logger.warning(f"Error loading import file {import_path}: {str(e)}")

        return config

    def _merge_configs(self, main_config: Dict[str, Any], imported_config: Dict[str, Any]) -> Dict[str, Any]:
        """Merge imported config into main config"""
        result = main_config.copy()
        for key, value in imported_config.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            elif key not in result:
                result[key] = value
        return result

    def _process_env_vars(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Process environment variables in config values"""
        def replace_env_vars(value):
            if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                env_var_name = value[2:-1]
                return os.environ.get(env_var_name, "")
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
        model = "default"
        if self.provider in self.config.get('inference', {}):
            model = self.config.get('inference', {}).get(self.provider, {}).get('model', 'default')
        logger.info(f"📦 Using model: {model}")
        self.inference_client = UnifiedProviderFactory.create_provider_by_name(self.provider, self.config)
        await self.inference_client.initialize()
        logger.info("✅ Inference client initialized successfully")
    
    def _create_schema_summary(self, tables: Dict[str, Any]) -> str:
        """Create a summary of the database schema for LLM"""
        summary = []
        for table_name, table_info in tables.items():
            cols = [f"{c['name']} ({c['type']})" for c in table_info['columns']]
            summary.append(f"{table_name}: {', '.join(cols)}")
            if 'relationships' in table_info and table_info['relationships']:
                for rel in table_info['relationships']:
                    foreign_table, foreign_col, local_col = rel
                    summary.append(f"  Relationship: {table_name}.{local_col} -> {foreign_table}.{foreign_col}")
        return '\n'.join(summary)
    
    async def generate_queries_for_table(
        self,
        table_name: str,
        table_info: Dict[str, Any],
        tables: Dict[str, Any],
        query_type: str = "basic"
    ) -> List[str]:
        """Generate queries for a table using LLM
        
        Args:
            table_name: Name of the table
            table_info: Table information (columns, relationships, etc.)
            tables: All tables in the schema
            query_type: Type of queries to generate (basic, analytical, join)
        
        Returns:
            List of generated queries
        """
        entity_label = get_entity_label(table_name)
        schema_summary = self._create_schema_summary(tables)
        
        columns_info = []
        for col in table_info['columns']:
            semantics = detect_column_semantics(col['name'], col['type'])
            col_info = f"- {col['name']} ({col['type']})"
            semantic_tags = [k.replace('is_', '') for k, v in semantics.items() if v and k.startswith('is_')]
            if semantic_tags:
                col_info += f" [semantic: {', '.join(semantic_tags[:3])}]"
            columns_info.append(col_info)
        
        relationships_info = []
        if 'relationships' in table_info and table_info['relationships']:
            for rel in table_info['relationships']:
                foreign_table, foreign_col, local_col = rel
                foreign_entity = get_entity_label(foreign_table)
                relationships_info.append(f"- {table_name}.{local_col} -> {foreign_table}.{foreign_col} ({foreign_entity})")
        
        if query_type == "basic":
            prompt = f"""Generate 15-20 NATURAL LANGUAGE test queries for searching and filtering {entity_label} records.

Database Schema:
{schema_summary}

Table: {table_name} ({entity_label})
Columns:
{chr(10).join(columns_info)}

Relationships:
{chr(10).join(relationships_info) if relationships_info else "None"}

IMPORTANT: Generate NATURAL LANGUAGE questions that users would ask, NOT SQL code. These should be questions like "Find customers named John" NOT "SELECT * FROM customers WHERE name = 'John'".

Generate diverse, natural-sounding queries that users might ask, including:
- Search by name/title fields - e.g., "Find customers named John"
- Filter by specific column values - e.g., "Show me orders with status pending"
- Date range queries - e.g., "List orders created this year"
- Status/category filters - e.g., "Find active customers"
- Numeric range queries - e.g., "Show me orders over 100 dollars"
- Location-based queries - e.g., "Find customers in New York"
- Combination queries - e.g., "Show me high-value orders from customers in France"

Return ONLY a JSON array of natural language query strings, like this:
[
  "Find {entity_label} by name",
  "Show me {entity_label} created this year",
  "List {entity_label} with status active"
]

CRITICAL: Do NOT generate SQL code. Only generate natural language questions that users would ask.

JSON Response:"""
        
        elif query_type == "analytical":
            prompt = f"""Generate 15-20 NATURAL LANGUAGE analytical and business intelligence queries for {entity_label}.

Database Schema:
{schema_summary}

Table: {table_name} ({entity_label})
Columns:
{chr(10).join(columns_info)}

IMPORTANT: Generate NATURAL LANGUAGE questions that users would ask, NOT SQL code. These should be questions like "What's the total revenue this month?" NOT "SELECT SUM(revenue) FROM table".

Generate natural language queries for:
- Aggregations (sum, count, average) - e.g., "What's the total amount of all orders?"
- Time-series analysis - e.g., "Show me sales by month"
- Comparative analysis - e.g., "Compare this month's revenue to last month"
- Ranking and top N queries - e.g., "Show me the top 10 customers by order count"
- Grouping and distribution - e.g., "How many orders per status?"
- Trend analysis - e.g., "Show me revenue trends over time"
- Performance metrics - e.g., "What's the average order value?"

Return ONLY a JSON array of natural language query strings, like this:
[
  "What's the total amount of all {entity_label}?",
  "Show me the average value by month",
  "Compare this month's total to last month",
  "List the top 10 {entity_label} by amount"
]

CRITICAL: Do NOT generate SQL code. Only generate natural language questions that users would ask.

JSON Response:"""
        
        else:  # join queries
            prompt = f"""Generate 10-15 NATURAL LANGUAGE multi-table join queries involving {entity_label}.

Database Schema:
{schema_summary}

Table: {table_name} ({entity_label})
Relationships:
{chr(10).join(relationships_info) if relationships_info else "None"}

IMPORTANT: Generate NATURAL LANGUAGE questions that users would ask, NOT SQL code. These should be questions like "Show me orders with customer names" NOT "SELECT o.* FROM orders o JOIN customers c...".

Generate natural language queries that combine {entity_label} with related tables, including:
- Queries that combine data from multiple tables - e.g., "Show me orders with customer names"
- Filtering by related entity attributes - e.g., "Find orders from customers in New York"
- Aggregations across joined tables - e.g., "What's the total sales by country?"
- Complex multi-criteria searches - e.g., "Show me high-value orders from customers in France"

Return ONLY a JSON array of natural language query strings, like this:
[
  "Show me {entity_label} with related customer information",
  "Find {entity_label} from customers in New York",
  "What's the total sales by country?",
  "List {entity_label} with customer details"
]

CRITICAL: Do NOT generate SQL code. Only generate natural language questions that users would ask.

JSON Response:"""
        
        try:
            response = await self.inference_client.generate(prompt)
            
            # Extract JSON from response
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                queries = json.loads(json_match.group())
                if isinstance(queries, list):
                    # Filter out SQL queries and clean up
                    filtered_queries = []
                    for q in queries:
                        query_str = str(q).strip('"').strip()
                        if query_str:
                            # Reject queries that look like SQL
                            query_upper = query_str.upper()
                            sql_keywords = ['SELECT', 'FROM', 'WHERE', 'JOIN', 'GROUP BY', 'ORDER BY', 'HAVING', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP']
                            if not any(keyword in query_upper for keyword in sql_keywords):
                                filtered_queries.append(query_str)
                            else:
                                logger.warning(f"Filtered out SQL query: {query_str[:50]}...")
                    return filtered_queries
            
            # Fallback: try to extract quoted strings
            queries = re.findall(r'"([^"]+)"', response)
            if queries:
                # Filter out SQL queries
                filtered_queries = []
                for q in queries:
                    query_str = q.strip()
                    if query_str:
                        query_upper = query_str.upper()
                        sql_keywords = ['SELECT', 'FROM', 'WHERE', 'JOIN', 'GROUP BY', 'ORDER BY', 'HAVING', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP']
                        if not any(keyword in query_upper for keyword in sql_keywords):
                            filtered_queries.append(query_str)
                        else:
                            logger.warning(f"Filtered out SQL query: {query_str[:50]}...")
                return filtered_queries
            
            logger.warning(f"Could not parse queries from LLM response for {table_name}")
            return []
            
        except Exception as e:
            logger.error(f"Error generating queries for {table_name}: {e}")
            return []

def generate_basic_queries(table_name: str, columns: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Generate basic search and filter queries"""
    categories = []
    entity_label = get_entity_label(table_name)
    entity_label.rstrip('s') if entity_label.endswith('s') else entity_label
    
    # Find name column
    name_col = None
    for col in columns:
        semantics = detect_column_semantics(col['name'], col['type'])
        if semantics['is_name']:
            name_col = col['name']
            break
    
    # Basic search queries (only if name column exists)
    if name_col:
        name_label = name_col.replace("_", " ").title()
        categories.append({
                'title': f'Search by {name_label}',
                'queries': [
                    f'"Find {entity_label} by {name_label}"',
                    f'"Show me {entity_label} with specific {name_label}"',
                    f'"Search for {entity_label} by {name_label} pattern"',
                    f'"Find {entity_label} matching {name_label}"',
                    f'"Show me {entity_label} with {name_label} containing text"',
                    f'"Search for {entity_label} by partial {name_label}"',
                    f'"Find {entity_label} with exact {name_label}"',
                    f'"Show me {entity_label} filtered by {name_label}"',
            ]
        })

    # Search by each column
    for col in columns:
        col_name = col['name']
        col_type = col['type']
        col_label = col_name.replace("_", " ").title()
        semantics = detect_column_semantics(col_name, col_type)
        
        # Email queries
        if semantics['is_email']:
            categories.append({
                'title': f'Search by {col_label}',
                'queries': [
                    f'"Find {entity_label} with {col_name}"',
                    f'"Show me {entity_label} with {col_name} addresses"',
                    f'"Search for {entity_label} by {col_name}"',
                    f'"Find {entity_label} with {col_name} containing text"',
                    f'"Show me {entity_label} with {col_name} domain"',
                    f'"Search for {entity_label} with {col_name} pattern"',
                    f'"Find {entity_label} by {col_name} address"',
                    f'"Show me {entity_label} filtered by {col_name}"',
                ]
            })
        
        # Phone queries
        elif semantics['is_phone']:
            categories.append({
                'title': f'Search by {col_label}',
                'queries': [
                    f'"Find {entity_label} with {col_name}"',
                    f'"Show me {entity_label} with {col_name} numbers"',
                    f'"Search for {entity_label} by {col_name}"',
                    f'"Find {entity_label} with {col_name} pattern"',
                    f'"Show me {entity_label} with {col_name} starting with digits"',
                    f'"Search for {entity_label} with {col_name} containing digits"',
                ]
            })
        
        # Location queries
        elif semantics['is_city']:
            categories.append({
                'title': f'Search by {col_label}',
                'queries': [
                    f'"Find {entity_label} by {col_label}"',
                    f'"Show me {entity_label} from specific {col_label}"',
                    f'"Search for {entity_label} by {col_label} name"',
                    f'"Find {entity_label} in {col_label}"',
                    f'"Show me {entity_label} filtered by {col_label}"',
                    f'"Search for {entity_label} by {col_label} location"',
                    f'"Find {entity_label} from {col_label}"',
                    f'"Show me {entity_label} by {col_label}"',
                ]
            })
        
        elif semantics['is_country']:
            categories.append({
                'title': f'Search by {col_label}',
                'queries': [
                    f'"Find {entity_label} by {col_label}"',
                    f'"Show me {entity_label} from specific {col_label}"',
                    f'"Search for {entity_label} by {col_label} name"',
                    f'"Find {entity_label} in {col_label}"',
                    f'"Show me {entity_label} filtered by {col_label}"',
                    f'"Search for {entity_label} by {col_label} location"',
                    f'"Find {entity_label} from {col_label}"',
                    f'"Show me {entity_label} by {col_label}"',
                ]
            })
        
        # Date queries
        elif semantics['is_date']:
            date_label = col_label.lower()
            categories.append({
                'title': f'Search by {col_label}',
                'queries': [
                    f'"Show me {entity_label} {date_label} this year"',
                    f'"Find {entity_label} {date_label} last month"',
                    f'"List {entity_label} {date_label} in the last 30 days"',
                    f'"Show me {entity_label} {date_label} in 2024"',
                    f'"Find {entity_label} {date_label} this week"',
                    f'"Show me recent {entity_label}"',
                    f'"List {entity_label} {date_label} yesterday"',
                    f'"Show me {entity_label} {date_label} today"',
                ]
            })
        
        # Status queries
        elif semantics['is_status']:
            categories.append({
                'title': f'Search by {col_label}',
                'queries': [
                    f'"Show me {entity_label} with {col_name} pending"',
                    f'"Find {entity_label} with {col_name} completed"',
                    f'"List {entity_label} with {col_name} cancelled"',
                    f'"Show me {entity_label} with {col_name} active"',
                    f'"Find {entity_label} with {col_name} inactive"',
                    f'"List {entity_label} with {col_name} processing"',
                ]
            })
        
        # Amount/Price queries
        elif semantics['is_amount'] or semantics['is_price']:
            categories.append({
                'title': f'Search by {col_label}',
                'queries': [
                    f'"Show me {entity_label} with {col_name} over 100"',
                    f'"Find {entity_label} with {col_name} under 50"',
                    f'"List {entity_label} with {col_name} between 50 and 100"',
                    f'"Show me {entity_label} with {col_name} over 500"',
                    f'"Find {entity_label} with {col_name} under 25"',
                    f'"List {entity_label} with {col_name} between 100 and 200"',
                    f'"Show me {entity_label} with {col_name} over 1000"',
                    f'"Find {entity_label} with {col_name} under 10"',
                ]
            })
        
        # ID queries
        elif semantics['is_id'] and not col_name.lower().endswith('_id'):
            categories.append({
                'title': f'Search by {col_label}',
                'queries': [
                    f'"Find {entity_label} with {col_name} 12345"',
                    f'"Show me {entity_label} {col_name} 67890"',
                    f'"Search for {entity_label} {col_name} 11111"',
                    f'"Find {entity_label} {col_name} 99999"',
                ]
            })
    
    return categories

def generate_analytical_queries(table_name: str, columns: List[Dict[str, str]], 
                                relationships: List[Tuple], tables: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate advanced analytical and business intelligence queries"""
    categories = []
    entity_label = get_entity_label(table_name)
    entity_singular = entity_label.rstrip('s') if entity_label.endswith('s') else entity_label
    
    # Detect key columns
    amount_cols = [c for c in columns if detect_column_semantics(c['name'], c['type'])['is_amount'] or 
                   detect_column_semantics(c['name'], c['type'])['is_price'] or
                   detect_column_semantics(c['name'], c['type'])['is_revenue']]
    date_cols = [c for c in columns if detect_column_semantics(c['name'], c['type'])['is_date']]
    status_cols = [c for c in columns if detect_column_semantics(c['name'], c['type'])['is_status']]
    location_cols = [c for c in columns if detect_column_semantics(c['name'], c['type'])['is_location'] or
                     detect_column_semantics(c['name'], c['type'])['is_city'] or
                     detect_column_semantics(c['name'], c['type'])['is_country']]
    
    # Analytics queries - use ALL amount columns, not just first
    if amount_cols:
        # Generate queries for each amount column
        for amount_col in amount_cols:
            amount_label = amount_col['name'].replace("_", " ").title()
            categories.append({
                'title': f'{entity_label} Analytics by {amount_label}',
                'queries': [
                    f'"What\'s the total {amount_label} of all {entity_label}?"',
                    f'"Show me the average {amount_label}"',
                    f'"Find the highest {amount_label} {entity_singular}"',
                    f'"List {entity_label} by {amount_label} count"',
                    f'"Show me total {amount_label} by month"',
                    f'"Find the most popular {entity_singular} by {amount_label}"',
                    f'"List {entity_label} by {amount_label} and location"',
                    f'"Show me {amount_label} trends over time"',
                ]
            })
    
    # Value Analysis (generic term instead of "Revenue") - use ALL amount/date combinations
    if amount_cols and date_cols:
        # Generate queries for each amount/date combination
        for amount_col in amount_cols[:3]:  # Limit to first 3 to avoid too many queries
            for date_col in date_cols[:2]:  # Limit to first 2 date columns
                amount_label = amount_col['name'].replace("_", " ").title()
                date_label = date_col['name'].replace("_", " ").title()
                categories.append({
                    'title': f'{amount_label} Analysis by {date_label}',
                    'queries': [
                        f'"What\'s the total {amount_label} this year?"',
                        f'"Show me {amount_label} by month"',
                        f'"Find {amount_label} by country"',
                        f'"List {amount_label} by category"',
                        f'"Show me {amount_label} from completed {entity_label} only"',
                        f'"Find {amount_label} by city"',
                        f'"List {amount_label} trends over time"',
                        f'"Show me {amount_label} by status"',
                    ]
                })
    
    # Time-Based Analysis - use ALL date columns
    if date_cols:
        for date_col in date_cols[:2]:  # Limit to first 2 to avoid too many queries
            date_label = date_col['name'].replace("_", " ").title()
            categories.append({
                'title': f'Time-Based Analysis by {date_label}',
                'queries': [
                    f'"Show me {entity_label} from this quarter"',
                    f'"Find {entity_label} from last quarter"',
                    f'"List {entity_label} by day of week"',
                    f'"Show me {entity_label} by hour of day"',
                    f'"Find {entity_label} from weekends"',
                    f'"List {entity_label} from weekdays"',
                    f'"Show me {entity_label} from holidays"',
                    f'"Find {entity_label} from business hours"',
                ]
            })
    
    # Geographic Analysis - use ALL location columns
    if location_cols:
        for loc_col in location_cols[:3]:  # Limit to first 3 location columns
            loc_label = loc_col['name'].replace("_", " ").title()
            categories.append({
                'title': f'Geographic Analysis by {loc_label}',
                'queries': [
                    f'"Show me {entity_label} by {loc_label}"',
                    f'"Find {entity_label} by {loc_label} location"',
                    f'"List {entity_label} grouped by {loc_label}"',
                    f'"Show me {entity_label} distribution by {loc_label}"',
                    f'"Find {entity_label} by {loc_label} region"',
                    f'"List {entity_label} by {loc_label} area"',
                    f'"Show me {entity_label} by {loc_label} zone"',
                    f'"Find {entity_label} by geographic {loc_label}"',
                ]
            })
    
    # Status Tracking - use ALL status columns
    if status_cols:
        for status_col in status_cols:
            status_label = status_col['name'].replace("_", " ").title()
            categories.append({
                'title': f'Status Tracking by {status_label}',
                'queries': [
                    f'"Show me all {entity_label} by {status_label}"',
                    f'"Find {entity_label} filtered by {status_label}"',
                    f'"List {entity_label} grouped by {status_label}"',
                    f'"Show me {entity_label} distribution by {status_label}"',
                    f'"Find {entity_label} with specific {status_label}"',
                    f'"List {entity_label} by {status_label} value"',
                    f'"Show me {entity_label} with {status_label} issues"',
                    f'"Find {entity_label} by {status_label} category"',
                ]
            })
    
    # Related Entity Behavior (if relationships exist) - process ALL relationships
    if relationships:
        for foreign_table, foreign_col, local_col in relationships:
            foreign_entity = get_entity_label(foreign_table)
            foreign_entity.rstrip('s') if foreign_entity.endswith('s') else foreign_entity
            categories.append({
                'title': f'{foreign_entity} Behavior',
                'queries': [
                    f'"Show me {foreign_entity} who have multiple {entity_label}"',
                    f'"Find {foreign_entity} with {entity_label} over threshold"',
                    f'"List {foreign_entity} who haven\'t created {entity_label} recently"',
                    f'"Show me {foreign_entity} with pending {entity_label}"',
                    f'"Find {foreign_entity} who cancelled {entity_label}"',
                    f'"List {foreign_entity} by {entity_label} frequency"',
                    f'"Show me {foreign_entity} with high-value {entity_label}"',
                    f'"Find {foreign_entity} who create {entity_label} frequently"',
                ]
            })
    
    # Comparative Analysis - use ALL amount/date combinations
    if amount_cols and date_cols:
        for amount_col in amount_cols[:2]:  # Limit to first 2 to avoid too many queries
            amount_label = amount_col['name'].replace("_", " ").title()
            categories.append({
                'title': f'Comparative Analysis by {amount_label}',
                'queries': [
                    f'"Compare this month\'s {amount_label} to last month"',
                    f'"How do {amount_label} this quarter compare to last quarter?"',
                    f'"Show me year over year {amount_label} comparison"',
                    f'"Compare {amount_label} this week vs last week"',
                    f'"Month over month {amount_label} comparison"',
                    f'"{amount_label} comparison between periods"',
                    f'"{amount_label} growth from last month to this month"',
                ]
            })
    
    # Ranking and Top N queries - use ALL amount columns
    if amount_cols:
        for amount_col in amount_cols[:3]:  # Limit to first 3 to avoid too many queries
            amount_label = amount_col['name'].replace("_", " ").title()
            categories.append({
                'title': f'Ranking and Top N by {amount_label}',
                'queries': [
                    f'"Show me the top 10 {entity_label} by {amount_label}"',
                    f'"Find the highest {amount_label} {entity_singular}"',
                    f'"List top performing {entity_label} by {amount_label}"',
                    f'"Show me bottom 10 {entity_label} by {amount_label}"',
                    f'"Find worst performing {entity_singular} by {amount_label}"',
                    f'"List {entity_label} by {amount_label} percentile"',
                    f'"Show me top 5% of {entity_label} by {amount_label}"',
                    f'"Find {entity_label} in the top quartile by {amount_label}"',
                ]
            })
    
    return categories

def generate_join_queries(tables: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate multi-table join queries based on relationships"""
    categories = []
    
    for table_name, table_info in tables.items():
        relationships = table_info.get('relationships', [])
        if not relationships:
            continue
        
        entity_label = get_entity_label(table_name)
        
        for foreign_table, foreign_col, local_col in relationships:
            foreign_entity = get_entity_label(foreign_table)
            # Generate join queries - generic, no hard-coded literals
            category_title = f'Multi-Table Queries ({entity_label} + {foreign_entity})'
            queries = [
                f'"Show me {entity_label} with {foreign_entity} details"',
                f'"Find {entity_label} by {foreign_entity} name"',
                f'"List {entity_label} for {foreign_entity} by location"',
                f'"Show me {entity_label} over threshold from {foreign_entity} by region"',
                f'"Find {entity_label} by {foreign_entity} with email"',
                f'"List {entity_label} from this month for {foreign_entity} by name"',
                f'"Show me {entity_label} with status pending from {foreign_entity} by location"',
                f'"Find {entity_label} from {foreign_entity} created this year"',
                f'"Show me {entity_label} with {foreign_entity} filtered by date"',
                f'"Find {entity_label} by {foreign_entity} with specific criteria"',
            ]
            
            categories.append({
                'title': category_title,
                'queries': queries
            })

    return categories

async def create_markdown_template(
    generator: QueryGenerator,
    tables: Dict[str, Any],
    domain_name: str = None
) -> str:
    """Create comprehensive markdown template with AI-generated queries"""

    if not domain_name:
        domain_name = " & ".join([t.title() for t in tables.keys()])

    md = f"""# {domain_name} - Test Queries

This document provides test queries for the {domain_name.lower()} database schema. These queries were generated using AI and will be used to generate SQL intent templates for the Intent PostgreSQL retriever.

"""
    
    # Generate queries for each table
    all_query_num = 1
    
    for table_name, table_info in tables.items():
        entity_label = get_entity_label(table_name)
        
        md += f"## {entity_label} Queries\n\n"
        
        # Basic queries using LLM
        logger.info(f"🤖 Generating basic queries for {table_name}...")
        basic_queries = await generator.generate_queries_for_table(
            table_name, table_info, tables, query_type="basic"
        )
        
        if basic_queries:
            md += "### Basic Search and Filter Queries\n"
            for query in basic_queries:
                md += f"{all_query_num}. \"{query}\"\n"
                all_query_num += 1
            md += "\n"
        
        # Analytical queries using LLM
        logger.info(f"🤖 Generating analytical queries for {table_name}...")
        analytical_queries = await generator.generate_queries_for_table(
            table_name, table_info, tables, query_type="analytical"
        )
        
        if analytical_queries:
            md += "### Analytical and Business Intelligence Queries\n"
            for query in analytical_queries:
                md += f"{all_query_num}. \"{query}\"\n"
                all_query_num += 1
            md += "\n"
    
    # Multi-table join queries
    md += "## Complex Queries\n\n"
    md += "### Multi-Table Join Queries\n"
    
    for table_name, table_info in tables.items():
        if 'relationships' in table_info and table_info['relationships']:
            entity_label = get_entity_label(table_name)
            logger.info(f"🤖 Generating join queries for {table_name}...")
            join_queries = await generator.generate_queries_for_table(
                table_name, table_info, tables, query_type="join"
            )
            
            if join_queries:
                md += f"#### {entity_label} Join Queries\n"
                for query in join_queries:
                    md += f"{all_query_num}. \"{query}\"\n"
                    all_query_num += 1
                md += "\n"
    
    return md

async def main():
    parser = argparse.ArgumentParser(description='Create comprehensive test queries template from schema using AI')
    parser.add_argument('--schema', required=True, help='Path to SQL schema file')
    parser.add_argument('--output', default='test_queries.md', help='Output markdown file (default: test_queries.md)')
    parser.add_argument('--domain', help='Domain name for title (default: inferred from tables)')
    parser.add_argument('--config', default='../../config/config.yaml', help='Path to config file')
    parser.add_argument('--provider', help='Inference provider to use (default: from config)')

    args = parser.parse_args()

    # Parse schema
    logger.info(f"📋 Parsing schema: {args.schema}")
    tables = parse_schema(args.schema)

    if not tables:
        logger.error("❌ No tables found in schema file")
        return 1

    logger.info(f"✅ Found {len(tables)} tables: {', '.join(tables.keys())}")
    
    # Count relationships
    total_relationships = sum(len(t.get('relationships', [])) for t in tables.values())
    if total_relationships > 0:
        logger.info(f"🔗 Detected {total_relationships} table relationships")

    # Initialize query generator
    logger.info("🔧 Initializing AI query generator...")
    generator = QueryGenerator(config_path=args.config, provider=args.provider)
    await generator.initialize()

    # Generate markdown using AI
    logger.info("📝 Generating comprehensive query template using AI...")
    markdown = await create_markdown_template(generator, tables, args.domain)

    # Save to file
    output_path = Path(args.output)
    with open(output_path, 'w') as f:
        f.write(markdown)

    # Count generated queries
    query_count = len(re.findall(r'^\d+\.', markdown, re.MULTILINE))

    logger.info(f"✅ Template created: {output_path}")
    logger.info(f"📊 Generated {query_count} query examples using AI")
    logger.info("\n📖 Next steps:")
    logger.info(f"   1. Open {output_path}")
    logger.info("   2. Review and customize the generated queries")
    logger.info("   3. Add domain-specific queries as needed")
    logger.info("   4. Run template generator with this file")
    logger.info("\n💡 The template includes:")
    logger.info("   • Basic search and filter queries (AI-generated)")
    logger.info("   • Advanced analytical queries (AI-generated)")
    logger.info("   • Business intelligence queries (AI-generated)")
    logger.info("   • Multi-table join queries (AI-generated)")

    return 0

if __name__ == '__main__':
    exit(asyncio.run(main()))
