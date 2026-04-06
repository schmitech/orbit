#!/usr/bin/env python3
"""
Test script for customer activity queries with multiple parameters.
Supports comprehensive testing of RAG system query capabilities.

Usage:
    python test_query.py                    # Run all demo queries
    python test_query.py --data             # Show available data summary
    python test_query.py --customer 1       # Test specific customer queries
    python test_query.py --performance      # Run performance tests
    python test_query.py --stress           # Run stress tests with large datasets
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv, find_dotenv
import os
import sys
import time
import argparse
from datetime import datetime, timedelta
from decimal import Decimal
import json

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
    """Build the query with parameters"""
    query = """
        SELECT 
          c.id as customer_id,
          c.name as customer_name,
          c.email as customer_email,
          c.city as customer_city,
          c.country as customer_country,
          o.id as order_id,
          o.order_date,
          o.total,
          o.status,
          o.payment_method,
          o.created_at,
          o.shipping_address,
          EXTRACT(EPOCH FROM (NOW() - o.created_at))/86400 as days_ago
        FROM customers c
        INNER JOIN orders o ON c.id = o.customer_id
        WHERE 1=1
    """
    
    query_params = []
    
    # Add customer_id filter
    if 'customer_id' in params and params['customer_id']:
        query += " AND c.id = %s"
        query_params.append(params['customer_id'])
    
    # Add customer name filter
    if 'customer_name' in params and params['customer_name']:
        query += " AND c.name ILIKE %s"
        query_params.append(f"%{params['customer_name']}%")
    
    # Add date filter
    if 'days_back' in params and params['days_back']:
        query += f" AND o.created_at >= NOW() - INTERVAL '{params['days_back']} days'"
    elif 'date_from' in params and params['date_from']:
        query += " AND o.order_date >= %s"
        query_params.append(params['date_from'])
    elif 'date_to' in params and params['date_to']:
        query += " AND o.order_date <= %s"
        query_params.append(params['date_to'])
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
    
    # Add country filter
    if 'country' in params and params['country']:
        query += " AND c.country ILIKE %s"
        query_params.append(f"%{params['country']}%")
    
    # Add payment method filter
    if 'payment_method' in params and params['payment_method']:
        query += " AND o.payment_method = %s"
        query_params.append(params['payment_method'])
    
    # Add ordering
    order_by = params.get('order_by', 'o.created_at DESC')
    query += f" ORDER BY {order_by}"
    
    # Add limit
    limit = params.get('limit', 20)
    query += f" LIMIT {limit}"
    
    return query, query_params

def test_query(params, description, show_query=True, show_details=True):
    """Test the query with given parameters"""
    connection = None
    start_time = time.time()
    
    try:
        config = get_db_config()
        connection = psycopg2.connect(**config)
        cursor = connection.cursor(cursor_factory=RealDictCursor)
        
        query, query_params = build_query(params)
        
        if show_query:
            print(f"\n🔍 {description}")
            print("📋 Parameters:", {k: v for k, v in params.items() if v is not None})
            print("📋 Query:", query.strip())
            print("-" * 60)
        
        cursor.execute(query, query_params)
        results = cursor.fetchall()
        execution_time = time.time() - start_time
        
        if results:
            print(f"✅ Found {len(results)} records in {execution_time:.3f}s")
            
            if show_details:
                for i, row in enumerate(results, 1):
                    # Convert Decimal to float for display
                    total = float(row['total']) if isinstance(row['total'], Decimal) else row['total']
                    days_ago = f"{row['days_ago']:.1f}d ago" if row['days_ago'] else "N/A"
                    location = f"{row['customer_city']}, {row['customer_country']}" if row['customer_city'] and row['customer_country'] else "N/A"
                    print(f"  {i:2d}. {row['customer_name']:<20} | {location:<25} | {row['order_date']} | ${total:>8.2f} | {row['status']:<10} | {days_ago}")
        else:
            print(f"❌ No records found in {execution_time:.3f}s")
        
        cursor.close()
        return results, execution_time
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return [], time.time() - start_time
        
    finally:
        if connection:
            connection.close()

def run_demo_queries():
    """Run various demo queries to show RAG capabilities"""
    print("🚀 Customer Activity Query Demo")
    print("=" * 60)
    
    # Test 1: Recent orders (default behavior)
    test_query(
        {},
        "Recent orders (last 7 days)"
    )
    
    # Test 2: High-value orders
    test_query(
        {"min_amount": 500, "days_back": 30},
        "High-value orders (>$500) from last 30 days"
    )
    
    # Test 3: Orders by status
    test_query(
        {"status": "delivered", "days_back": 60},
        "Delivered orders from last 60 days"
    )
    
    # Test 4: Orders by city (Canadian cities)
    test_query(
        {"city": "Toronto", "limit": 10},
        "Orders from Toronto customers"
    )
    
    # Test 5: Specific customer
    test_query(
        {"customer_id": 1, "limit": 5},
        "All orders for customer ID 1"
    )
    
    # Test 6: Amount range
    test_query(
        {"min_amount": 100, "max_amount": 500, "days_back": 14},
        "Orders between $100-$500 from last 14 days"
    )
    
    # Test 7: Payment method analysis
    test_query(
        {"payment_method": "credit_card", "days_back": 30},
        "Credit card orders from last 30 days"
    )
    
    # Test 8: Orders by country
    test_query(
        {"country": "Canada", "limit": 15},
        "Orders from Canadian customers"
    )
    
    # Test 9: Customer name search
    test_query(
        {"customer_name": "Smith", "limit": 10},
        "Orders from customers with 'Smith' in name"
    )
    
    # Test 10: High-value pending orders
    test_query(
        {"status": "pending", "min_amount": 200, "order_by": "o.total DESC"},
        "High-value pending orders (sorted by amount)"
    )

def show_available_data():
    """Show what data is available for testing"""
    connection = None
    try:
        config = get_db_config()
        connection = psycopg2.connect(**config)
        cursor = connection.cursor(cursor_factory=RealDictCursor)
        
        print("\n📊 Available Data Summary:")
        print("=" * 50)
        
        # Count customers
        cursor.execute("SELECT COUNT(*) as count FROM customers")
        customer_count = cursor.fetchone()['count']
        print(f"👥 Total customers: {customer_count}")
        
        # Count orders
        cursor.execute("SELECT COUNT(*) as count FROM orders")
        order_count = cursor.fetchone()['count']
        print(f"📦 Total orders: {order_count}")
        
        # Show order statuses
        cursor.execute("SELECT status, COUNT(*) as count FROM orders GROUP BY status ORDER BY count DESC")
        statuses = cursor.fetchall()
        print(f"\n📋 Order statuses:")
        for status in statuses:
            print(f"  • {status['status']}: {status['count']} orders")
        
        # Show payment methods
        cursor.execute("SELECT payment_method, COUNT(*) as count FROM orders GROUP BY payment_method ORDER BY count DESC")
        payments = cursor.fetchall()
        print(f"\n💳 Payment methods:")
        for payment in payments:
            print(f"  • {payment['payment_method']}: {payment['count']} orders")
        
        # Show amount range
        cursor.execute("SELECT MIN(total) as min, MAX(total) as max, AVG(total) as avg, SUM(total) as total FROM orders")
        amounts = cursor.fetchone()
        print(f"\n💰 Financial summary:")
        print(f"  • Range: ${amounts['min']:.2f} - ${amounts['max']:.2f}")
        print(f"  • Average: ${amounts['avg']:.2f}")
        print(f"  • Total revenue: ${amounts['total']:.2f}")
        
        # Show cities
        cursor.execute("SELECT city, COUNT(*) as count FROM customers GROUP BY city ORDER BY count DESC LIMIT 10")
        cities = cursor.fetchall()
        print(f"\n🏙️  Top cities:")
        for city in cities:
            print(f"  • {city['city']}: {city['count']} customers")
        
        # Show countries
        cursor.execute("SELECT country, COUNT(*) as count FROM customers GROUP BY country ORDER BY count DESC")
        countries = cursor.fetchall()
        print(f"\n🌍 Countries:")
        for country in countries:
            print(f"  • {country['country']}: {country['count']} customers")
        
        # Show recent activity
        cursor.execute("""
            SELECT COUNT(*) as count, 
                   MIN(created_at) as oldest, 
                   MAX(created_at) as newest 
            FROM orders 
            WHERE created_at >= NOW() - INTERVAL '7 days'
        """)
        recent = cursor.fetchone()
        print(f"\n📅 Recent activity (last 7 days):")
        print(f"  • Orders: {recent['count']}")
        if recent['oldest'] and recent['newest']:
            print(f"  • Date range: {recent['oldest'].strftime('%Y-%m-%d')} to {recent['newest'].strftime('%Y-%m-%d')}")
        
        cursor.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        
    finally:
        if connection:
            connection.close()


def run_performance_tests():
    """Run performance tests to measure query execution times"""
    print("⚡ Performance Testing")
    print("=" * 50)
    
    test_cases = [
        ({"limit": 10}, "Small result set (10 records)"),
        ({"limit": 100}, "Medium result set (100 records)"),
        ({"limit": 1000}, "Large result set (1000 records)"),
        ({"days_back": 1}, "Recent orders (1 day)"),
        ({"days_back": 7}, "Recent orders (7 days)"),
        ({"days_back": 30}, "Recent orders (30 days)"),
        ({"min_amount": 100}, "Filtered by amount (min $100)"),
        ({"status": "delivered"}, "Filtered by status"),
        ({"city": "Toronto"}, "Filtered by city"),
        ({"customer_id": 1}, "Filtered by customer ID"),
    ]
    
    results = []
    for params, description in test_cases:
        _, execution_time = test_query(params, description, show_query=False, show_details=False)
        results.append((description, execution_time))
    
    print(f"\n📊 Performance Summary:")
    print("-" * 50)
    for description, time_taken in sorted(results, key=lambda x: x[1]):
        print(f"  {description:<40} {time_taken:.3f}s")
    
    avg_time = sum(t for _, t in results) / len(results)
    print(f"\n⏱️  Average execution time: {avg_time:.3f}s")


def run_customer_analysis(customer_id):
    """Run comprehensive analysis for a specific customer"""
    print(f"👤 Customer Analysis for ID {customer_id}")
    print("=" * 50)
    
    # Customer profile
    test_query(
        {"customer_id": customer_id, "limit": 1},
        "Customer Profile",
        show_details=False
    )
    
    # All orders for this customer
    test_query(
        {"customer_id": customer_id, "order_by": "o.order_date DESC"},
        "All Orders (chronological)"
    )
    
    # High-value orders
    test_query(
        {"customer_id": customer_id, "min_amount": 200, "order_by": "o.total DESC"},
        "High-Value Orders (>$200)"
    )
    
    # Recent activity
    test_query(
        {"customer_id": customer_id, "days_back": 7},
        "Recent Activity (last 7 days)"
    )
    
    # Payment method analysis
    test_query(
        {"customer_id": customer_id, "order_by": "o.payment_method"},
        "Orders by Payment Method"
    )


def run_stress_tests():
    """Run stress tests with various parameter combinations"""
    print("🔥 Stress Testing")
    print("=" * 50)
    
    # Test multiple filters simultaneously
    complex_queries = [
        ({"min_amount": 100, "max_amount": 500, "status": "delivered", "days_back": 30}, "Complex filter 1"),
        ({"city": "Toronto", "payment_method": "credit_card", "min_amount": 200}, "Complex filter 2"),
        ({"country": "Canada", "status": "pending", "days_back": 7}, "Complex filter 3"),
    ]
    
    for params, description in complex_queries:
        test_query(params, description, show_details=False)


def main():
    """Main function with command line argument parsing"""
    parser = argparse.ArgumentParser(description='Customer activity query testing')
    parser.add_argument('--data', action='store_true', help='Show available data summary')
    parser.add_argument('--customer', type=int, help='Run analysis for specific customer ID')
    parser.add_argument('--performance', action='store_true', help='Run performance tests')
    parser.add_argument('--stress', action='store_true', help='Run stress tests')
    parser.add_argument('--demo', action='store_true', help='Run demo queries (default)')
    
    args = parser.parse_args()
    
    if args.data:
        show_available_data()
    elif args.customer:
        run_customer_analysis(args.customer)
    elif args.performance:
        run_performance_tests()
    elif args.stress:
        run_stress_tests()
    else:
        # Default behavior
        run_demo_queries()


if __name__ == "__main__":
    main() 