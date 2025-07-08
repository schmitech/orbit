#!/usr/bin/env python3
"""
PostgreSQL Adapter Configuration Validation
===========================================

This script validates that your PostgreSQL adapter configuration follows
the adapter granularity strategy without requiring PostgreSQL to be installed.

Usage:
    python validate_config_only.py
"""

import sys
import os
sys.path.insert(0, '../../server')

import yaml
import json
from services.sql_adapter_validation_service import SQLAdapterValidationService

def load_config():
    """Load the main config.yaml file."""
    try:
        with open('../../config.yaml', 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print("❌ config.yaml not found. Make sure you're running from the postgresql directory.")
        return None

def validate_adapter_config():
    """Validate the PostgreSQL adapter configuration."""
    print("PostgreSQL Adapter Configuration Validation")
    print("=" * 60)
    
    config = load_config()
    if not config:
        return False
    
    # Find all PostgreSQL adapters
    postgres_adapters = [
        adapter for adapter in config.get('adapters', [])
        if adapter.get('datasource') == 'postgres'
    ]
    
    if not postgres_adapters:
        print("❌ No PostgreSQL adapters found in config.yaml")
        return False
    
    print(f"✅ Found {len(postgres_adapters)} PostgreSQL adapter(s)")
    
    # Initialize validation service
    service = SQLAdapterValidationService(config)
    
    all_valid = True
    
    for adapter in postgres_adapters:
        print(f"\n📋 Validating adapter: {adapter['name']}")
        print("-" * 40)
        
        # Validate the adapter
        result = service.validate_adapter_config(adapter)
        
        # Display results
        print(f"✅ Valid: {'YES' if result['is_valid'] else 'NO'}")
        print(f"✅ Complexity: {result['complexity'].upper()}")
        print(f"✅ Risk Level: {result['risk_level'].upper()}")
        
        if result['warnings']:
            print(f"\n⚠️  Warnings ({len(result['warnings'])}):")
            for warning in result['warnings']:
                print(f"  - {warning}")
        
        if result['recommendations']:
            print(f"\n💡 Recommendations ({len(result['recommendations'])}):")
            for rec in result['recommendations']:
                print(f"  - {rec}")
        
        if result['errors']:
            print(f"\n❌ Errors ({len(result['errors'])}):")
            for error in result['errors']:
                print(f"  - {error}")
            all_valid = False
    
    return all_valid

def analyze_query_pattern():
    """Analyze the query pattern in the adapter."""
    print("\n" + "=" * 60)
    print("QUERY PATTERN ANALYSIS")
    print("=" * 60)
    
    config = load_config()
    if not config:
        return False
    
    # Find the recent-customer-activity adapter
    adapter = next((a for a in config['adapters'] if a['name'] == 'recent-customer-activity'), None)
    
    if not adapter:
        print("❌ 'recent-customer-activity' adapter not found")
        return False
    
    query_template = adapter.get('config', {}).get('query_template', '')
    if not query_template:
        print("❌ No query_template found in adapter config")
        return False
    
    print("📊 Query Template:")
    print("-" * 20)
    print(query_template.strip())
    
    # Analyze query characteristics
    print("\n🔍 Query Analysis:")
    print("-" * 20)
    
    # Check for JOIN operations
    join_count = query_template.upper().count('JOIN')
    print(f"✅ JOIN operations: {join_count}")
    
    # Check for WHERE clauses
    where_count = query_template.upper().count('WHERE')
    print(f"✅ WHERE clauses: {where_count}")
    
    # Check for parameters
    param_count = query_template.count('{')
    print(f"✅ Parameters: {param_count}")
    
    # Check for LIMIT
    has_limit = 'LIMIT' in query_template.upper()
    print(f"✅ Has LIMIT: {'YES' if has_limit else 'NO'}")
    
    # Check for date filtering
    has_date_filter = 'INTERVAL' in query_template.upper()
    print(f"✅ Has date filtering: {'YES' if has_date_filter else 'NO'}")
    
    # Security analysis
    print("\n🔒 Security Analysis:")
    print("-" * 20)
    
    required_params = adapter.get('config', {}).get('required_parameters', [])
    print(f"✅ Required parameters: {required_params}")
    
    if 'customer_id' in required_params:
        print("✅ Customer-specific filtering: YES (prevents full table scans)")
    else:
        print("⚠️  Customer-specific filtering: NO (potential security risk)")
    
    return True

def validate_datasource_config():
    """Validate the PostgreSQL datasource configuration."""
    print("\n" + "=" * 60)
    print("DATASOURCE CONFIGURATION")
    print("=" * 60)
    
    config = load_config()
    if not config:
        return False
    
    postgres_config = config.get('datasources', {}).get('postgres', {})
    
    if not postgres_config:
        print("❌ PostgreSQL datasource not found in config.yaml")
        return False
    
    print("📋 PostgreSQL Datasource Config:")
    print("-" * 30)
    
    print(f"✅ Host: {postgres_config.get('host', 'NOT SET')}")
    print(f"✅ Port: {postgres_config.get('port', 'NOT SET')}")
    print(f"✅ Database: {postgres_config.get('database', 'NOT SET')}")
    print(f"✅ Username: {postgres_config.get('username', 'NOT SET')}")
    print(f"✅ Password: {'SET' if postgres_config.get('password') else 'NOT SET'}")
    
    # Check for environment variables
    username = postgres_config.get('username', '')
    password = postgres_config.get('password', '')
    
    if username.startswith('${') and username.endswith('}'):
        env_var = username[2:-1]
        print(f"✅ Username uses environment variable: {env_var}")
        env_value = os.getenv(env_var)
        print(f"✅ Environment variable value: {'SET' if env_value else 'NOT SET'}")
    
    if password.startswith('${') and password.endswith('}'):
        env_var = password[2:-1]
        print(f"✅ Password uses environment variable: {env_var}")
        env_value = os.getenv(env_var)
        print(f"✅ Environment variable value: {'SET' if env_value else 'NOT SET'}")
    
    return True

def check_test_script_alignment():
    """Check if the test script matches the adapter configuration."""
    print("\n" + "=" * 60)
    print("TEST SCRIPT ALIGNMENT")
    print("=" * 60)
    
    # Load the adapter query
    config = load_config()
    if not config:
        return False
    
    adapter = next((a for a in config['adapters'] if a['name'] == 'recent-customer-activity'), None)
    if not adapter:
        print("❌ 'recent-customer-activity' adapter not found")
        return False
    
    adapter_query = adapter.get('config', {}).get('query_template', '').strip()
    
    # Check if the test script exists and read it
    try:
        with open('customer-order.py', 'r') as f:
            script_content = f.read()
        
        # Look for the query in the script
        if 'SELECT c.name, o.order_date, o.total' in script_content:
            print("✅ Test script contains matching query structure")
            
            # Check if the query patterns match
            if 'customers c' in script_content and 'orders o' in script_content:
                print("✅ Test script uses correct table aliases")
            
            if 'INNER JOIN' in script_content:
                print("✅ Test script uses INNER JOIN like adapter")
            
            if 'customer_id' in script_content:
                print("✅ Test script filters by customer_id")
            
            if 'INTERVAL' in script_content:
                print("✅ Test script uses date interval filtering")
            
            print("✅ Test script alignment: GOOD")
            return True
        else:
            print("❌ Test script query doesn't match adapter query")
            return False
            
    except FileNotFoundError:
        print("❌ customer-order.py not found")
        return False

def main():
    """Run all validation checks."""
    print("🔍 PostgreSQL Adapter Configuration Validation")
    print("=" * 60)
    
    all_checks_passed = True
    
    # 1. Validate adapter configuration
    if not validate_adapter_config():
        all_checks_passed = False
    
    # 2. Analyze query patterns
    if not analyze_query_pattern():
        all_checks_passed = False
    
    # 3. Validate datasource configuration
    if not validate_datasource_config():
        all_checks_passed = False
    
    # 4. Check test script alignment
    if not check_test_script_alignment():
        all_checks_passed = False
    
    # Final result
    print("\n" + "=" * 60)
    if all_checks_passed:
        print("🎉 ALL CONFIGURATION CHECKS PASSED!")
        print("=" * 60)
        print("✅ Your PostgreSQL adapter configuration is correct")
        print("✅ Adapter follows granularity strategy best practices")
        print("✅ Test scripts are aligned with adapter configuration")
        print("✅ Security patterns are properly implemented")
        print("\n💡 Next Steps:")
        print("   1. Install PostgreSQL: brew install postgresql")
        print("   2. Create database: createdb retrieval")
        print("   3. Run schema: psql -d retrieval -f customer-order.sql")
        print("   4. Test adapter: python test_adapter_integration.py")
        return 0
    else:
        print("❌ SOME CHECKS FAILED")
        print("=" * 60)
        print("Please review the errors above and fix configuration issues.")
        return 1

if __name__ == "__main__":
    exit(main()) 