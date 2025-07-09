"""
Tests for the SQL Adapter Validation Service
============================================

Tests for validating SQL adapter configurations according to the adapter granularity strategy.
Specifically focuses on SQL adapters (SQLite, PostgreSQL, MySQL) and SQL-specific validation rules.
"""

import pytest
import sys
import os
import yaml
from pathlib import Path
from typing import Dict, Any, List

# Add the server directory to path to fix import issues
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.sql_adapter_validation_service import SQLAdapterValidationService, AdapterComplexity, QueryRiskLevel


@pytest.fixture
def test_config():
    """Load the actual config.yaml for testing."""
    # Try to use the server's config loading function which handles imports
    try:
        from config.config_manager import load_config as load_server_config
        return load_server_config()
    except Exception as e:
        # Fallback to manual loading if server config loading fails
        config_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"
        
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            # Manually process imports if present
            if 'import' in config:
                import_files = config['import']
                if isinstance(import_files, str):
                    import_files = [import_files]
                
                # Remove the import key from config
                del config['import']
                
                # Load and merge each imported file
                config_dir = config_path.parent
                for import_file in import_files:
                    import_path = config_dir / import_file
                    try:
                        with open(import_path, 'r') as f:
                            imported_config = yaml.safe_load(f)
                            # Merge the imported config into the main config
                            config.update(imported_config)
                    except Exception as import_error:
                        print(f"Warning: Failed to import {import_file}: {import_error}")
            
            return config
        else:
            # Fallback minimal config for testing
            return {
                "general": {
                    "verbose": False
                },
                "adapter_limits": {
                    "single_table": {
                        "max_results": 500,
                        "query_timeout": 5000,
                        "memory_limit": "100MB"
                    },
                    "materialized_view": {
                        "max_results": 1000,
                        "query_timeout": 10000,
                        "memory_limit": "200MB"
                    },
                    "multi_table": {
                        "max_results": 100,
                        "query_timeout": 15000,
                        "memory_limit": "50MB",
                        "required_approval": True
                    }
                }
            }


@pytest.fixture
def validation_service(test_config):
    """Create an SQLAdapterValidationService instance for testing."""
    return SQLAdapterValidationService(test_config)


@pytest.fixture
def single_table_adapter():
    """Sample single-table adapter configuration."""
    return {
        "name": "test-single-table",
        "type": "retriever",
        "datasource": "sqlite",
        "adapter": "qa",
        "implementation": "retrievers.implementations.qa.QASSQLRetriever",
        "config": {
            "table": "test_table",
            "max_results": 100,
            "query_timeout": 3000,
            "confidence_threshold": 0.3,
            "allowed_columns": ["id", "name", "content"],
            "security_filter": "active = true"
        }
    }


@pytest.fixture
def materialized_view_adapter():
    """Sample materialized view adapter configuration."""
    return {
        "name": "test-materialized-view",
        "type": "retriever",
        "datasource": "postgres",
        "adapter": "sql",
        "implementation": "retrievers.implementations.relational.PostgreSQLRetriever",
        "config": {
            "table": "customer_summary_mv",
            "max_results": 200,
            "query_timeout": 8000,
            "cache_ttl": 3600
        }
    }


@pytest.fixture
def multi_table_adapter():
    """Sample multi-table adapter configuration."""
    return {
        "name": "test-multi-table",
        "type": "retriever",
        "datasource": "postgres",
        "adapter": "sql",
        "implementation": "retrievers.implementations.relational.PostgreSQLRetriever",
        "config": {
            "query_template": """
                SELECT c.name, o.order_date, o.total
                FROM customers c
                INNER JOIN orders o ON c.id = o.customer_id
                WHERE c.id = {customer_id}
                AND o.created_at >= NOW() - INTERVAL '7 days'
                ORDER BY o.created_at DESC
                LIMIT 20
            """,
            "max_results": 20,
            "query_timeout": 12000,
            "required_parameters": ["customer_id"],
            "approved_by_admin": True
        }
    }


