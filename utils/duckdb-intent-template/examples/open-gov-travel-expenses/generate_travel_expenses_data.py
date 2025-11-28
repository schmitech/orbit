#!/usr/bin/env python3
"""
Travel Expenses Database Data Generator

DESCRIPTION:
    Downloads the Government of Canada Proactive Disclosure - Travel Expenses
    CSV dataset and populates a DuckDB database. The dataset contains travel
    expense reports submitted by federal institutions.

    Source: https://open.canada.ca/data/en/dataset/009f9a49-c2d9-4d29-a6d4-1a228da335ce

USAGE:
    python generate_travel_expenses_data.py [--csv-file FILE] [--output FILE] [--clean]

ARGUMENTS:
    --csv-file FILE   Path to local CSV file (if not provided, downloads from URL)
    --output FILE     Path to DuckDB database file (default: travel_expenses.duckdb)
    --clean           Drop existing tables before generating new data
    --url URL         URL to download CSV from (default: official Canada Open Data URL)

EXAMPLES:
    # Download and populate from official source
    python generate_travel_expenses_data.py

    # Use local CSV file
    python generate_travel_expenses_data.py --csv-file travelq.csv

    # Generate to specific database file
    python generate_travel_expenses_data.py --output ./data/travel_expenses.duckdb

    # Clean existing data and generate fresh
    python generate_travel_expenses_data.py --clean

OUTPUT:
    Creates a DuckDB database with the following structure:
    - Database: travel_expenses.duckdb (or specified path)
    - Table: travel_expenses
    - Indexes: On dates, name, organization, total, disclosure_group

REQUIREMENTS:
    pip install duckdb requests

SAMPLE DATA:
    ref_number      | name              | start_date | destination_en              | total
    ----------------|-------------------|------------|----------------------------|--------
    T-2020-P11-0001| Bérubé, Paul-Claude| 2020-02-09 | Vancouver, British Columbia| 2597.14
    T-2020-P11-0002| Reid, Mary         | 2020-02-09 | Vancouver, British Columbia| 4128.74

TESTING WITH INTENT ADAPTER:
    After generating data, you can test with the DuckDB Intent adapter:

    1. Configure adapter in config/adapters.yaml (see documentation)
    2. Start Orbit server
    3. Query: "Show me travel expenses for 2020"
    4. Query: "What are the total travel expenses by organization?"

SEE ALSO:
    - travel_expenses.sql - Database schema
    - travel_expenses_test_queries.md - Sample queries for template generation
    - ../../README.md - DuckDB Intent Template Generator documentation

AUTHOR:
    DuckDB Intent Template Generator v1.0.0
"""

import duckdb
import argparse
import sys
import csv
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    import requests
except ImportError:
    print("❌ Error: requests library is required")
    print("   Install with: pip install requests")
    sys.exit(1)


# Official CSV download URL from Government of Canada Open Data
DEFAULT_CSV_URL = "https://open.canada.ca/data/dataset/009f9a49-c2d9-4d29-a6d4-1a228da335ce/resource/8282db2a-878f-475c-af10-ad56aa8fa72c/download/travelq.csv"


def download_csv(url: str, output_path: str) -> bool:
    """Download CSV file from URL"""
    print(f"📥 Downloading CSV from: {url}")
    
    try:
        response = requests.get(url, timeout=60, stream=True)
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
        
        print()  # New line after progress
        print(f"✅ Downloaded {downloaded:,} bytes to {output_path}")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Error downloading CSV: {e}")
        return False


def parse_decimal(value: str) -> Optional[float]:
    """Parse decimal value from CSV, handling empty strings"""
    if not value or value.strip() == '':
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_date(value: str) -> Optional[str]:
    """Parse date value from CSV, handling empty strings"""
    if not value or value.strip() == '':
        return None
    # Dates are in YYYY-MM-DD format
    return value.strip()


