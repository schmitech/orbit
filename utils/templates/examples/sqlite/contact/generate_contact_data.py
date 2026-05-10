#!/usr/bin/env python3
"""
Contact Database Sample Data Generator

DESCRIPTION:
    Generates realistic sample data for the contact database schema using the
    Faker library. Creates a SQLite database with synthetic user records for
    testing the SQL Intent Template Generator.

    The users table contains: id, name, email, age, city, created_at.

USAGE:
    python generate_contact_data.py [--records N] [--output FILE] [--seed N] [--clean]

ARGUMENTS:
    --records N   Number of user records to generate (default: 100)
    --output FILE Path to SQLite database file (default: contact.db)
    --seed N      Random seed for reproducibility
    --clean       Drop and recreate the table before inserting

EXAMPLES:
    python generate_contact_data.py
    python generate_contact_data.py --records 500 --seed 42
    python generate_contact_data.py --output ./data/contact.db --clean

REQUIREMENTS:
    pip install faker
"""

import sqlite3
import argparse
import sys
import random
from datetime import datetime, timedelta

try:
    from faker import Faker
except ImportError:
    print("❌ Error: Faker library is required")
    print("   Install with: pip install faker")
    sys.exit(1)


CITIES = [
    ("New York", 30),
    ("Los Angeles", 20),
    ("Chicago", 15),
    ("Houston", 10),
    ("Phoenix", 8),
    ("Philadelphia", 7),
    ("San Antonio", 6),
    ("San Diego", 6),
    ("Dallas", 6),
    ("Seattle", 5),
    ("Boston", 5),
    ("Denver", 4),
    ("Austin", 4),
    ("Nashville", 3),
    ("Portland", 3),
]


def weighted_city() -> str:
    names = [c[0] for c in CITIES]
    weights = [c[1] for c in CITIES]
    return random.choices(names, weights=weights, k=1)[0]


def create_table(conn: sqlite3.Connection, clean: bool = False) -> None:
    cursor = conn.cursor()
    if clean:
        cursor.execute("DROP TABLE IF EXISTS users")
        print("🧹 Dropped existing users table")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            age INTEGER,
            city TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_city  ON users(city)")
    conn.commit()


def generate_records(count: int) -> list:
    fake = Faker('en_US')
    records = []
    seen_emails: set = set()
    now = datetime.now()

    for _ in range(count):
        # Unique email with retry
        for _ in range(10):
            email = fake.email()
            if email not in seen_emails:
                seen_emails.add(email)
                break
        else:
            continue  # give up on this record rather than duplicate

        name = fake.name()
        age = random.randint(18, 75)
        city = weighted_city()

        # created_at spread over the last 3 years, weighted toward recent
        days_ago = int(random.triangular(0, 1095, 90))
        created_at = (now - timedelta(days=days_ago)).strftime('%Y-%m-%d %H:%M:%S')

        records.append((name, email, age, city, created_at))

    return records


def insert_records(conn: sqlite3.Connection, records: list) -> tuple:
    cursor = conn.cursor()
    inserted = skipped = 0
    for rec in records:
        try:
            cursor.execute(
                "INSERT INTO users (name, email, age, city, created_at) VALUES (?, ?, ?, ?, ?)",
                rec
            )
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1
    conn.commit()
    return inserted, skipped


def print_sample(conn: sqlite3.Connection, limit: int = 10) -> None:
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, age, city, created_at FROM users LIMIT ?", (limit,))
    rows = cursor.fetchall()
    print(f"\n{'ID':<5} {'Name':<25} {'Email':<30} {'Age':<5} {'City':<15} {'Created At'}")
    print("-" * 95)
    for r in rows:
        print(f"{r[0]:<5} {r[1]:<25} {r[2]:<30} {r[3]:<5} {r[4]:<15} {r[5]}")


def print_stats(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT AVG(age), MIN(age), MAX(age) FROM users")
    avg_age, min_age, max_age = cursor.fetchone()
    cursor.execute("SELECT city, COUNT(*) c FROM users GROUP BY city ORDER BY c DESC LIMIT 5")
    top_cities = cursor.fetchall()

    print(f"\n📈 Stats: {total} users | age avg={avg_age:.1f} min={min_age} max={max_age}")
    print("   Top cities: " + ", ".join(f"{c} ({n})" for c, n in top_cities))


def main() -> int:
    parser = argparse.ArgumentParser(description='Generate sample contact data')
    parser.add_argument('--records', type=int, default=100,
                        help='Number of user records to generate (default: 100)')
    parser.add_argument('--output', type=str, default='contact.db',
                        help='Path to SQLite database file (default: contact.db)')
    parser.add_argument('--seed', type=int, default=None,
                        help='Random seed for reproducibility')
    parser.add_argument('--clean', action='store_true',
                        help='Drop and recreate the table before inserting')
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)
        Faker.seed(args.seed)

    if args.records < 1:
        print("❌ --records must be at least 1")
        return 1

    print("=" * 50)
    print("  Contact Database Generator")
    print("=" * 50)
    print(f"  Records : {args.records}")
    print(f"  Output  : {args.output}")
    print(f"  Seed    : {args.seed or 'random'}")
    print(f"  Clean   : {args.clean}")
    print()

    conn = sqlite3.connect(args.output)
    create_table(conn, clean=args.clean)

    print(f"👥 Generating {args.records} users...")
    records = generate_records(args.records)

    print("💾 Inserting records...")
    inserted, skipped = insert_records(conn, records)
    print(f"   ✅ Inserted {inserted}" + (f"  ⚠️  Skipped {skipped} duplicates" if skipped else ""))

    print_sample(conn)
    print_stats(conn)
    conn.close()

    print(f"\n✅ Database ready: {args.output}")
    print("\n💡 Next steps:")
    print(f"   sqlite3 {args.output} 'SELECT * FROM users LIMIT 5;'")
    print("   ./run_contact_example.sh --generate")
    return 0


if __name__ == '__main__':
    sys.exit(main())
