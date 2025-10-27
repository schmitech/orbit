#!/usr/bin/env python3
"""
Contact Database Sample Data Generator

DESCRIPTION:
    Generates realistic sample data for the contact database schema using the
    Faker library. Creates a SQLite database with synthetic user records for
    testing the SQL Intent Template Generator.

    This script populates the 'users' table with:
    - Realistic names (first + last name)
    - Valid email addresses
    - Random ages (18-80)
    - Major US cities
    - Timestamps for created_at

USAGE:
    python generate_contact_data.py [--records N] [--output FILE]

ARGUMENTS:
    --records N     Number of user records to generate (default: 100)
    --output FILE   Path to SQLite database file (default: contact.db)
    --clean         Drop existing table before generating new data

EXAMPLES:
    # Generate 100 records (default)
    python generate_contact_data.py

    # Generate 1000 records
    python generate_contact_data.py --records 1000

    # Generate to specific database file
    python generate_contact_data.py --output ./data/contacts.db

    # Clean existing data and generate fresh
    python generate_contact_data.py --records 500 --clean

OUTPUT:
    Creates a SQLite database with the following structure:
    - Database: contact.db (or specified path)
    - Table: users
    - Columns: id, name, email, age, city, created_at
    - Indexes: email (unique)

REQUIREMENTS:
    pip install faker

SAMPLE DATA:
    id  | name           | email                 | age | city        | created_at
    ----|----------------|----------------------|-----|-------------|-------------------
    1   | John Smith     | jsmith@example.com   | 34  | New York    | 2024-01-15 10:23:45
    2   | Sarah Johnson  | sarahj@example.com   | 28  | Los Angeles | 2024-01-16 14:32:11
    3   | Michael Brown  | mbrown@example.com   | 45  | Chicago     | 2024-01-17 09:15:22

TESTING WITH INTENT ADAPTER:
    After generating data, you can test with the SQL Intent Template Generator:

    1. Generate templates:
       cd ../..
       ./generate_templates.sh \\
         --schema examples/contact.sql \\
         --queries examples/contact_test_queries.md \\
         --domain configs/contact-config.yaml \\
         --output contact-templates.yaml

    2. Test with Intent adapter:
       - Add adapter to config/adapters.yaml (see below)
       - Start Orbit server
       - Query: "Show me all users from New York"

SEE ALSO:
    - contact.sql - Database schema
    - contact_test_queries.md - Sample queries for template generation
    - ../../README.md - SQL Intent Template Generator documentation

AUTHOR:
    SQL Intent Template Generator v1.0.0
"""

import sqlite3
import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta
import random

try:
    from faker import Faker
except ImportError:
    print("❌ Error: Faker library is required")
    print("   Install with: pip install faker")
    sys.exit(1)


# US cities for realistic location data
US_CITIES = [
    "New York", "Los Angeles", "Chicago", "Houston", "Phoenix",
    "Philadelphia", "San Antonio", "San Diego", "Dallas", "San Jose",
    "Austin", "Jacksonville", "Fort Worth", "Columbus", "Charlotte",
    "San Francisco", "Indianapolis", "Seattle", "Denver", "Washington",
    "Boston", "El Paso", "Nashville", "Detroit", "Oklahoma City",
    "Portland", "Las Vegas", "Memphis", "Louisville", "Baltimore",
    "Milwaukee", "Albuquerque", "Tucson", "Fresno", "Sacramento",
    "Miami", "Atlanta", "Kansas City", "Colorado Springs", "Raleigh"
]


def create_database(db_path: str, clean: bool = False):
    """Create database and schema"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON")

    # Drop table if clean mode
    if clean:
        cursor.execute("DROP TABLE IF EXISTS users")
        print("🧹 Cleaned existing data")

    # Create users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            age INTEGER,
            city TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    return conn


def generate_users(count: int) -> list:
    """Generate fake user records"""
    fake = Faker()
    users = []

    # Generate records with varied creation dates (last 2 years)
    start_date = datetime.now() - timedelta(days=730)

    for _ in range(count):
        # Generate realistic created_at timestamp
        days_offset = random.randint(0, 730)
        hours_offset = random.randint(0, 23)
        minutes_offset = random.randint(0, 59)
        created_at = start_date + timedelta(
            days=days_offset,
            hours=hours_offset,
            minutes=minutes_offset
        )

        user = {
            'name': fake.name(),
            'email': fake.email(),
            'age': random.randint(18, 80),
            'city': random.choice(US_CITIES),
            'created_at': created_at.strftime('%Y-%m-%d %H:%M:%S')
        }
        users.append(user)

    return users


def insert_users(conn: sqlite3.Connection, users: list) -> int:
    """Insert user records into database"""
    cursor = conn.cursor()
    inserted = 0
    skipped = 0

    for user in users:
        try:
            cursor.execute("""
                INSERT INTO users (name, email, age, city, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                user['name'],
                user['email'],
                user['age'],
                user['city'],
                user['created_at']
            ))
            inserted += 1
        except sqlite3.IntegrityError:
            # Skip duplicate emails
            skipped += 1
            continue

    conn.commit()
    return inserted, skipped


