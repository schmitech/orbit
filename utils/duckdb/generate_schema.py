#!/usr/bin/env python3
"""
Schema Generator Utility

Auto-generate DuckDB SQL schema from CSV files.

USAGE:
    python generate_schema.py <csv_file> [options]

EXAMPLES:
    # Generate schema with auto-detected types
    python generate_schema.py data.csv

    # Specify output file and table name
    python generate_schema.py data.csv --output schema.sql --table my_table

    # Also generate import_config.yaml
    python generate_schema.py data.csv --config

    # Preview without writing files
    python generate_schema.py data.csv --dry-run

    # Force all columns to VARCHAR (safest)
    python generate_schema.py data.csv --all-varchar

    # Control CSV parsing behavior
    python generate_schema.py data.tsv --delimiter '\\t' --quote '"' --null '' --encoding latin-1

    # Override specific column types
    python generate_schema.py data.csv --type-override amount=DECIMAL(12,2) --type-override created_at=TIMESTAMP
"""

import argparse
import sys
import re
from pathlib import Path
from typing import List, Tuple, Optional, Set, Dict
from datetime import datetime

try:
    import duckdb
except ImportError:
    print("Error: duckdb required. Install with: pip install duckdb")
    sys.exit(1)

try:
    import yaml
except ImportError:
    yaml = None


# Common patterns for index suggestions
INDEX_PATTERNS = {
    'date': ['date', 'created', 'updated', 'timestamp', 'time', '_at$', '_on$'],
    'id': ['_id$', '^id$', 'uuid', 'guid', 'ref', 'number', 'code'],
    'category': ['type', 'status', 'category', 'class', 'kind', 'level', 'tier'],
    'location': ['city', 'province', 'state', 'country', 'region', 'division', 'district', 'neighbourhood', 'zone'],
    'name': ['name', 'title', 'label', 'vendor', 'organization', 'company', 'department'],
    'year': ['^year$', '_year$', 'fiscal_year', 'occ_year', 'report_year'],
}

# Patterns for primary key detection
PK_PATTERNS = [
    r'^id$',
    r'_id$',
    r'^pk$',
    r'^uuid$',
    r'^guid$',
    r'reference_number',
    r'unique_id',
    r'event_unique_id',
]

RESERVED_TABLE_NAMES: Set[str] = {
    'table', 'view', 'index', 'select', 'from', 'where', 'group', 'order',
    'limit', 'offset', 'join', 'inner', 'left', 'right', 'full', 'on', 'using',
}


def _sql_literal(value: str) -> str:
    """Escape a value for interpolation into SQL strings."""
    return "'" + value.replace("'", "''") + "'"


def _decode_escape_sequence(value: str) -> str:
    """Convert common escape sequence inputs to literal characters."""
    escape_map = {
        r'\t': '\t',
        r'\n': '\n',
        r'\r': '\r',
        r'\0': '\0',
        r'\\': '\\',
    }
    return escape_map.get(value, value)


def _build_csv_options(
    header: bool,
    delimiter: Optional[str],
    quote: Optional[str],
    escape: Optional[str],
    null_values: Optional[List[str]],
    sample_size: Optional[int],
    encoding: Optional[str],
) -> str:
    options = [f"header={'true' if header else 'false'}"]

    if delimiter:
        options.append(f"delim={_sql_literal(delimiter)}")
    if quote:
        options.append(f"quote={_sql_literal(quote)}")
    if escape:
        options.append(f"escape={_sql_literal(escape)}")
    if null_values:
        null_literals = ", ".join(_sql_literal(v) for v in null_values)
        options.append(f"nullstr=[{null_literals}]")
    if sample_size and sample_size > 0:
        options.append(f"sample_size={sample_size}")
    if encoding:
        options.append(f"encoding={_sql_literal(encoding)}")

    return ", ".join(options)


