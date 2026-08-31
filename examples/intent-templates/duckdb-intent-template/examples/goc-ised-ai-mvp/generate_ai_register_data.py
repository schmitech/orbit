#!/usr/bin/env python3
"""
Government of Canada AI Register (MVP) Database Generator
==========================================================

Loads AI Register data from the GC AI Register CSV into a DuckDB database
for analysis and querying.

Data Source
-----------
Government of Canada AI Register (Minimum Viable Product)
Innovation, Science and Economic Development Canada (ISED)
https://open.canada.ca/data/en/dataset/fcbc0200-79ba-4fa4-94a6-00e32facea6b/resource/369f6f34-148a-42ed-b581-8c164e941a89

The dataset contains information about AI systems deployed across federal
government institutions, including:
- System name and description (bilingual)
- Government organization
- Development status
- Capabilities
- Privacy considerations
- Vendor information

Usage
-----
Basic usage (uses default file paths):
    python generate_ai_register_data.py

With custom CSV file:
    python generate_ai_register_data.py --csv path/to/data.csv

With custom output database:
    python generate_ai_register_data.py --db my_database.duckdb

Clean existing data before inserting:
    python generate_ai_register_data.py --clean

Full example with all options:
    python generate_ai_register_data.py --csv goc-ai-mvp-register.csv \\
                                        --db goc-ai-register.duckdb \\
                                        --sql ai_register.sql \\
                                        --clean

Arguments
---------
--csv     Path to input CSV file (default: goc-ai-mvp-register.csv)
--db      Output DuckDB database path (default: goc-ai-register.duckdb)
--sql     SQL schema file path (default: ai_register.sql)
--clean   Remove existing data before inserting new records

Requirements
------------
- Python 3.8+
- duckdb: pip install duckdb

Output
------
Creates a DuckDB database with the ai_register table containing all
registered AI systems from federal government institutions.

Example Queries
---------------
After generating the database, you can query it:

    # View all systems
    duckdb goc-ai-register.duckdb "SELECT * FROM ai_register LIMIT 10"

    # Count by organization
    duckdb goc-ai-register.duckdb "SELECT government_organization, COUNT(*) FROM ai_register GROUP BY 1"

    # Find production systems
    duckdb goc-ai-register.duckdb "SELECT * FROM ai_register WHERE ai_system_status_en = 'In production'"
"""

import argparse
import csv
import os
import sys
from pathlib import Path

try:
    import duckdb
except ImportError:
    print("Error: duckdb package is required. Install with: pip install duckdb")
    sys.exit(1)


# Column mapping from CSV headers to database columns
COLUMN_MAPPING = {
    'ai_register_id': 'ai_register_id',
    'name_ai_system_en': 'name_ai_system_en',
    'name_ai_system_fr': 'name_ai_system_fr',
    'government_organization': 'government_organization',
    'description_ai_system_en': 'description_ai_system_en',
    'description_ai_system_fr': 'description_ai_system_fr',
    'ai_system_primary_users_en': 'ai_system_primary_users_en',
    'ai_system_primary_users_fr': 'ai_system_primary_users_fr',
    'developed_by_en': 'developed_by_en',
    'developed_by_fr': 'developed_by_fr',
    'vendor_information': 'vendor_information',
    'ai_system_status_en': 'ai_system_status_en',
    'ai_system_status_fr': 'ai_system_status_fr',
    'status_date': 'status_date',
    'ai_system_capabilities_en': 'ai_system_capabilities_en',
    'ai_system_capabilities_fr': 'ai_system_capabilities_fr',
    'data_sources_en': 'data_sources_en',
    'data_sources_fr': 'data_sources_fr',
    'involves_personal_information': 'involves_personal_information',
    'personal_information_banks_en': 'personal_information_banks_en',
    'personal_information_banks_fr': 'personal_information_banks_fr',
    'notification_ai': 'notification_ai',
    'ai_system_results_en': 'ai_system_results_en',
    'ai_system_results_fr': 'ai_system_results_fr',
}


def parse_year(year_str: str) -> int:
    """Parse year string to integer."""
    if not year_str:
        return None
    try:
        return int(year_str.strip())
    except ValueError:
        return None


