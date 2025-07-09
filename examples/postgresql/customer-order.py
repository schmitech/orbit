#!/usr/bin/env python3
"""
PostgreSQL test data management script for adapter testing.
Usage:
    python postgres_utils.py --action insert --customers 100 --orders 500
    python postgres_utils.py --action query --customer-id 1
    python postgres_utils.py --action delete --confirm
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

# Initialize Faker
fake = Faker()

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
    """Insert fake customer data."""
    cursor = conn.cursor()
    customers = []
    
    print(f"Inserting {count} customers...")
    
    for _ in range(count):
        customer = (
            fake.name(),
            fake.email(),
            fake.phone_number()[:20],
            fake.street_address(),
            fake.city(),
            fake.country()
        )
        
        cursor.execute("""
            INSERT INTO customers (name, email, phone, address, city, country)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, customer)
        
        customer_id = cursor.fetchone()[0]
        customers.append(customer_id)
    
    conn.commit()
    print(f"✓ Inserted {count} customers")
    return customers


def insert_orders(conn, customer_ids, count=500):
    """Insert fake order data."""
    cursor = conn.cursor()
    
    print(f"Inserting {count} orders...")
    
    # Payment methods
    payment_methods = ['credit_card', 'debit_card', 'paypal', 'bank_transfer', 'cash']
    statuses = ['pending', 'processing', 'shipped', 'delivered', 'cancelled']
    
    for _ in range(count):
        # Random date within the last 30 days
        days_ago = random.randint(0, 30)
        order_date = datetime.now() - timedelta(days=days_ago)
        
        # Random total between $10 and $1000
        total = round(random.uniform(10.0, 1000.0), 2)
        
        order = (
            random.choice(customer_ids),
            order_date.date(),
            total,
            random.choice(statuses),
            fake.street_address(),
            random.choice(payment_methods),
            order_date  # created_at
        )
        
        cursor.execute("""
            INSERT INTO orders (customer_id, order_date, total, status, 
                              shipping_address, payment_method, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, order)
    
    conn.commit()
    print(f"✓ Inserted {count} orders")


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
    
    print(json.dumps(results, indent=2, default=str))
    print(f"\nTotal records: {len(results)}")


def main():
    parser = argparse.ArgumentParser(description='PostgreSQL test data management')
    parser.add_argument('--action', choices=['insert', 'query', 'delete'], 
                       required=True, help='Action to perform')
    parser.add_argument('--customers', type=int, default=100, 
                       help='Number of customers to insert')
    parser.add_argument('--orders', type=int, default=500, 
                       help='Number of orders to insert')
    parser.add_argument('--customer-id', type=int, 
                       help='Customer ID for querying')
    parser.add_argument('--confirm', action='store_true', 
                       help='Confirm deletion')
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
                
        conn.close()
        
    except psycopg2.Error as e:
        print(f"Database error: {e}")
        exit(1)
    except Exception as e:
        print(f"Error: {e}")
        exit(1)


if __name__ == "__main__":
    main()