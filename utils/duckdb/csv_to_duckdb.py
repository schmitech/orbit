#!/usr/bin/env python3
"""
Universal CSV to DuckDB Loader

DESCRIPTION:
    A fast, universal tool to load any CSV file into a DuckDB database using
    DuckDB's native CSV reader. Automatically detects schema or uses an existing
    SQL schema file for precise type definitions.

USAGE:
    python csv_to_duckdb.py <csv_file> [options]

ARGUMENTS:
    csv_file              Path to the CSV file to load
    --output FILE         Output DuckDB database file (default: <csv_name>.duckdb)
    --table NAME          Table name (default: derived from CSV filename or SQL)
    --schema FILE         SQL schema file (CREATE TABLE + CREATE INDEX statements)
    --config FILE         Optional YAML config for schema customization
    --clean               Drop existing table before loading
    --primary-key COL     Column to use as primary key
    --url URL             Download CSV from URL instead of local file
    --show-schema         Show detected schema and exit without loading
    --indexes COL1,COL2   Comma-separated columns to index
    --delimiter CHAR      Field delimiter (default: comma)
    --quote CHAR          Quote character (default: ")
    --escape CHAR         Escape character (default: \\)
    --null VALUE          Treat value as NULL (repeatable)
    --sample-size N       Rows to sample for detection (default: 10000)
    --no-header           CSV has no header row
    --encoding NAME       File encoding hint (e.g., latin-1)

EXAMPLES:
    # Basic usage - auto-detect everything
    python csv_to_duckdb.py data.csv

    # Use existing SQL schema file (recommended)
    python csv_to_duckdb.py travelq.csv --schema travel_expenses.sql --output travel.duckdb

    # Specify output and table name
    python csv_to_duckdb.py travelq.csv --output travel.duckdb --table travel_expenses

    # With primary key and indexes
    python csv_to_duckdb.py contracts.csv --primary-key reference_number --indexes contract_date,vendor_name

    # Download from URL
    python csv_to_duckdb.py --url https://example.com/data.csv --output data.duckdb

    # Use config file for advanced customization
    python csv_to_duckdb.py data.csv --config schema.yaml

SQL SCHEMA FILE FORMAT:
    CREATE TABLE my_table (
        id VARCHAR PRIMARY KEY,
        name VARCHAR,
        amount DECIMAL(10,2),
        created_date DATE
    );
    CREATE INDEX idx_name ON my_table(name);
    CREATE INDEX idx_date ON my_table(created_date);

CONFIG FILE FORMAT (YAML):
    table_name: my_table
    primary_key: id_column
    indexes:
      - date_column
      - name_column
    type_overrides:
      date_column: DATE
      amount_column: DECIMAL(15,2)
    skip_columns:
      - unwanted_column

    # CSV reader options
    delimiter: "\t"
    quote: '"'
    escape: '\\'
    null_values:
      - ""
      - "NA"
    header: true
    sample_size: 20000
    encoding: latin-1

REQUIREMENTS:
    pip install duckdb requests pyyaml

AUTHOR:
    Universal CSV to DuckDB Loader v1.0.0
"""

import duckdb
import argparse
import sys
import time
import re
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Set

try:
    import requests
except ImportError:
    requests = None

try:
    import yaml
except ImportError:
    yaml = None


RESERVED_TABLE_NAMES: Set[str] = {
    'table', 'view', 'index', 'select', 'from', 'where', 'group', 'order',
    'limit', 'offset', 'join', 'inner', 'left', 'right', 'full', 'on', 'using',
}


def _sql_literal(value: str) -> str:
    """Escape a Python string for embedding in DuckDB SQL."""
    return "'" + value.replace("'", "''") + "'"


