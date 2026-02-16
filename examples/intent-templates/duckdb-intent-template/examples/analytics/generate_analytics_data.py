#!/usr/bin/env python3
"""
Analytics Database Sample Data Generator

DESCRIPTION:
    Generates realistic sample data for the analytics database schema using the
    Faker library. Creates a DuckDB database with synthetic sales, product, and
    customer records for testing the DuckDB Intent Template Generator.

    This script populates the database with:
    - Products (Electronics, Clothing, Food, etc.)
    - Customers (with regions and segments)
    - Sales transactions (with dates, amounts, quantities)

USAGE:
    python generate_analytics_data.py [--records N] [--output FILE]

ARGUMENTS:
    --records N     Number of sales records to generate (default: 1000)
    --output FILE   Path to DuckDB database file (default: analytics.duckdb)
    --clean         Drop existing tables before generating new data

EXAMPLES:
    # Generate 1000 records (default)
    python generate_analytics_data.py

    # Generate 10000 records
    python generate_analytics_data.py --records 10000

    # Generate to specific database file
    python generate_analytics_data.py --output ./data/analytics.duckdb

    # Clean existing data and generate fresh
    python generate_analytics_data.py --records 5000 --clean

OUTPUT:
    Creates a DuckDB database with the following structure:
    - Database: analytics.duckdb (or specified path)
    - Tables: products, customers, sales
    - Indexes: On date, product, region, category

REQUIREMENTS:
    pip install duckdb faker

SAMPLE DATA:
    id  | sale_date  | product_name    | category   | region  | sales_amount
    ----|------------|-----------------|------------|---------|---------------
    1   | 2024-01-15 | Laptop Pro      | Electronics| West    | 1299.99
    2   | 2024-01-16 | T-Shirt         | Clothing   | East    | 29.99
    3   | 2024-01-17 | Coffee Maker    | Electronics| North   | 89.99

TESTING WITH INTENT ADAPTER:
    After generating data, you can test with the DuckDB Intent adapter:

    1. Configure adapter in config/adapters.yaml (see documentation)
    2. Start Orbit server
    3. Query: "Show me top 10 products by sales"

SEE ALSO:
    - analytics.sql - Database schema
    - analytics_test_queries.md - Sample queries for template generation
    - ../../README.md - DuckDB Intent Template Generator documentation

AUTHOR:
    DuckDB Intent Template Generator v1.0.0
"""

import duckdb
import argparse
import sys
from datetime import datetime, timedelta
import random

try:
    from faker import Faker
except ImportError:
    print("❌ Error: Faker library is required")
    print("   Install with: pip install faker")
    sys.exit(1)


# Categories for products
PRODUCT_CATEGORIES = [
    "Electronics",
    "Clothing",
    "Food",
    "Home & Garden",
    "Sports",
    "Books",
    "Toys",
    "Health & Beauty"
]

# Regions for sales and customers
REGIONS = [
    "West",
    "East",
    "North",
    "South",
    "Central"
]

# Customer segments
CUSTOMER_SEGMENTS = [
    "Enterprise",
    "Small Business",
    "Consumer",
    "Government"
]

# Sample product names by category
PRODUCT_NAMES_BY_CATEGORY = {
    "Electronics": ["Laptop Pro", "Smartphone", "Tablet", "Monitor", "Keyboard", "Mouse", "Headphones", "Speaker", "Camera", "Smartwatch"],
    "Clothing": ["T-Shirt", "Jeans", "Jacket", "Dress", "Shoes", "Hat", "Socks", "Sweater", "Shorts", "Pants"],
    "Food": ["Coffee", "Tea", "Bread", "Milk", "Cheese", "Yogurt", "Fruit", "Vegetables", "Snacks", "Cereal"],
    "Home & Garden": ["Plant Pot", "Garden Tool", "Lamp", "Chair", "Table", "Vase", "Candle", "Rug", "Curtain", "Mirror"],
    "Sports": ["Basketball", "Football", "Tennis Racket", "Golf Club", "Running Shoes", "Yoga Mat", "Dumbbell", "Bike", "Helmet", "Water Bottle"],
    "Books": ["Novel", "Textbook", "Cookbook", "Biography", "Guide", "Manual", "Dictionary", "Encyclopedia", "Atlas", "Comic"],
    "Toys": ["Action Figure", "Puzzle", "Board Game", "Doll", "RC Car", "Lego Set", "Building Blocks", "Art Kit", "Musical Toy", "Educational Toy"],
    "Health & Beauty": ["Shampoo", "Soap", "Lotion", "Perfume", "Makeup", "Toothbrush", "Vitamins", "Skincare", "Hair Care", "Fitness Equipment"]
}