def create_database(db_path: str, clean: bool = False):
    """Create database and schema"""
    conn = duckdb.connect(db_path)
    
    # Drop table if clean mode
    if clean:
        conn.execute("DROP TABLE IF EXISTS travel_expenses")
        print("🧹 Cleaned existing data")
    
    # Create table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS travel_expenses (
            ref_number VARCHAR PRIMARY KEY,
            disclosure_group VARCHAR,
            title_en VARCHAR,
            title_fr VARCHAR,
            name VARCHAR,
            purpose_en VARCHAR,
            purpose_fr VARCHAR,
            start_date DATE,
            end_date DATE,
            destination_en VARCHAR,
            destination_fr VARCHAR,
            destination_2_en VARCHAR,
            destination_2_fr VARCHAR,
            destination_other_en VARCHAR,
            destination_other_fr VARCHAR,
            airfare DECIMAL(10, 2),
            other_transport DECIMAL(10, 2),
            lodging DECIMAL(10, 2),
            meals DECIMAL(10, 2),
            other_expenses DECIMAL(10, 2),
            total DECIMAL(10, 2),
            additional_comments_en VARCHAR,
            additional_comments_fr VARCHAR,
            owner_org VARCHAR,
            owner_org_title VARCHAR
        )
    """)
    
    # Create indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_travel_start_date ON travel_expenses(start_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_travel_end_date ON travel_expenses(end_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_travel_name ON travel_expenses(name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_travel_owner_org ON travel_expenses(owner_org)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_travel_total ON travel_expenses(total)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_travel_disclosure_group ON travel_expenses(disclosure_group)")
    
    return conn


def load_csv_data(csv_path: str) -> list:
    """Load and parse CSV data"""
    records = []
    
    print(f"📖 Reading CSV file: {csv_path}")
    
    # Try different encodings in case of BOM or encoding issues
    encodings = ['utf-8-sig', 'utf-8', 'latin-1']
    
    for encoding in encodings:
        try:
            with open(csv_path, 'r', encoding=encoding) as f:
                reader = csv.DictReader(f)
                
                # Check if we got the expected columns
                if 'ref_number' not in reader.fieldnames:
                    if encoding != encodings[-1]:  # Not the last encoding
                        continue
                    else:
                        print(f"⚠️  Warning: Expected 'ref_number' column not found. Available columns: {reader.fieldnames}")
                        return []
                
                parsed_count = 0
                skipped_count = 0
                
                for row_num, row in enumerate(reader, start=2):  # Start at 2 (row 1 is header)
                    try:
                        # Handle empty rows
                        if not row or not any(row.values()):
                            continue
                        
                        ref_number = row.get('ref_number', '').strip() if row.get('ref_number') else ''
                        
                        # Skip records without ref_number
                        if not ref_number:
                            skipped_count += 1
                            continue
                        
                        record = {
                            'ref_number': ref_number,
                            'disclosure_group': row.get('disclosure_group', '').strip() or None,
                            'title_en': row.get('title_en', '').strip() or None,
                            'title_fr': row.get('title_fr', '').strip() or None,
                            'name': row.get('name', '').strip() or None,
                            'purpose_en': row.get('purpose_en', '').strip() or None,
                            'purpose_fr': row.get('purpose_fr', '').strip() or None,
                            'start_date': parse_date(row.get('start_date', '')),
                            'end_date': parse_date(row.get('end_date', '')),
                            'destination_en': row.get('destination_en', '').strip() or None,
                            'destination_fr': row.get('destination_fr', '').strip() or None,
                            'destination_2_en': row.get('destination_2_en', '').strip() or None,
                            'destination_2_fr': row.get('destination_2_fr', '').strip() or None,
                            'destination_other_en': row.get('destination_other_en', '').strip() or None,
                            'destination_other_fr': row.get('destination_other_fr', '').strip() or None,
                            'airfare': parse_decimal(row.get('airfare', '')),
                            'other_transport': parse_decimal(row.get('other_transport', '')),
                            'lodging': parse_decimal(row.get('lodging', '')),
                            'meals': parse_decimal(row.get('meals', '')),
                            'other_expenses': parse_decimal(row.get('other_expenses', '')),
                            'total': parse_decimal(row.get('total', '')),
                            'additional_comments_en': row.get('additional_comments_en', '').strip() or None,
                            'additional_comments_fr': row.get('additional_comments_fr', '').strip() or None,
                            'owner_org': row.get('owner_org', '').strip() or None,
                            'owner_org_title': row.get('owner_org_title', '').strip() or None,
                        }
                        
                        records.append(record)
                        parsed_count += 1
                        
                        # Show progress for large files
                        if parsed_count % 10000 == 0:
                            print(f"   Processed {parsed_count:,} records...", end='\r', flush=True)
                        
                    except Exception as e:
                        if row_num <= 5:  # Only show first few errors
                            print(f"⚠️  Warning: Error parsing row {row_num}: {e}")
                        skipped_count += 1
                        continue
                
                if parsed_count > 0:
                    if skipped_count > 0:
                        print(f"\n   Skipped {skipped_count:,} invalid rows")
                    return records
                else:
                    if encoding != encodings[-1]:  # Not the last encoding
                        continue
                    else:
                        print(f"⚠️  Warning: No valid records found in CSV file")
                        return []
                        
        except UnicodeDecodeError:
            if encoding != encodings[-1]:  # Not the last encoding
                continue
            else:
                raise
        except Exception as e:
            if encoding != encodings[-1]:  # Not the last encoding
                continue
            else:
                print(f"❌ Error reading CSV with {encoding} encoding: {e}")
                raise
    
    return records


def insert_records(conn: duckdb.DuckDBPyConnection, records: list) -> int:
    """Insert records into database"""
    inserted = 0
    skipped = 0
    
    for record in records:
        try:
            # Use INSERT OR REPLACE to handle duplicates (updates existing records)
            conn.execute("""
                INSERT OR REPLACE INTO travel_expenses (
                    ref_number, disclosure_group, title_en, title_fr, name,
                    purpose_en, purpose_fr, start_date, end_date,
                    destination_en, destination_fr, destination_2_en, destination_2_fr,
                    destination_other_en, destination_other_fr,
                    airfare, other_transport, lodging, meals, other_expenses, total,
                    additional_comments_en, additional_comments_fr,
                    owner_org, owner_org_title
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record['ref_number'],
                record['disclosure_group'],
                record['title_en'],
                record['title_fr'],
                record['name'],
                record['purpose_en'],
                record['purpose_fr'],
                record['start_date'],
                record['end_date'],
                record['destination_en'],
                record['destination_fr'],
                record['destination_2_en'],
                record['destination_2_fr'],
                record['destination_other_en'],
                record['destination_other_fr'],
                record['airfare'],
                record['other_transport'],
                record['lodging'],
                record['meals'],
                record['other_expenses'],
                record['total'],
                record['additional_comments_en'],
                record['additional_comments_fr'],
                record['owner_org'],
                record['owner_org_title']
            ))
            inserted += 1
            
            # Show progress for large files
            if inserted % 10000 == 0:
                print(f"   Inserted {inserted:,} records...", end='\r', flush=True)
            
        except Exception as e:
            skipped += 1
            if skipped <= 10:  # Only show first 10 errors
                print(f"⚠️  Warning: Error inserting record {record.get('ref_number', 'unknown')}: {e}")
            continue
    
    if skipped > 10:
        print(f"\n   Skipped {skipped:,} records with errors")
    
    return inserted


