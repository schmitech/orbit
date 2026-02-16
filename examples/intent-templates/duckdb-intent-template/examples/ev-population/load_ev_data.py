#!/usr/bin/env python3
"""
Electric Vehicle Population Data Loader

DESCRIPTION:
    Loads the Washington State Electric Vehicle Population Data from CSV into
    a DuckDB database. This script handles the data transformation and creates
    the necessary schema for analytical queries.

    Data source: https://catalog.data.gov/dataset/electric-vehicle-population-data
    
USAGE:
    python load_ev_data.py [--csv FILE] [--output FILE] [--clean]

ARGUMENTS:
    --csv FILE      Path to CSV file (default: Electric_Vehicle_Population_Data.csv)
    --output FILE   Path to DuckDB database file (default: ev_population.duckdb)
    --clean         Drop existing tables before loading new data
    --sample N      Only load first N records (for testing)

EXAMPLES:
    # Load full dataset
    python load_ev_data.py

    # Load from specific CSV file
    python load_ev_data.py --csv /path/to/data.csv

    # Load sample for testing
    python load_ev_data.py --sample 1000 --clean

    # Load to specific database
    python load_ev_data.py --output ./data/ev.duckdb

OUTPUT:
    Creates a DuckDB database with:
    - Table: electric_vehicles
    - Views: ev_by_county, ev_by_make, ev_adoption_trends, etc.
    - Indexes: On county, city, make, model, model_year, etc.

REQUIREMENTS:
    pip install duckdb

DATA FIELDS:
    The CSV contains these columns:
    - VIN (1-10): First 10 characters of Vehicle Identification Number
    - County: Washington State county
    - City: City of registration
    - State: State code (WA)
    - Postal Code: ZIP code
    - Model Year: Vehicle model year
    - Make: Vehicle manufacturer (Tesla, Nissan, etc.)
    - Model: Vehicle model (Model 3, Leaf, etc.)
    - Electric Vehicle Type: BEV or PHEV
    - Clean Alternative Fuel Vehicle (CAFV) Eligibility
    - Electric Range: Range in miles (0 if unknown)
    - Legislative District: WA state legislative district
    - DOL Vehicle ID: Unique identifier
    - Vehicle Location: POINT coordinates
    - Electric Utility: Serving utility company
    - 2020 Census Tract: Census tract identifier

SEE ALSO:
    - ev_population.sql - Database schema
    - ev_population_test_queries.md - Sample queries
    - demo-questions.md - Demo questions for officials

AUTHOR:
    DuckDB EV Population Analyzer v1.0.0
"""

import duckdb
import argparse
import sys
import re
from pathlib import Path


def parse_location(location_str):
    """Extract longitude and latitude from POINT string"""
    if not location_str or location_str == '':
        return None, None

    # Parse POINT (-122.89165 47.03954) format
    match = re.match(r'POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)', location_str)
    if match:
        try:
            longitude = float(match.group(1))
            latitude = float(match.group(2))
            return longitude, latitude
        except (ValueError, IndexError):
            return None, None
    return None, None