def clean_text(text: str) -> str:
    """Clean text value, handling multiline content."""
    if not text:
        return None
    # Replace newlines with spaces and clean up whitespace
    cleaned = ' '.join(text.split())
    return cleaned.strip() if cleaned else None


def load_csv_data(csv_path: str) -> list:
    """Load and parse CSV data."""
    records = []
    
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            record = {}
            
            # Map each column
            for csv_col, db_col in COLUMN_MAPPING.items():
                value = row.get(csv_col, '').strip()
                
                if db_col == 'status_date':
                    record[db_col] = parse_year(value)
                else:
                    record[db_col] = clean_text(value)
            
            # Skip rows without an ID
            if not record.get('ai_register_id'):
                continue
                
            records.append(record)
    
    return records


def create_database(db_path: str, sql_path: str, records: list, clean: bool = False):
    """Create DuckDB database and insert records."""
    
    # Remove existing database if clean mode
    if clean and os.path.exists(db_path):
        os.remove(db_path)
        print("Removed existing database")
    
    conn = duckdb.connect(db_path)
    
    # Read and execute schema SQL
    with open(sql_path, 'r') as f:
        schema_sql = f.read()
    
    # Execute schema (may be multiple statements)
    for statement in schema_sql.split(';'):
        statement = statement.strip()
        if statement:
            conn.execute(statement)
    
    # Clean existing data if requested
    if clean:
        conn.execute("DELETE FROM ai_register")
        print("Cleaned existing data")
    
    # Build column list for insert
    columns = list(COLUMN_MAPPING.values())
    placeholders = ', '.join(['?' for _ in columns])
    column_names = ', '.join(columns)
    
    insert_sql = f"""
        INSERT INTO ai_register ({column_names})
        VALUES ({placeholders})
    """
    
    # Insert records
    total_inserted = 0
    skipped = 0
    
    for record in records:
        try:
            values = [record.get(col) for col in columns]
            conn.execute(insert_sql, values)
            total_inserted += 1
        except Exception as e:
            # Skip duplicates
            if 'duplicate' in str(e).lower() or 'unique' in str(e).lower():
                skipped += 1
            else:
                print(f"Warning: Error inserting record {record.get('ai_register_id')}: {e}")
                skipped += 1
    
    print(f"   Inserted {total_inserted} records")
    if skipped > 0:
        print(f"   Skipped {skipped} duplicate/error records")
    
    conn.close()
    
    return total_inserted


def print_statistics(db_path: str):
    """Print database statistics."""
    conn = duckdb.connect(db_path, read_only=True)
    
    # Total records
    total = conn.execute("SELECT COUNT(*) FROM ai_register").fetchone()[0]
    print(f"\nDatabase Statistics:")
    print(f"   Total AI Systems: {total:,}")
    
    # Organizations
    orgs = conn.execute("SELECT COUNT(DISTINCT government_organization) FROM ai_register").fetchone()[0]
    print(f"   Unique Organizations: {orgs}")
    
    # Status breakdown
    print(f"\n   AI Systems by Status:")
    results = conn.execute("""
        SELECT ai_system_status_en, COUNT(*) as count
        FROM ai_register
        WHERE ai_system_status_en IS NOT NULL
        GROUP BY ai_system_status_en
        ORDER BY count DESC
    """).fetchall()
    
    for row in results:
        status = row[0] if row[0] else 'Unknown'
        count = row[1]
        print(f"      {status}: {count}")
    
    # Top organizations
    print(f"\n   Top Organizations by AI System Count:")
    results = conn.execute("""
        SELECT government_organization, COUNT(*) as count
        FROM ai_register
        GROUP BY government_organization
        ORDER BY count DESC
        LIMIT 10
    """).fetchall()
    
    for row in results:
        org = row[0][:60] if row[0] else 'Unknown'
        count = row[1]
        print(f"      {org}: {count}")
    
    # Developer breakdown
    print(f"\n   AI Systems by Developer:")
    results = conn.execute("""
        SELECT developed_by_en, COUNT(*) as count
        FROM ai_register
        WHERE developed_by_en IS NOT NULL
        GROUP BY developed_by_en
        ORDER BY count DESC
    """).fetchall()
    
    for row in results:
        dev = row[0] if row[0] else 'Unknown'
        count = row[1]
        print(f"      {dev}: {count}")
    
    # Privacy stats
    print(f"\n   Privacy Statistics:")
    result = conn.execute("""
        SELECT
            COUNT(CASE WHEN involves_personal_information = 'Y' THEN 1 END) as with_pii,
            COUNT(CASE WHEN notification_ai = 'Y' THEN 1 END) as with_notification
        FROM ai_register
    """).fetchone()
    print(f"      Systems with Personal Information: {result[0]}")
    print(f"      Systems with AI Notification: {result[1]}")
    
    conn.close()


