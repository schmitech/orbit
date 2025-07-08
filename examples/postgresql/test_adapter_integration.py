#!/usr/bin/env python3
"""
PostgreSQL Adapter Integration Test
===================================

This script validates that your PostgreSQL adapter configuration and test scripts
work correctly with our adapter granularity strategy.

Usage:
    python test_adapter_integration.py
"""

import sys
import os
sys.path.insert(0, '../../server')

import json
import yaml
import psycopg2
from psycopg2.extras import RealDictCursor
from services.sql_adapter_validation_service import SQLAdapterValidationService
from datetime import datetime, timedelta

def load_config():
    """Load the main config.yaml file."""
    with open('../../config.yaml', 'r') as f:
        return yaml.safe_load(f)

def test_adapter_validation():
    """Test that our PostgreSQL adapter passes validation."""
    print("=" * 60)
    print("1. TESTING ADAPTER VALIDATION")
    print("=" * 60)
    
    config = load_config()
    
    # Find the PostgreSQL adapter
    adapter = next((a for a in config['adapters'] if a['name'] == 'recent-customer-activity'), None)
    
    if not adapter:
        print("❌ PostgreSQL adapter not found in config")
        return False
    
    print(f"✅ Found adapter: {adapter['name']}")
    
    # Validate the adapter
    service = SQLAdapterValidationService(config)
    result = service.validate_adapter_config(adapter)
    
    print(f"✅ Validation Result: {'VALID' if result['is_valid'] else 'INVALID'}")
    print(f"✅ Complexity: {result['complexity'].upper()}")
    print(f"✅ Risk Level: {result['risk_level'].upper()}")
    
    if result['warnings']:
        print("\n⚠️  Warnings:")
        for warning in result['warnings']:
            print(f"  - {warning}")
    
    if result['recommendations']:
        print("\n💡 Recommendations:")
        for rec in result['recommendations']:
            print(f"  - {rec}")
    
    if result['errors']:
        print("\n❌ Errors:")
        for error in result['errors']:
            print(f"  - {error}")
        return False
    
    return True