def detect_csv_schema(
    csv_path: str,
    all_varchar: bool = False,
    delimiter: Optional[str] = None,
    quote: Optional[str] = None,
    escape: Optional[str] = None,
    null_values: Optional[List[str]] = None,
    sample_size: Optional[int] = 10000,
    header: bool = True,
    encoding: Optional[str] = None,
) -> List[Tuple[str, str]]:
    """Detect CSV schema using DuckDB's auto-detection."""
    conn = duckdb.connect(':memory:')

    options = _build_csv_options(header, delimiter, quote, escape, null_values, sample_size, encoding)

    attempts = []

    if all_varchar:
        attempts.append((
            'forced VARCHAR',
            f"read_csv('{csv_path}', {options}, all_varchar=true)"
        ))
    else:
        attempts.extend([
            (
                'read_csv_auto',
                f"read_csv_auto('{csv_path}', {options})"
            ),
            (
                'read_csv auto_detect',
                f"read_csv('{csv_path}', {options}, ignore_errors=true, auto_detect=true)"
            ),
            (
                'read_csv all_varchar',
                f"read_csv('{csv_path}', {options}, ignore_errors=true, all_varchar=true)"
            ),
        ])

    errors = []
    for label, attempt in attempts:
        try:
            query = f"SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM {attempt})"
            result = conn.execute(query).fetchall()
            conn.close()
            return result
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}: {exc}")
            continue

    conn.close()
    error_message = "Could not detect CSV schema"
    if errors:
        joined = "\n  - " + "\n  - ".join(errors)
        error_message += f":{joined}"
    raise RuntimeError(error_message)


def suggest_primary_key(columns: List[Tuple[str, str]]) -> Optional[str]:
    """Suggest a primary key based on column names."""
    col_names = [col[0].lower() for col in columns]

    for pattern in PK_PATTERNS:
        for i, name in enumerate(col_names):
            if re.search(pattern, name, re.IGNORECASE):
                return columns[i][0]

    return None


def suggest_indexes(columns: List[Tuple[str, str]], primary_key: Optional[str] = None) -> List[str]:
    """Suggest columns to index based on naming patterns."""
    suggestions = set()

    for col_name, col_type in columns:
        # Skip primary key (already indexed)
        if primary_key and col_name.lower() == primary_key.lower():
            continue

        col_lower = col_name.lower()

        # Check against patterns
        for category, patterns in INDEX_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, col_lower, re.IGNORECASE):
                    suggestions.add(col_name)
                    break

        # Also suggest DATE/TIMESTAMP columns
        if 'DATE' in col_type.upper() or 'TIMESTAMP' in col_type.upper():
            suggestions.add(col_name)

    return sorted(suggestions)


def apply_type_overrides(
    columns: List[Tuple[str, str]],
    overrides: Optional[Dict[str, str]] = None,
) -> Tuple[List[Tuple[str, str]], List[str]]:
    """Apply user-provided column type overrides."""
    if not overrides:
        return columns, []

    lowered = {name.lower(): dtype for name, dtype in overrides.items()}
    matched: Set[str] = set()
    updated_columns: List[Tuple[str, str]] = []

    for col_name, col_type in columns:
        override = lowered.get(col_name.lower())
        if override:
            matched.add(col_name.lower())
            updated_columns.append((col_name, override))
        else:
            updated_columns.append((col_name, col_type))

    missing = [orig for orig in overrides if orig.lower() not in matched]
    return updated_columns, missing


def sanitize_table_name(name: str) -> str:
    """Convert filename to valid SQL table name."""
    # Remove extension and common suffixes
    name = Path(name).stem
    for suffix in ['_download', '_data', '_export', '_open_data', 'q']:
        if name.lower().endswith(suffix):
            name = name[:-len(suffix)]

    # Replace invalid characters
    name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    name = re.sub(r'_+', '_', name)  # Collapse multiple underscores
    name = name.strip('_').lower()

    if not name:
        name = 'imported_table'
    if name[0].isdigit():
        name = f"t_{name}"
    if name in RESERVED_TABLE_NAMES:
        name = f"{name}_table"

    return name


