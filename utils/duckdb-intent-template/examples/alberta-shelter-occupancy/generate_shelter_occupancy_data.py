#!/usr/bin/env python3
"""
Alberta Emergency Shelter Occupancy Database Data Generator

DESCRIPTION:
    Loads the Alberta Emergency Shelter Occupancy CSV dataset and populates
    a DuckDB database. The dataset contains daily occupancy data for emergency
    shelters across Alberta from 2013-2025.

    Source: Government of Alberta Open Data (https://open.alberta.ca/opendata/funded-emergency-shelters-daily-occupancy-ab)

USAGE:
    python generate_shelter_occupancy_data.py [--csv-file FILE] [--output FILE] [--clean]

ARGUMENTS:
    --csv-file FILE   Path to local CSV file (default: looks for CSV in same directory)
    --output FILE     Path to DuckDB database file (default: shelter_occupancy.duckdb)
    --clean           Drop existing tables before generating new data

EXAMPLES:
    # Generate from default CSV in same directory
    python generate_shelter_occupancy_data.py

    # Use specific CSV file
    python generate_shelter_occupancy_data.py --csv-file shelter_data.csv

    # Generate to specific database file
    python generate_shelter_occupancy_data.py --output ./data/shelter_occupancy.duckdb

    # Clean existing data and generate fresh
    python generate_shelter_occupancy_data.py --clean

OUTPUT:
    Creates a DuckDB database with the following structure:
    - Database: shelter_occupancy.duckdb (or specified path)
    - Table: shelter_occupancy
    - Indexes: On date, city, shelter_type, shelter_name, organization, year, month

REQUIREMENTS:
    pip install duckdb

SAMPLE DATA:
    date       | city     | shelter_type    | shelter_name                  | capacity | overnight
    -----------|----------|-----------------|-------------------------------|----------|----------
    2024-01-15 | Edmonton | Adult Emergency | Hope Mission - Herb Jamieson  | 250      | 253
    2024-01-15 | Calgary  | Women Emergency | YWCA - Mary Dover House       | 45       | 42

TESTING WITH INTENT ADAPTER:
    After generating data, you can test with the DuckDB Intent adapter:

    1. Configure adapter in config/adapters/intent.yaml
    2. Start Orbit server
    3. Query: "Show me shelter occupancy for Edmonton in 2024"
    4. Query: "What is the average occupancy rate by shelter type?"

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
import glob


def find_csv_file(directory: Path) -> Optional[Path]:
    """Find the shelter occupancy CSV file in the directory"""
    csv_files = list(directory.glob("*.csv"))
    if csv_files:
        return csv_files[0]
    return None


def parse_integer(value: str) -> Optional[int]:
    """Parse integer value from CSV, handling empty strings"""
    if not value or value.strip() == '':
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def parse_date(value: str) -> Optional[str]:
    """Parse date value from CSV (M/D/YYYY format), returns YYYY-MM-DD"""
    if not value or value.strip() == '':
        return None
    try:
        # Parse M/D/YYYY format
        dt = datetime.strptime(value.strip(), '%m/%d/%Y')
        return dt.strftime('%Y-%m-%d')
    except ValueError:
        try:
            # Try alternative format D/M/YYYY
            dt = datetime.strptime(value.strip(), '%d/%m/%Y')
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            return value.strip()


def create_database(db_path: str, clean: bool = False):
    """Create database and schema"""
    conn = duckdb.connect(db_path)

    # Drop table if clean mode
    if clean:
        conn.execute("DROP TABLE IF EXISTS shelter_occupancy")
        print("Cleaned existing data")

    # Create table with auto-incrementing id
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shelter_occupancy (
            id INTEGER PRIMARY KEY,
            date DATE,
            city VARCHAR,
            shelter_type VARCHAR,
            shelter_name VARCHAR,
            organization VARCHAR,
            shelter VARCHAR,
            capacity INTEGER,
            overnight INTEGER,
            daytime INTEGER,
            year INTEGER,
            month INTEGER
        )
    """)

    # Create sequence for auto-increment if not exists
    try:
        conn.execute("CREATE SEQUENCE IF NOT EXISTS shelter_id_seq START 1")
    except Exception:
        pass  # Sequence might already exist

    # Create indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_shelter_date ON shelter_occupancy(date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_shelter_city ON shelter_occupancy(city)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_shelter_type ON shelter_occupancy(shelter_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_shelter_name ON shelter_occupancy(shelter_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_shelter_organization ON shelter_occupancy(organization)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_shelter_year ON shelter_occupancy(year)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_shelter_month ON shelter_occupancy(month)")

    return conn


