# Orbit Adapters Database Generation

This project uses a configuration-driven approach to generate DuckDB databases from CSV files. This allows for flexible column mapping, custom SQL transformations, and automated downloading of datasets.

## Quick Start

The main entry point is the `generate_duckdbs.py` script.

**Generate a single dataset:**
```bash
python generate_duckdbs.py my-sample-csv --clean
```

**Generate all datasets:**
```bash
python generate_duckdbs.py all --clean
```

## Configuration (`csv_to_duckdb.yaml`)

The master configuration file `csv_to_duckdb.yaml` defines all available datasets.

```yaml
datasets:
  my-sample-csv:
    description: "My Sample CSV"
    url: null
    csv_path: "example.csv"
    schema_path: "example-csv-schema.sql"
    output_path: "example.duckdb"

  another-csv:
    description: "My other CSV"
    url: "https://example.com/example.csv"
    csv_path: "another-example.csv"
    schema_path: "anpther-example-csv-schema.sql"
    output_path: "another-example.duckdb"
```

## Import Configuration (`import_config.yaml`)

For datasets where CSV headers don't match database columns exactly, or where data transformation is needed (e.g., parsing dates, removing '%', calculating years), you can create a per-dataset YAML config.

**Example `import_config.yaml`:**

```yaml
# Map specific database columns (key) to CSV headers (value)
column_mapping:
  target_column1: "CSV_Header1"
  target_column2: "CSV_Header2"
  target_column3: "CSV_Header3"

# Define columns using raw SQL expressions
# This is useful for parsing dates, extracting years, or cleaning data on the fly
derived_columns:
  # Example: Cast string date to SQL Date and extract Year
  year_extracted: 'YEAR(CAST("CSV_Header1" AS DATE))'

  # Example: Remove '%' and cast to Decimal
  percent_clean: 'CAST(REPLACE("CSV_Header2", ''%'', '''') AS DECIMAL(5,2))'

# Optional: Custom delimiter for non-CSV files (TSV, semicolon-separated, etc.)
# delimiter: "\t"      # Tab-separated (TSV)
# delimiter: ";"       # Semicolon-separated (common in European datasets)

# Optional: File encoding (auto-detected by default)
# encoding: "utf-8"    # Explicit UTF-8
# encoding: "latin-1"  # ISO-8859-1 / Latin-1

# Optional: Control table name derivation from filename
# strip_suffixes: []              # Disable suffix stripping
# strip_suffixes: ["_export"]     # Custom suffixes to remove
```

### Advanced CSV parsing

`generate_schema.py` and `csv_to_duckdb.py` now expose DuckDB CSV reader knobs so messy files are easier to ingest:

- `--delimiter`, `--quote`, and `--escape` align with uncommon separators and quoting rules.
- `--null` (repeatable) declares additional NULL markers, such as empty strings or `NA` tokens.
- `--sample-size` adjusts how many rows DuckDB inspects when inferring column types.
- `--no-header` plus `--encoding` handle headerless or non-UTF-8 datasets.
- The same keys can be set in per-dataset YAML configs when you prefer not to pass CLI flags.

## Large CSV Support (Auto-Split)

For very large CSV files (e.g. 450 MB+), the loader can automatically split the file into chunks before importing. This provides per-chunk progress, resilience (if one chunk has issues the rest still loads), and reduced memory pressure.

**CLI usage:**
```bash
# Auto-split files >100 MB into 50 MB chunks
python csv_to_duckdb.py huge.csv --auto-split --schema huge.sql --output huge.duckdb

# Custom chunk size (split into 25 MB chunks)
python csv_to_duckdb.py huge.csv --split-size 25 --schema huge.sql --output huge.duckdb
```

**Per-dataset config** (`csv_to_duckdb.yaml`):
```yaml
datasets:
  large-dataset:
    description: "Large dataset"
    csv_path: "huge.csv"
    schema_path: "huge.sql"
    output_path: "huge.duckdb"
    split_size: 50  # MB — auto-split if CSV exceeds this
```

If the CSV is smaller than the split size, it loads normally in a single pass.

## How It Works

1.  **`generate_duckdbs.py`**: Reads `csv_to_duckdb.yaml`.
2.  **Dataset Selection**: Identifies the target dataset(s).
3.  **Command Construction**: Builds a command to call `csv_to_duckdb.py`, passing arguments like `--schema`, `--output`, `--url`, and optionally `--config`.
4.  **`csv_to_duckdb.py`**:
    *   Creates the database and table using the SQL schema.
    *   Reads the CSV (downloading first if a URL is provided).
    *   Uses the `import_config.yaml` (if provided) to map columns or apply transformations.
    *   Loads data efficiently into DuckDB.