def generate_sql_schema(
    columns: List[Tuple[str, str]],
    table_name: str,
    primary_key: Optional[str] = None,
    indexes: Optional[List[str]] = None
) -> str:
    """Generate CREATE TABLE and CREATE INDEX SQL."""
    lines = []

    # Header comment
    lines.append(f"-- Schema for {table_name}")
    lines.append(f"-- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # CREATE TABLE
    lines.append(f"CREATE TABLE IF NOT EXISTS {table_name} (")

    col_defs = []
    for col_name, col_type in columns:
        # Quote column names with special characters
        quoted_name = f'"{col_name}"' if not col_name.isidentifier() else col_name

        if primary_key and col_name.lower() == primary_key.lower():
            col_defs.append(f"    {quoted_name} {col_type} PRIMARY KEY")
        else:
            col_defs.append(f"    {quoted_name} {col_type}")

    lines.append(",\n".join(col_defs))
    lines.append(");")
    lines.append("")

    # CREATE INDEX statements
    if indexes:
        lines.append("-- Indexes for common query patterns")
        for col in indexes:
            quoted_col = f'"{col}"' if not col.isidentifier() else col
            index_name = f"idx_{table_name}_{col.lower().replace(' ', '_')}"
            lines.append(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}({quoted_col});")

    return "\n".join(lines)


def generate_import_config(
    columns: List[Tuple[str, str]],
    table_name: str,
    primary_key: Optional[str] = None,
    indexes: Optional[List[str]] = None
) -> str:
    """Generate import_config.yaml content."""
    config = {
        'table_name': table_name,
    }

    if primary_key:
        config['primary_key'] = primary_key

    if indexes:
        config['indexes'] = indexes

    # Add commented examples for column_mapping and derived_columns
    yaml_content = yaml.dump(config, default_flow_style=False, sort_keys=False)

    yaml_content += """
# Optional: Map database columns to CSV headers if they differ
# column_mapping:
#   db_column_name: "CSV Header Name"

# Optional: Define columns using SQL expressions
# derived_columns:
#   year: 'YEAR(CAST("date_column" AS DATE))'
#   clean_pct: 'CAST(REPLACE("pct_column", ''%'', '''') AS DECIMAL(5,2))'

# Optional: Skip columns from the CSV
# skip_columns:
#   - unwanted_column

# Optional: Override auto-detected types
# type_overrides:
#   some_column: VARCHAR

# Optional: Custom delimiter for TSV or semicolon-separated files
# delimiter: "\\t"
"""

    return yaml_content


def preview_schema(columns: List[Tuple[str, str]], primary_key: Optional[str], indexes: List[str]):
    """Print schema preview to console."""
    print("\nDetected Schema:")
    print("-" * 60)

    for col_name, col_type in columns:
        markers = []
        if primary_key and col_name.lower() == primary_key.lower():
            markers.append("PK")
        if col_name in indexes:
            markers.append("IDX")

        marker_str = f" [{', '.join(markers)}]" if markers else ""
        print(f"  {col_name}: {col_type}{marker_str}")

    print("-" * 60)
    print(f"Total: {len(columns)} columns")
    if primary_key:
        print(f"Primary Key: {primary_key}")
    if indexes:
        print(f"Suggested Indexes: {', '.join(indexes)}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate DuckDB SQL schema from CSV files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_schema.py data.csv
  python generate_schema.py data.csv --output schema.sql --table my_table
  python generate_schema.py data.csv --config --dry-run
  python generate_schema.py data.csv --all-varchar
  python generate_schema.py data.tsv --delimiter '\\t'
  python generate_schema.py data.csv --null '' --sample-size 50000
  python generate_schema.py data.csv --type-override amount=DECIMAL(12,2)
        """
    )

    parser.add_argument(
        'csv_file',
        help='Path to CSV file to analyze'
    )

    parser.add_argument(
        '--output', '-o',
        help='Output SQL file path (default: <table_name>.sql)'
    )

    parser.add_argument(
        '--table', '-t',
        help='Table name (default: derived from filename)'
    )

    parser.add_argument(
        '--primary-key', '-pk',
        help='Primary key column (default: auto-detect)'
    )

    parser.add_argument(
        '--no-indexes',
        action='store_true',
        help='Skip index suggestions'
    )

    parser.add_argument(
        '--config', '-c',
        action='store_true',
        help='Also generate import_config.yaml'
    )

    parser.add_argument(
        '--all-varchar',
        action='store_true',
        help='Force all columns to VARCHAR type'
    )

    parser.add_argument(
        '--delimiter', '-d',
        help='Field delimiter (default: comma)'
    )

    parser.add_argument(
        '--quote',
        help='Quote character (default: ")'
    )

    parser.add_argument(
        '--escape',
        help='Escape character (default: \\)'
    )

    parser.add_argument(
        '--null', '-n',
        action='append',
        dest='null_values',
        help='Value treated as NULL (repeatable)'
    )

    parser.add_argument(
        '--sample-size',
        type=int,
        default=10000,
        help='Rows to sample for type detection (default: 10000)'
    )

    parser.add_argument(
        '--no-header',
        action='store_true',
        help='CSV has no header row'
    )

    parser.add_argument(
        '--encoding',
        help='File encoding passed to DuckDB (default: UTF8)'
    )

    parser.add_argument(
        '--type-override',
        action='append',
        metavar='COLUMN=TYPE',
        help='Override detected SQL type for a column (repeatable)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview schema without writing files'
    )

    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Minimal output'
    )

    args = parser.parse_args()

    # Validate input
    csv_path = Path(args.csv_file)
    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        sys.exit(1)

    delimiter = _decode_escape_sequence(args.delimiter) if args.delimiter else None
    quote = _decode_escape_sequence(args.quote) if args.quote else None
    escape_char = _decode_escape_sequence(args.escape) if args.escape else None
    null_values = [_decode_escape_sequence(v) for v in args.null_values] if args.null_values else None
    header = not args.no_header

    type_overrides: Dict[str, str] = {}
    if args.type_override:
        for override in args.type_override:
            if '=' not in override:
                print(f"Invalid type override '{override}'. Use COLUMN=TYPE format.")
                sys.exit(1)
            column, dtype = override.split('=', 1)
            column = column.strip()
            dtype = dtype.strip()
            if not column or not dtype:
                print(f"Invalid type override '{override}'. Column and type required.")
                sys.exit(1)
            type_overrides[column] = dtype

    if not args.quiet:
        print(f"Analyzing: {csv_path}")

    # Detect schema
    try:
        columns = detect_csv_schema(
            str(csv_path),
            args.all_varchar,
            delimiter,
            quote,
            escape_char,
            null_values,
            args.sample_size,
            header,
            args.encoding,
        )
    except Exception as e:
        print(f"Error detecting schema: {e}")
        sys.exit(1)

    if not args.quiet:
        print(f"Detected {len(columns)} columns")

    columns, missing_overrides = apply_type_overrides(columns, type_overrides or None)
    if type_overrides and not args.quiet:
        applied = sorted(set(type_overrides.keys()) - set(missing_overrides))
        if applied:
            print(f"Applied type overrides for: {', '.join(applied)}")
    if missing_overrides:
        print(f"Warning: type overrides not applied (columns not found): {', '.join(missing_overrides)}")

    # Determine table name
    table_name = args.table or sanitize_table_name(csv_path.name)

    # Detect or use specified primary key
    primary_key = args.primary_key or suggest_primary_key(columns)

    # Suggest indexes
    indexes = [] if args.no_indexes else suggest_indexes(columns, primary_key)

    # Preview
    if not args.quiet or args.dry_run:
        preview_schema(columns, primary_key, indexes)

    if args.dry_run:
        print("\n[Dry run - no files written]")

        # Show what would be generated
        print("\n" + "=" * 60)
        print("SQL Schema (would be written):")
        print("=" * 60)
        sql_content = generate_sql_schema(columns, table_name, primary_key, indexes)
        print(sql_content)

        if args.config:
            if yaml is None:
                print("\nWarning: pyyaml not installed, cannot generate config")
            else:
                print("\n" + "=" * 60)
                print("Import Config (would be written):")
                print("=" * 60)
                config_content = generate_import_config(columns, table_name, primary_key, indexes)
                print(config_content)

        sys.exit(0)

    # Generate and write SQL schema
    sql_content = generate_sql_schema(columns, table_name, primary_key, indexes)
    sql_path = Path(args.output) if args.output else csv_path.parent / f"{table_name}.sql"

    with open(sql_path, 'w') as f:
        f.write(sql_content)

    if not args.quiet:
        print(f"\nGenerated: {sql_path}")

    # Generate import config if requested
    if args.config:
        if yaml is None:
            print("Warning: pyyaml not installed, cannot generate config")
        else:
            config_content = generate_import_config(columns, table_name, primary_key, indexes)
            config_path = csv_path.parent / "import_config.yaml"

            with open(config_path, 'w') as f:
                f.write(config_content)

            if not args.quiet:
                print(f"Generated: {config_path}")

    # Print next steps
    if not args.quiet:
        print("\nNext steps:")
        print(f"  1. Review and adjust: {sql_path}")
        print("  2. Add to csv_to_duckdb.yaml")
        print(f"  3. Run: python generate_duckdbs.py {table_name} --clean")


if __name__ == '__main__':
    main()