@pytest.fixture
def vector_adapter():
    """Sample vector adapter configuration (non-SQL)."""
    return {
        "name": "test-vector",
        "type": "retriever",
        "datasource": "chroma",
        "adapter": "qa",
        "implementation": "retrievers.implementations.qa.QAChromaRetriever",
        "config": {
            "confidence_threshold": 0.3,
            "max_results": 5,
            "return_results": 3
        }
    }


class TestSQLAdapterValidationService:
    """Test cases for the SQLAdapterValidationService."""
    
    def test_service_initialization(self, test_config):
        """Test that the SQL adapter validation service initializes correctly."""
        service = SQLAdapterValidationService(test_config)
        assert service.config == test_config
        assert hasattr(service, 'adapter_limits')
        assert hasattr(service, 'default_limits')
        assert hasattr(service, 'dangerous_patterns')
    
    def test_sql_adapter_detection(self, validation_service, single_table_adapter, vector_adapter):
        """Test SQL adapter detection logic."""
        # SQL adapter should be detected
        assert validation_service._is_sql_adapter(single_table_adapter) == True
        
        # Vector adapter should not be detected as SQL
        assert validation_service._is_sql_adapter(vector_adapter) == False
        
        # Test with different datasources
        postgres_adapter = {"datasource": "postgres", "config": {}}
        assert validation_service._is_sql_adapter(postgres_adapter) == True
        
        chroma_adapter = {"datasource": "chroma", "config": {}}
        assert validation_service._is_sql_adapter(chroma_adapter) == False
    
    def test_complexity_determination(self, validation_service):
        """Test adapter complexity determination."""
        # Single table
        single_config = {"config": {"table": "users"}}
        complexity = validation_service._determine_complexity(single_config)
        assert complexity == AdapterComplexity.SINGLE_TABLE
        
        # Materialized view
        mv_config = {"config": {"table": "user_summary_mv"}}
        complexity = validation_service._determine_complexity(mv_config)
        assert complexity == AdapterComplexity.MATERIALIZED_VIEW
        
        # Multi-table with JOIN
        join_config = {"config": {"query_template": "SELECT * FROM users u JOIN orders o ON u.id = o.user_id"}}
        complexity = validation_service._determine_complexity(join_config)
        assert complexity == AdapterComplexity.MULTI_TABLE
    
    def test_query_risk_analysis(self, validation_service):
        """Test query risk analysis."""
        # Low risk query
        low_risk_query = "SELECT id, name FROM users WHERE active = true LIMIT 10"
        result = validation_service._analyze_query_risk(low_risk_query)
        assert result['risk_level'] == QueryRiskLevel.LOW.value
        
        # High risk query (no WHERE, no LIMIT, JOIN)
        high_risk_query = "SELECT * FROM users u JOIN orders o ON u.id = o.user_id"
        result = validation_service._analyze_query_risk(high_risk_query)
        assert result['risk_level'] == QueryRiskLevel.HIGH.value
        assert len(result['warnings']) > 0
    
    def test_single_table_validation(self, validation_service, single_table_adapter):
        """Test validation of single-table adapter."""
        result = validation_service.validate_adapter_config(single_table_adapter)
        
        assert result['is_valid'] == True
        assert result['complexity'] == AdapterComplexity.SINGLE_TABLE.value
        assert 'recommendations' in result
        assert isinstance(result['recommendations'], list)
    
    def test_materialized_view_validation(self, validation_service, materialized_view_adapter):
        """Test validation of materialized view adapter."""
        result = validation_service.validate_adapter_config(materialized_view_adapter)
        
        assert result['is_valid'] == True
        assert result['complexity'] == AdapterComplexity.MATERIALIZED_VIEW.value
        assert any('materialized view' in rec.lower() for rec in result['recommendations'])
    
    def test_multi_table_validation(self, validation_service, multi_table_adapter):
        """Test validation of multi-table adapter."""
        result = validation_service.validate_adapter_config(multi_table_adapter)
        
        assert result['is_valid'] == True
        assert result['complexity'] == AdapterComplexity.MULTI_TABLE.value
        assert result['risk_level'] in [QueryRiskLevel.LOW.value, QueryRiskLevel.MEDIUM.value]
        assert any('splitting into multiple' in rec.lower() for rec in result['recommendations'])
    
    def test_vector_adapter_skipped(self, validation_service, vector_adapter):
        """Test that vector adapters skip SQL validation."""
        result = validation_service.validate_adapter_config(vector_adapter)
        
        assert result['is_valid'] == True
        assert result['complexity'] is None
        assert any('non-sql adapter' in rec.lower() for rec in result['recommendations'])
    
    def test_invalid_configuration(self, validation_service):
        """Test validation of invalid configurations."""
        # Missing max_results
        invalid_config = {
            "name": "invalid-adapter",
            "datasource": "sqlite",
            "config": {
                "table": "test_table"
                # Missing max_results and query_timeout
            }
        }
        
        result = validation_service.validate_adapter_config(invalid_config)
        assert result['is_valid'] == False
        assert len(result['errors']) > 0
        assert any('max_results' in error for error in result['errors'])
        assert any('query_timeout' in error for error in result['errors'])
    
    def test_resource_limit_validation(self, validation_service):
        """Test resource limit validation."""
        # Exceeds single table limits
        excessive_config = {
            "name": "excessive-adapter",
            "datasource": "sqlite",
            "config": {
                "table": "test_table",
                "max_results": 1000,  # Exceeds single table limit of 500
                "query_timeout": 10000  # Exceeds single table limit of 5000
            }
        }
        
        result = validation_service.validate_adapter_config(excessive_config)
        assert result['is_valid'] == False
        assert any('exceeds limit' in error for error in result['errors'])
    
    def test_security_validation(self, validation_service):
        """Test security validation for multi-table queries."""
        # Multi-table query without proper security
        insecure_config = {
            "name": "insecure-adapter",
            "datasource": "postgres",
            "config": {
                "query_template": "SELECT * FROM users u JOIN orders o ON u.id = o.user_id",
                "max_results": 50,
                "query_timeout": 10000
            }
        }
        
        result = validation_service.validate_adapter_config(insecure_config)
        assert result['is_valid'] == False
        assert any('required parameters' in error.lower() for error in result['errors'])