def load_csv_data(csv_path: str) -> list:
    """Load and parse CSV data"""
    records = []

    print(f"Reading CSV file: {csv_path}")

    # Try different encodings
    encodings = ['utf-8-sig', 'utf-8', 'latin-1']

    for encoding in encodings:
        try:
            with open(csv_path, 'r', encoding=encoding) as f:
                reader = csv.DictReader(f)

                # Map CSV headers to expected column names
                header_map = {
                    'date': 'date',
                    'city': 'city',
                    'ShelterType': 'shelter_type',
                    'ShelterName': 'shelter_name',
                    'Organization': 'organization',
                    'Shelter': 'shelter',
                    'Capacity': 'capacity',
                    'Overnight': 'overnight',
                    'Daytime': 'daytime',
                    'year': 'year',
                    'month': 'month'
                }

                parsed_count = 0
                skipped_count = 0

                for row_num, row in enumerate(reader, start=2):
                    try:
                        # Handle empty rows
                        if not row or not any(row.values()):
                            continue

                        date_val = row.get('date', '').strip()

                        # Skip records without date
                        if not date_val:
                            skipped_count += 1
                            continue

                        record = {
                            'date': parse_date(date_val),
                            'city': row.get('city', '').strip() or None,
                            'shelter_type': row.get('ShelterType', '').strip() or None,
                            'shelter_name': row.get('ShelterName', '').strip() or None,
                            'organization': row.get('Organization', '').strip() or None,
                            'shelter': row.get('Shelter', '').strip() or None,
                            'capacity': parse_integer(row.get('Capacity', '')),
                            'overnight': parse_integer(row.get('Overnight', '')),
                            'daytime': parse_integer(row.get('Daytime', '')),
                            'year': parse_integer(row.get('year', '')),
                            'month': parse_integer(row.get('month', '')),
                        }

                        records.append(record)
                        parsed_count += 1

                        # Show progress for large files
                        if parsed_count % 50000 == 0:
                            print(f"   Processed {parsed_count:,} records...", end='\r', flush=True)

                    except Exception as e:
                        if row_num <= 5:
                            print(f"Warning: Error parsing row {row_num}: {e}")
                        skipped_count += 1
                        continue

                if parsed_count > 0:
                    print(f"\n   Parsed {parsed_count:,} records")
                    if skipped_count > 0:
                        print(f"   Skipped {skipped_count:,} invalid rows")
                    return records

        except UnicodeDecodeError:
            if encoding != encodings[-1]:
                continue
            else:
                raise
        except Exception as e:
            if encoding != encodings[-1]:
                continue
            else:
                print(f"Error reading CSV with {encoding} encoding: {e}")
                raise

    return records


