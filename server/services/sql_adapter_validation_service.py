"""
SQL Adapter Validation Service
==============================

Service that validates SQL adapter configurations according to the adapter granularity strategy,
implementing SQL-specific performance safeguards, query pattern detection, and resource limits validation.

This service is specifically designed for SQL adapters (SQLite, PostgreSQL, MySQL) and implements
SQL-specific validation rules including query analysis, table access patterns, and JOIN complexity.
"""

import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class AdapterComplexity(Enum):
    """Adapter complexity levels based on granularity strategy"""
    SINGLE_TABLE = "single_table"
    MATERIALIZED_VIEW = "materialized_view"
    MULTI_TABLE = "multi_table"


class QueryRiskLevel(Enum):
    """Query risk levels for performance assessment"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SQLAdapterValidationService:
    """
    Service for validating SQL adapter configurations according to granularity strategy.
    
    Implements the SQL adapter granularity strategy with:
    - SQL query analysis and optimization suggestions
    - JOIN complexity detection and risk assessment
    - SQL-specific performance safeguards
    - Table access pattern validation
    - Resource limits by SQL adapter complexity
    - SQL security validation (parameterization, filters)
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the adapter validation service.
        
        Args:
            config: Application configuration dictionary
        """
        self.config = config
        self.verbose = config.get('general', {}).get('verbose', False)
        
        # Load adapter limits configuration
        self.adapter_limits = config.get('adapter_limits', {})
        
        # Default resource limits by adapter complexity
        self.default_limits = {
            AdapterComplexity.SINGLE_TABLE: {
                'max_results': 500,
                'query_timeout': 5000,
                'memory_limit': '100MB'
            },
            AdapterComplexity.MATERIALIZED_VIEW: {
                'max_results': 1000,
                'query_timeout': 10000,
                'memory_limit': '200MB'
            },
            AdapterComplexity.MULTI_TABLE: {
                'max_results': 100,
                'query_timeout': 15000,
                'memory_limit': '50MB',
                'required_approval': True
            }
        }
        
        # Dangerous query patterns to detect
        self.dangerous_patterns = [
            r'SELECT\s+\*\s+FROM\s+\w+\s*(?:,\s*\w+)+(?:\s+WHERE)?',  # Cartesian product risk
            r'SELECT\s+.*\s+FROM\s+.*\s+WHERE\s+1\s*=\s*1',  # Always true condition
            r'SELECT\s+.*\s+FROM\s+.*\s+WHERE\s+.*\s+OR\s+.*\s+OR',  # Multiple OR conditions
            r'SELECT\s+.*\s+FROM\s+.*\s+(?:LEFT|RIGHT|FULL)\s+JOIN.*(?:LEFT|RIGHT|FULL)\s+JOIN',  # Multiple joins
        ]
        
        # Required security filters for multi-table queries
        self.required_security_patterns = [
            r'WHERE\s+.*\s*=\s*\{[^}]+\}',  # Parameterized WHERE clause
            r'LIMIT\s+\d+',  # Explicit LIMIT
        ]
        
        logger.info("SQL adapter validation service initialized")
    
    def _is_sql_adapter(self, adapter_config: Dict[str, Any]) -> bool:
        """
        Determine if an adapter should be validated with SQL-specific rules.
        
        Args:
            adapter_config: Adapter configuration dictionary
            
        Returns:
            True if this is a SQL adapter that needs SQL validation
        """
        # Check datasource type
        datasource = adapter_config.get('datasource', '')
        sql_datasources = ['sqlite', 'postgres', 'mysql', 'postgresql']
        
        if datasource in sql_datasources:
            return True
        
        # Check implementation path
        implementation = adapter_config.get('implementation', '')
        if 'sql' in implementation.lower() or 'relational' in implementation.lower():
            return True
        
        # Check for SQL-specific config
        config = adapter_config.get('config', {})
        if config.get('table') or config.get('query_template'):
            return True
            
        return False
    
    def validate_adapter_config(self, adapter_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate adapter configuration with enhanced performance safeguards.
        
        Args:
            adapter_config: Adapter configuration dictionary
            
        Returns:
            Validation result with errors, warnings, and recommendations
        """
        result = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'recommendations': [],
            'complexity': None,
            'risk_level': None
        }
        
        try:
            # Check if this is a SQL adapter that needs validation
            if not self._is_sql_adapter(adapter_config):
                result['recommendations'].append("Non-SQL adapter - skipping SQL-specific validation")
                return result
            
            # Basic configuration validation
            self._validate_basic_config(adapter_config, result)
            
            # Determine adapter complexity
            complexity = self._determine_complexity(adapter_config)
            result['complexity'] = complexity.value
            
            # Validate resource limits
            self._validate_resource_limits(adapter_config, complexity, result)
            
            # Validate query patterns if custom query is provided
            if adapter_config.get('config', {}).get('query_template'):
                query_template = adapter_config['config']['query_template']
                query_analysis = self._analyze_query_risk(query_template)
                result['risk_level'] = query_analysis['risk_level']
                result['warnings'].extend(query_analysis['warnings'])
                
                if query_analysis['risk_level'] == QueryRiskLevel.HIGH.value:
                    result['errors'].append("High-risk query pattern detected - requires manual review")
                    result['is_valid'] = False
                
                # Validate security requirements for complex queries
                if complexity == AdapterComplexity.MULTI_TABLE:
                    self._validate_security_requirements(query_template, result)
            
            # Validate table access patterns
            self._validate_table_access(adapter_config, result)
            
            # Add recommendations based on complexity
            self._add_complexity_recommendations(complexity, result)
            
            # Final validation
            if result['errors']:
                result['is_valid'] = False
                
        except Exception as e:
            logger.error(f"Error validating adapter config: {str(e)}")
            result['is_valid'] = False
            result['errors'].append(f"Validation error: {str(e)}")
        
        return result
    
    def _validate_basic_config(self, adapter_config: Dict[str, Any], result: Dict[str, Any]):
        """Validate basic adapter configuration requirements."""
        config = adapter_config.get('config', {})
        
        # Check for required performance safeguards
        if not config.get('max_results'):
            result['errors'].append("max_results is required to prevent runaway queries")
        elif config.get('max_results') > 1000:
            result['errors'].append("max_results cannot exceed 1000 for performance")
        
        if not config.get('query_timeout'):
            result['errors'].append("query_timeout is required to prevent long-running queries")
        elif config.get('query_timeout') > 30000:  # 30 seconds
            result['errors'].append("query_timeout cannot exceed 30 seconds")
        
        # Check for conflicting configurations
        if config.get('table') and config.get('query_template'):
            result['errors'].append("Use either 'table' (simple) or 'query_template' (complex), not both")
    
    def _determine_complexity(self, adapter_config: Dict[str, Any]) -> AdapterComplexity:
        """Determine adapter complexity based on configuration."""
        config = adapter_config.get('config', {})
        
        # Check for materialized view indicators
        table_name = config.get('table', '')
        if '_mv' in table_name.lower() or 'materialized' in table_name.lower():
            return AdapterComplexity.MATERIALIZED_VIEW
        
        # Check for multi-table patterns
        query_template = config.get('query_template', '')
        if query_template:
            if 'JOIN' in query_template.upper():
                return AdapterComplexity.MULTI_TABLE
            if len(re.findall(r'FROM\s+(\w+)', query_template, re.IGNORECASE)) > 1:
                return AdapterComplexity.MULTI_TABLE
        
        # Default to single table
        return AdapterComplexity.SINGLE_TABLE
    
    def _validate_resource_limits(self, adapter_config: Dict[str, Any], 
                                 complexity: AdapterComplexity, result: Dict[str, Any]):
        """Validate resource limits based on adapter complexity."""
        config = adapter_config.get('config', {})
        limits = self.adapter_limits.get(complexity.value, self.default_limits[complexity])
        
        # Check max_results limit
        max_results = config.get('max_results', 0)
        if max_results > limits['max_results']:
            result['errors'].append(
                f"max_results ({max_results}) exceeds limit for {complexity.value} "
                f"adapters ({limits['max_results']})"
            )
        
        # Check query timeout limit
        query_timeout = config.get('query_timeout', 0)
        if query_timeout > limits['query_timeout']:
            result['errors'].append(
                f"query_timeout ({query_timeout}ms) exceeds limit for {complexity.value} "
                f"adapters ({limits['query_timeout']}ms)"
            )
        
        # Check for required approval for multi-table adapters
        if complexity == AdapterComplexity.MULTI_TABLE and limits.get('required_approval'):
            if not config.get('approved_by_admin'):
                result['warnings'].append(
                    "Multi-table adapter requires admin approval for production use"
                )
    
    def _analyze_query_risk(self, query: str) -> Dict[str, Any]:
        """Analyze query for potential performance issues."""
        risk_score = 0
        warnings = []
        
        query_upper = query.upper()
        
        # Check for JOINs
        join_count = query_upper.count('JOIN')
        if join_count > 0:
            risk_score += join_count * 10
            warnings.append(f"Query contains {join_count} JOIN operations")
        
        # Check for subqueries
        select_count = query_upper.count('SELECT')
        if select_count > 1:
            risk_score += (select_count - 1) * 15
            warnings.append(f"Query contains {select_count - 1} subqueries")
        
        # Check for WHERE clause
        if 'WHERE' not in query_upper:
            risk_score += 25
            warnings.append("Query lacks WHERE clause - potential full table scan")
        
        # Check for LIMIT
        if 'LIMIT' not in query_upper:
            risk_score += 20
            warnings.append("Query lacks LIMIT clause")
        
        # Check for dangerous patterns
        for pattern in self.dangerous_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                risk_score += 30
                warnings.append(f"Potentially dangerous query pattern detected")
        
        # Check for SELECT *
        if re.search(r'SELECT\s+\*', query, re.IGNORECASE):
            risk_score += 15
            warnings.append("SELECT * can be inefficient - consider specifying columns")
        
        # Determine risk level
        if risk_score < 20:
            risk_level = QueryRiskLevel.LOW.value
        elif risk_score < 50:
            risk_level = QueryRiskLevel.MEDIUM.value
        else:
            risk_level = QueryRiskLevel.HIGH.value
        
        return {
            'risk_score': risk_score,
            'risk_level': risk_level,
            'warnings': warnings,
            'approved': risk_score < 50
        }
    
    def _validate_security_requirements(self, query_template: str, result: Dict[str, Any]):
        """Validate security requirements for multi-table queries."""
        # Check for required parameters
        if not re.search(r'\{[^}]+\}', query_template):
            result['errors'].append(
                "Multi-table queries must have required parameters to prevent full table scans"
            )
        
        # Check for parameterized WHERE clause
        has_parameterized_where = any(
            re.search(pattern, query_template, re.IGNORECASE) 
            for pattern in self.required_security_patterns
        )
        
        if not has_parameterized_where:
            result['errors'].append(
                "Multi-table queries must include parameterized WHERE clauses"
            )
    
    def _validate_table_access(self, adapter_config: Dict[str, Any], result: Dict[str, Any]):
        """Validate table access patterns for security."""
        config = adapter_config.get('config', {})
        
        # Check for security filters
        if not config.get('security_filter') and not config.get('allowed_columns'):
            result['warnings'].append(
                "Consider adding security_filter or allowed_columns for better access control"
            )
        
        # Validate allowed columns if specified
        allowed_columns = config.get('allowed_columns', [])
        if allowed_columns:
            sensitive_columns = ['password', 'ssn', 'credit_card', 'api_key', 'secret']
            for col in allowed_columns:
                if any(sensitive in col.lower() for sensitive in sensitive_columns):
                    result['warnings'].append(
                        f"Column '{col}' may contain sensitive data - verify access requirements"
                    )
    
    def _add_complexity_recommendations(self, complexity: AdapterComplexity, result: Dict[str, Any]):
        """Add recommendations based on adapter complexity."""
        if complexity == AdapterComplexity.SINGLE_TABLE:
            result['recommendations'].extend([
                "Consider adding caching for frequently accessed data",
                "Ensure proper indexing on query columns",
                "Monitor query performance and adjust limits if needed"
            ])
        elif complexity == AdapterComplexity.MATERIALIZED_VIEW:
            result['recommendations'].extend([
                "Set up appropriate refresh schedule for materialized view",
                "Monitor view freshness and update frequency",
                "Consider partitioning for large datasets"
            ])
        elif complexity == AdapterComplexity.MULTI_TABLE:
            result['recommendations'].extend([
                "Consider splitting into multiple single-table adapters",
                "Implement comprehensive monitoring for query performance",
                "Add query execution plan analysis",
                "Consider creating a materialized view for this query pattern"
            ])
    
    def validate_all_adapters(self, adapter_configs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validate all adapter configurations in batch.
        
        Args:
            adapter_configs: List of adapter configurations
            
        Returns:
            Batch validation results
        """
        results = {
            'overall_valid': True,
            'total_adapters': len(adapter_configs),
            'valid_adapters': 0,
            'invalid_adapters': 0,
            'adapter_results': {}
        }
        
        for adapter_config in adapter_configs:
            adapter_name = adapter_config.get('name', 'unnamed')
            validation_result = self.validate_adapter_config(adapter_config)
            
            results['adapter_results'][adapter_name] = validation_result
            
            if validation_result['is_valid']:
                results['valid_adapters'] += 1
            else:
                results['invalid_adapters'] += 1
                results['overall_valid'] = False
        
        return results 