def print_sample_data(db_path: str, limit: int = 10):
    """Print sample records from the database."""
    conn = duckdb.connect(db_path, read_only=True)
    
    print(f"\nSample AI Systems:")
    print("-" * 120)
    print(f"{'ID':<25} {'Name':<35} {'Organization':<40} {'Status':<15}")
    print("-" * 120)
    
    results = conn.execute(f"""
        SELECT ai_register_id, name_ai_system_en, government_organization, ai_system_status_en
        FROM ai_register
        ORDER BY status_date DESC, name_ai_system_en
        LIMIT {limit}
    """).fetchall()
    
    for row in results:
        reg_id = (row[0][:23] + '..') if row[0] and len(row[0]) > 25 else (row[0] or 'N/A')
        name = (row[1][:33] + '..') if row[1] and len(row[1]) > 35 else (row[1] or 'N/A')
        org = (row[2][:38] + '..') if row[2] and len(row[2]) > 40 else (row[2] or 'N/A')
        status = row[3] if row[3] else 'N/A'
        print(f"{reg_id:<25} {name:<35} {org:<40} {status:<15}")
    
    print("-" * 120)
    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description='Generate Government of Canada AI Register DuckDB database from CSV'
    )
    parser.add_argument(
        '--csv',
        default='goc-ai-mvp-register.csv',
        help='Path to CSV file (default: goc-ai-mvp-register.csv)'
    )
    parser.add_argument(
        '--db',
        default='goc-ai-register.duckdb',
        help='Output database path (default: goc-ai-register.duckdb)'
    )
    parser.add_argument(
        '--sql',
        default='ai_register.sql',
        help='SQL schema file (default: ai_register.sql)'
    )
    parser.add_argument(
        '--clean',
        action='store_true',
        help='Clean existing data before inserting'
    )
    
    args = parser.parse_args()
    
    # Get script directory for relative paths
    script_dir = Path(__file__).parent.resolve()
    
    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = script_dir / csv_path
    
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = script_dir / db_path
    
    sql_path = Path(args.sql)
    if not sql_path.is_absolute():
        sql_path = script_dir / sql_path
    
    # Validate files exist
    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        sys.exit(1)
    
    if not sql_path.exists():
        print(f"Error: SQL schema file not found: {sql_path}")
        sys.exit(1)
    
    print("=" * 70)
    print("  Government of Canada AI Register Database Generator")
    print("=" * 70)
    print(f"Configuration:")
    print(f"   CSV File: {csv_path}")
    print(f"   Output: {db_path}")
    print(f"   Clean mode: {'Yes' if args.clean else 'No'}")
    print()
    
    # Load CSV data
    print(f"Creating database...")
    if args.clean and db_path.exists():
        print("Cleaned existing data")
    
    print(f"Reading CSV file: {csv_path}")
    records = load_csv_data(str(csv_path))
    print(f"   Parsed {len(records)} records")
    
    # Create database
    print(f"Inserting records...")
    inserted = create_database(str(db_path), str(sql_path), records, args.clean)
    
    # Print sample data
    print_sample_data(str(db_path))
    
    # Print statistics
    print_statistics(str(db_path))
    
    print(f"\nDatabase created successfully: {db_path}")
    print(f"\nNext steps:")
    print(f"   1. Test queries with DuckDB:")
    print(f"      duckdb {db_path} 'SELECT * FROM ai_register LIMIT 5;'")
    print(f"\n   2. Configure Intent adapter in config/adapters/intent.yaml")


if __name__ == '__main__':
    main()

