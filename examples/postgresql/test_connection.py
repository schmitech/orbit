import psycopg2
from psycopg2 import OperationalError, Error
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
        'port': os.getenv('DATASOURCE_POSTGRES_PORT', '5432'),
        'dbname': os.getenv('DATASOURCE_POSTGRES_DATABASE', 'orbit'),
        'user': os.getenv('DATASOURCE_POSTGRES_USERNAME', 'postgres'),
        'password': os.getenv('DATASOURCE_POSTGRES_PASSWORD', 'postgres'),
        'sslmode': os.getenv('DATASOURCE_POSTGRES_SSL_MODE', 'require')
    }

def test_connection():
    """Test PostgreSQL connection with AWS RDS optimizations"""
    connection = None
    try:
        # Get fresh configuration
        config = get_db_config()
        
        print(f"Attempting to connect to PostgreSQL at {config['host']}:{config['port']}")
        print(f"Database: {config['dbname']}, User: {config['user']}")
        print(f"SSL Mode: {config['sslmode']}")
        
        # Connect with SSL for AWS RDS
        connection = psycopg2.connect(
            user=config['user'],
            password=config['password'],
            host=config['host'],
            port=config['port'],
            dbname=config['dbname'],
            sslmode=config['sslmode']
        )
        
        print("✅ Connection successful!")
        
        # Test basic functionality
        cursor = connection.cursor()
        
        # Test 1: Current timestamp
        cursor.execute("SELECT NOW();")
        result = cursor.fetchone()
        print(f"📅 Current Time: {result[0]}")
        
        # Test 2: PostgreSQL version
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"🔧 PostgreSQL Version: {version[0].split(',')[0]}")
        
        # Test 3: Check if we can create a test table (optional)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS connection_test (
                id SERIAL PRIMARY KEY,
                test_time TIMESTAMP DEFAULT NOW(),
                message TEXT
            );
        """)
        connection.commit()
        print("✅ Test table created/verified successfully")
        
        # Test 4: Insert and query test data
        cursor.execute("""
            INSERT INTO connection_test (message) 
            VALUES ('AWS RDS connection test successful')
            RETURNING id, test_time, message;
        """)
        test_result = cursor.fetchone()
        print(f"✅ Test data inserted: ID={test_result[0]}, Time={test_result[1]}, Message='{test_result[2]}'")
        
        cursor.close()
        return True
        
    except OperationalError as e:
        print(f"❌ Connection failed: {e}")
        print("\nTroubleshooting tips:")
        print("1. Check if RDS instance is running")
        print("2. Verify security group allows connections from your IP")
        print("3. Ensure VPC/subnet configuration is correct")
        print("4. Check if SSL mode is appropriate for your setup")
        print("5. Verify your .env file has correct values")
        return False
        
    except Error as e:
        print(f"❌ Database error: {e}")
        return False
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
        
    finally:
        if connection:
            connection.close()
            print("🔒 Connection closed.")

def show_current_config():
    """Display current configuration without connecting"""
    config = get_db_config()
    print("📋 Current Configuration:")
    print(f"  Host: {config['host']}")
    print(f"  Port: {config['port']}")
    print(f"  Database: {config['dbname']}")
    print(f"  User: {config['user']}")
    print(f"  SSL Mode: {config['sslmode']}")
    print(f"  Password: {'*' * len(config['password']) if config['password'] else 'Not set'}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--config":
        show_current_config()
    else:
        success = test_connection()
        sys.exit(0 if success else 1) 