def create_database(db_path: str, clean: bool = False):
    """Create database and schema"""
    conn = duckdb.connect(db_path)
    
    # Drop tables if clean mode
    if clean:
        conn.execute("DROP TABLE IF EXISTS sales")
        conn.execute("DROP TABLE IF EXISTS products")
        conn.execute("DROP TABLE IF EXISTS customers")
        print("🧹 Cleaned existing data")
    
    # Create tables
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            product_name VARCHAR NOT NULL,
            category VARCHAR NOT NULL,
            price DECIMAL(10, 2) NOT NULL,
            cost DECIMAL(10, 2),
            description VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY,
            customer_name VARCHAR NOT NULL,
            email VARCHAR,
            region VARCHAR,
            segment VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY,
            sale_date DATE NOT NULL,
            product_id INTEGER NOT NULL,
            product_name VARCHAR NOT NULL,
            category VARCHAR,
            region VARCHAR NOT NULL,
            customer_id INTEGER,
            sales_amount DECIMAL(10, 2) NOT NULL,
            quantity INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(sale_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_product ON sales(product_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_region ON sales(region)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_category ON sales(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)")
    
    return conn


def generate_products() -> list:
    """Generate product records"""
    products = []
    product_id = 1
    
    for category in PRODUCT_CATEGORIES:
        product_names = PRODUCT_NAMES_BY_CATEGORY.get(category, ["Generic Product"])
        
        for product_name in product_names:
            # Generate price between 10 and 2000
            price = round(random.uniform(10.0, 2000.0), 2)
            # Cost is typically 40-60% of price
            cost = round(price * random.uniform(0.4, 0.6), 2)
            
            product = {
                'id': product_id,
                'product_name': f"{product_name}",
                'category': category,
                'price': price,
                'cost': cost,
                'description': f"{category} - {product_name}",
                'created_at': datetime.now() - timedelta(days=random.randint(1, 365))
            }
            products.append(product)
            product_id += 1
    
    return products


def generate_customers(count: int) -> list:
    """Generate customer records"""
    fake = Faker()
    customers = []
    
    start_date = datetime.now() - timedelta(days=365)
    
    for i in range(count):
        customer = {
            'id': i + 1,
            'customer_name': fake.company(),
            'email': fake.email(),
            'region': random.choice(REGIONS),
            'segment': random.choice(CUSTOMER_SEGMENTS),
            'created_at': start_date + timedelta(days=random.randint(0, 365))
        }
        customers.append(customer)
    
    return customers


def generate_sales(products: list, customers: list, count: int) -> list:
    """Generate sales transaction records"""
    Faker()
    sales = []
    
    # Generate sales over the last year
    start_date = datetime.now() - timedelta(days=365)
    
    for i in range(count):
        # Pick random product
        product = random.choice(products)
        
        # Pick random customer
        customer = random.choice(customers) if customers else None
        
        # Generate sale date
        days_offset = random.randint(0, 365)
        hours_offset = random.randint(0, 23)
        minutes_offset = random.randint(0, 59)
        sale_date = start_date + timedelta(
            days=days_offset,
            hours=hours_offset,
            minutes=minutes_offset
        )
        
        # Generate quantity (1-10)
        quantity = random.randint(1, 10)
        
        # Sales amount = product price * quantity (with some variation)
        base_amount = product['price'] * quantity
        # Add some price variation (±5%)
        variation = random.uniform(0.95, 1.05)
        sales_amount = round(base_amount * variation, 2)
        
        sale = {
            'id': i + 1,
            'sale_date': sale_date.date(),
            'product_id': product['id'],
            'product_name': product['product_name'],
            'category': product['category'],
            'region': customer['region'] if customer else random.choice(REGIONS),
            'customer_id': customer['id'] if customer else None,
            'sales_amount': sales_amount,
            'quantity': quantity,
            'created_at': sale_date
        }
        sales.append(sale)
    
    return sales


def insert_products(conn: duckdb.DuckDBPyConnection, products: list) -> int:
    """Insert product records into database"""
    inserted = 0
    
    for product in products:
        conn.execute("""
            INSERT INTO products (id, product_name, category, price, cost, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            product['id'],
            product['product_name'],
            product['category'],
            product['price'],
            product['cost'],
            product['description'],
            product['created_at']
        ))
        inserted += 1
    
    return inserted


def insert_customers(conn: duckdb.DuckDBPyConnection, customers: list) -> int:
    """Insert customer records into database"""
    inserted = 0
    
    for customer in customers:
        conn.execute("""
            INSERT INTO customers (id, customer_name, email, region, segment, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            customer['id'],
            customer['customer_name'],
            customer['email'],
            customer['region'],
            customer['segment'],
            customer['created_at']
        ))
        inserted += 1
    
    return inserted


def insert_sales(conn: duckdb.DuckDBPyConnection, sales: list) -> int:
    """Insert sales records into database"""
    inserted = 0
    
    for sale in sales:
        conn.execute("""
            INSERT INTO sales (id, sale_date, product_id, product_name, category, region, customer_id, sales_amount, quantity, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sale['id'],
            sale['sale_date'],
            sale['product_id'],
            sale['product_name'],
            sale['category'],
            sale['region'],
            sale['customer_id'],
            sale['sales_amount'],
            sale['quantity'],
            sale['created_at']
        ))
        inserted += 1
    
    return inserted


def print_sample_data(conn: duckdb.DuckDBPyConnection, limit: int = 5):
    """Print sample records from database"""
    print("\n📊 Sample Sales Data:")
    print("-" * 100)
    
    result = conn.execute(f"""
        SELECT id, sale_date, product_name, category, region, sales_amount, quantity
        FROM sales
        ORDER BY id
        LIMIT {limit}
    """).fetchall()
    
    if result:
        print(f"{'ID':<5} {'Date':<12} {'Product':<25} {'Category':<15} {'Region':<10} {'Amount':<12} {'Qty':<5}")
        print("-" * 100)
        
        for row in result:
            print(f"{row[0]:<5} {str(row[1]):<12} {row[2]:<25} {row[3]:<15} {row[4]:<10} ${row[5]:<11.2f} {row[6]:<5}")
        
        print("-" * 100)


def get_database_stats(conn: duckdb.DuckDBPyConnection):
    """Get and display database statistics"""
    # Total sales
    result = conn.execute("SELECT COUNT(*) FROM sales").fetchone()
    total_sales = result[0] if result else 0
    
    # Total products
    result = conn.execute("SELECT COUNT(*) FROM products").fetchone()
    total_products = result[0] if result else 0
    
    # Total customers
    result = conn.execute("SELECT COUNT(*) FROM customers").fetchone()
    total_customers = result[0] if result else 0
    
    # Total revenue
    result = conn.execute("SELECT SUM(sales_amount) FROM sales").fetchone()
    total_revenue = result[0] if result else 0.0
    
    # Unique categories
    result = conn.execute("SELECT COUNT(DISTINCT category) FROM products").fetchone()
    unique_categories = result[0] if result else 0
    
    # Most common categories
    result = conn.execute("""
        SELECT category, COUNT(*) as count
        FROM sales
        GROUP BY category
        ORDER BY count DESC
        LIMIT 5
    """).fetchall()
    top_categories = result if result else []
    
    # Most common regions
    result = conn.execute("""
        SELECT region, COUNT(*) as count
        FROM sales
        GROUP BY region
        ORDER BY count DESC
        LIMIT 5
    """).fetchall()
    top_regions = result if result else []
    
    print("\n📈 Database Statistics:")
    print(f"   Total Sales: {total_sales}")
    print(f"   Total Products: {total_products}")
    print(f"   Total Customers: {total_customers}")
    print(f"   Total Revenue: ${total_revenue:,.2f}")
    print(f"   Unique Categories: {unique_categories}")
    print("\n   Top 5 Categories:")
    for category, count in top_categories:
        print(f"      {category}: {count} sales")
    print("\n   Top 5 Regions:")
    for region, count in top_regions:
        print(f"      {region}: {count} sales")


def main():
    parser = argparse.ArgumentParser(
        description='Generate sample analytics data using Faker',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_analytics_data.py --records 1000
  python generate_analytics_data.py --output myanalytics.duckdb --clean
  python generate_analytics_data.py --records 5000 --clean
        """
    )
    
    parser.add_argument(
        '--records',
        type=int,
        default=1000,
        help='Number of sales records to generate (default: 1000)'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default='analytics.duckdb',
        help='Path to DuckDB database file (default: analytics.duckdb)'
    )
    
    parser.add_argument(
        '--clean',
        action='store_true',
        help='Drop existing tables before generating new data'
    )
    
    args = parser.parse_args()
    
    # Validate records
    if args.records < 1:
        print("❌ Error: --records must be at least 1")
        return 1
    
    if args.records > 1000000:
        print("⚠️  Warning: Generating more than 1,000,000 records may take a while")
        response = input("   Continue? (y/n): ")
        if response.lower() != 'y':
            print("   Cancelled")
            return 0
    
    print("=" * 60)
    print("  Analytics Database Generator")
    print("=" * 60)
    print("📝 Configuration:")
    print(f"   Records: {args.records}")
    print(f"   Output: {args.output}")
    print(f"   Clean mode: {'Yes' if args.clean else 'No'}")
    print()
    
    # Create database
    print("🔨 Creating database...")
    conn = create_database(args.output, clean=args.clean)
    
    # Generate products
    print("📦 Generating products...")
    products = generate_products()
    print(f"✅ Generated {len(products)} products")
    
    # Insert products
    print("💾 Inserting products...")
    inserted = insert_products(conn, products)
    print(f"✅ Inserted {inserted} products")
    
    # Generate customers
    customer_count = max(50, args.records // 20)  # 1 customer per 20 sales, minimum 50
    print(f"👥 Generating {customer_count} customers...")
    customers = generate_customers(customer_count)
    print(f"✅ Generated {len(customers)} customers")
    
    # Insert customers
    print("💾 Inserting customers...")
    inserted = insert_customers(conn, customers)
    print(f"✅ Inserted {inserted} customers")
    
    # Generate sales
    print(f"💰 Generating {args.records} sales...")
    sales = generate_sales(products, customers, args.records)
    print(f"✅ Generated {len(sales)} sales")
    
    # Insert sales
    print("💾 Inserting sales...")
    inserted = insert_sales(conn, sales)
    print(f"✅ Inserted {inserted} sales")
    
    # Show sample data
    print_sample_data(conn, limit=10)
    
    # Show statistics
    get_database_stats(conn)
    
    # Close connection
    conn.close()
    
    print(f"\n✅ Database created successfully: {args.output}")
    print("\n💡 Next steps:")
    print("   1. Test queries with DuckDB:")
    print(f"      duckdb {args.output} 'SELECT * FROM sales LIMIT 5;'")
    print("\n   2. Configure Intent adapter in config/adapters.yaml")
    print("      (See documentation for example configuration)")
    print("\n   3. Generate SQL templates (if needed):")
    print("      cd ../..")
    print("      python template_generator.py \\")
    print("        --schema examples/analytics/analytics.sql \\")
    print("        --queries examples/analytics/analytics_test_queries.md \\")
    print("        --output analytics-templates.yaml")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