def print_sample_data(conn: duckdb.DuckDBPyConnection, limit: int = 5):
    """Print sample records from database"""
    print("\n📊 Sample Travel Expenses Data:")
    print("-" * 120)
    
    result = conn.execute(f"""
        SELECT ref_number, name, start_date, destination_en, total
        FROM travel_expenses
        ORDER BY start_date DESC
        LIMIT {limit}
    """).fetchall()
    
    if result:
        print(f"{'Ref Number':<20} {'Name':<30} {'Start Date':<12} {'Destination':<35} {'Total':<12}")
        print("-" * 120)
        
        for row in result:
            ref_num = row[0] or ''
            name = (row[1] or '')[:28]
            start_date = str(row[2]) if row[2] else ''
            destination = (row[3] or '')[:33]
            total = f"${row[4]:,.2f}" if row[4] else 'N/A'
            print(f"{ref_num:<20} {name:<30} {start_date:<12} {destination:<35} {total:<12}")
        
        print("-" * 120)


def get_database_stats(conn: duckdb.DuckDBPyConnection):
    """Get and display database statistics"""
    # Total records
    result = conn.execute("SELECT COUNT(*) FROM travel_expenses").fetchone()
    total_records = result[0] if result else 0
    
    if total_records == 0:
        print("\n📈 Database Statistics:")
        print(f"   Total Records: 0")
        print("   No data available for statistics")
        return
    
    # Total expenses
    result = conn.execute("SELECT SUM(total) FROM travel_expenses WHERE total IS NOT NULL").fetchone()
    total_expenses = result[0] if result and result[0] is not None else 0.0
    
    # Average expense
    result = conn.execute("SELECT AVG(total) FROM travel_expenses WHERE total IS NOT NULL").fetchone()
    avg_expense = result[0] if result and result[0] is not None else 0.0
    
    # Date range
    result = conn.execute("SELECT MIN(start_date), MAX(start_date) FROM travel_expenses WHERE start_date IS NOT NULL").fetchone()
    min_date = result[0] if result and result[0] else None
    max_date = result[1] if result and result[1] else None
    
    # Unique organizations
    result = conn.execute("SELECT COUNT(DISTINCT owner_org) FROM travel_expenses WHERE owner_org IS NOT NULL").fetchone()
    unique_orgs = result[0] if result else 0
    
    # Top organizations by expense count
    result = conn.execute("""
        SELECT owner_org_title, COUNT(*) as count
        FROM travel_expenses
        WHERE owner_org_title IS NOT NULL
        GROUP BY owner_org_title
        ORDER BY count DESC
        LIMIT 5
    """).fetchall()
    top_orgs = result if result else []
    
    # Top destinations
    result = conn.execute("""
        SELECT destination_en, COUNT(*) as count
        FROM travel_expenses
        WHERE destination_en IS NOT NULL
        GROUP BY destination_en
        ORDER BY count DESC
        LIMIT 5
    """).fetchall()
    top_destinations = result if result else []
    
    print("\n📈 Database Statistics:")
    print(f"   Total Records: {total_records:,}")
    print(f"   Total Expenses: ${total_expenses:,.2f}")
    print(f"   Average Expense: ${avg_expense:,.2f}")
    if min_date and max_date:
        print(f"   Date Range: {min_date} to {max_date}")
    else:
        print(f"   Date Range: N/A")
    print(f"   Unique Organizations: {unique_orgs}")
    if top_orgs:
        print(f"\n   Top 5 Organizations by Record Count:")
        for org, count in top_orgs:
            print(f"      {org}: {count:,} records")
    if top_destinations:
        print(f"\n   Top 5 Destinations:")
        for dest, count in top_destinations:
            print(f"      {dest}: {count:,} trips")


