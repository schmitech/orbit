#!/usr/bin/env python3
"""
Template Testing Utility

Test SQL templates against DuckDB databases before deployment.

USAGE:
    python test_template.py --template <yaml_file> --id <template_id> [options]

EXAMPLES:
    # Test a specific template with default parameters
    python test_template.py --template my-templates.yaml --id yearly_trends

    # Test with custom parameter values
    python test_template.py --template my-templates.yaml --id thefts_by_month --param year=2023

    # List all templates in a file
    python test_template.py --template my-templates.yaml --list

    # Test all templates in a file
    python test_template.py --template my-templates.yaml --all

    # Specify database explicitly
    python test_template.py --template my-templates.yaml --id template-id --db example.duckdb
"""

import argparse
import sys
import re
from pathlib import Path
from typing import Optional, Dict, Any, List

try:
    import yaml
except ImportError:
    print("Error: pyyaml required. Install with: pip install pyyaml")
    sys.exit(1)

try:
    import duckdb
except ImportError:
    print("Error: duckdb required. Install with: pip install duckdb")
    sys.exit(1)


def load_templates(yaml_path: str) -> Dict[str, Any]:
    """Load templates from YAML file."""
    with open(yaml_path, 'r') as f:
        return yaml.safe_load(f)


def find_template(data: Dict, template_id: str) -> Optional[Dict]:
    """Find a template by ID."""
    templates = data.get('templates', [])
    for template in templates:
        if template.get('id') == template_id:
            return template
    return None


def list_templates(data: Dict) -> List[Dict]:
    """List all templates with their IDs and descriptions."""
    return data.get('templates', [])


def find_database(yaml_path: str, template: Dict, explicit_db: Optional[str] = None) -> Optional[str]:
    """Find the DuckDB file for a template.

    Search order:
    1. Explicit --db argument
    2. Look for .duckdb files in same directory as template
    3. Check csv_to_duckdb.yaml for matching dataset
    """
    if explicit_db:
        return explicit_db

    template_dir = Path(yaml_path).parent

    # Look for .duckdb files in same directory
    duckdb_files = list(template_dir.glob("*.duckdb"))
    if len(duckdb_files) == 1:
        return str(duckdb_files[0])

    # Try to match based on primary_entity from semantic_tags
    primary_entity = template.get('semantic_tags', {}).get('primary_entity')
    if primary_entity and duckdb_files:
        for db_file in duckdb_files:
            if primary_entity.replace('_', '-') in db_file.stem or primary_entity in db_file.stem:
                return str(db_file)

    # Check master config
    config_path = Path(yaml_path).parent.parent / "csv_to_duckdb.yaml"
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        datasets = config.get('datasets', {})
        for name, dataset in datasets.items():
            output_path = dataset.get('output_path', '')
            if template_dir.name in output_path:
                return output_path

    # Return first duckdb if multiple found
    if duckdb_files:
        return str(duckdb_files[0])

    return None


def substitute_parameters(sql: str, template: Dict, param_overrides: Dict[str, str]) -> str:
    """Substitute :param placeholders with values."""
    parameters = template.get('parameters', [])

    # Build parameter values from defaults and overrides
    param_values = {}
    for param in parameters:
        name = param['name']
        param_type = param.get('type', 'string')

        if name in param_overrides:
            value = param_overrides[name]
        elif 'default' in param:
            value = param['default']
        elif param.get('required', False):
            raise ValueError(f"Required parameter '{name}' not provided and has no default")
        else:
            value = None

        if value is not None:
            # Convert to appropriate type for SQL
            if param_type == 'integer':
                param_values[name] = int(value)
            elif param_type == 'string':
                param_values[name] = f"'{value}'"
            else:
                param_values[name] = value

    # Substitute parameters in SQL
    result = sql
    for name, value in param_values.items():
        result = re.sub(rf':({name})\b', str(value), result)

    return result


def run_query(db_path: str, sql: str, limit: int = 10) -> tuple:
    """Execute query and return results."""
    conn = duckdb.connect(db_path, read_only=True)
    try:
        result = conn.execute(sql).fetchall()
        columns = [desc[0] for desc in conn.description]
        return columns, result[:limit], len(result)
    finally:
        conn.close()


def format_table(columns: List[str], rows: List[tuple], max_width: int = 25) -> str:
    """Format results as a table."""
    if not rows:
        return "  (no results)"

    # Calculate column widths
    widths = [min(max(len(str(col)), max(len(str(row[i])) for row in rows)), max_width)
              for i, col in enumerate(columns)]

    # Build table
    lines = []

    # Header
    header = " | ".join(str(col)[:max_width].ljust(widths[i]) for i, col in enumerate(columns))
    lines.append(header)
    lines.append("-" * len(header))

    # Rows
    for row in rows:
        line = " | ".join(str(val)[:max_width].ljust(widths[i]) for i, val in enumerate(row))
        lines.append(line)

    return "\n".join(lines)


