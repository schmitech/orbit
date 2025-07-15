#!/usr/bin/env python3
"""
PostgreSQL test data management script for adapter testing.
Generates Canadian customer and order data using Faker.

Usage Examples:
    # Insert fresh data (adds to existing data)
    python customer-order.py --action insert --customers 100 --orders 500
    
    # Insert fresh data after cleaning existing data
    python customer-order.py --action insert --clean --customers 50 --orders 200
    
    # Query specific customer
    python customer-order.py --action query --customer-id 1
    
    # Query top customers by spending
    python customer-order.py --action query
    
    # Delete all data (requires confirmation)
    python customer-order.py --action delete --confirm
    
    # Completely recreate tables from scratch (requires confirmation)
    python customer-order.py --action recreate --confirm
    
    # Use custom database connection
    python customer-order.py --action insert --host localhost --port 5432 --database mydb --user myuser --password mypass

Actions:
    insert    - Insert customer and order data
    query     - Query existing data
    delete    - Delete all data from tables
    recreate  - Drop and recreate tables with full schema

Flags:
    --clean   - Clean existing data before inserting (for insert action)
    --confirm - Confirm destructive operations (delete, recreate)
"""

import argparse
import psycopg2
from psycopg2.extras import RealDictCursor
from faker import Faker
import random
from datetime import datetime, timedelta
import json
from decimal import Decimal
import os
from dotenv import load_dotenv, find_dotenv

def reload_env_variables():
    """Reload environment variables from .env file"""
    env_file = find_dotenv()
    if env_file:
        load_dotenv(env_file, override=True)
        print(f"🔄 Reloaded environment variables from: {env_file}")
    else:
        print("⚠️  No .env file found")

# Initialize Faker with multiple locales for international data
fake = Faker(['en_CA', 'en_US', 'en_GB', 'fr_FR', 'de_DE', 'es_ES', 'it_IT', 'ja_JP', 'ko_KR', 'zh_CN'])
# Set seed for reproducible results (optional)
# fake.seed_instance(12345)

# Database configuration from environment variables
def get_db_config():
    """Get database configuration from environment variables and construct connection string."""
    # Reload environment variables to get latest values
    reload_env_variables()
    
    # Get individual environment variables
    host = os.getenv('DATASOURCE_POSTGRES_HOST', 'localhost')
    port = int(os.getenv('DATASOURCE_POSTGRES_PORT', '5432'))
    database = os.getenv('DATASOURCE_POSTGRES_DATABASE', 'test_db')
    user = os.getenv('DATASOURCE_POSTGRES_USERNAME', 'postgres')
    password = os.getenv('DATASOURCE_POSTGRES_PASSWORD', 'postgres')
    sslmode = os.getenv('DATASOURCE_POSTGRES_SSL_MODE', 'require')
    
    # Construct connection string dynamically
    connection_string = f"postgresql://{user}:{password}@{host}:{port}/{database}"
    print(f"🔗 Using connection string: postgresql://{user}:{'*' * len(password)}@{host}:{port}/{database}")
    print(f"🔒 SSL Mode: {sslmode}")
    
    return {
        'host': host,
        'port': port,
        'database': database,
        'user': user,
        'password': password,
        'sslmode': sslmode
    }


def get_connection():
    """Create and return a database connection."""
    # Get fresh configuration each time
    config = get_db_config()
    return psycopg2.connect(**config)


