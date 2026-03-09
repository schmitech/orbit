#!/usr/bin/env python3
"""
Dataset Initializer

Scaffold a new dataset in one command: detect schema, generate SQL,
create import_config.yaml, and register the dataset in csv_to_duckdb.yaml.

USAGE:
    python init_dataset.py <csv_file> [options]

EXAMPLES:
    # Scaffold with defaults (name derived from filename)
    python init_dataset.py data.csv

    # Explicit name and description
    python init_dataset.py data.csv --name my-dataset --description "My Dataset"

    # Preview without writing any files
    python init_dataset.py data.csv --name my-dataset --dry-run

    # Scaffold and immediately load the database
    python init_dataset.py data.csv --name my-dataset --load

    # TSV file with custom delimiter
    python init_dataset.py data.tsv --name my-tsv --delimiter '\\t'

    # Override detected types
    python init_dataset.py data.csv --type-override amount=DECIMAL(12,2)
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from generate_schema import (
    _decode_escape_sequence,
    apply_type_overrides,
    detect_csv_schema,
    generate_import_config,
    generate_sql_schema,
    sanitize_table_name,
    suggest_indexes,
    suggest_primary_key,
)


def _to_kebab(name: str) -> str:
    """Convert a filename stem to kebab-case dataset name."""
    stem = Path(name).stem
    # Strip long numeric suffixes (open-data IDs)
    stem = re.sub(r'[_-]\d{10,}$', '', stem)
    # Replace non-alphanumeric runs with hyphens
    stem = re.sub(r'[^a-zA-Z0-9]+', '-', stem)
    return stem.strip('-').lower()


def scaffold_dataset(
    csv_path: Path,
    *,
    dataset_name: str,
    description: str,
    url: Optional[str],
    output_dir: Path,
    config_path: Path,
    table_name: str,
    primary_key: Optional[str],
    no_indexes: bool,
    all_varchar: bool,
    type_overrides: Dict[str, str],
    delimiter: Optional[str],
    quote: Optional[str],
    escape: Optional[str],
    null_values: Optional[List[str]],
    sample_size: int,
    header: bool,
    encoding: Optional[str],
    dry_run: bool,
    quiet: bool,
) -> bool:
    """Run the full scaffold pipeline. Returns True on success."""

    # ------------------------------------------------------------------
    # Step A — Resolve paths
    # ------------------------------------------------------------------
    sql_filename = f"{table_name}.sql"
    config_yaml_filename = "import_config.yaml"
    db_filename = f"{table_name}.duckdb"

    sql_path = output_dir / sql_filename
    import_config_path = output_dir / config_yaml_filename
    db_path = output_dir / db_filename

    if not quiet:
        print(f"Dataset name : {dataset_name}")
        print(f"Table name   : {table_name}")
        print(f"Output dir   : {output_dir}")

    # ------------------------------------------------------------------
    # Step B — Detect schema
    # ------------------------------------------------------------------
    if not quiet:
        print(f"\nAnalyzing: {csv_path}")

    columns = detect_csv_schema(
        str(csv_path),
        all_varchar,
        delimiter,
        quote,
        escape,
        null_values,
        sample_size,
        header,
        encoding,
    )

    if not quiet:
        print(f"Detected {len(columns)} columns")

    # Apply type overrides
    columns, missing_overrides = apply_type_overrides(columns, type_overrides or None)
    if type_overrides and not quiet:
        applied = sorted(set(type_overrides.keys()) - set(missing_overrides))
        if applied:
            print(f"Applied type overrides: {', '.join(applied)}")
    if missing_overrides:
        print(f"Warning: type overrides not applied (columns not found): {', '.join(missing_overrides)}")

    # PK and indexes
    pk = primary_key or suggest_primary_key(columns)
    indexes = [] if no_indexes else suggest_indexes(columns, pk)

    if not quiet:
        if pk:
            print(f"Primary key  : {pk}")
        if indexes:
            print(f"Indexes      : {', '.join(indexes)}")

    # ------------------------------------------------------------------
    # Step C — Generate SQL schema
    # ------------------------------------------------------------------
    sql_content = generate_sql_schema(columns, table_name, pk, indexes)

    if dry_run:
        print(f"\n{'=' * 60}")
        print(f"SQL Schema → {sql_path}")
        print('=' * 60)
        print(sql_content)
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        sql_path.write_text(sql_content)
        if not quiet:
            print(f"\nWrote: {sql_path}")

    # ------------------------------------------------------------------
    # Step D — Generate import_config.yaml
    # ------------------------------------------------------------------
    import_config_content = generate_import_config(
        columns,
        str(csv_path),
        delimiter=delimiter,
        quote=quote,
        escape=escape,
        null_values=null_values,
        sample_size=sample_size,
        encoding=encoding,
    )

    if dry_run:
        print(f"\n{'=' * 60}")
        print(f"Import Config → {import_config_path}")
        print('=' * 60)
        print(import_config_content)
    else:
        import_config_path.write_text(import_config_content)
        if not quiet:
            print(f"Wrote: {import_config_path}")

    # ------------------------------------------------------------------
    # Step E — Register in csv_to_duckdb.yaml
    # ------------------------------------------------------------------
    _register_dataset(
        config_path=config_path,
        dataset_name=dataset_name,
        description=description,
        url=url,
        csv_path=str(csv_path),
        schema_path=str(sql_path),
        output_path=str(db_path),
        import_config_path=str(import_config_path),
        dry_run=dry_run,
        quiet=quiet,
    )

    # ------------------------------------------------------------------
    # Step F — Summary
    # ------------------------------------------------------------------
    if not quiet:
        print(f"\n{'=' * 60}")
        print("  Scaffold complete!")
        print('=' * 60)
        print(f"  SQL schema       : {sql_path}")
        print(f"  Import config    : {import_config_path}")
        print(f"  Master config    : {config_path}")
        print(f"\nNext steps:")
        print(f"  1. Review {sql_path} and {import_config_path}")
        print(f"  2. Run: python generate_duckdbs.py {dataset_name} --clean")

    return True


def _register_dataset(
    *,
    config_path: Path,
    dataset_name: str,
    description: str,
    url: Optional[str],
    csv_path: str,
    schema_path: str,
    output_path: str,
    import_config_path: str,
    dry_run: bool,
    quiet: bool,
) -> None:
    """Append a dataset entry to csv_to_duckdb.yaml (raw text to preserve comments)."""

    url_value = f'"{url}"' if url else 'null'
    entry = (
        f"\n  {dataset_name}:\n"
        f'    description: "{description}"\n'
        f"    url: {url_value}\n"
        f'    csv_path: "{csv_path}"\n'
        f'    schema_path: "{schema_path}"\n'
        f'    output_path: "{output_path}"\n'
        f'    config_path: "{import_config_path}"\n'
    )

    if dry_run:
        print(f"\n{'=' * 60}")
        print(f"Would append to {config_path}:")
        print('=' * 60)
        print(entry)
        return

    # Create the file if it doesn't exist
    if not config_path.exists():
        header = (
            "# =============================================================================\n"
            "# Orbit Adapters Database Configuration\n"
            "# =============================================================================\n"
            "# Generated by init_dataset.py\n"
            "#\n"
            "# Field Reference:\n"
            "#   description:  Human-readable description of the dataset.\n"
            "#   url:          (Optional) URL to download the CSV from. Set to null for local file.\n"
            "#   csv_path:     Local path to the CSV file.\n"
            "#   schema_path:  Path to the SQL file containing CREATE TABLE/INDEX statements.\n"
            "#   output_path:  Path where the resulting DuckDB file will be saved.\n"
            "#   config_path:  (Optional) Path to a YAML import configuration.\n"
            "#   split_size:   (Optional) Split CSVs larger than this (MB) into chunks.\n"
            "# =============================================================================\n"
            "\n"
            "datasets:\n"
        )
        config_path.write_text(header)
        if not quiet:
            print(f"\nCreated: {config_path}")

    # Check for duplicate
    existing = config_path.read_text()
    # Look for the dataset name as a YAML key under datasets
    pattern = re.compile(rf'^\s+{re.escape(dataset_name)}\s*:', re.MULTILINE)
    if pattern.search(existing):
        print(f"Warning: '{dataset_name}' already exists in {config_path} — skipping registration")
        return

    with open(config_path, 'a') as f:
        f.write(entry)

    if not quiet:
        print(f"Registered '{dataset_name}' in {config_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Initialize a new dataset: detect schema, generate configs, register in csv_to_duckdb.yaml',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python init_dataset.py data.csv
  python init_dataset.py data.csv --name my-dataset --description "My Dataset"
  python init_dataset.py data.csv --name my-dataset --dry-run
  python init_dataset.py data.csv --name my-dataset --load
  python init_dataset.py data.tsv --name my-tsv --delimiter '\\t'
  python init_dataset.py data.csv --type-override amount=DECIMAL(12,2)
        """,
    )

    # Positional
    parser.add_argument('csv_file', help='Path to CSV file')

    # Dataset identity
    parser.add_argument('--name', help='Dataset name for csv_to_duckdb.yaml (default: derived from filename, kebab-case)')
    parser.add_argument('--description', default='', help='Human-readable description')
    parser.add_argument('--url', help='Download URL stored in config')

    # Output control
    parser.add_argument('--output-dir', help="Where to write generated files (default: CSV's directory)")
    parser.add_argument('--config', default='csv_to_duckdb.yaml', help='Master config path (default: csv_to_duckdb.yaml)')

    # Schema control
    parser.add_argument('--table', help='Override table name (default: derived from filename)')
    parser.add_argument('--primary-key', help='Override primary key detection')
    parser.add_argument('--no-indexes', action='store_true', help='Skip index suggestions')
    parser.add_argument('--all-varchar', action='store_true', help='Force all columns to VARCHAR')
    parser.add_argument(
        '--type-override', action='append', metavar='COLUMN=TYPE',
        help='Override detected SQL type for a column (repeatable)',
    )

    # CSV parsing
    parser.add_argument('--delimiter', '-d', help='Field delimiter (default: comma)')
    parser.add_argument('--quote', help='Quote character (default: ")')
    parser.add_argument('--escape', help='Escape character')
    parser.add_argument('--null', '-n', action='append', dest='null_values', help='Value treated as NULL (repeatable)')
    parser.add_argument('--sample-size', type=int, default=10000, help='Rows to sample for type detection (default: 10000)')
    parser.add_argument('--no-header', action='store_true', help='CSV has no header row')
    parser.add_argument('--encoding', help='File encoding (default: UTF8)')

    # Modes
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing files')
    parser.add_argument('--load', action='store_true', help='Scaffold and immediately load the database')
    parser.add_argument('--quiet', '-q', action='store_true', help='Minimal output')

    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Validate input
    # ------------------------------------------------------------------
    csv_path = Path(args.csv_file)
    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        sys.exit(1)

    # Decode escape sequences
    delimiter = _decode_escape_sequence(args.delimiter) if args.delimiter else None
    quote = _decode_escape_sequence(args.quote) if args.quote else None
    escape_char = _decode_escape_sequence(args.escape) if args.escape else None
    null_values = [_decode_escape_sequence(v) for v in args.null_values] if args.null_values else None
    header = not args.no_header

    # Parse type overrides
    type_overrides: Dict[str, str] = {}
    if args.type_override:
        for override in args.type_override:
            if '=' not in override:
                print(f"Invalid type override '{override}'. Use COLUMN=TYPE format.")
                sys.exit(1)
            column, dtype = override.split('=', 1)
            column, dtype = column.strip(), dtype.strip()
            if not column or not dtype:
                print(f"Invalid type override '{override}'. Column and type required.")
                sys.exit(1)
            type_overrides[column] = dtype

    # Resolve names
    dataset_name = args.name or _to_kebab(csv_path.name)
    table_name = args.table or sanitize_table_name(csv_path.name)
    output_dir = Path(args.output_dir) if args.output_dir else csv_path.parent
    config_path = Path(args.config)

    # ------------------------------------------------------------------
    # Run scaffold
    # ------------------------------------------------------------------
    try:
        success = scaffold_dataset(
            csv_path,
            dataset_name=dataset_name,
            description=args.description or dataset_name,
            url=args.url,
            output_dir=output_dir,
            config_path=config_path,
            table_name=table_name,
            primary_key=args.primary_key,
            no_indexes=args.no_indexes,
            all_varchar=args.all_varchar,
            type_overrides=type_overrides,
            delimiter=delimiter,
            quote=quote,
            escape=escape_char,
            null_values=null_values,
            sample_size=args.sample_size,
            header=header,
            encoding=args.encoding,
            dry_run=args.dry_run,
            quiet=args.quiet,
        )
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    if not success:
        sys.exit(1)

    # ------------------------------------------------------------------
    # Step G — optional --load
    # ------------------------------------------------------------------
    if args.load and not args.dry_run:
        if not args.quiet:
            print(f"\nLoading database via generate_duckdbs.py {dataset_name} --clean ...")
        cmd = [sys.executable, 'generate_duckdbs.py', dataset_name, '--clean', '--config', str(config_path)]
        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError:
            print("Error: database loading failed")
            sys.exit(1)


if __name__ == '__main__':
    main()