def test_template(
    yaml_path: str,
    template_id: str,
    db_path: Optional[str] = None,
    param_overrides: Optional[Dict[str, str]] = None,
    limit: int = 10,
    verbose: bool = False
) -> bool:
    """Test a single template. Returns True if successful."""
    param_overrides = param_overrides or {}

    # Load template
    data = load_templates(yaml_path)
    template = find_template(data, template_id)

    if not template:
        print(f"Error: Template '{template_id}' not found")
        return False

    # Find database
    db_path = find_database(yaml_path, template, db_path)
    if not db_path or not Path(db_path).exists():
        print("Error: Could not find DuckDB file. Use --db to specify.")
        return False

    print(f"Template: {template_id}")
    print(f"Database: {db_path}")
    print(f"Description: {template.get('description', 'N/A')}")

    # Show parameters
    params = template.get('parameters', [])
    if params:
        print("Parameters:")
        for p in params:
            default = p.get('default', 'N/A')
            override = param_overrides.get(p['name'])
            value = override if override else default
            marker = " (override)" if override else ""
            print(f"  - {p['name']}: {value}{marker}")

    # Substitute parameters
    sql = template.get('sql', '')
    try:
        final_sql = substitute_parameters(sql, template, param_overrides)
    except ValueError as e:
        print(f"Error: {e}")
        return False

    if verbose:
        print("\nSQL:")
        print(f"  {final_sql.strip()}")

    # Execute query
    print("\nExecuting...")
    try:
        columns, rows, total = run_query(db_path, final_sql, limit)
        print(f"Results ({total} total, showing {len(rows)}):\n")
        print(format_table(columns, rows))
        print()
        return True
    except Exception as e:
        print(f"Error executing query: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


def test_all_templates(
    yaml_path: str,
    db_path: Optional[str] = None,
    limit: int = 5
) -> tuple:
    """Test all templates in a file. Returns (passed, failed) counts."""
    data = load_templates(yaml_path)
    templates = list_templates(data)

    passed = 0
    failed = 0
    failures = []

    print(f"Testing {len(templates)} templates from {yaml_path}\n")
    print("=" * 60)

    for template in templates:
        template_id = template.get('id', 'unknown')
        print(f"\n[{template_id}] ", end="")

        try:
            # Find database
            found_db = find_database(yaml_path, template, db_path)
            if not found_db or not Path(found_db).exists():
                print("SKIP (no database)")
                continue

            # Substitute with defaults
            sql = template.get('sql', '')
            final_sql = substitute_parameters(sql, template, {})

            # Execute
            conn = duckdb.connect(found_db, read_only=True)
            result = conn.execute(final_sql).fetchall()
            conn.close()

            print(f"PASS ({len(result)} rows)")
            passed += 1

        except Exception as e:
            print(f"FAIL: {e}")
            failed += 1
            failures.append((template_id, str(e)))

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")

    if failures:
        print("\nFailed templates:")
        for tid, err in failures:
            print(f"  - {tid}: {err}")

    return passed, failed


def main():
    parser = argparse.ArgumentParser(
        description='Test SQL templates against DuckDB databases',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_template.py --template my-templates.yaml --id yearly_trends
  python test_template.py --template my-templates.yaml --id trends_by_month --param year=2026
  python test_template.py --template my-templates.yaml --list
  python test_template.py --template my-templates.yaml --all
        """
    )

    parser.add_argument(
        '--template', '-t',
        required=True,
        help='Path to template YAML file'
    )

    parser.add_argument(
        '--id', '-i',
        help='Template ID to test'
    )

    parser.add_argument(
        '--db', '-d',
        help='Path to DuckDB file (auto-detected if not specified)'
    )

    parser.add_argument(
        '--param', '-p',
        action='append',
        default=[],
        help='Parameter override in format name=value (can be repeated)'
    )

    parser.add_argument(
        '--list', '-l',
        action='store_true',
        help='List all templates in the file'
    )

    parser.add_argument(
        '--all', '-a',
        action='store_true',
        help='Test all templates in the file'
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=10,
        help='Maximum rows to display (default: 10)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show SQL and detailed errors'
    )

    args = parser.parse_args()

    # Validate template file exists
    if not Path(args.template).exists():
        print(f"Error: Template file not found: {args.template}")
        sys.exit(1)

    # Parse parameter overrides
    param_overrides = {}
    for p in args.param:
        if '=' not in p:
            print(f"Error: Invalid parameter format '{p}'. Use name=value")
            sys.exit(1)
        name, value = p.split('=', 1)
        param_overrides[name] = value

    # List templates
    if args.list:
        data = load_templates(args.template)
        templates = list_templates(data)
        print(f"Templates in {args.template}:\n")
        for t in templates:
            params = t.get('parameters', [])
            param_str = ", ".join(p['name'] for p in params) if params else "(none)"
            print(f"  {t['id']}")
            print(f"    Description: {t.get('description', 'N/A')}")
            print(f"    Parameters: {param_str}")
            print()
        print(f"Total: {len(templates)} templates")
        sys.exit(0)

    # Test all templates
    if args.all:
        passed, failed = test_all_templates(args.template, args.db, args.limit)
        sys.exit(0 if failed == 0 else 1)

    # Test single template
    if not args.id:
        print("Error: Either --id, --list, or --all is required")
        sys.exit(1)

    success = test_template(
        args.template,
        args.id,
        args.db,
        param_overrides,
        args.limit,
        args.verbose
    )

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
