#!/usr/bin/env python3
"""
Database schema setup script for PostgreSQL customer-order tables.
This script creates the necessary tables for the customer-order.py script.
"""

import psycopg2
from dotenv import load_dotenv, find_dotenv
import os
import sys

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

def setup_schema():
    """Set up the database schema by executing the SQL file"""
    connection = None
    try:
        config = get_db_config()
        
        print(f"🔗 Connecting to PostgreSQL at {config['host']}:{config['port']}")
        print(f"📊 Database: {config['database']}, User: {config['user']}")
        print(f"🔒 SSL Mode: {config['sslmode']}")
        
        # Connect to database
        connection = psycopg2.connect(**config)
        print("✅ Connected successfully!")
        
        # Read the SQL file
        sql_file_path = os.path.join(os.path.dirname(__file__), 'customer-order.sql')
        
        if not os.path.exists(sql_file_path):
            print(f"❌ SQL file not found: {sql_file_path}")
            return False
        
        print(f"📄 Reading schema from: {sql_file_path}")
        
        with open(sql_file_path, 'r') as file:
            sql_content = file.read()
        
        # Execute the SQL
        cursor = connection.cursor()
        
        # Check if tables exist and drop them first
        print("🧹 Checking for existing tables...")
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('customers', 'orders')
        """)
        
        existing_tables = cursor.fetchall()
        if existing_tables:
            print(f"🗑️  Dropping existing tables: {[table[0] for table in existing_tables]}")
            cursor.execute("DROP TABLE IF EXISTS orders CASCADE")
            cursor.execute("DROP TABLE IF EXISTS customers CASCADE")
            connection.commit()
            print("✅ Existing tables dropped")
        
        # Execute the entire SQL content as one statement
        print("🔨 Setting up database schema...")
        cursor.execute(sql_content)
        
        connection.commit()
        print("✅ Schema setup completed successfully!")
        
        # Verify tables were created
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('customers', 'orders')
            ORDER BY table_name
        """)
        
        tables = cursor.fetchall()
        print(f"📋 Created tables: {[table[0] for table in tables]}")
        
        cursor.close()
        return True
        
    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
        if connection:
            connection.rollback()
        return False
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        if connection:
            connection.rollback()
        return False
        
    finally:
        if connection:
            connection.close()
            print("🔒 Connection closed.")

def verify_schema():
    """Verify that the schema is properly set up"""
    connection = None
    try:
        config = get_db_config()
        connection = psycopg2.connect(**config)
        cursor = connection.cursor()
        
        # Check if tables exist
        cursor.execute("""
            SELECT table_name, column_name, data_type 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name IN ('customers', 'orders')
            ORDER BY table_name, ordinal_position
        """)
        
        columns = cursor.fetchall()
        
        print("📋 Database Schema Verification:")
        print("-" * 50)
        
        current_table = None
        for table, column, data_type in columns:
            if table != current_table:
                print(f"\n📊 Table: {table}")
                current_table = table
            print(f"  - {column}: {data_type}")
        
        cursor.close()
        return True
        
    except Exception as e:
        print(f"❌ Verification error: {e}")
        return False
        
    finally:
        if connection:
            connection.close()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        success = verify_schema()
    else:
        success = setup_schema()
        if success:
            print("\n🔍 Verifying schema...")
            verify_schema()
    
    sys.exit(0 if success else 1) 