def main():
    parser = argparse.ArgumentParser(
        description='Generate travel expenses database from Government of Canada Open Data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_travel_expenses_data.py
  python generate_travel_expenses_data.py --csv-file travelq.csv
  python generate_travel_expenses_data.py --output travel_expenses.duckdb --clean
  python generate_travel_expenses_data.py --url https://example.com/travelq.csv
        """
    )
    
    parser.add_argument(
        '--csv-file',
        type=str,
        help='Path to local CSV file (if not provided, downloads from URL)'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default='travel_expenses.duckdb',
        help='Path to DuckDB database file (default: travel_expenses.duckdb)'
    )
    
    parser.add_argument(
        '--clean',
        action='store_true',
        help='Drop existing tables before generating new data'
    )
    
    parser.add_argument(
        '--url',
        type=str,
        default=DEFAULT_CSV_URL,
        help=f'URL to download CSV from (default: official Canada Open Data URL)'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("  Travel Expenses Database Generator")
    print("=" * 60)
    print(f"📝 Configuration:")
    print(f"   CSV File: {args.csv_file or 'Download from URL'}")
    print(f"   Output: {args.output}")
    print(f"   Clean mode: {'Yes' if args.clean else 'No'}")
    if not args.csv_file:
        print(f"   Download URL: {args.url}")
    print()
    
    # Determine CSV file path
    csv_path = args.csv_file
    
    if not csv_path:
        # Download CSV
        csv_path = Path(__file__).parent / 'travelq.csv'
        
        if not csv_path.exists() or args.clean:
            if not download_csv(args.url, str(csv_path)):
                print("❌ Failed to download CSV file")
                return 1
        else:
            print(f"📄 Using existing CSV file: {csv_path}")
    
    # Check if CSV file exists
    if not Path(csv_path).exists():
        print(f"❌ Error: CSV file not found: {csv_path}")
        return 1
    
    # Create database
    print("🔨 Creating database...")
    conn = create_database(args.output, clean=args.clean)
    
    # Load CSV data
    print("📖 Loading CSV data...")
    records = load_csv_data(csv_path)
    print(f"✅ Loaded {len(records):,} records from CSV")
    
    # Insert records
    print("💾 Inserting records...")
    inserted = insert_records(conn, records)
    print(f"✅ Inserted {inserted:,} records")
    
    # Show sample data
    print_sample_data(conn, limit=10)
    
    # Show statistics
    get_database_stats(conn)
    
    # Close connection
    conn.close()
    
    print(f"\n✅ Database created successfully: {args.output}")
    print(f"\n💡 Next steps:")
    print(f"   1. Test queries with DuckDB:")
    print(f"      duckdb {args.output} 'SELECT * FROM travel_expenses LIMIT 5;'")
    print(f"\n   2. Configure Intent adapter in config/adapters.yaml")
    print(f"      (See documentation for example configuration)")
    print(f"\n   3. Generate SQL templates (if needed):")
    print(f"      cd ../..")
    print(f"      python template_generator.py \\")
    print(f"        --schema examples/open-gov-travel-expenses/travel_expenses.sql \\")
    print(f"        --queries examples/open-gov-travel-expenses/travel_expenses_test_queries.md \\")
    print(f"        --output travel_expenses_templates.yaml")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

