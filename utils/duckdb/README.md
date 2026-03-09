# Orbit Adapters Database Generation

This project uses a configuration-driven approach to generate DuckDB databases from CSV files. This allows for flexible column mapping, custom SQL transformations, and automated downloading of datasets.

## Quick Setup

The fastest way to go from a raw CSV to a loaded DuckDB database is `init_dataset.py`. It detects the schema, generates SQL and import config, and registers the dataset — all in one command.

```bash
# 1. Scaffold everything (SQL schema, import_config.yaml, csv_to_duckdb.yaml entry)
python init_dataset.py data.csv --name my-dataset --description "My Dataset"

# 2. Review the generated files, then load
python generate_duckdbs.py my-dataset --clean

# Or do both in one shot:
python init_dataset.py data.csv --name my-dataset --load
```

Preview what would be generated without writing files:
```bash
python init_dataset.py data.csv --name my-dataset --dry-run
```

### Common options

| Flag | Purpose |
|------|---------|
| `--name` | Dataset name for `csv_to_duckdb.yaml` (default: derived from filename) |
| `--description` | Human-readable description |
| `--table` | Override SQL table name |
| `--primary-key` | Override PK auto-detection |
| `--all-varchar` | Force all columns to VARCHAR |
| `--type-override COL=TYPE` | Override detected type (repeatable) |
| `--delimiter`, `--quote`, `--escape` | CSV parsing control |
| `--dry-run` | Preview without writing |
| `--load` | Scaffold + load immediately |

## Generate All Datasets

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

## Per-Script Usage

The steps below show the individual scripts that `init_dataset.py` automates. Use these when you need finer control.

### 1. Generate the SQL schema and import config

```bash
# Generate schema.sql + import_config.yaml with real column mappings
python generate_schema.py data.csv --config

# Schema only (no import config)
python generate_schema.py data.csv --output data_schema.sql --table my_table

# Preview without writing
python generate_schema.py data.csv --config --dry-run
```

The `--config` flag reads CSV headers and uses slug-based matching to produce a `column_mapping` section in `import_config.yaml`. Columns that can't be matched are flagged as comments.

To regenerate just the import config against an existing (possibly hand-edited) SQL schema, use `generate_import_config.py`:

```bash
python generate_import_config.py data.csv --schema data_schema.sql
python generate_import_config.py data.csv --schema data_schema.sql --dry-run
```

### 2. Review and adjust

Edit the generated `data_schema.sql` and `import_config.yaml` as needed:
- Fix any unmatched columns (e.g., `id: "OBJECTID"` when the names differ completely).
- Add `derived_columns` for computed values.
- Adjust column types in the SQL schema.

### 3. Register the dataset

Add an entry to `csv_to_duckdb.yaml`:

```yaml
datasets:
  my-dataset:
    description: "My Dataset"
    url: null
    csv_path: "data.csv"
    schema_path: "data_schema.sql"
    output_path: "my_dataset.duckdb"
    config_path: "import_config.yaml"
```

### 4. Load the database

```bash
python generate_duckdbs.py my-dataset --clean
```

### CSV parsing options

`generate_schema.py`, `generate_import_config.py`, and `csv_to_duckdb.py` expose DuckDB CSV reader knobs for messy files:

- `--delimiter`, `--quote`, `--escape` — uncommon separators and quoting rules.
- `--null` (repeatable) — additional NULL markers such as empty strings or `NA`.
- `--sample-size` — rows DuckDB inspects when inferring column types.
- `--no-header`, `--encoding` — headerless or non-UTF-8 datasets.
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

1.  **`init_dataset.py`**: One-command scaffold — detects schema, generates SQL + import config, registers the dataset in `csv_to_duckdb.yaml`. Optionally loads the database with `--load`.
2.  **`generate_schema.py`**: Auto-detects column types from the CSV and writes a SQL schema file. With `--config`, also produces an `import_config.yaml` with real column mappings.
3.  **`generate_import_config.py`**: Matches schema columns to CSV headers and writes an `import_config.yaml`.
4.  **`generate_duckdbs.py`**: Reads `csv_to_duckdb.yaml`, identifies the target dataset(s), and calls `csv_to_duckdb.py`.
5.  **`csv_to_duckdb.py`**:
    *   Creates the database and table using the SQL schema.
    *   Reads the CSV (downloading first if a URL is provided).
    *   Uses the `import_config.yaml` (if provided) to map columns or apply transformations.
    *   Loads data efficiently into DuckDB.