def _decode_escape_sequence(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    escape_map = {
        r'\t': '\t',
        r'\n': '\n',
        r'\r': '\r',
        r'\0': '\0',
        r'\\': '\\',
    }
    return escape_map.get(value, value)


def _build_csv_base_args(
    header: bool,
    delimiter: Optional[str],
    quote: Optional[str],
    escape: Optional[str],
    null_values: Optional[List[str]],
    sample_size: Optional[int] = None,
    encoding: Optional[str] = None,
) -> str:
    parts = [f"header={'true' if header else 'false'}"]

    if delimiter:
        parts.append(f"delim={_sql_literal(delimiter)}")
    if quote:
        parts.append(f"quote={_sql_literal(quote)}")
    if escape:
        parts.append(f"escape={_sql_literal(escape)}")
    if null_values:
        literals = ", ".join(_sql_literal(v) for v in null_values)
        parts.append(f"nullstr=[{literals}]")
    if sample_size and sample_size > 0:
        parts.append(f"sample_size={sample_size}")
    if encoding:
        parts.append(f"encoding={_sql_literal(encoding)}")

    return ", ".join(parts)


def sanitize_table_name(name: str) -> str:
    base = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    base = re.sub(r'_+', '_', base).strip('_').lower()
    if not base:
        base = 'imported_table'
    if base[0].isdigit():
        base = f"t_{base}"
    if base in RESERVED_TABLE_NAMES:
        base = f"{base}_table"
    return base


def slugify_column(value: str) -> str:
    return re.sub(r'[^a-z0-9]', '', value.lower())


def _coerce_bool(value: Optional[object], default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return bool(value)

def parse_sql_schema(sql_path: str) -> Dict:
    """
    Parse a SQL schema file to extract table name, columns, types, primary key, and indexes.

    Returns dict with:
        - table_name: str
        - columns: list of (name, type) tuples
        - primary_key: str or None
        - indexes: list of column names
        - create_table_sql: the original CREATE TABLE statement
        - create_index_sqls: list of CREATE INDEX statements
    """
    with open(sql_path, 'r') as f:
        sql_content = f.read()

    result = {
        'table_name': None,
        'columns': [],
        'primary_key': None,
        'indexes': [],
        'create_table_sql': None,
        'create_index_sqls': []
    }

    # Extract CREATE TABLE statement
    create_table_match = re.search(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*?)\);',
        sql_content,
        re.IGNORECASE | re.DOTALL
    )

    if create_table_match:
        result['table_name'] = create_table_match.group(1)
        result['create_table_sql'] = create_table_match.group(0)
        columns_str = create_table_match.group(2)

        # Parse column definitions
        # Split by comma but not inside parentheses (for DECIMAL(10,2) etc)
        depth = 0
        current = ""
        parts = []
        for char in columns_str:
            if char == '(':
                depth += 1
                current += char
            elif char == ')':
                depth -= 1
                current += char
            elif char == ',' and depth == 0:
                parts.append(current.strip())
                current = ""
            else:
                current += char
        if current.strip():
            parts.append(current.strip())

        for part in parts:
            part = part.strip()
            if not part or part.upper().startswith('PRIMARY KEY') or part.upper().startswith('FOREIGN KEY'):
                continue

            # Parse column: name type [PRIMARY KEY] [other constraints]
            # Supports: VARCHAR, DECIMAL(10,2), DOUBLE PRECISION, TIMESTAMP WITH TIME ZONE, etc.
            # Pattern: column_name + type (with optional parentheses) + optional additional type words + constraints
            col_match = re.match(
                r'"?(\w+)"?\s+'                           # Column name (optionally quoted)
                r'(\w+(?:\([^)]+\))?'                     # Base type with optional params: VARCHAR, DECIMAL(10,2)
                r'(?:\s+\w+)*?)'                          # Additional type words: DOUBLE PRECISION, WITH TIME ZONE
                r'(?:\s+((?:PRIMARY\s+KEY|NOT\s+NULL|UNIQUE|DEFAULT\s+\S+|REFERENCES\s+\S+).*))?$',  # Constraints
                part, re.IGNORECASE
            )
            if col_match:
                col_name = col_match.group(1)
                col_type = col_match.group(2).strip()
                constraints = col_match.group(3).upper() if col_match.group(3) else ""

                result['columns'].append((col_name, col_type))

                if 'PRIMARY KEY' in constraints:
                    result['primary_key'] = col_name

    # Extract CREATE INDEX statements (supports composite indexes)
    index_pattern = re.compile(
        r'CREATE\s+INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+ON\s+(\w+)\s*\(([^)]+)\)',
        re.IGNORECASE
    )

    for match in index_pattern.finditer(sql_content):
        index_name = match.group(1)
        table_name = match.group(2)
        columns_str = match.group(3)
        # Parse comma-separated column names (handles composite indexes)
        for col in columns_str.split(','):
            col = col.strip().strip('"').strip("'")
            if col:
                result['indexes'].append(col)
        result['create_index_sqls'].append(match.group(0))

    return result


