"""
Environment variable utilities for PostgreSQL and Ollama configuration
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

def get_postgres_config(env_file: Optional[str] = None, reload_env: bool = True) -> Dict[str, str]:
    """
    Get PostgreSQL configuration from environment variables
    
    Args:
        env_file: Optional path to .env file to reload before getting config
        reload_env: Whether to reload environment variables (default: True)
    
    Returns:
        Dictionary with database configuration
    """
    if reload_env:
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

def get_ollama_config(env_file: Optional[str] = None, reload_env: bool = True) -> Dict[str, str]:
    """
    Get Ollama configuration from environment variables
    
    Args:
        env_file: Optional path to .env file to reload before getting config
        reload_env: Whether to reload environment variables (default: True)
    
    Returns:
        Dictionary with Ollama configuration
    """
    if reload_env:
        if env_file:
            reload_env_variables(env_file)
        else:
            reload_env_variables()
    
    return {
        'base_url': os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434'),
        'embedding_model': os.getenv('OLLAMA_EMBEDDING_MODEL', 'nomic-embed-text'),
        'inference_model': os.getenv('OLLAMA_INFERENCE_MODEL', 'gemma3:1b')
    }

def print_postgres_config(config: Dict[str, str], show_password: bool = False):
    """
    Print PostgreSQL configuration in a readable format
    
    Args:
        config: Database configuration dictionary
        show_password: Whether to show the actual password (default: False)
    """
    print("📋 PostgreSQL Configuration:")
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

def print_ollama_config(config: Dict[str, str]):
    """
    Print Ollama configuration in a readable format
    
    Args:
        config: Ollama configuration dictionary
    """
    print("🤖 Ollama Configuration:")
    print(f"  Base URL: {config['base_url']}")
    print(f"  Embedding Model: {config['embedding_model']}")
    print(f"  Inference Model: {config['inference_model']}")

def print_all_config(show_password: bool = False):
    """
    Print all configuration (PostgreSQL and Ollama) in a readable format
    
    Args:
        show_password: Whether to show the actual password (default: False)
    """
    reload_env_variables()
    
    postgres_config = get_postgres_config(reload_env=False)
    ollama_config = get_ollama_config(reload_env=False)
    
    print_postgres_config(postgres_config, show_password)
    print()
    print_ollama_config(ollama_config)

def validate_postgres_config(config: Dict[str, str]) -> bool:
    """
    Validate that required PostgreSQL configuration values are present
    
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
        print(f"❌ Missing required PostgreSQL configuration: {', '.join(missing_fields)}")
        return False
    
    return True

def validate_ollama_config(config: Dict[str, str]) -> bool:
    """
    Validate that required Ollama configuration values are present
    
    Args:
        config: Ollama configuration dictionary
    
    Returns:
        True if configuration is valid, False otherwise
    """
    required_fields = ['base_url', 'embedding_model', 'inference_model']
    missing_fields = []
    
    for field in required_fields:
        if not config.get(field):
            missing_fields.append(field)
    
    if missing_fields:
        print(f"❌ Missing required Ollama configuration: {', '.join(missing_fields)}")
        return False
    
    return True

def validate_all_config() -> bool:
    """
    Validate all configuration (PostgreSQL and Ollama)
    
    Returns:
        True if all configuration is valid, False otherwise
    """
    reload_env_variables()
    
    postgres_config = get_postgres_config(reload_env=False)
    ollama_config = get_ollama_config(reload_env=False)
    
    postgres_valid = validate_postgres_config(postgres_config)
    ollama_valid = validate_ollama_config(ollama_config)
    
    return postgres_valid and ollama_valid

# Example usage
if __name__ == "__main__":
    print("Testing environment utilities...")
    print("=" * 50)
    
    # Print all configuration
    print_all_config()
    print()
    
    # Validate all configuration
    if validate_all_config():
        print("✅ All configuration is valid")
    else:
        print("❌ Configuration has issues")
    
    print("\n" + "=" * 50)
    print("Configuration Summary:")
    
    # Get individual configs for testing (no reload needed since we already did it)
    postgres_config = get_postgres_config(reload_env=False)
    ollama_config = get_ollama_config(reload_env=False)
    
    print(f"PostgreSQL: {postgres_config['host']}:{postgres_config['port']}/{postgres_config['dbname']}")
    print(f"Ollama: {ollama_config['base_url']}")
    print(f"Models: {ollama_config['embedding_model']} + {ollama_config['inference_model']}") 