class TestConfigurationValidation:
    """Test validation against actual configuration file."""
    
    def test_current_adapters_validation(self, validation_service, test_config):
        """Test validation of all adapters in current config."""
        adapter_configs = test_config.get('adapters', [])
        
        # Should have some adapters configured
        assert len(adapter_configs) > 0
        
        valid_count = 0
        invalid_count = 0
        
        for adapter_config in adapter_configs:
            result = validation_service.validate_adapter_config(adapter_config)
            
            if result['is_valid']:
                valid_count += 1
            else:
                invalid_count += 1
                # Print errors for debugging if needed
                if result['errors']:
                    print(f"Validation errors for {adapter_config.get('name')}: {result['errors']}")
        
        # Most adapters should be valid
        assert valid_count > 0
        print(f"Validation results: {valid_count} valid, {invalid_count} invalid out of {len(adapter_configs)} total")
    
    def test_sql_adapters_only(self, validation_service, test_config):
        """Test that only SQL adapters get full validation."""
        adapter_configs = test_config.get('adapters', [])
        
        sql_adapters = []
        non_sql_adapters = []
        
        for adapter_config in adapter_configs:
            result = validation_service.validate_adapter_config(adapter_config)
            
            if validation_service._is_sql_adapter(adapter_config):
                sql_adapters.append((adapter_config.get('name'), result))
            else:
                non_sql_adapters.append((adapter_config.get('name'), result))
        
        # SQL adapters should have complexity assigned
        for name, result in sql_adapters:
            if result['is_valid']:
                assert result['complexity'] is not None, f"SQL adapter {name} should have complexity"
        
        # Non-SQL adapters should skip validation
        for name, result in non_sql_adapters:
            assert any('non-sql adapter' in rec.lower() for rec in result['recommendations']), \
                f"Non-SQL adapter {name} should skip SQL validation"