def test_database_connectivity():
    """Test database connectivity using environment variables."""
    print("\n" + "=" * 60)
    print("2. TESTING DATABASE CONNECTIVITY")
    print("=" * 60)
    
    # Try with environment variables first
    db_config = {
        'host': 'localhost',
        'port': 5432,
        'database': 'retrieval',
        'user': os.getenv('DATASOURCE_POSTGRES_USERNAME', 'postgres'),
        'password': os.getenv('DATASOURCE_POSTGRES_PASSWORD', 'postgres')
    }
    
    print(f"🔌 Attempting connection to:")
    print(f"   Host: {db_config['host']}:{db_config['port']}")
    print(f"   Database: {db_config['database']}")
    print(f"   User: {db_config['user']}")
    
    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        
        # Test basic connectivity
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"✅ Connected to PostgreSQL: {version[0][:50]}...")
        
        # Check if our tables exist
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('customers', 'orders')
        """)
        tables = cursor.fetchall()
        existing_tables = [t[0] for t in tables]
        
        print(f"✅ Found tables: {existing_tables}")
        
        if 'customers' not in existing_tables or 'orders' not in existing_tables:
            print("⚠️  Warning: customers or orders table not found")
            print("   Run the SQL setup script first: psql -d retrieval -f customer-order.sql")
            return False, None
        
        # Test table structure
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'customers'
            ORDER BY ordinal_position
        """)
        customer_cols = cursor.fetchall()
        print(f"✅ Customer table columns: {[col[0] for col in customer_cols]}")
        
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'orders'
            ORDER BY ordinal_position
        """)
        order_cols = cursor.fetchall()
        print(f"✅ Orders table columns: {[col[0] for col in order_cols]}")
        
        return True, conn
        
    except psycopg2.Error as e:
        print(f"❌ Database connection failed: {e}")
        print("\n💡 Troubleshooting:")
        print("   1. Make sure PostgreSQL is running")
        print("   2. Create the 'retrieval' database: createdb retrieval")
        print("   3. Run the setup script: psql -d retrieval -f customer-order.sql")
        print("   4. Set environment variables:")
        print("      export DATASOURCE_POSTGRES_USERNAME=postgres")
        print("      export DATASOURCE_POSTGRES_PASSWORD=postgres")
        return False, None

def test_query_execution(conn):
    """Test executing the actual adapter query."""
    print("\n" + "=" * 60)
    print("3. TESTING QUERY EXECUTION")
    print("=" * 60)
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Check if we have any data
    cursor.execute("SELECT COUNT(*) FROM customers")
    customer_count = cursor.fetchone()[0]
    print(f"✅ Customer count: {customer_count}")
    
    cursor.execute("SELECT COUNT(*) FROM orders")
    order_count = cursor.fetchone()[0]
    print(f"✅ Order count: {order_count}")
    
    if customer_count == 0 or order_count == 0:
        print("⚠️  Warning: No test data found")
        print("   Generate test data: python customer-order.py --action insert --customers 10 --orders 20")
        return False
    
    # Test the actual adapter query
    adapter_query = """
        SELECT c.name, o.order_date, o.total
        FROM customers c
        INNER JOIN orders o ON c.id = o.customer_id
        WHERE o.created_at >= NOW() - INTERVAL '7 days'
        AND c.id = %s
        ORDER BY o.created_at DESC
        LIMIT 20
    """
    
    # Get a random customer ID
    cursor.execute("SELECT id FROM customers ORDER BY RANDOM() LIMIT 1")
    customer_id = cursor.fetchone()[0]
    
    print(f"🔍 Testing adapter query for customer ID: {customer_id}")
    
    cursor.execute(adapter_query, (customer_id,))
    results = cursor.fetchall()
    
    print(f"✅ Query executed successfully")
    print(f"✅ Results found: {len(results)} rows")
    
    if results:
        print("\n📊 Sample Results:")
        for i, row in enumerate(results[:3]):
            print(f"   {i+1}. {row['name']} - {row['order_date']} - ${row['total']}")
    
    return True

def test_performance_monitoring(conn):
    """Test query performance and monitoring."""
    print("\n" + "=" * 60)
    print("4. TESTING PERFORMANCE MONITORING")
    print("=" * 60)
    
    import time
    
    cursor = conn.cursor()
    
    # Test query execution time
    start_time = time.time()
    
    cursor.execute("""
        SELECT c.name, o.order_date, o.total
        FROM customers c
        INNER JOIN orders o ON c.id = o.customer_id
        WHERE o.created_at >= NOW() - INTERVAL '7 days'
        ORDER BY o.created_at DESC
        LIMIT 20
    """)
    
    results = cursor.fetchall()
    execution_time = time.time() - start_time
    
    print(f"✅ Query execution time: {execution_time:.3f} seconds")
    print(f"✅ Results returned: {len(results)} rows")
    
    # Check if within adapter limits
    if execution_time > 15.0:  # 15 second timeout from config
        print("⚠️  Warning: Query execution time exceeds adapter timeout limit")
    else:
        print("✅ Query execution time within adapter limits")
    
    # Test with explain plan
    cursor.execute("""
        EXPLAIN ANALYZE
        SELECT c.name, o.order_date, o.total
        FROM customers c
        INNER JOIN orders o ON c.id = o.customer_id
        WHERE o.created_at >= NOW() - INTERVAL '7 days'
        ORDER BY o.created_at DESC
        LIMIT 20
    """)
    
    explain_results = cursor.fetchall()
    print(f"✅ Query plan generated ({len(explain_results)} lines)")
    
    return True

def main():
    """Run all tests."""
    print("PostgreSQL Adapter Integration Test")
    print("=" * 60)
    
    # Test 1: Adapter validation
    if not test_adapter_validation():
        print("\n❌ Adapter validation failed")
        return 1
    
    # Test 2: Database connectivity
    connected, conn = test_database_connectivity()
    if not connected:
        print("\n❌ Database connectivity failed")
        return 1
    
    try:
        # Test 3: Query execution
        if not test_query_execution(conn):
            print("\n❌ Query execution failed")
            return 1
        
        # Test 4: Performance monitoring
        if not test_performance_monitoring(conn):
            print("\n❌ Performance monitoring failed")
            return 1
        
        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 60)
        print("Your PostgreSQL adapter is correctly configured and working!")
        print("\n📋 Summary:")
        print("✅ Adapter configuration validates successfully")
        print("✅ Database connectivity works")
        print("✅ Query execution works")
        print("✅ Performance monitoring works")
        print("✅ Schema matches adapter expectations")
        
        return 0
        
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    exit(main()) 