def print_sample_data(conn: sqlite3.Connection, limit: int = 5):
    """Print sample records from database"""
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT id, name, email, age, city, created_at
        FROM users
        ORDER BY id
        LIMIT {limit}
    """)

    rows = cursor.fetchall()

    print("\n📊 Sample Data:")
    print("-" * 100)
    print(f"{'ID':<5} {'Name':<20} {'Email':<30} {'Age':<5} {'City':<20} {'Created':<20}")
    print("-" * 100)

    for row in rows:
        print(f"{row[0]:<5} {row[1]:<20} {row[2]:<30} {row[3]:<5} {row[4]:<20} {row[5]:<20}")

    print("-" * 100)


def get_database_stats(conn: sqlite3.Connection):
    """Get and display database statistics"""
    cursor = conn.cursor()

    # Total users
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    # Unique cities
    cursor.execute("SELECT COUNT(DISTINCT city) FROM users")
    unique_cities = cursor.fetchone()[0]

    # Age distribution
    cursor.execute("SELECT MIN(age), MAX(age), AVG(age) FROM users")
    min_age, max_age, avg_age = cursor.fetchone()

    # Most common cities
    cursor.execute("""
        SELECT city, COUNT(*) as count
        FROM users
        GROUP BY city
        ORDER BY count DESC
        LIMIT 5
    """)
    top_cities = cursor.fetchall()

    print("\n📈 Database Statistics:")
    print(f"   Total Users: {total_users}")
    print(f"   Unique Cities: {unique_cities}")
    print(f"   Age Range: {min_age} - {max_age} (avg: {avg_age:.1f})")
    print(f"\n   Top 5 Cities:")
    for city, count in top_cities:
        print(f"      {city}: {count} users")


def main():
    parser = argparse.ArgumentParser(
        description='Generate sample contact data using Faker',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_contact_data.py --records 1000
  python generate_contact_data.py --output mycontacts.db --clean
  python generate_contact_data.py --records 5000 --clean
        """
    )

    parser.add_argument(
        '--records',
        type=int,
        default=100,
        help='Number of user records to generate (default: 100)'
    )

    parser.add_argument(
        '--output',
        type=str,
        default='contact.db',
        help='Path to SQLite database file (default: contact.db)'
    )

    parser.add_argument(
        '--clean',
        action='store_true',
        help='Drop existing table before generating new data'
    )

    args = parser.parse_args()

    # Validate records
    if args.records < 1:
        print("❌ Error: --records must be at least 1")
        return 1

    if args.records > 100000:
        print("⚠️  Warning: Generating more than 100,000 records may take a while")
        response = input("   Continue? (y/n): ")
        if response.lower() != 'y':
            print("   Cancelled")
            return 0

    print("=" * 60)
    print("  Contact Database Generator")
    print("=" * 60)
    print(f"📝 Configuration:")
    print(f"   Records: {args.records}")
    print(f"   Output: {args.output}")
    print(f"   Clean mode: {'Yes' if args.clean else 'No'}")
    print()

    # Create database
    print("🔨 Creating database...")
    conn = create_database(args.output, clean=args.clean)

    # Generate users
    print(f"👥 Generating {args.records} users...")
    users = generate_users(args.records)

    # Insert users
    print("💾 Inserting data...")
    inserted, skipped = insert_users(conn, users)

    print(f"✅ Inserted {inserted} records")
    if skipped > 0:
        print(f"⚠️  Skipped {skipped} duplicates")

    # Show sample data
    print_sample_data(conn, limit=10)

    # Show statistics
    get_database_stats(conn)

    # Close connection
    conn.close()

    print(f"\n✅ Database created successfully: {args.output}")
    print(f"\n💡 Next steps:")
    print(f"   1. Test queries with sqlite3:")
    print(f"      sqlite3 {args.output} 'SELECT * FROM users LIMIT 5;'")
    print(f"\n   2. Generate SQL templates:")
    print(f"      cd ../..")
    print(f"      ./generate_templates.sh \\")
    print(f"        --schema examples/contact.sql \\")
    print(f"        --queries examples/contact_test_queries.md \\")
    print(f"        --domain configs/contact-config.yaml \\")
    print(f"        --output contact-templates.yaml")
    print(f"\n   3. Configure Intent adapter in config/adapters.yaml")
    print(f"      (See script documentation for example)")

    return 0


if __name__ == '__main__':
    sys.exit(main())