def insert_records(conn: duckdb.DuckDBPyConnection, records: list) -> int:
    """Insert records into database using batch insert for performance"""

    if not records:
        return 0

    print(f"Inserting {len(records):,} records...")

    # Batch insert for better performance
    batch_size = 10000
    inserted = 0

    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]

        # Prepare values for batch insert
        values = []
        for idx, record in enumerate(batch):
            values.append((
                i + idx + 1,  # id
                record['date'],
                record['city'],
                record['shelter_type'],
                record['shelter_name'],
                record['organization'],
                record['shelter'],
                record['capacity'],
                record['overnight'],
                record['daytime'],
                record['year'],
                record['month']
            ))

        # Use executemany for batch insert
        conn.executemany("""
            INSERT INTO shelter_occupancy (
                id, date, city, shelter_type, shelter_name, organization,
                shelter, capacity, overnight, daytime, year, month
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, values)

        inserted += len(batch)
        print(f"   Inserted {inserted:,} records...", end='\r', flush=True)

    print(f"\n   Completed: {inserted:,} records inserted")
    return inserted


def print_sample_data(conn: duckdb.DuckDBPyConnection, limit: int = 5):
    """Print sample records from database"""
    print(f"\nSample Shelter Occupancy Data:")
    print("-" * 120)

    result = conn.execute(f"""
        SELECT date, city, shelter_type, shelter_name, capacity, overnight, daytime
        FROM shelter_occupancy
        ORDER BY date DESC
        LIMIT {limit}
    """).fetchall()

    if result:
        print(f"{'Date':<12} {'City':<15} {'Type':<20} {'Shelter Name':<35} {'Capacity':<10} {'Overnight':<10} {'Daytime':<10}")
        print("-" * 120)

        for row in result:
            date_str = str(row[0]) if row[0] else ''
            city = (row[1] or '')[:13]
            shelter_type = (row[2] or '')[:18]
            shelter_name = (row[3] or '')[:33]
            capacity = str(row[4]) if row[4] is not None else 'N/A'
            overnight = str(row[5]) if row[5] is not None else 'N/A'
            daytime = str(row[6]) if row[6] is not None else 'N/A'
            print(f"{date_str:<12} {city:<15} {shelter_type:<20} {shelter_name:<35} {capacity:<10} {overnight:<10} {daytime:<10}")

        print("-" * 120)


def get_database_stats(conn: duckdb.DuckDBPyConnection):
    """Get and display database statistics"""
    # Total records
    result = conn.execute("SELECT COUNT(*) FROM shelter_occupancy").fetchone()
    total_records = result[0] if result else 0

    if total_records == 0:
        print("\nDatabase Statistics:")
        print(f"   Total Records: 0")
        print("   No data available for statistics")
        return

    # Date range
    result = conn.execute("SELECT MIN(date), MAX(date) FROM shelter_occupancy WHERE date IS NOT NULL").fetchone()
    min_date = result[0] if result and result[0] else None
    max_date = result[1] if result and result[1] else None

    # Unique cities
    result = conn.execute("SELECT COUNT(DISTINCT city) FROM shelter_occupancy WHERE city IS NOT NULL").fetchone()
    unique_cities = result[0] if result else 0

    # Unique shelter types
    result = conn.execute("SELECT COUNT(DISTINCT shelter_type) FROM shelter_occupancy WHERE shelter_type IS NOT NULL").fetchone()
    unique_types = result[0] if result else 0

    # Total capacity (latest record per shelter)
    result = conn.execute("""
        SELECT SUM(overnight) as total_overnight
        FROM shelter_occupancy
        WHERE overnight IS NOT NULL
    """).fetchone()
    total_overnight = result[0] if result and result[0] else 0

    # Cities list
    result = conn.execute("""
        SELECT city, COUNT(*) as count
        FROM shelter_occupancy
        WHERE city IS NOT NULL
        GROUP BY city
        ORDER BY count DESC
        LIMIT 10
    """).fetchall()
    cities = result if result else []

    # Shelter types
    result = conn.execute("""
        SELECT shelter_type, COUNT(*) as count
        FROM shelter_occupancy
        WHERE shelter_type IS NOT NULL
        GROUP BY shelter_type
        ORDER BY count DESC
    """).fetchall()
    shelter_types = result if result else []

    print("\nDatabase Statistics:")
    print(f"   Total Records: {total_records:,}")
    if min_date and max_date:
        print(f"   Date Range: {min_date} to {max_date}")
    print(f"   Unique Cities: {unique_cities}")
    print(f"   Unique Shelter Types: {unique_types}")
    print(f"   Total Overnight Stays: {total_overnight:,}")

    if cities:
        print(f"\n   Top 10 Cities by Record Count:")
        for city, count in cities:
            print(f"      {city}: {count:,} records")

    if shelter_types:
        print(f"\n   Shelter Types:")
        for stype, count in shelter_types:
            print(f"      {stype}: {count:,} records")


def main():
    parser = argparse.ArgumentParser(
        description='Generate shelter occupancy database from Alberta Open Data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_shelter_occupancy_data.py
  python generate_shelter_occupancy_data.py --csv-file shelter_data.csv
  python generate_shelter_occupancy_data.py --output shelter_occupancy.duckdb --clean
        """
    )

    parser.add_argument(
        '--csv-file',
        type=str,
        help='Path to local CSV file (if not provided, searches for CSV in same directory)'
    )

    parser.add_argument(
        '--output',
        type=str,
        default='shelter_occupancy.duckdb',
        help='Path to DuckDB database file (default: shelter_occupancy.duckdb)'
    )

    parser.add_argument(
        '--clean',
        action='store_true',
        help='Drop existing tables before generating new data'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("  Alberta Shelter Occupancy Database Generator")
    print("=" * 60)

    # Determine CSV file path
    script_dir = Path(__file__).parent

    if args.csv_file:
        csv_path = Path(args.csv_file)
    else:
        csv_path = find_csv_file(script_dir)
        if not csv_path:
            print("Error: No CSV file found in directory")
            print(f"   Looking in: {script_dir}")
            return 1

    # Resolve output path
    output_path = script_dir / args.output if not Path(args.output).is_absolute() else Path(args.output)

    print(f"Configuration:")
    print(f"   CSV File: {csv_path}")
    print(f"   Output: {output_path}")
    print(f"   Clean mode: {'Yes' if args.clean else 'No'}")
    print()

    # Check if CSV file exists
    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        return 1

    # Create database
    print("Creating database...")
    conn = create_database(str(output_path), clean=args.clean)

    # Load CSV data
    records = load_csv_data(str(csv_path))
    print(f"Loaded {len(records):,} records from CSV")

    # Insert records
    inserted = insert_records(conn, records)
    print(f"Inserted {inserted:,} records")

    # Show sample data
    print_sample_data(conn, limit=10)

    # Show statistics
    get_database_stats(conn)

    # Close connection
    conn.close()

    print(f"\nDatabase created successfully: {output_path}")
    print(f"\nNext steps:")
    print(f"   1. Test queries with DuckDB:")
    print(f"      duckdb {output_path} 'SELECT * FROM shelter_occupancy LIMIT 5;'")
    print(f"\n   2. Configure Intent adapter in config/adapters/intent.yaml")

    return 0


if __name__ == '__main__':
    sys.exit(main())