def download_csv(url: str, output_path: str, timeout: int = 120) -> bool:
    """Download CSV file from URL with progress indicator."""
    if requests is None:
        print("Error: requests library required for URL downloads")
        print("   Install with: pip install requests")
        return False

    print(f"Downloading CSV from: {url}")

    try:
        response = requests.get(url, timeout=timeout, stream=True)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0

        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"\r   Progress: {percent:.1f}% ({downloaded:,} / {total_size:,} bytes)", end='', flush=True)

        print()
        print(f"Downloaded {downloaded:,} bytes to {output_path}")
        return True

    except Exception as e:
        print(f"Error downloading CSV: {e}")
        return False


def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    if yaml is None:
        print("Error: pyyaml library required for config files")
        print("   Install with: pip install pyyaml")
        sys.exit(1)

    with open(config_path, 'r') as f:
        return yaml.safe_load(f) or {}


def get_csv_schema(
    conn: duckdb.DuckDBPyConnection,
    csv_path: str,
    *,
    header: bool = True,
    delimiter: Optional[str] = None,
    quote: Optional[str] = None,
    escape: Optional[str] = None,
    null_values: Optional[List[str]] = None,
    sample_size: int = 10000,
    encoding: Optional[str] = None,
) -> list:
    """Detect CSV schema using DuckDB's auto-detection with fallback options."""

    base_args = _build_csv_base_args(header, delimiter, quote, escape, null_values, sample_size, encoding)
    attempts = [
        (
            'read_csv_auto',
            f"read_csv_auto('{csv_path}', {base_args})"
        ),
        (
            'read_csv_auto lenient',
            f"read_csv_auto('{csv_path}', {base_args}, ignore_errors=true)"
        ),
        (
            'read_csv auto_detect',
            f"read_csv('{csv_path}', {base_args}, ignore_errors=true, auto_detect=true, max_line_size=10000000, strict_mode=false)"
        ),
        (
            'read_csv all_varchar',
            f"read_csv('{csv_path}', {base_args}, ignore_errors=true, all_varchar=true, max_line_size=10000000, strict_mode=false)"
        ),
    ]

    errors = []
    for label, attempt in attempts:
        try:
            result = conn.execute(f"""
                SELECT column_name, column_type
                FROM (DESCRIBE SELECT * FROM {attempt})
            """).fetchall()
            return result
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}: {exc}")
            continue

    error_message = "Could not detect CSV schema"
    if errors:
        error_message += "\n  - " + "\n  - ".join(errors)
    raise RuntimeError(error_message)


def derive_table_name(csv_path: str, strip_suffixes: Optional[list] = None) -> str:
    """Derive table name from CSV filename.

    Args:
        csv_path: Path to the CSV file
        strip_suffixes: Optional list of suffixes to remove from the name.
                       If None, uses default list: ['_download', '_data', '_export', 'q']
                       Pass empty list [] to disable suffix stripping.
    """
    name = Path(csv_path).stem

    # Use default suffixes if not specified
    if strip_suffixes is None:
        strip_suffixes = ['_download', '_data', '_export', 'q']

    # Clean up configured suffixes
    for suffix in strip_suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]

    name = name.replace('-', '_')
    return sanitize_table_name(name)


