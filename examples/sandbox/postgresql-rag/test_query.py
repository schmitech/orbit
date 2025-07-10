#!/usr/bin/env python3
"""
Test script for enhanced customer activity queries with multiple parameters
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv, find_dotenv
import os
from datetime import datetime, timedelta

def reload_env_variables():
    """Reload environment variables from .env file"""
    env_file = find_dotenv()
    if env_file:
        load_dotenv(env_file, override=True)
        print(f"🔄 Reloaded environment variables from: {env_file}")
    else:
        print("⚠️  No .env file found")

def get_db_config():
    """Get database configuration from environment variables"""
    reload_env_variables()
    
    return {
        'host': os.getenv('DATASOURCE_POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('DATASOURCE_POSTGRES_PORT', '5432')),
        'database': os.getenv('DATASOURCE_POSTGRES_DATABASE', 'orbit'),
        'user': os.getenv('DATASOURCE_POSTGRES_USERNAME', 'postgres'),
        'password': os.getenv('DATASOURCE_POSTGRES_PASSWORD', 'postgres'),
        'sslmode': os.getenv('DATASOURCE_POSTGRES_SSL_MODE', 'require')
    }

def build_query(params):
    """Build the enhanced query with parameters"""
    query = """
        SELECT 
          c.id as customer_id,
          c.name as customer_name,
          c.email as customer_email,
          c.city as customer_city,
          o.id as order_id,
          o.order_date,
          o.total,
          o.status,
          o.payment_method,
          o.created_at,
          o.shipping_address
        FROM customers c
        INNER JOIN orders o ON c.id = o.customer_id
        WHERE 1=1
    """
    
    query_params = []
    
    # Add customer_id filter
    if 'customer_id' in params and params['customer_id']:
        query += " AND c.id = %s"
        query_params.append(params['customer_id'])
    
    # Add date filter
    if 'days_back' in params and params['days_back']:
        query += f" AND o.created_at >= NOW() - INTERVAL '{params['days_back']} days'"
    else:
        query += " AND o.created_at >= NOW() - INTERVAL '7 days'"
    
    # Add status filter
    if 'status' in params and params['status']:
        query += " AND o.status = %s"
        query_params.append(params['status'])
    
    # Add amount filters
    if 'min_amount' in params and params['min_amount']:
        query += " AND o.total >= %s"
        query_params.append(params['min_amount'])
    
    if 'max_amount' in params and params['max_amount']:
        query += " AND o.total <= %s"
        query_params.append(params['max_amount'])
    
    # Add city filter
    if 'city' in params and params['city']:
        query += " AND c.city ILIKE %s"
        query_params.append(f"%{params['city']}%")
    
    # Add ordering and limit
    query += " ORDER BY o.created_at DESC"
    
    limit = params.get('limit', 20)
    query += f" LIMIT {limit}"
    
    return query, query_params

def test_enhanced_query(params, description):
    """Test the enhanced query with given parameters"""
    connection = None
    try:
        config = get_db_config()
        connection = psycopg2.connect(**config)
        cursor = connection.cursor(cursor_factory=RealDictCursor)
        
        query, query_params = build_query(params)
        
        print(f"\n🔍 {description}")
        print("📋 Parameters:", params)
        print("📋 Query:", query.strip())
        print("-" * 60)
        
        cursor.execute(query, query_params)
        results = cursor.fetchall()
        
        if results:
            print(f"✅ Found {len(results)} records:")
            for i, row in enumerate(results, 1):
                print(f"  {i}. {row['customer_name']} - {row['order_date']} - ${row['total']} - {row['status']}")
        else:
            print("❌ No records found")
        
        cursor.close()
        return results
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return []
        
    finally:
        if connection:
            connection.close()

def run_demo_queries():
    """Run various demo queries to show RAG capabilities"""
    print("🚀 Enhanced Customer Activity Query Demo")
    print("=" * 60)
    
    # Test 1: Recent orders (default behavior)
    test_enhanced_query(
        {},
        "Recent orders (last 7 days)"
    )
    
    # Test 2: High-value orders
    test_enhanced_query(
        {"min_amount": 500, "days_back": 30},
        "High-value orders (>$500) from last 30 days"
    )
    
    # Test 3: Orders by status
    test_enhanced_query(
        {"status": "delivered", "days_back": 60},
        "Delivered orders from last 60 days"
    )
    
    # Test 4: Orders by city (if we have city data)
    test_enhanced_query(
        {"city": "New York", "limit": 10},
        "Orders from New York customers"
    )
    
    # Test 5: Specific customer
    test_enhanced_query(
        {"customer_id": 1, "limit": 5},
        "All orders for customer ID 1"
    )
    
    # Test 6: Amount range
    test_enhanced_query(
        {"min_amount": 100, "max_amount": 500, "days_back": 14},
        "Orders between $100-$500 from last 14 days"
    )

def show_available_data():
    """Show what data is available for testing"""
    connection = None
    try:
        config = get_db_config()
        connection = psycopg2.connect(**config)
        cursor = connection.cursor(cursor_factory=RealDictCursor)
        
        print("\n📊 Available Data Summary:")
        print("-" * 40)
        
        # Count customers
        cursor.execute("SELECT COUNT(*) as count FROM customers")
        customer_count = cursor.fetchone()['count']
        print(f"👥 Total customers: {customer_count}")
        
        # Count orders
        cursor.execute("SELECT COUNT(*) as count FROM orders")
        order_count = cursor.fetchone()['count']
        print(f"📦 Total orders: {order_count}")
        
        # Show order statuses
        cursor.execute("SELECT status, COUNT(*) as count FROM orders GROUP BY status")
        statuses = cursor.fetchall()
        print(f"📋 Order statuses: {', '.join([f'{s['status']}: {s['count']}' for s in statuses])}")
        
        # Show payment methods
        cursor.execute("SELECT payment_method, COUNT(*) as count FROM orders GROUP BY payment_method")
        payments = cursor.fetchall()
        print(f"💳 Payment methods: {', '.join([f'{p['payment_method']}: {p['count']}' for p in payments])}")
        
        # Show amount range
        cursor.execute("SELECT MIN(total) as min, MAX(total) as max, AVG(total) as avg FROM orders")
        amounts = cursor.fetchone()
        print(f"💰 Amount range: ${amounts['min']:.2f} - ${amounts['max']:.2f} (avg: ${amounts['avg']:.2f})")
        
        # Show cities
        cursor.execute("SELECT city, COUNT(*) as count FROM customers GROUP BY city ORDER BY count DESC LIMIT 5")
        cities = cursor.fetchall()
        print(f"🏙️  Top cities: {', '.join([f'{c['city']}: {c['count']}' for c in cities])}")
        
        cursor.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        
    finally:
        if connection:
            connection.close()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--data":
        show_available_data()
    else:
        run_demo_queries() 