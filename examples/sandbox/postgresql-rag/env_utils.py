"""
Environment variable utilities for PostgreSQL connection testing
"""
from dotenv import load_dotenv, find_dotenv
import os
from typing import Dict, Optional

def reload_env_variables(env_file: Optional[str] = None) -> str:
    """
    Reload environment variables from .env file
    
    Args:
        env_file: Optional path to .env file. If None, will auto-detect.
    
    Returns:
        Path to the .env file that was loaded
    """
    if env_file is None:
        env_file = find_dotenv()
    
    if env_file and os.path.exists(env_file):
        load_dotenv(env_file, override=True)
        print(f"🔄 Reloaded environment variables from: {env_file}")
        return env_file
    else:
        print("⚠️  No .env file found")
        return ""

def get_postgres_config(env_file: Optional[str] = None) -> Dict[str, str]:
    """
    Get PostgreSQL configuration from environment variables
    
    Args:
        env_file: Optional path to .env file to reload before getting config
    
    Returns:
        Dictionary with database configuration
    """
    if env_file:
        reload_env_variables(env_file)
    else:
        reload_env_variables()
    
    return {
        'host': os.getenv('DATASOURCE_POSTGRES_HOST', 'localhost'),
        'port': os.getenv('DATASOURCE_POSTGRES_PORT', '5432'),
        'dbname': os.getenv('DATASOURCE_POSTGRES_DATABASE', 'orbit'),
        'user': os.getenv('DATASOURCE_POSTGRES_USERNAME', 'postgres'),
        'password': os.getenv('DATASOURCE_POSTGRES_PASSWORD', 'postgres'),
        'sslmode': os.getenv('DATASOURCE_POSTGRES_SSL_MODE', 'require')
    }

def print_config(config: Dict[str, str], show_password: bool = False):
    """
    Print database configuration in a readable format
    
    Args:
        config: Database configuration dictionary
        show_password: Whether to show the actual password (default: False)
    """
    print("📋 Database Configuration:")
    print(f"  Host: {config['host']}")
    print(f"  Port: {config['port']}")
    print(f"  Database: {config['dbname']}")
    print(f"  User: {config['user']}")
    print(f"  SSL Mode: {config['sslmode']}")
    
    if show_password:
        print(f"  Password: {config['password']}")
    else:
        password_display = '*' * len(config['password']) if config['password'] else 'Not set'
        print(f"  Password: {password_display}")

def validate_config(config: Dict[str, str]) -> bool:
    """
    Validate that required configuration values are present
    
    Args:
        config: Database configuration dictionary
    
    Returns:
        True if configuration is valid, False otherwise
    """
    required_fields = ['host', 'port', 'dbname', 'user', 'password']
    missing_fields = []
    
    for field in required_fields:
        if not config.get(field):
            missing_fields.append(field)
    
    if missing_fields:
        print(f"❌ Missing required configuration: {', '.join(missing_fields)}")
        return False
    
    return True

# Example usage
if __name__ == "__main__":
    print("Testing environment utilities...")
    
    # Reload and get config
    config = get_postgres_config()
    
    # Print config (without password)
    print_config(config)
    
    # Validate config
    if validate_config(config):
        print("✅ Configuration is valid")
    else:
        print("❌ Configuration is invalid") 