def create_table_sql(
    table_name: str,
    schema: list,
    primary_key: Optional[str] = None,
    type_overrides: Optional[dict] = None,
    skip_columns: Optional[list] = None
) -> str:
    """Generate CREATE TABLE SQL from detected schema."""
    type_overrides = type_overrides or {}
    skip_columns = skip_columns or []

    columns = []
    for col_name, col_type in schema:
        if col_name in skip_columns:
            continue

        # Apply type override if specified
        final_type = type_overrides.get(col_name, col_type)

        # Add PRIMARY KEY constraint if this is the primary key column
        if primary_key and col_name == primary_key:
            columns.append(f'    "{col_name}" {final_type} PRIMARY KEY')
        else:
            columns.append(f'    "{col_name}" {final_type}')

    columns_sql = ',\n'.join(columns)
    return f'CREATE TABLE IF NOT EXISTS "{table_name}" (\n{columns_sql}\n)'


def create_indexes(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    index_columns: list,
    schema: list
) -> int:
    """Create indexes on specified columns."""
    schema_cols = {col[0] for col in schema}
    created = 0

    for col in index_columns:
        if col not in schema_cols:
            print(f"   Warning: Index column '{col}' not found in schema, skipping")
            continue

        safe_col = re.sub(r'[^a-zA-Z0-9_]', '_', col.lower()) or 'col'
        index_name = f"idx_{table_name}_{safe_col}"
        try:
            conn.execute(f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{table_name}"("{col}")')
            created += 1
        except Exception as e:
            print(f"   Warning: Could not create index on '{col}': {e}")

    return created


def load_csv_fast(
    conn: duckdb.DuckDBPyConnection,
    csv_path: str,
    table_name: str,
    schema: list,
    primary_key: Optional[str] = None,
    skip_columns: Optional[list] = None,
    config: Optional[dict] = None,
    *,
    header: bool = True,
    delimiter: Optional[str] = None,
    quote: Optional[str] = None,
    escape: Optional[str] = None,
    null_values: Optional[List[str]] = None,
    encoding: Optional[str] = None,
    sample_size: int = 10000,
    quiet: bool = False,
) -> int:
    """Load CSV using DuckDB's native reader (fast!)."""

    skip_columns = skip_columns or []
    config = config or {}
    column_mapping = config.get('column_mapping', {})
    derived_columns = config.get('derived_columns', {})

    try:
        csv_info = get_csv_schema(
            conn,
            csv_path,
            header=header,
            delimiter=delimiter,
            quote=quote,
            escape=escape,
            null_values=null_values,
            sample_size=sample_size,
            encoding=encoding,
        )
    except Exception as exc:  # noqa: BLE001
        if not quiet:
            print(f"   Warning: Could not pre-detect CSV schema for column alignment: {exc}")
        csv_info = schema

    csv_cols_map: Dict[str, List[str]] = {}
    csv_name_lookup: Dict[str, str] = {}
    for col_name, _ in csv_info:
        slug = slugify_column(col_name)
        csv_cols_map.setdefault(slug, [])
        if col_name not in csv_cols_map[slug]:
            csv_cols_map[slug].append(col_name)
        csv_name_lookup.setdefault(col_name.lower(), col_name)

    duplicate_slugs = {slug: names for slug, names in csv_cols_map.items() if len(names) > 1}
    if duplicate_slugs and not quiet:
        for slug, names in duplicate_slugs.items():
            print(f"   Warning: Multiple CSV columns look like '{slug}': {', '.join(names)} (first match will be used)")

    insert_cols: List[str] = []
    select_exprs: List[str] = []
    missing_columns: List[str] = []
    mapping_missing: List[str] = []

    for col_name, _ in schema:
        if col_name in skip_columns:
            continue

        if col_name in derived_columns:
            insert_cols.append(f'"{col_name}"')
            select_exprs.append(derived_columns[col_name])
            continue

        if col_name in column_mapping:
            mapped = column_mapping[col_name]
            lookup = csv_name_lookup.get(mapped.lower()) if isinstance(mapped, str) else None
            csv_name = lookup or mapped
            if lookup is None and not quiet:
                mapping_missing.append(mapped)
            insert_cols.append(f'"{col_name}"')
            select_exprs.append(f'"{csv_name}"')
            continue

        slug_name = slugify_column(col_name)
        candidates = csv_cols_map.get(slug_name)

        if candidates:
            csv_name = candidates[0]
            insert_cols.append(f'"{col_name}"')
            select_exprs.append(f'"{csv_name}"')
        elif primary_key and col_name == primary_key:
            insert_cols.append(f'"{col_name}"')
            select_exprs.append('row_number() OVER ()')
        else:
            missing_columns.append(col_name)

    if mapping_missing and not quiet:
        print(f"   Warning: Configured column mappings not found in CSV headers: {', '.join(sorted(set(mapping_missing)))}")

    if missing_columns and not quiet:
        print(f"   Warning: Columns missing from CSV and skipped: {', '.join(sorted(set(missing_columns)))}")

    if not insert_cols:
        raise RuntimeError("No matching columns found between schema and CSV")

    columns_sql_insert = ', '.join(insert_cols)
    columns_sql_select = ', '.join(select_exprs)

    start_time = time.time()
    if not quiet:
        print("   Using DuckDB native CSV reader (fast mode)...")

    where_clause = ""
    pk_slug = slugify_column(primary_key) if primary_key else None
    pk_in_csv = pk_slug and pk_slug in csv_cols_map
    if pk_in_csv:
        csv_pk_name = csv_cols_map[pk_slug][0]
        where_clause = f'WHERE "{csv_pk_name}" IS NOT NULL'

    insert_type = "INSERT OR REPLACE" if primary_key else "INSERT"
    base_args = _build_csv_base_args(header, delimiter, quote, escape, null_values, None, encoding)
    read_attempts = [
        (
            'read_csv_auto',
            f"read_csv_auto('{csv_path}', {base_args}, ignore_errors=true, auto_detect=true)"
        ),
        (
            'read_csv auto_detect',
            f"read_csv('{csv_path}', {base_args}, ignore_errors=true, auto_detect=true, max_line_size=10000000, strict_mode=false)"
        ),
        (
            'read_csv all_varchar',
            f"read_csv('{csv_path}', {base_args}, ignore_errors=true, all_varchar=true, max_line_size=10000000, strict_mode=false)"
        ),
    ]

    errors = []
    for label, read_sql in read_attempts:
        try:
            conn.execute(f"""
                {insert_type} INTO "{table_name}" ({columns_sql_insert})
                SELECT {columns_sql_select}
                FROM {read_sql}
                {where_clause}
            """)
            break
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}: {exc}")
            continue
    else:
        error_message = "Unable to load CSV with DuckDB"
        if errors:
            error_message += "\n  - " + "\n  - ".join(errors)
        raise RuntimeError(error_message)

    elapsed = time.time() - start_time

    # Get count
    result = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()
    count = result[0] if result else 0

    rate = count / elapsed if elapsed > 0 else 0
    print(f"   Completed in {elapsed:.2f}s ({rate:,.0f} records/sec)")

    return count


