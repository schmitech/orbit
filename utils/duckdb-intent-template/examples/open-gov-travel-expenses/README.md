# Government of Canada Travel Expenses Database

This example demonstrates how to use the DuckDB Intent Template with real-world government data from the [Government of Canada Open Data Portal](https://open.canada.ca/data/en/dataset/009f9a49-c2d9-4d29-a6d4-1a228da335ce).

## Overview

The dataset contains **~13,000 records** of travel expense reports submitted by federal institutions, including:
- Travel dates and destinations
- Expense breakdowns (airfare, lodging, meals, etc.)
- Organization and person information
- Purpose of travel

## Files

- `travel_expenses.sql` - Database schema definition
- `generate_travel_expenses_data.py` - Script to download CSV and populate DuckDB database
- `travel_expenses_domain.yaml` - Domain configuration for intent adapter
- `travel_expenses_templates.yaml` - SQL query templates
- `travel_expenses_test_queries.md` - Natural language test queries
- `test_travel_expenses_queries.sh` - Test script for queries
- `travelq.csv` - Sample CSV data (full dataset has ~13K records)

## Quick Start

### 1. Generate the Database

```bash
cd utils/duckdb-intent-template/examples/open-gov-travel-expenses

# Download CSV from official source and create database
python generate_travel_expenses_data.py

# Or use local CSV file
python generate_travel_expenses_data.py --csv-file travelq.csv

# Specify output location
python generate_travel_expenses_data.py --output /path/to/travel_expenses.duckdb
```

The script will:
- Download the CSV from the Government of Canada Open Data portal (if not using local file)
- Create a DuckDB database with the schema
- Load all ~13,000 records
- Create indexes for optimal query performance
- Display statistics about the loaded data

### 2. Test Queries

```bash
# Run test queries
./test_travel_expenses_queries.sh travel_expenses.duckdb
```

### 3. Configure Intent Adapter

Add to `config/adapters.yaml`:

```yaml
travel_expenses:
  type: duckdb_intent
  enabled: true
  database_path: utils/duckdb-intent-template/examples/open-gov-travel-expenses/travel_expenses.duckdb
  domain_config: utils/duckdb-intent-template/examples/open-gov-travel-expenses/travel_expenses_domain.yaml
  templates: utils/duckdb-intent-template/examples/open-gov-travel-expenses/travel_expenses_templates.yaml
```

### 4. Query Examples

Once configured, you can query the database using natural language:

- "Show me travel expenses for 2020"
- "What are the total travel expenses by organization?"
- "List top 10 most expensive trips"
- "Show me expenses for Accessibility Standards Canada"
- "What's the average travel expense?"
- "Find expenses to Vancouver"

## Database Schema

The `travel_expenses` table contains the following fields:

- **ref_number** (VARCHAR, PRIMARY KEY) - Reference number
- **disclosure_group** (VARCHAR) - Disclosure group classification
- **title_en/title_fr** (VARCHAR) - Title in English/French
- **name** (VARCHAR) - Person who incurred the expense
- **purpose_en/purpose_fr** (VARCHAR) - Purpose of travel
- **start_date/end_date** (DATE) - Travel dates
- **destination_en/destination_fr** (VARCHAR) - Destination
- **airfare, other_transport, lodging, meals, other_expenses** (DECIMAL) - Expense categories
- **total** (DECIMAL) - Total expense amount
- **owner_org/owner_org_title** (VARCHAR) - Organization information

## Indexes

The following indexes are created for optimal query performance:

- `idx_travel_start_date` - On start_date
- `idx_travel_end_date` - On end_date
- `idx_travel_name` - On name
- `idx_travel_owner_org` - On owner_org
- `idx_travel_total` - On total
- `idx_travel_disclosure_group` - On disclosure_group

## Data Source

**Source:** [Government of Canada - Proactive Disclosure - Travel Expenses](https://open.canada.ca/data/en/dataset/009f9a49-c2d9-4d29-a6d4-1a228da335ce)

**License:** Open Government Licence - Canada

**Update Frequency:** Quarterly

**CSV Download URL:** https://open.canada.ca/data/dataset/009f9a49-c2d9-4d29-a6d4-1a228da335ce/resource/8282db2a-878f-475c-af10-ad56aa8fa72c/download/travelq.csv

## Requirements

- Python 3.7+
- duckdb (`pip install duckdb`)
- requests (`pip install requests`)

## Example Queries

### Basic Queries

```sql
-- Count all expenses
SELECT COUNT(*) FROM travel_expenses;

-- Total expense amount
SELECT SUM(total) FROM travel_expenses WHERE total IS NOT NULL;

-- Average expense
SELECT AVG(total) FROM travel_expenses WHERE total IS NOT NULL;
```

### Filtered Queries

```sql
-- Expenses for a specific year
SELECT * FROM travel_expenses 
WHERE EXTRACT(YEAR FROM start_date) = 2020;

-- Expenses by organization
SELECT * FROM travel_expenses 
WHERE owner_org_title = 'Accessibility Standards Canada | Normes d'accessibilité Canada';
```

### Aggregated Queries

```sql
-- Expenses by organization
SELECT owner_org_title, COUNT(*) as count, SUM(total) as total_expenses
FROM travel_expenses
WHERE owner_org_title IS NOT NULL AND total IS NOT NULL
GROUP BY owner_org_title
ORDER BY total_expenses DESC;

-- Expenses by destination
SELECT destination_en, COUNT(*) as trip_count, SUM(total) as total_expenses
FROM travel_expenses
WHERE destination_en IS NOT NULL AND total IS NOT NULL
GROUP BY destination_en
ORDER BY total_expenses DESC;
```

## Troubleshooting

### Database file not found

Make sure you've run `generate_travel_expenses_data.py` first to create the database.

### CSV download fails

The script will attempt to download from the official URL. If it fails:
1. Check your internet connection
2. Try downloading manually and use `--csv-file` option
3. The URL may have changed - check the official dataset page

### Import errors

If you get import errors for `duckdb` or `requests`:
```bash
pip install duckdb requests
```

## See Also

- [Analytics Example](../analytics/README.md) - Another example with synthetic data
- [DuckDB Intent Template Documentation](../../README.md) - Full documentation
- [Government of Canada Open Data](https://open.canada.ca/en/open-data) - More datasets

