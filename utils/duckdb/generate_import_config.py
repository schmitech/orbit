#!/usr/bin/env python3
"""
Import Config Generator

Generate an import_config.yaml file by matching a SQL schema against CSV headers.
The resulting config maps each database column to its corresponding CSV header,
enabling csv_to_duckdb.py to load files where headers don't match column names exactly.

USAGE:
    python generate_import_config.py <csv_file> --schema <sql_file> [options]

EXAMPLES:
    # Generate import_config.yaml from CSV + SQL schema
    python generate_import_config.py data.csv --schema schema.sql

    # Preview without writing
    python generate_import_config.py data.csv --schema schema.sql --dry-run

    # Custom output path
    python generate_import_config.py data.csv --schema schema.sql --output my_config.yaml

    # Auto-detect schema from CSV (no SQL file needed)
    python generate_import_config.py data.csv

    # Handle TSV or non-standard delimiters
    python generate_import_config.py data.tsv --schema schema.sql --delimiter '\\t'
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import duckdb
except ImportError:
    print("Error: duckdb required. Install with: pip install duckdb")
    sys.exit(1)

try:
    import yaml
except ImportError:
    print("Error: pyyaml required. Install with: pip install pyyaml")
    sys.exit(1)


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


def _build_csv_options(
    header: bool,
    delimiter: Optional[str],
    quote: Optional[str],
    escape: Optional[str],
    null_values: Optional[List[str]],
    sample_size: Optional[int],
    encoding: Optional[str],
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


def slugify(value: str) -> str:
    """Normalize a column name for fuzzy matching."""
    return re.sub(r'[^a-z0-9]', '', value.lower())


def read_csv_headers(
    csv_path: str,
    *,
    delimiter: Optional[str] = None,
    quote: Optional[str] = None,
    escape: Optional[str] = None,
    null_values: Optional[List[str]] = None,
    sample_size: int = 10000,
    encoding: Optional[str] = None,
) -> List[str]:
    """Read CSV headers using DuckDB auto-detection. Returns original header names."""
    conn = duckdb.connect(':memory:')
    opts = _build_csv_options(True, delimiter, quote, escape, null_values, sample_size, encoding)

    attempts = [
        f"read_csv_auto('{csv_path}', {opts})",
        f"read_csv('{csv_path}', {opts}, ignore_errors=true, auto_detect=true)",
    ]

    errors = []
    for attempt in attempts:
        try:
            result = conn.execute(
                f"SELECT column_name FROM (DESCRIBE SELECT * FROM {attempt})"
            ).fetchall()
            conn.close()
            return [row[0] for row in result]
        except Exception as exc:
            errors.append(str(exc))
            continue

    conn.close()
    raise RuntimeError(
        "Could not read CSV headers:\n  - " + "\n  - ".join(errors)
    )


def parse_sql_schema(sql_path: str) -> List[Tuple[str, str]]:
    """Parse a SQL schema file and return a list of (column_name, column_type) tuples."""
    with open(sql_path, 'r') as f:
        sql_content = f.read()

    create_match = re.search(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*?)\);',
        sql_content,
        re.IGNORECASE | re.DOTALL,
    )
    if not create_match:
        raise RuntimeError(f"No CREATE TABLE statement found in {sql_path}")

    columns_str = create_match.group(2)

    # Split by comma respecting parentheses (for DECIMAL(10,2) etc.)
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

    columns = []
    for part in parts:
        part = part.strip()
        if not part or part.upper().startswith('PRIMARY KEY') or part.upper().startswith('FOREIGN KEY'):
            continue

        col_match = re.match(
            r'"?(\w+)"?\s+'
            r'(\w+(?:\([^)]+\))?'
            r'(?:\s+\w+)*?)',
            part, re.IGNORECASE,
        )
        if col_match:
            columns.append((col_match.group(1), col_match.group(2).strip()))

    return columns


def match_columns(
    schema_columns: List[Tuple[str, str]],
    csv_headers: List[str],
) -> Tuple[Dict[str, str], List[str], List[str]]:
    """Match schema columns to CSV headers using slug-based fuzzy matching.

    Returns:
        mapping: dict of schema_col -> csv_header for matched columns
        unmatched_schema: schema columns with no CSV match
        unmatched_csv: CSV headers with no schema match
    """
    # Build slug -> original header lookup
    csv_slug_map: Dict[str, List[str]] = {}
    for header in csv_headers:
        slug = slugify(header)
        csv_slug_map.setdefault(slug, []).append(header)

    matched_csv: set = set()
    mapping: Dict[str, str] = {}
    unmatched_schema: List[str] = []

    for col_name, _ in schema_columns:
        slug = slugify(col_name)
        candidates = csv_slug_map.get(slug)
        if candidates:
            csv_header = candidates[0]
            mapping[col_name] = csv_header
            matched_csv.add(csv_header)
        else:
            unmatched_schema.append(col_name)

    unmatched_csv = [h for h in csv_headers if h not in matched_csv]

    return mapping, unmatched_schema, unmatched_csv


def generate_yaml(
    mapping: Dict[str, str],
    unmatched_schema: List[str],
    unmatched_csv: List[str],
) -> str:
    """Generate import_config.yaml content."""
    lines = []

    # column_mapping section
    lines.append("column_mapping:")
    for schema_col, csv_header in mapping.items():
        lines.append(f'  {schema_col}: "{csv_header}"')

    # Warn about unmatched schema columns as comments
    if unmatched_schema:
        lines.append("")
        lines.append("# WARNING: The following schema columns had no matching CSV header.")
        lines.append("# Add manual mappings or derived_columns expressions for them:")
        for col in unmatched_schema:
            lines.append(f"#   {col}: ???")

    # Show unmatched CSV headers as comments for reference
    if unmatched_csv:
        lines.append("")
        lines.append("# NOTE: The following CSV headers were not matched to any schema column:")
        for header in unmatched_csv:
            lines.append(f"#   - {header}")

    # Add derived_columns example
    lines.append("")
    lines.append("# Optional: Define columns using raw SQL expressions")
    lines.append("# derived_columns:")
    lines.append('#   year_extracted: \'YEAR(CAST("Date_Column" AS DATE))\'')

    lines.append("")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Generate import_config.yaml by matching SQL schema columns to CSV headers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_import_config.py data.csv --schema schema.sql
  python generate_import_config.py data.csv --schema schema.sql --dry-run
  python generate_import_config.py data.csv --schema schema.sql --output config.yaml
  python generate_import_config.py data.csv
  python generate_import_config.py data.tsv --schema schema.sql --delimiter '\\t'
        """,
    )

    parser.add_argument('csv_file', help='Path to the CSV file')
    parser.add_argument('--schema', '-s', help='SQL schema file (CREATE TABLE statements)')
    parser.add_argument(
        '--output', '-o',
        help='Output YAML file path (default: import_config.yaml next to CSV)',
    )
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing files')
    parser.add_argument('--delimiter', '-d', help='Field delimiter (default: comma)')
    parser.add_argument('--quote', help='Quote character (default: ")')
    parser.add_argument('--escape', help='Escape character (default: \\)')
    parser.add_argument(
        '--null', '-n', action='append', dest='null_values',
        help='Value treated as NULL (repeatable)',
    )
    parser.add_argument(
        '--sample-size', type=int, default=10000,
        help='Rows to sample for CSV detection (default: 10000)',
    )
    parser.add_argument('--encoding', help='File encoding hint (e.g., latin-1)')
    parser.add_argument('--quiet', '-q', action='store_true', help='Minimal output')

    args = parser.parse_args()

    csv_path = Path(args.csv_file)
    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        sys.exit(1)

    delimiter = _decode_escape_sequence(args.delimiter) if args.delimiter else None
    quote = _decode_escape_sequence(args.quote) if args.quote else None
    escape_char = _decode_escape_sequence(args.escape) if args.escape else None
    null_values = (
        [_decode_escape_sequence(v) for v in args.null_values]
        if args.null_values
        else None
    )

    # Read CSV headers
    if not args.quiet:
        print(f"Reading CSV headers from: {csv_path}")

    csv_headers = read_csv_headers(
        str(csv_path),
        delimiter=delimiter,
        quote=quote,
        escape=escape_char,
        null_values=null_values,
        sample_size=args.sample_size,
        encoding=args.encoding,
    )

    if not args.quiet:
        print(f"  Found {len(csv_headers)} CSV columns")

    # Get schema columns
    if args.schema:
        schema_path = Path(args.schema)
        if not schema_path.exists():
            print(f"Error: Schema file not found: {schema_path}")
            sys.exit(1)

        if not args.quiet:
            print(f"Reading schema from: {schema_path}")

        schema_columns = parse_sql_schema(str(schema_path))

        if not args.quiet:
            print(f"  Found {len(schema_columns)} schema columns")
    else:
        # No SQL schema: generate identity mapping from normalized names to CSV headers
        if not args.quiet:
            print("No schema file provided — generating mapping from normalized column names")

        schema_columns = []
        for header in csv_headers:
            normalized = re.sub(r'[^a-zA-Z0-9_]', '_', header)
            normalized = re.sub(r'_+', '_', normalized).strip('_').lower()
            schema_columns.append((normalized, 'VARCHAR'))

    # Match columns
    mapping, unmatched_schema, unmatched_csv = match_columns(schema_columns, csv_headers)

    if not args.quiet:
        print(f"\nMatched: {len(mapping)} columns")
        if unmatched_schema:
            print(f"Unmatched schema columns: {', '.join(unmatched_schema)}")
        if unmatched_csv:
            print(f"Unmatched CSV headers: {', '.join(unmatched_csv)}")

    # Generate YAML
    yaml_content = generate_yaml(mapping, unmatched_schema, unmatched_csv)

    if args.dry_run:
        print("\n" + "=" * 60)
        print("import_config.yaml (dry run):")
        print("=" * 60)
        print(yaml_content)
        sys.exit(0)

    output_path = Path(args.output) if args.output else csv_path.parent / "import_config.yaml"

    with open(output_path, 'w') as f:
        f.write(yaml_content)

    if not args.quiet:
        print(f"\nGenerated: {output_path}")


if __name__ == '__main__':
    main()
