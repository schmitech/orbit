#!/usr/bin/env python3
"""
Configuration Selector for Template Generator

This script helps select the appropriate configuration file based on the
database schema being analyzed. It automatically detects schema patterns
and suggests the best configuration.

USAGE:
    python config_selector.py --schema <schema_file> [--output <config_file>]

EXAMPLES:
    # Auto-detect and suggest configuration
    python config_selector.py --schema database-schema.sql
    
    # Generate custom configuration file
    python config_selector.py --schema database-schema.sql --output custom-config.yaml
"""

import re
import yaml
import argparse
from typing import Dict, Any

class SchemaAnalyzer:
    """Analyzes database schema to determine the best configuration"""
    
    def __init__(self):
        self.schema_patterns = {
            'classified_data': {
                'keywords': ['classification', 'clearance', 'compartment', 'audit', 'pii', 'caveats'],
                'tables': ['knowledge_item', 'access_audit', 'users', 'compartments'],
                'score': 0
            },
            'ecommerce': {
                'keywords': ['customer', 'order', 'product', 'payment', 'shipping', 'cart'],
                'tables': ['customers', 'orders', 'products', 'payments'],
                'score': 0
            },
            'financial': {
                'keywords': ['transaction', 'account', 'balance', 'currency', 'tax', 'reconciliation'],
                'tables': ['transactions', 'accounts', 'balances', 'ledger'],
                'score': 0
            },
            'inventory': {
                'keywords': ['inventory', 'stock', 'warehouse', 'supplier', 'product'],
                'tables': ['inventory', 'stock', 'warehouses', 'suppliers'],
                'score': 0
            },
            'hr': {
                'keywords': ['employee', 'department', 'salary', 'position', 'hire'],
                'tables': ['employees', 'departments', 'positions', 'salaries'],
                'score': 0
            }
        }
    
    def analyze_schema(self, schema_path: str) -> Dict[str, Any]:
        """Analyze schema file to determine domain type"""
        with open(schema_path, 'r') as f:
            schema_content = f.read()
        
        # Convert to lowercase for case-insensitive matching
        content_lower = schema_content.lower()
        
        # Score each domain based on keyword and table presence
        for domain, patterns in self.schema_patterns.items():
            score = 0
            
            # Check for keywords
            for keyword in patterns['keywords']:
                if keyword in content_lower:
                    score += 1
            
            # Check for table names
            for table in patterns['tables']:
                if table in content_lower:
                    score += 2  # Tables are more significant than keywords
            
            # Check for specific patterns
            if domain == 'classified_data':
                if re.search(r'classification.*level', content_lower):
                    score += 3
                if re.search(r'clearance.*level', content_lower):
                    score += 3
                if re.search(r'audit.*log', content_lower):
                    score += 2
            
            elif domain == 'ecommerce':
                if re.search(r'customer.*id', content_lower):
                    score += 2
                if re.search(r'order.*total', content_lower):
                    score += 2
                if re.search(r'payment.*method', content_lower):
                    score += 2
            
            elif domain == 'financial':
                if re.search(r'transaction.*amount', content_lower):
                    score += 3
                if re.search(r'account.*balance', content_lower):
                    score += 3
                if re.search(r'currency.*code', content_lower):
                    score += 2
            
            patterns['score'] = score
        
        # Find the domain with highest score
        best_domain = max(self.schema_patterns.items(), key=lambda x: x[1]['score'])
        
        return {
            'detected_domain': best_domain[0],
            'confidence': best_domain[1]['score'],
            'all_scores': {k: v['score'] for k, v in self.schema_patterns.items()},
            'recommended_config': f"{best_domain[0]}-config.yaml"
        }
    
    def generate_custom_config(self, schema_path: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a custom configuration based on schema analysis"""
        base_config = {
            'generation': {
                'max_examples_per_template': 10,
                'similarity_threshold': 0.8,
                'defaults': {
                    'version': '1.0.0',
                    'approved': False,
                    'result_format': 'table'
                },
                'categories': []
            },
            'inference': {
                'analysis': {
                    'temperature': 0.1,
                    'max_tokens': 1024
                },
                'sql_generation': {
                    'temperature': 0.2,
                    'max_tokens': 2048
                }
            },
            'validation': {
                'required_fields': ['id', 'description', 'sql_template', 'parameters', 'nl_examples'],
                'min_examples': 3,
                'max_sql_length': 5000,
                'parameters': {
                    'valid_types': ['string', 'integer', 'decimal', 'date', 'datetime', 'boolean', 'enum'],
                    'required_fields': ['name', 'type', 'description', 'required']
                }
            },
            'schema': {
                'include_tables': [],
                'exclude_tables': ['migrations', 'schema_version'],
                'special_columns': {}
            },
            'grouping': {
                'features': ['intent', 'primary_entity', 'secondary_entity', 'aggregations', 'filters'],
                'feature_weights': {
                    'intent': 0.3,
                    'primary_entity': 0.3,
                    'secondary_entity': 0.2,
                    'aggregations': 0.1,
                    'filters': 0.1
                }
            },
            'output': {
                'sort_by': 'primary_entity',
                'group_by_category': True,
                'include_metadata': ['created_at', 'created_by', 'generator_version', 'validation_status']
            }
        }
        
        # Customize based on detected domain
        domain = analysis['detected_domain']
        
        if domain == 'classified_data':
            base_config['generation']['similarity_threshold'] = 0.85
            base_config['generation']['categories'] = [
                'access_control_queries', 'audit_queries', 'classification_queries',
                'compartment_queries', 'user_management_queries', 'retention_queries'
            ]
            base_config['schema']['special_columns'] = {
                'classification': {'pattern': '.*classification.*', 'format': 'enum'},
                'clearance': {'pattern': '.*clearance.*', 'format': 'enum'},
                'compartments': {'pattern': '.*compartment.*', 'format': 'enum'},
                'pii': {'pattern': '.*pii.*', 'format': 'boolean'},
                'caveats': {'pattern': '.*caveat.*', 'format': 'enum'}
            }
        
        elif domain == 'ecommerce':
            base_config['generation']['categories'] = [
                'customer_queries', 'order_queries', 'product_queries',
                'analytics_queries', 'payment_queries', 'shipping_queries'
            ]
            base_config['schema']['special_columns'] = {
                'email': {'pattern': '.*email.*', 'format': 'email'},
                'phone': {'pattern': '.*phone.*', 'format': 'phone'},
                'amount': {'pattern': '.*(amount|total|price).*', 'format': 'currency'},
                'status': {'pattern': '.*status.*', 'format': 'enum'},
                'date': {'pattern': '.*(date|_at)$', 'format': 'date'}
            }
        
        elif domain == 'financial':
            base_config['generation']['similarity_threshold'] = 0.85
            base_config['generation']['categories'] = [
                'transaction_queries', 'balance_queries', 'reporting_queries',
                'reconciliation_queries', 'compliance_queries', 'audit_queries'
            ]
            base_config['schema']['special_columns'] = {
                'amount': {'pattern': '.*(amount|total|balance).*', 'format': 'currency'},
                'account': {'pattern': '.*account.*', 'format': 'string'},
                'currency': {'pattern': '.*currency.*', 'format': 'enum'},
                'transaction_date': {'pattern': '.*transaction_date.*', 'format': 'date'},
                'tax': {'pattern': '.*tax.*', 'format': 'decimal'}
            }
        
        return base_config

def main():
    parser = argparse.ArgumentParser(description='Select configuration for template generator')
    parser.add_argument('--schema', required=True, help='Path to SQL schema file')
    parser.add_argument('--output', help='Path to output custom configuration file')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    analyzer = SchemaAnalyzer()
    analysis = analyzer.analyze_schema(args.schema)
    
    print("Schema Analysis Results:")
    print(f"Detected Domain: {analysis['detected_domain']}")
    print(f"Confidence Score: {analysis['confidence']}")
    print(f"Recommended Config: {analysis['recommended_config']}")
    
    if args.verbose:
        print("\nAll Domain Scores:")
        for domain, score in analysis['all_scores'].items():
            print(f"  {domain}: {score}")
    
    if args.output:
        custom_config = analyzer.generate_custom_config(args.schema, analysis)
        
        with open(args.output, 'w') as f:
            yaml.dump(custom_config, f, default_flow_style=False, sort_keys=False)
        
        print(f"\nCustom configuration saved to: {args.output}")
    
    # Suggest next steps
    print("\nNext Steps:")
    print(f"1. Use the recommended config: configs/{analysis['recommended_config']}")
    print(f"2. Or generate a custom config: python config_selector.py --schema {args.schema} --output custom-config.yaml")
    print(f"3. Run template generator: python template_generator.py --schema {args.schema} --config <config_file>")

if __name__ == '__main__':
    main()