class TestPerformanceAndSecurity:
    """Test performance and security validation features."""
    
    def test_dangerous_query_detection(self, validation_service):
        """Test detection of dangerous query patterns."""
        dangerous_queries = [
            "SELECT * FROM users, orders",  # Cartesian product
            "SELECT * FROM users WHERE 1=1",  # Always true condition
            "SELECT * FROM users u LEFT JOIN orders o ON u.id = o.user_id LEFT JOIN products p ON o.product_id = p.id"  # Multiple joins
        ]
        
        for query in dangerous_queries:
            result = validation_service._analyze_query_risk(query)
            assert result['risk_score'] > 20, f"Dangerous query should have high risk score: {query}"
    
    def test_query_optimization_suggestions(self, validation_service):
        """Test that validation provides optimization suggestions."""
        # Query without LIMIT
        no_limit_query = "SELECT * FROM users WHERE active = true"
        result = validation_service._analyze_query_risk(no_limit_query)
        assert any('LIMIT' in warning for warning in result['warnings'])
        
        # Query with SELECT *
        select_all_query = "SELECT * FROM users LIMIT 10"
        result = validation_service._analyze_query_risk(select_all_query)
        assert any('SELECT *' in warning for warning in result['warnings'])


@pytest.mark.integration
class TestIntegrationWithRetriever:
    """Integration tests with actual retriever initialization."""
    
    def test_validation_during_retriever_init(self, test_config):
        """Test that validation occurs during retriever initialization."""
        # This would require setting up an actual retriever, but demonstrates
        # how the validation integrates with the retriever lifecycle
        pass


def test_validation_script_functionality():
    """Test that validates the core SQL adapter functionality works like the original script."""
    # Try to use the server's config loading function which handles imports
    try:
        from config.config_manager import load_config as load_server_config
        config = load_server_config()
    except Exception as e:
        # Fallback to manual loading if server config loading fails
        config_path = Path(__file__).parent.parent.parent / "config" / "config.yaml"
        if not config_path.exists():
            # Fallback to old location for backward compatibility
            config_path = Path(__file__).parent.parent.parent / "config.yaml"
        
        if not config_path.exists():
            pytest.skip("config.yaml not found, skipping integration test")
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Manually process imports if present
        if 'import' in config:
            import_files = config['import']
            if isinstance(import_files, str):
                import_files = [import_files]
            
            # Remove the import key from config
            del config['import']
            
            # Load and merge each imported file
            config_dir = config_path.parent
            for import_file in import_files:
                import_path = config_dir / import_file
                try:
                    with open(import_path, 'r') as f:
                        imported_config = yaml.safe_load(f)
                        # Merge the imported config into the main config
                        config.update(imported_config)
                except Exception as import_error:
                    print(f"Warning: Failed to import {import_file}: {import_error}")
    
    validator = SQLAdapterValidationService(config)
    adapter_configs = config.get('adapters', [])
    
    assert len(adapter_configs) > 0, "Should have adapter configurations"
    
    results = []
    for adapter_config in adapter_configs:
        result = validator.validate_adapter_config(adapter_config)
        results.append((adapter_config.get('name'), result))
    
    # Should process all adapters without errors
    assert len(results) == len(adapter_configs)
    
    # Should have some valid adapters
    valid_count = sum(1 for _, result in results if result['is_valid'])
    assert valid_count > 0, "Should have at least some valid adapters" 