def print_sample_data(conn: duckdb.DuckDBPyConnection, table_name: str, limit: int = 5):
    """Print sample records from the table."""
    print(f"\nSample Data (first {limit} rows):")
    print("-" * 100)

    # Get column names
    schema = conn.execute(f'DESCRIBE "{table_name}"').fetchall()
    col_names = [col[0] for col in schema[:6]]  # Show first 6 columns max

    # Fetch sample data
    cols_sql = ', '.join(f'"{c}"' for c in col_names)
    result = conn.execute(f'SELECT {cols_sql} FROM "{table_name}" LIMIT {limit}').fetchall()

    if result:
        # Print header
        header = ' | '.join(f'{c[:18]:<18}' for c in col_names)
        print(header)
        print("-" * 100)

        # Print rows
        for row in result:
            values = []
            for val in row:
                if val is None:
                    values.append('NULL')
                else:
                    s = str(val)[:18]
                    values.append(f'{s:<18}')
            print(' | '.join(values))

        print("-" * 100)


def print_stats(conn: duckdb.DuckDBPyConnection, table_name: str, verbose: bool = False):
    """Print basic statistics about the loaded data."""
    result = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()
    total = result[0] if result else 0

    print(f"\nDatabase Statistics:")
    print(f"   Total Records: {total:,}")

    # Get schema info
    schema = conn.execute(f'DESCRIBE "{table_name}"').fetchall()
    print(f"   Total Columns: {len(schema)}")

    # Find numeric columns and show stats
    for row in schema:
        col_name, col_type = row[0], row[1]
        if 'DECIMAL' in col_type or 'DOUBLE' in col_type or 'INTEGER' in col_type or 'BIGINT' in col_type:
            try:
                result = conn.execute(f'''
                    SELECT MIN("{col_name}"), MAX("{col_name}"), AVG("{col_name}")
                    FROM "{table_name}"
                    WHERE "{col_name}" IS NOT NULL
                ''').fetchone()
                if result and result[0] is not None:
                    print(f"   {col_name}: min={result[0]:,.2f}, max={result[1]:,.2f}, avg={result[2]:,.2f}")
            except Exception as e:
                if verbose:
                    print(f"   {col_name}: (stats unavailable: {e})")

    # Find date columns and show range
    for row in schema:
        col_name, col_type = row[0], row[1]
        if 'DATE' in col_type or 'TIMESTAMP' in col_type:
            try:
                result = conn.execute(f'''
                    SELECT MIN("{col_name}"), MAX("{col_name}")
                    FROM "{table_name}"
                    WHERE "{col_name}" IS NOT NULL
                ''').fetchone()
                if result and result[0] is not None:
                    print(f"   {col_name}: {result[0]} to {result[1]}")
            except Exception as e:
                if verbose:
                    print(f"   {col_name}: (range unavailable: {e})")