def create_schema(conn, clean=False):
    """Create database schema"""
    if clean:
        conn.execute("DROP VIEW IF EXISTS cafv_eligibility_summary")
        conn.execute("DROP VIEW IF EXISTS ev_by_utility")
        conn.execute("DROP VIEW IF EXISTS ev_by_district")
        conn.execute("DROP VIEW IF EXISTS ev_adoption_trends")
        conn.execute("DROP VIEW IF EXISTS ev_by_make")
        conn.execute("DROP VIEW IF EXISTS ev_by_county")
        conn.execute("DROP TABLE IF EXISTS electric_vehicles")
        print("Cleaned existing data")

    # Create table directly (more reliable than parsing SQL file)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS electric_vehicles (
            id INTEGER PRIMARY KEY,
            vin_prefix VARCHAR(10) NOT NULL,
            county VARCHAR(100) NOT NULL,
            city VARCHAR(100) NOT NULL,
            state VARCHAR(2) NOT NULL DEFAULT 'WA',
            postal_code VARCHAR(10),
            model_year INTEGER NOT NULL,
            make VARCHAR(50) NOT NULL,
            model VARCHAR(100) NOT NULL,
            ev_type VARCHAR(50) NOT NULL,
            cafv_eligibility VARCHAR(100),
            electric_range INTEGER DEFAULT 0,
            legislative_district INTEGER,
            dol_vehicle_id BIGINT UNIQUE,
            vehicle_location VARCHAR(100),
            longitude DOUBLE,
            latitude DOUBLE,
            electric_utility VARCHAR(200),
            census_tract BIGINT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ev_county ON electric_vehicles(county)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ev_city ON electric_vehicles(city)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ev_postal_code ON electric_vehicles(postal_code)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ev_model_year ON electric_vehicles(model_year)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ev_make ON electric_vehicles(make)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ev_model ON electric_vehicles(model)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ev_type ON electric_vehicles(ev_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ev_cafv ON electric_vehicles(cafv_eligibility)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ev_range ON electric_vehicles(electric_range)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ev_district ON electric_vehicles(legislative_district)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ev_utility ON electric_vehicles(electric_utility)")

    return conn


def load_csv_data(conn, csv_path, sample_limit=None):
    """Load data from CSV file into database"""

    # Check if file exists
    if not Path(csv_path).exists():
        print(f"Error: CSV file not found: {csv_path}")
        return 0

    # Use DuckDB's native CSV reader for speed
    limit_clause = f"LIMIT {sample_limit}" if sample_limit else ""

    # First, load into a temporary table
    conn.execute(f"""
        CREATE TEMPORARY TABLE temp_ev AS
        SELECT * FROM read_csv_auto('{csv_path}', header=true)
        {limit_clause}
    """)

    # Get column names from temp table
    columns = conn.execute("DESCRIBE temp_ev").fetchall()
    column_names = [col[0] for col in columns]

    print(f"CSV columns detected: {column_names}")

    # Map CSV columns to our schema
    # Handle various possible column name formats
    column_mapping = {}
    for col in column_names:
        col_lower = col.lower().replace(' ', '_').replace('(', '').replace(')', '')
        if 'vin' in col_lower:
            column_mapping['vin_prefix'] = col
        elif col_lower == 'county':
            column_mapping['county'] = col
        elif col_lower == 'city':
            column_mapping['city'] = col
        elif col_lower == 'state':
            column_mapping['state'] = col
        elif 'postal' in col_lower or 'zip' in col_lower:
            column_mapping['postal_code'] = col
        elif 'model_year' in col_lower or col_lower == 'model year':
            column_mapping['model_year'] = col
        elif col_lower == 'make':
            column_mapping['make'] = col
        elif col_lower == 'model':
            column_mapping['model'] = col
        elif 'electric_vehicle_type' in col_lower or 'ev_type' in col_lower:
            column_mapping['ev_type'] = col
        elif 'cafv' in col_lower or 'clean_alternative' in col_lower:
            column_mapping['cafv_eligibility'] = col
        elif 'electric_range' in col_lower or col_lower == 'electric range':
            column_mapping['electric_range'] = col
        elif 'legislative' in col_lower:
            column_mapping['legislative_district'] = col
        elif 'dol' in col_lower and 'vehicle' in col_lower:
            column_mapping['dol_vehicle_id'] = col
        elif 'location' in col_lower and 'vehicle' in col_lower:
            column_mapping['vehicle_location'] = col
        elif 'utility' in col_lower:
            column_mapping['electric_utility'] = col
        elif 'census' in col_lower:
            column_mapping['census_tract'] = col

    print(f"Column mapping: {column_mapping}")

    # Get the current max ID to avoid primary key conflicts
    max_id_result = conn.execute("SELECT COALESCE(MAX(id), 0) FROM electric_vehicles").fetchone()
    max_id = max_id_result[0] if max_id_result else 0

    # Insert data with transformation
    insert_sql = f"""
        INSERT INTO electric_vehicles (
            id,
            vin_prefix,
            county,
            city,
            state,
            postal_code,
            model_year,
            make,
            model,
            ev_type,
            cafv_eligibility,
            electric_range,
            legislative_district,
            dol_vehicle_id,
            vehicle_location,
            longitude,
            latitude,
            electric_utility,
            census_tract
        )
        SELECT
            ROW_NUMBER() OVER () + {max_id} as id,
            COALESCE("{column_mapping.get('vin_prefix', 'VIN (1-10)')}", 'UNKNOWN'),
            COALESCE("{column_mapping.get('county', 'County')}", 'Unknown'),
            COALESCE("{column_mapping.get('city', 'City')}", 'Unknown'),
            COALESCE("{column_mapping.get('state', 'State')}", 'WA'),
            "{column_mapping.get('postal_code', 'Postal Code')}",
            COALESCE(TRY_CAST("{column_mapping.get('model_year', 'Model Year')}" AS INTEGER), 2020),
            COALESCE("{column_mapping.get('make', 'Make')}", 'Unknown'),
            COALESCE("{column_mapping.get('model', 'Model')}", 'Unknown'),
            COALESCE("{column_mapping.get('ev_type', 'Electric Vehicle Type')}", 'Unknown'),
            "{column_mapping.get('cafv_eligibility', 'Clean Alternative Fuel Vehicle (CAFV) Eligibility')}",
            COALESCE(TRY_CAST("{column_mapping.get('electric_range', 'Electric Range')}" AS INTEGER), 0),
            TRY_CAST("{column_mapping.get('legislative_district', 'Legislative District')}" AS INTEGER),
            TRY_CAST("{column_mapping.get('dol_vehicle_id', 'DOL Vehicle ID')}" AS BIGINT),
            "{column_mapping.get('vehicle_location', 'Vehicle Location')}",
            -- Extract longitude from POINT string
            CASE
                WHEN "{column_mapping.get('vehicle_location', 'Vehicle Location')}" LIKE 'POINT%'
                THEN TRY_CAST(
                    REGEXP_EXTRACT("{column_mapping.get('vehicle_location', 'Vehicle Location')}",
                    'POINT\\s*\\(\\s*([-\\d.]+)', 1) AS DOUBLE)
                ELSE NULL
            END,
            -- Extract latitude from POINT string
            CASE
                WHEN "{column_mapping.get('vehicle_location', 'Vehicle Location')}" LIKE 'POINT%'
                THEN TRY_CAST(
                    REGEXP_EXTRACT("{column_mapping.get('vehicle_location', 'Vehicle Location')}",
                    'POINT\\s*\\([^\\s]+\\s+([-\\d.]+)', 1) AS DOUBLE)
                ELSE NULL
            END,
            "{column_mapping.get('electric_utility', 'Electric Utility')}",
            TRY_CAST("{column_mapping.get('census_tract', '2020 Census Tract')}" AS BIGINT)
        FROM temp_ev
        WHERE "{column_mapping.get('county', 'County')}" IS NOT NULL
          AND "{column_mapping.get('city', 'City')}" IS NOT NULL
    """

    conn.execute(insert_sql)

    # Get count of inserted records
    result = conn.execute("SELECT COUNT(*) FROM electric_vehicles").fetchone()
    count = result[0] if result else 0

    # Clean up temp table
    conn.execute("DROP TABLE IF EXISTS temp_ev")

    return count


def print_sample_data(conn, limit=10):
    """Print sample records from database"""
    print(f"\nSample Data (first {limit} records):")
    print("-" * 120)

    result = conn.execute(f"""
        SELECT
            id, vin_prefix, county, city, model_year, make, model,
            ev_type, electric_range
        FROM electric_vehicles
        ORDER BY id
        LIMIT {limit}
    """).fetchall()

    if result:
        print(f"{'ID':<5} {'VIN':<12} {'County':<15} {'City':<15} {'Year':<6} {'Make':<12} {'Model':<15} {'Type':<6} {'Range':<6}")
        print("-" * 120)

        for row in result:
            ev_type = 'BEV' if 'BEV' in str(row[7]) else 'PHEV'
            print(f"{row[0]:<5} {row[1]:<12} {row[2]:<15} {row[3]:<15} {row[4]:<6} {row[5]:<12} {row[6]:<15} {ev_type:<6} {row[8]:<6}")

    print("-" * 120)


def print_statistics(conn):
    """Print database statistics"""
    print("\nDatabase Statistics:")
    print("=" * 60)

    # Total vehicles
    result = conn.execute("SELECT COUNT(*) FROM electric_vehicles").fetchone()
    print(f"Total Registered EVs: {result[0]:,}")

    # BEV vs PHEV
    result = conn.execute("""
        SELECT
            COUNT(CASE WHEN ev_type LIKE '%BEV%' THEN 1 END) as bev,
            COUNT(CASE WHEN ev_type LIKE '%PHEV%' THEN 1 END) as phev
        FROM electric_vehicles
    """).fetchone()
    print(f"Battery Electric (BEV): {result[0]:,}")
    print(f"Plug-in Hybrid (PHEV): {result[1]:,}")

    # Unique makes
    result = conn.execute("SELECT COUNT(DISTINCT make) FROM electric_vehicles").fetchone()
    print(f"Unique Manufacturers: {result[0]}")

    # Unique models
    result = conn.execute("SELECT COUNT(DISTINCT model) FROM electric_vehicles").fetchone()
    print(f"Unique Models: {result[0]}")

    # Counties covered
    result = conn.execute("SELECT COUNT(DISTINCT county) FROM electric_vehicles").fetchone()
    print(f"Counties Covered: {result[0]}")

    # Cities covered
    result = conn.execute("SELECT COUNT(DISTINCT city) FROM electric_vehicles").fetchone()
    print(f"Cities Covered: {result[0]}")

    # Model year range
    result = conn.execute("""
        SELECT MIN(model_year), MAX(model_year)
        FROM electric_vehicles
    """).fetchone()
    print(f"Model Year Range: {result[0]} - {result[1]}")

    # Average electric range
    result = conn.execute("""
        SELECT AVG(electric_range)
        FROM electric_vehicles
        WHERE electric_range > 0
    """).fetchone()
    print(f"Average Electric Range: {result[0]:.1f} miles")

    print("\nTop 5 Manufacturers:")
    result = conn.execute("""
        SELECT make, COUNT(*) as count
        FROM electric_vehicles
        GROUP BY make
        ORDER BY count DESC
        LIMIT 5
    """).fetchall()
    for row in result:
        print(f"  {row[0]}: {row[1]:,}")

    print("\nTop 5 Counties:")
    result = conn.execute("""
        SELECT county, COUNT(*) as count
        FROM electric_vehicles
        GROUP BY county
        ORDER BY count DESC
        LIMIT 5
    """).fetchall()
    for row in result:
        print(f"  {row[0]}: {row[1]:,}")

    print("\nCAFV Eligibility Distribution:")
    result = conn.execute("""
        SELECT
            cafv_eligibility,
            COUNT(*) as count,
            ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) as pct
        FROM electric_vehicles
        GROUP BY cafv_eligibility
        ORDER BY count DESC
    """).fetchall()
    for row in result:
        eligibility = row[0][:50] + '...' if len(row[0]) > 50 else row[0]
        print(f"  {eligibility}: {row[1]:,} ({row[2]}%)")


def main():
    parser = argparse.ArgumentParser(
        description='Load Electric Vehicle Population Data into DuckDB',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python load_ev_data.py
  python load_ev_data.py --csv my_data.csv --output ev.duckdb
  python load_ev_data.py --sample 1000 --clean
        """
    )

    parser.add_argument(
        '--csv',
        type=str,
        default='Electric_Vehicle_Population_Data.csv',
        help='Path to CSV file (default: Electric_Vehicle_Population_Data.csv)'
    )

    parser.add_argument(
        '--output',
        type=str,
        default='ev_population.duckdb',
        help='Path to DuckDB database file (default: ev_population.duckdb)'
    )

    parser.add_argument(
        '--clean',
        action='store_true',
        help='Drop existing tables before loading new data'
    )

    parser.add_argument(
        '--sample',
        type=int,
        default=None,
        help='Only load first N records (for testing)'
    )

    args = parser.parse_args()

    # Resolve paths relative to script directory
    script_dir = Path(__file__).parent
    csv_path = script_dir / args.csv if not Path(args.csv).is_absolute() else Path(args.csv)
    db_path = script_dir / args.output if not Path(args.output).is_absolute() else Path(args.output)

    print("=" * 60)
    print("  Electric Vehicle Population Data Loader")
    print("=" * 60)
    print(f"CSV File: {csv_path}")
    print(f"Database: {db_path}")
    print(f"Clean mode: {'Yes' if args.clean else 'No'}")
    if args.sample:
        print(f"Sample limit: {args.sample:,} records")
    print()

    # Connect to database
    print("Connecting to database...")
    conn = duckdb.connect(str(db_path))

    # Create schema
    print("Creating schema...")
    create_schema(conn, clean=args.clean)

    # Load data
    print("Loading CSV data...")
    count = load_csv_data(conn, str(csv_path), args.sample)
    print(f"Loaded {count:,} records")

    if count > 0:
        # Print sample data
        print_sample_data(conn)

        # Print statistics
        print_statistics(conn)

    # Close connection
    conn.close()

    print(f"\nDatabase created successfully: {db_path}")
    print("\nNext steps:")
    print("  1. Test queries with DuckDB:")
    print(f"     duckdb {db_path} 'SELECT * FROM electric_vehicles LIMIT 5;'")
    print("\n  2. Run test queries:")
    print("     ./test_ev_queries.sh")
    print("\n  3. Configure Intent adapter in config/adapters.yaml")

    return 0


if __name__ == '__main__':
    sys.exit(main())