def insert_customers(conn, count=100):
    """Insert fake customer data with unique emails."""
    cursor = conn.cursor()
    customers = []
    inserted_count = 0
    attempts = 0
    max_attempts = count * 10  # Prevent infinite loops
    
    print(f"Inserting {count} customers with unique emails...")
    
    while inserted_count < count and attempts < max_attempts:
        attempts += 1
        
        # Generate unique email using timestamp and random components
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_suffix = fake.random_number(digits=4)
        unique_email = f"{fake.user_name()}{timestamp}{random_suffix}@{fake.domain_name()}"
        
        customer = (
            fake.name(),
            unique_email,
            fake.phone_number()[:20],
            fake.street_address(),
            fake.city(),
            "Canada"  # Ensure Canadian data
        )
        
        try:
            cursor.execute("""
                INSERT INTO customers (name, email, phone, address, city, country)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, customer)
            
            customer_id = cursor.fetchone()[0]
            customers.append(customer_id)
            inserted_count += 1
            
            if inserted_count % 100 == 0:
                print(f"  Progress: {inserted_count}/{count} customers inserted")
                
        except psycopg2.IntegrityError as e:
            if "customers_email_key" in str(e):
                # Email already exists, continue to next attempt
                continue
            else:
                # Other integrity error, re-raise
                raise e
    
    conn.commit()
    print(f"✓ Inserted {inserted_count} customers (after {attempts} attempts)")
    
    if inserted_count < count:
        print(f"⚠️  Could only insert {inserted_count} customers due to email conflicts")
    
    return customers


def insert_orders(conn, customer_ids, count=500):
    """Insert fake order data with international shipping addresses."""
    cursor = conn.cursor()
    
    print(f"Inserting {count} orders with international shipping addresses...")
    
    # Payment methods
    payment_methods = ['credit_card', 'debit_card', 'paypal', 'bank_transfer', 'cash']
    statuses = ['pending', 'processing', 'shipped', 'delivered', 'cancelled']
    
    # International shipping destinations with weights (more likely to ship to certain countries)
    shipping_destinations = [
        ('Canada', 0.4),      # 40% - Canadian customers
        ('United States', 0.25),  # 25% - US shipping
        ('United Kingdom', 0.1),  # 10% - UK shipping
        ('Germany', 0.08),    # 8% - German shipping
        ('France', 0.06),     # 6% - French shipping
        ('Japan', 0.04),      # 4% - Japanese shipping
        ('Australia', 0.03),  # 3% - Australian shipping
        ('Spain', 0.02),      # 2% - Spanish shipping
        ('Italy', 0.01),      # 1% - Italian shipping
        ('South Korea', 0.01) # 1% - Korean shipping
    ]
    
    for i in range(count):
        # Random date within the last 30 days
        days_ago = random.randint(0, 30)
        order_date = datetime.now() - timedelta(days=days_ago)
        
        # Random total between $10 and $1000
        total = round(random.uniform(10.0, 1000.0), 2)
        
        # Select shipping destination based on weights
        destination = random.choices(
            [dest[0] for dest in shipping_destinations],
            weights=[dest[1] for dest in shipping_destinations]
        )[0]
        
        # Generate international shipping address
        if destination == 'Canada':
            # Canadian address format
            street_address = fake.street_address()
            city = fake.city()
            province = fake.state_abbr() if hasattr(fake, 'state_abbr') else fake.state()
            postal_code = fake.postcode()
            shipping_address = f"{street_address}, {city}, {province} {postal_code}, Canada"
        elif destination == 'United States':
            # US address format
            street_address = fake.street_address()
            city = fake.city()
            state = fake.state_abbr()
            zip_code = fake.postcode()
            shipping_address = f"{street_address}, {city}, {state} {zip_code}, USA"
        elif destination == 'United Kingdom':
            # UK address format
            street_address = fake.street_address()
            city = fake.city()
            postcode = fake.postcode()
            shipping_address = f"{street_address}, {city}, {postcode}, United Kingdom"
        elif destination in ['Germany', 'France', 'Spain', 'Italy']:
            # European address format
            street_address = fake.street_address()
            city = fake.city()
            postal_code = fake.postcode()
            shipping_address = f"{street_address}, {postal_code} {city}, {destination}"
        elif destination in ['Japan', 'South Korea']:
            # Asian address format
            street_address = fake.street_address()
            city = fake.city()
            postal_code = fake.postcode()
            shipping_address = f"{street_address}, {city}, {postal_code}, {destination}"
        else:
            # Generic international format
            street_address = fake.street_address()
            city = fake.city()
            postal_code = fake.postcode()
            shipping_address = f"{street_address}, {city}, {postal_code}, {destination}"
        
        order = (
            random.choice(customer_ids),
            order_date.date(),
            total,
            random.choice(statuses),
            shipping_address,
            random.choice(payment_methods),
            order_date  # created_at
        )
        
        cursor.execute("""
            INSERT INTO orders (customer_id, order_date, total, status, 
                              shipping_address, payment_method, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, order)
        
        if (i + 1) % 500 == 0:
            print(f"  Progress: {i + 1}/{count} orders inserted")
    
    conn.commit()
    print(f"✓ Inserted {count} orders with international shipping")


def query_recent_activity(conn, customer_id):
    """Query recent customer activity (matching the retriever query)."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    query = """
        SELECT c.name, o.order_date, o.total
        FROM customers c
        INNER JOIN orders o ON c.id = o.customer_id
        WHERE o.created_at >= NOW() - INTERVAL '7 days'
        AND c.id = %s
        ORDER BY o.created_at DESC
        LIMIT 20
    """
    
    cursor.execute(query, (customer_id,))
    results = cursor.fetchall()
    
    return results


def query_customer_summary(conn, customer_id=None):
    """Query customer summary with order statistics."""
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    if customer_id:
        query = """
            SELECT 
                c.id,
                c.name,
                c.email,
                COUNT(o.id) as total_orders,
                COALESCE(SUM(o.total), 0) as total_spent,
                COALESCE(AVG(o.total), 0) as avg_order_value,
                MAX(o.order_date) as last_order_date
            FROM customers c
            LEFT JOIN orders o ON c.id = o.customer_id
            WHERE c.id = %s
            GROUP BY c.id, c.name, c.email
        """
        cursor.execute(query, (customer_id,))
    else:
        query = """
            SELECT 
                c.id,
                c.name,
                c.email,
                COUNT(o.id) as total_orders,
                COALESCE(SUM(o.total), 0) as total_spent,
                COALESCE(AVG(o.total), 0) as avg_order_value,
                MAX(o.order_date) as last_order_date
            FROM customers c
            LEFT JOIN orders o ON c.id = o.customer_id
            GROUP BY c.id, c.name, c.email
            ORDER BY total_spent DESC
            LIMIT 10
        """
        cursor.execute(query)
    
    results = cursor.fetchall()
    return results


def delete_all_data(conn):
    """Delete all data from tables."""
    cursor = conn.cursor()
    
    print("Deleting all data...")
    cursor.execute("DELETE FROM orders")
    cursor.execute("DELETE FROM customers")
    
    conn.commit()
    print("✓ All data deleted")


def drop_and_recreate_tables(conn):
    """Drop and recreate tables for fresh start."""
    cursor = conn.cursor()
    
    print("Dropping and recreating tables...")
    
    # Drop tables if they exist
    cursor.execute("DROP TABLE IF EXISTS orders CASCADE")
    cursor.execute("DROP TABLE IF EXISTS customers CASCADE")
    
    # Recreate customers table
    cursor.execute("""
        CREATE TABLE customers (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            phone VARCHAR(20),
            address TEXT,
            city VARCHAR(100),
            country VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Recreate orders table
    cursor.execute("""
        CREATE TABLE orders (
            id SERIAL PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            order_date DATE NOT NULL,
            total DECIMAL(10, 2) NOT NULL,
            status VARCHAR(50) DEFAULT 'pending',
            shipping_address TEXT,
            payment_method VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )
    """)
    
    # Create indexes for better performance
    cursor.execute("CREATE INDEX idx_orders_customer_id ON orders(customer_id)")
    cursor.execute("CREATE INDEX idx_orders_created_at ON orders(created_at)")
    cursor.execute("CREATE INDEX idx_orders_order_date ON orders(order_date)")
    
    # Create update trigger for updated_at
    cursor.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ language 'plpgsql'
    """)
    
    cursor.execute("""
        CREATE TRIGGER update_customers_updated_at BEFORE UPDATE ON customers
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)
    
    cursor.execute("""
        CREATE TRIGGER update_orders_updated_at BEFORE UPDATE ON orders
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)
    
    conn.commit()
    print("✓ Tables dropped and recreated with full schema")


def print_results(results, title="Query Results"):
    """Pretty print query results."""
    print(f"\n{title}")
    print("-" * 80)
    
    if not results:
        print("No results found.")
        return
    
    # Convert Decimal to float for JSON serialization
    for result in results:
        for key, value in result.items():
            if isinstance(value, Decimal):
                result[key] = float(value)
    
    print(json.dumps(results, indent=2, default=str, ensure_ascii=False))
    print(f"\nTotal records: {len(results)}")


def main():
    parser = argparse.ArgumentParser(description='PostgreSQL test data management')
    parser.add_argument('--action', choices=['insert', 'query', 'delete', 'recreate'], 
                       required=True, help='Action to perform')
    parser.add_argument('--customers', type=int, default=100, 
                       help='Number of customers to insert')
    parser.add_argument('--orders', type=int, default=500, 
                       help='Number of orders to insert')
    parser.add_argument('--customer-id', type=int, 
                       help='Customer ID for querying')
    parser.add_argument('--confirm', action='store_true', 
                       help='Confirm deletion')
    parser.add_argument('--clean', action='store_true',
                       help='Clean existing data before inserting (for insert action)')
    parser.add_argument('--host', 
                       help='Database host (defaults to DATASOURCE_POSTGRES_HOST env var)')
    parser.add_argument('--port', type=int, 
                       help='Database port (defaults to DATASOURCE_POSTGRES_PORT env var)')
    parser.add_argument('--database', 
                       help='Database name (defaults to DATASOURCE_POSTGRES_DATABASE env var)')
    parser.add_argument('--user', 
                       help='Database user (defaults to DATASOURCE_POSTGRES_USERNAME env var)')
    parser.add_argument('--password', 
                       help='Database password (defaults to DATASOURCE_POSTGRES_PASSWORD env var)')
    
    args = parser.parse_args()
    
    # Set environment variables from command line args if provided
    if args.host:
        os.environ['DATASOURCE_POSTGRES_HOST'] = args.host
    if args.port:
        os.environ['DATASOURCE_POSTGRES_PORT'] = str(args.port)
    if args.database:
        os.environ['DATASOURCE_POSTGRES_DATABASE'] = args.database
    if args.user:
        os.environ['DATASOURCE_POSTGRES_USERNAME'] = args.user
    if args.password:
        os.environ['DATASOURCE_POSTGRES_PASSWORD'] = args.password
    
    try:
        conn = get_connection()
        
        if args.action == 'insert':
            # Clean existing data if --clean flag is provided
            if args.clean:
                print("🧹 Cleaning existing data before insert...")
                delete_all_data(conn)
            
            # Insert customers first
            customer_ids = insert_customers(conn, args.customers)
            # Then insert orders
            insert_orders(conn, customer_ids, args.orders)
            print(f"\n✓ Test data inserted successfully!")
            
        elif args.action == 'query':
            if args.customer_id:
                # Query recent activity for specific customer
                results = query_recent_activity(conn, args.customer_id)
                print_results(results, f"Recent Activity for Customer {args.customer_id}")
                
                # Also show customer summary
                summary = query_customer_summary(conn, args.customer_id)
                print_results(summary, f"\nCustomer Summary for ID {args.customer_id}")
            else:
                # Show top customers
                results = query_customer_summary(conn)
                print_results(results, "Top Customers by Total Spent")
                
        elif args.action == 'delete':
            if args.confirm:
                delete_all_data(conn)
            else:
                print("⚠️  Use --confirm flag to delete all data")
                
        elif args.action == 'recreate':
            if args.confirm:
                drop_and_recreate_tables(conn)
            else:
                print("⚠️  Use --confirm flag to drop and recreate tables")
                
        conn.close()
        
    except psycopg2.Error as e:
        print(f"Database error: {e}")
        exit(1)
    except Exception as e:
        print(f"Error: {e}")
        exit(1)


if __name__ == "__main__":
    main()