def main():
    parser = argparse.ArgumentParser(
        description='Universal CSV to DuckDB loader with fast native import',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python csv_to_duckdb.py data.csv
  python csv_to_duckdb.py data.csv --output my_db.duckdb --table my_table
  python csv_to_duckdb.py data.csv --primary-key id --indexes date,name
  python csv_to_duckdb.py --url https://example.com/data.csv
  python csv_to_duckdb.py data.tsv --delimiter '\\t' --encoding latin-1 --null ""
        """
    )

    parser.add_argument(
        'csv_file',
        nargs='?',
        help='Path to CSV file to load'
    )

    parser.add_argument(
        '--output', '-o',
        type=str,
        help='Output DuckDB database file (default: <csv_name>.duckdb)'
    )

    parser.add_argument(
        '--table', '-t',
        type=str,
        help='Table name (default: derived from CSV filename)'
    )

    parser.add_argument(
        '--schema', '-s',
        type=str,
        help='SQL schema file with CREATE TABLE and CREATE INDEX statements'
    )

    parser.add_argument(
        '--config', '-c',
        type=str,
        help='YAML config file for schema customization'
    )

    parser.add_argument(
        '--clean',
        action='store_true',
        help='Drop existing table before loading'
    )

    parser.add_argument(
        '--primary-key', '-pk',
        type=str,
        help='Column to use as primary key'
    )

    parser.add_argument(
        '--indexes', '-i',
        type=str,
        help='Comma-separated columns to index'
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
        default=None,
        help='Rows to sample for auto-detection (default: 10000)'
    )

    parser.add_argument(
        '--no-header',
        action='store_true',
        help='CSV has no header row'
    )

    parser.add_argument(
        '--encoding',
        help='Encoding hint (default: UTF-8)'
    )

    parser.add_argument(
        '--url',
        type=str,
        help='Download CSV from URL'
    )

    parser.add_argument(
        '--show-schema',
        action='store_true',
        help='Show detected schema and exit'
    )

    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Minimal output'
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.csv_file and not args.url:
        parser.error("Either csv_file or --url is required")

    # Load SQL schema if provided
    sql_schema = None
    if args.schema:
        if not Path(args.schema).exists():
            print(f"Error: Schema file not found: {args.schema}")
            return 1
        sql_schema = parse_sql_schema(args.schema)

    # Load config if provided
    config = {}
    if args.config:
        config = load_config(args.config)

    # Determine CSV path
    if args.url:
        if args.csv_file:
            csv_path = Path(args.csv_file)
        else:
            csv_filename = Path(args.url).name or 'download.csv'
            csv_path = Path.cwd() / csv_filename
            
        if not csv_path.exists() or args.clean:
            # Create parent directories if they don't exist
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            if not download_csv(args.url, str(csv_path)):
                return 1
        else:
            print(f"Using existing CSV: {csv_path}")
    else:
        csv_path = Path(args.csv_file)
        if not csv_path.exists():
            print(f"Error: CSV file not found: {csv_path}")
            return 1

    # Determine table name (priority: CLI arg > SQL schema > YAML config > derive from filename)
    strip_suffixes = config.get('strip_suffixes')  # None = use defaults, [] = disable
    table_name = (
        args.table or
        (sql_schema['table_name'] if sql_schema else None) or
        config.get('table_name') or
        derive_table_name(str(csv_path), strip_suffixes)
    )

    # Determine output path
    output_path = args.output or config.get('output') or f"{table_name}.duckdb"

    # Determine primary key (priority: CLI arg > SQL schema > YAML config)
    primary_key = (
        args.primary_key or
        (sql_schema['primary_key'] if sql_schema else None) or
        config.get('primary_key')
    )

    # Determine indexes (priority: CLI arg > SQL schema > YAML config)
    index_columns = []
    if args.indexes:
        index_columns = [c.strip() for c in args.indexes.split(',')]
    elif sql_schema and sql_schema['indexes']:
        index_columns = sql_schema['indexes']
    elif config.get('indexes'):
        index_columns = config.get('indexes')

    # Get type overrides and skip columns from config
    type_overrides = config.get('type_overrides', {})
    skip_columns = config.get('skip_columns', [])

    # CSV reader options (CLI overrides config)
    delimiter_value = args.delimiter if args.delimiter is not None else config.get('delimiter')
    quote_value = args.quote if args.quote is not None else config.get('quote')
    escape_value = args.escape if args.escape is not None else config.get('escape')
    null_values_value = args.null_values if args.null_values else config.get('null_values')
    encoding_value = args.encoding if args.encoding is not None else config.get('encoding')
    header_config = config.get('header')
    if args.no_header:
        header = False
    else:
        header = _coerce_bool(header_config, True)

    delimiter = _decode_escape_sequence(delimiter_value) if delimiter_value else None
    quote = _decode_escape_sequence(quote_value) if quote_value else None
    escape_char = _decode_escape_sequence(escape_value) if escape_value else None
    null_values = None
    if null_values_value:
        if isinstance(null_values_value, (str, int)):
            raw_values = [str(null_values_value)]
        else:
            raw_values = [str(v) for v in null_values_value]
        null_values = [_decode_escape_sequence(v) for v in raw_values]
    encoding = encoding_value

    sample_size = args.sample_size if args.sample_size is not None else config.get('sample_size', 10000)

    csv_options_display = []
    if delimiter:
        csv_options_display.append(f"delimiter={repr(delimiter) if delimiter == '\t' else delimiter}")
    if quote:
        csv_options_display.append(f"quote={quote}")
    if escape_char:
        csv_options_display.append(f"escape={escape_char}")
    if null_values:
        csv_options_display.append(f"nulls={null_values}")
    csv_options_display.append(f"header={'Yes' if header else 'No'}")
    csv_options_display.append(f"sample_size={sample_size}")
    if encoding:
        csv_options_display.append(f"encoding={encoding}")

    # If SQL schema provided, build type_overrides from it
    if sql_schema and sql_schema['columns']:
        for col_name, col_type in sql_schema['columns']:
            if col_name not in type_overrides:
                type_overrides[col_name] = col_type

    if not args.quiet:
        print("=" * 60)
        print("  CSV to DuckDB Loader")
        print("=" * 60)
        print(f"Configuration:")
        print(f"   CSV File: {csv_path}")
        print(f"   Output: {output_path}")
        print(f"   Table: {table_name}")
        if args.schema:
            print(f"   Schema: {args.schema} ({len(sql_schema['columns'])} columns)")
        if primary_key:
            print(f"   Primary Key: {primary_key}")
        if index_columns:
            print(f"   Indexes: {', '.join(index_columns)}")
        if csv_options_display:
            print(f"   CSV Options: {', '.join(csv_options_display)}")
        print(f"   Clean mode: {'Yes' if args.clean else 'No'}")
        print()

    # Connect to DuckDB
    conn = duckdb.connect(output_path)

    # Get schema (from SQL file or auto-detect from CSV)
    if sql_schema and sql_schema['columns']:
        if not args.quiet:
            print(f"Using schema from: {args.schema}")
        schema = sql_schema['columns']
    else:
        if not args.quiet:
            print("Auto-detecting schema from CSV...")
        schema = get_csv_schema(
            conn,
            str(csv_path),
            header=header,
            delimiter=delimiter,
            quote=quote,
            escape=escape_char,
            null_values=null_values,
            sample_size=sample_size,
            encoding=encoding,
        )

    if args.show_schema:
        print("\nDetected Schema:")
        print("-" * 50)
        for col_name, col_type in schema:
            pk_marker = " (PK)" if col_name == primary_key else ""
            print(f"   {col_name}: {col_type}{pk_marker}")
        print("-" * 50)
        conn.close()
        return 0

    # Clean if requested
    if args.clean:
        conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        if not args.quiet:
            print("Cleaned existing table")

    # Create table
    if not args.quiet:
        print("Creating table...")
    create_sql = create_table_sql(table_name, schema, primary_key, type_overrides, skip_columns)
    conn.execute(create_sql)

    # Create indexes
    if index_columns:
        if not args.quiet:
            print("Creating indexes...")
        created = create_indexes(conn, table_name, index_columns, schema)
        if not args.quiet:
            print(f"   Created {created} indexes")

    # Load data
    if not args.quiet:
        print("Loading data...")
    count = load_csv_fast(
        conn,
        str(csv_path),
        table_name,
        schema,
        primary_key,
        skip_columns,
        config,
        header=header,
        delimiter=delimiter,
        quote=quote,
        escape=escape_char,
        null_values=null_values,
        encoding=encoding,
        sample_size=sample_size,
        quiet=args.quiet,
    )
    if not args.quiet:
        print(f"Loaded {count:,} records")

    # Show sample and stats
    if not args.quiet:
        print_sample_data(conn, table_name)
        print_stats(conn, table_name)

    conn.close()

    if not args.quiet:
        print(f"\nDatabase created: {output_path}")
        print(f"\nTest with:")
        print(f'   duckdb {output_path} \'SELECT * FROM "{table_name}" LIMIT 5;\'')

    return 0


if __name__ == '__main__':
    sys.exit(main())
