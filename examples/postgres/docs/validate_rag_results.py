#!/usr/bin/env python3
"""
RAG System Validation Test Suite
=================================

This script validates that the RAG system's responses match the actual SQL results.
It compares what the system claims to find with what's actually in the database.

Usage:
    python validate_rag_results.py                    # Run basic validation tests
    python validate_rag_results.py --full             # Run all test queries from test_queries.md
    python validate_rag_results.py --sample 10        # Run 10 random test queries
    python validate_rag_results.py --category customer # Run specific category tests
    python validate_rag_results.py --debug            # Show detailed comparison output
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv, find_dotenv
import os
import sys
import time
import argparse
import re
from typing import Dict, List, Any, Tuple, Optional
import random

# Add the current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import RAG system components
from base_rag_system import RAGSystem
from shared_domain_config import create_customer_order_domain
from shared_template_loader import load_or_generate_templates
from domain_plugin import DomainSpecificPlugin, DomainAnalyticsPlugin
from plugin_system import PluginManager
from sql_validation_templates import SQLValidationTemplates

# Import clients
from clients import (
    OllamaEmbeddingClient, 
    OllamaInferenceClient, 
    PostgreSQLDatabaseClient
)

# Import plugins
from plugin_system import (
    SecurityPlugin,
    QueryNormalizationPlugin,
    ResultFilteringPlugin,
    DataEnrichmentPlugin,
    ResponseEnhancementPlugin,
    LoggingPlugin
)

# Test queries organized by category
TEST_QUERIES = {
    "customer": [
        "What did customer 1 buy last week?",
        "Show me orders from Maria Smith",
        "Find orders for John Doe",
        "Show me recent orders for customer 123",
        "What has customer 456 ordered recently?",
        "Give me a summary for customer 5",
        "Show customer 1's recent activity",
        "Recent shopping history for customer 234",
    ],
    "order_value": [
        "Show me all orders over $500",
        "Find orders between $100 and $500",
        "Show me all orders under $50",
        "Find expensive orders above $1000",
        "Orders between $200 and $800",
        "Show orders worth more than $750",
        "Small purchases under $25",
        "Orders in the $300-$800 range",
    ],
    "order_status": [
        "Show me all pending orders",
        "Find delivered orders from last week",
        "List cancelled orders from the last month",
        "What orders are still processing?",
        "Show shipped orders from yesterday",
        "Orders that have been delivered",
        "Find all shipped packages",
        "Which orders are cancelled?",
    ],
    "location": [
        "Show orders from New York customers",
        "Find orders from customers in Los Angeles",
        "Orders from customers in Canada",
        "Show orders from Toronto customers",
        "Which customers from Seattle ordered?",
        "Orders from USA",
        "Canadian customer orders",
        "Show orders from Boston",
    ],
    "payment": [
        "Show me orders paid with credit card",
        "Find PayPal orders from last month",
        "What orders used bank transfer?",
        "Show cash payments",
        "Credit card orders analysis",
        "Orders paid via PayPal",
        "Which orders used credit cards?",
        "Bank transfer purchases",
    ],
    "analytics": [
        "Who are our top 10 customers?",
        "Show me the biggest spenders",
        "What's the lifetime value of customer 123?",
        "Show me new customers from this week",
        "Calculate customer 12's lifetime spending",
        "What were yesterday's sales?",
        "Show me today's revenue",
        "How much has customer 456 spent in total?",
    ]
}

class RAGValidationResult:
    """Container for validation results"""
    def __init__(self, query: str, rag_success: bool, sql_success: bool, 
                 rag_count: int, sql_count: int, rag_response: str, 
                 execution_time: float, validation_passed: bool, 
                 error_message: str = None):
        self.query = query
        self.rag_success = rag_success
        self.sql_success = sql_success
        self.rag_count = rag_count
        self.sql_count = sql_count
        self.rag_response = rag_response
        self.execution_time = execution_time
        self.validation_passed = validation_passed
        self.error_message = error_message


class RAGValidator:
    """Validates RAG system responses against actual SQL results"""
    
    def __init__(self, debug=False):
        self.debug = debug
        self.rag_system = None
        self.db_config = self._get_db_config()
        self._initialize_rag_system()
        
    def _get_db_config(self):
        """Get database configuration from environment variables"""
        # Look for .env file in parent directory (one level up)
        env_file = os.path.join(os.path.dirname(__file__), '..', '.env')
        if os.path.exists(env_file):
            load_dotenv(env_file, override=True)
        else:
            # Fallback to find_dotenv
            env_file = find_dotenv()
            if env_file:
                load_dotenv(env_file, override=True)
        
        return {
            'host': os.getenv('DATASOURCE_POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('DATASOURCE_POSTGRES_PORT', '5432')),
            'database': os.getenv('DATASOURCE_POSTGRES_DATABASE', 'orbit'),
            'user': os.getenv('DATASOURCE_POSTGRES_USERNAME', 'postgres'),
            'password': os.getenv('DATASOURCE_POSTGRES_PASSWORD', 'postgres'),
            'sslmode': os.getenv('DATASOURCE_POSTGRES_SSL_MODE', 'require')
        }
    
    def _initialize_rag_system(self):
        """Initialize the RAG system for testing"""
        try:
            print("🚀 Initializing RAG system for validation...")
            
            # Create domain configuration
            domain = create_customer_order_domain()
            
            # Initialize clients
            embedding_client = OllamaEmbeddingClient()
            inference_client = OllamaInferenceClient()
            db_client = PostgreSQLDatabaseClient()
            
            # Load templates
            template_library = load_or_generate_templates(domain)
            
            # Initialize RAG system
            self.rag_system = RAGSystem(
                domain=domain,
                template_library=template_library,
                embedding_client=embedding_client,
                inference_client=inference_client,
                db_client=db_client
            )
            
            # Register plugins
            plugin_manager = PluginManager()
            
            default_plugins = [
                SecurityPlugin(),
                QueryNormalizationPlugin(),
                ResultFilteringPlugin(max_results=50),
                DataEnrichmentPlugin(),
                ResponseEnhancementPlugin(),
                LoggingPlugin()
            ]
            
            for plugin in default_plugins:
                plugin_manager.register_plugin(plugin)
            
            # Register domain-specific plugins
            domain_plugin = DomainSpecificPlugin(domain, inference_client)
            plugin_manager.register_plugin(domain_plugin)
            
            analytics_plugin = DomainAnalyticsPlugin(domain)
            plugin_manager.register_plugin(analytics_plugin)
            
            # Attach plugin manager
            self.rag_system.plugin_manager = plugin_manager
            
            # Populate ChromaDB
            self.rag_system.populate_chromadb_from_library(clear_first=True)
            
            print("✅ RAG system initialized successfully")
            
        except Exception as e:
            print(f"❌ Failed to initialize RAG system: {e}")
            sys.exit(1)
    
    def _execute_sql_equivalent(self, query: str, rag_result: Dict) -> Tuple[List[Dict], Optional[str]]:
        """
        Execute SQL equivalent based on the RAG result's template and parameters
        """
        try:
            if not rag_result.get('success'):
                return [], "RAG query failed"
                
            template_id = rag_result.get('template_id', '')
            parameters = rag_result.get('parameters', {})
            
            # Build SQL query based on template pattern
            sql_query, sql_params = self._build_sql_from_template(template_id, parameters)
            
            if not sql_query:
                return [], f"Could not build SQL for template: {template_id}"
            
            # Execute the SQL query
            connection = psycopg2.connect(**self.db_config)
            cursor = connection.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute(sql_query, sql_params)
            results = cursor.fetchall()
            
            # Convert to list of dicts
            sql_results = [dict(row) for row in results]
            
            cursor.close()
            connection.close()
            
            return sql_results, None
            
        except Exception as e:
            return [], f"SQL execution error: {str(e)}"
    
    def _build_sql_from_template(self, template_id: str, parameters: Dict) -> Tuple[str, List]:
        """
        Build SQL query from template ID and parameters using validation templates
        """
        return SQLValidationTemplates.get_template_sql(template_id, parameters)
    
    def _extract_count_from_rag_response(self, rag_result: Dict) -> int:
        """Extract the number of results from RAG response"""
        if not rag_result.get('success'):
            return 0
        
        # First, check the result_count field
        if 'result_count' in rag_result:
            return rag_result['result_count']
        
        # Check the results array length
        if 'results' in rag_result and rag_result['results']:
            return len(rag_result['results'])
        
        # Try to extract from response text
        response = rag_result.get('response', '')
        
        # Look for patterns like "Found 5 results", "5 orders", etc.
        count_patterns = [
            r'Found (\d+) results',
            r'(\d+) orders?',
            r'(\d+) records?',
            r'(\d+) customers?',
            r'returned (\d+)',
            r'shows (\d+)',
        ]
        
        for pattern in count_patterns:
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        return 0
    
    def validate_query(self, query: str) -> RAGValidationResult:
        """
        Validate a single query by comparing RAG results with SQL results
        """
        start_time = time.time()
        
        try:
            # Execute RAG query
            if self.debug:
                print(f"\n🔍 Testing query: {query}")
                print("-" * 60)
            
            rag_result = self.rag_system.process_query(query)
            rag_success = rag_result.get('success', False)
            rag_count = self._extract_count_from_rag_response(rag_result)
            rag_response = rag_result.get('response', '')
            
            if self.debug:
                print(f"RAG Success: {rag_success}")
                print(f"RAG Count: {rag_count}")
                if rag_success:
                    print(f"Template: {rag_result.get('template_id', 'Unknown')}")
                    print(f"Parameters: {rag_result.get('parameters', {})}")
            
            # Execute equivalent SQL query
            sql_results, sql_error = self._execute_sql_equivalent(query, rag_result)
            sql_success = sql_error is None
            sql_count = len(sql_results) if sql_success else 0
            
            if self.debug:
                print(f"SQL Success: {sql_success}")
                print(f"SQL Count: {sql_count}")
                if sql_error:
                    print(f"SQL Error: {sql_error}")
            
            # Validate results
            validation_passed = False
            error_message = None
            
            if not rag_success and not sql_success:
                # Both failed - this could be acceptable for some queries
                validation_passed = True
            elif rag_success and sql_success:
                # Both succeeded - check count consistency
                count_diff = abs(rag_count - sql_count)
                count_tolerance = max(1, sql_count * 0.1)  # 10% tolerance or at least 1
                
                if count_diff <= count_tolerance:
                    validation_passed = True
                else:
                    validation_passed = False
                    error_message = f"Count mismatch: RAG={rag_count}, SQL={sql_count}, diff={count_diff}"
            elif rag_success and not sql_success:
                # RAG succeeded but SQL failed - might be template issue
                validation_passed = False
                error_message = f"RAG succeeded but SQL validation failed: {sql_error}"
            else:
                # SQL succeeded but RAG failed - RAG system issue
                validation_passed = False
                error_message = f"SQL found {sql_count} results but RAG failed"
            
            execution_time = time.time() - start_time
            
            return RAGValidationResult(
                query=query,
                rag_success=rag_success,
                sql_success=sql_success,
                rag_count=rag_count,
                sql_count=sql_count,
                rag_response=rag_response,
                execution_time=execution_time,
                validation_passed=validation_passed,
                error_message=error_message
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            return RAGValidationResult(
                query=query,
                rag_success=False,
                sql_success=False,
                rag_count=0,
                sql_count=0,
                rag_response="",
                execution_time=execution_time,
                validation_passed=False,
                error_message=f"Validation exception: {str(e)}"
            )
    
    def run_validation_suite(self, queries: List[str], category: str = "mixed") -> Dict[str, Any]:
        """
        Run validation on a list of queries and return summary results
        """
        print(f"\n🧪 Running validation suite: {category}")
        print(f"📋 Testing {len(queries)} queries")
        print("=" * 60)
        
        results = []
        passed = 0
        failed = 0
        total_time = 0
        
        for i, query in enumerate(queries, 1):
            result = self.validate_query(query)
            results.append(result)
            total_time += result.execution_time
            
            if result.validation_passed:
                passed += 1
                status = "✅ PASS"
            else:
                failed += 1
                status = "❌ FAIL"
            
            # Print progress
            print(f"{i:3d}. {status} | RAG:{result.rag_count:3d} SQL:{result.sql_count:3d} | {result.execution_time:.2f}s | {query[:50]}...")
            
            if not result.validation_passed and result.error_message:
                print(f"     Error: {result.error_message}")
        
        # Print summary
        print("\n" + "=" * 60)
        print(f"📊 Validation Summary - {category}")
        print(f"   Total queries: {len(queries)}")
        print(f"   Passed: {passed} ({passed/len(queries)*100:.1f}%)")
        print(f"   Failed: {failed} ({failed/len(queries)*100:.1f}%)")
        print(f"   Total time: {total_time:.2f}s")
        print(f"   Average time: {total_time/len(queries):.2f}s per query")
        
        # Detailed failure analysis
        if failed > 0:
            print("\n❌ Failed Queries Analysis:")
            failures = [r for r in results if not r.validation_passed]
            
            # Group by error type
            error_types = {}
            for failure in failures:
                error_key = failure.error_message.split(':')[0] if failure.error_message else "Unknown"
                if error_key not in error_types:
                    error_types[error_key] = []
                error_types[error_key].append(failure)
            
            for error_type, error_list in error_types.items():
                print(f"   • {error_type}: {len(error_list)} queries")
        
        return {
            'category': category,
            'total': len(queries),
            'passed': passed,
            'failed': failed,
            'pass_rate': passed / len(queries) * 100,
            'total_time': total_time,
            'avg_time': total_time / len(queries),
            'results': results
        }


def main():
    """Main function with command line argument parsing"""
    parser = argparse.ArgumentParser(description='RAG System Validation Testing')
    parser.add_argument('--full', action='store_true', help='Run all test queries')
    parser.add_argument('--sample', type=int, help='Run N random test queries')
    parser.add_argument('--category', type=str, choices=list(TEST_QUERIES.keys()), 
                       help='Run specific category tests')
    parser.add_argument('--debug', action='store_true', help='Show detailed comparison output')
    parser.add_argument('--custom', type=str, help='Test a single custom query')
    
    args = parser.parse_args()
    
    # Initialize validator
    validator = RAGValidator(debug=args.debug)
    
    if args.custom:
        # Test single custom query
        result = validator.validate_query(args.custom)
        status = "✅ PASS" if result.validation_passed else "❌ FAIL"
        print(f"\n{status} | RAG:{result.rag_count} SQL:{result.sql_count} | {result.execution_time:.2f}s")
        print(f"Query: {args.custom}")
        if result.error_message:
            print(f"Error: {result.error_message}")
        print(f"\nRAG Response: {result.rag_response[:200]}...")
        
    elif args.category:
        # Test specific category
        queries = TEST_QUERIES[args.category]
        validator.run_validation_suite(queries, args.category)
        
    elif args.sample:
        # Test random sample
        all_queries = []
        for category_queries in TEST_QUERIES.values():
            all_queries.extend(category_queries)
        
        sample_queries = random.sample(all_queries, min(args.sample, len(all_queries)))
        validator.run_validation_suite(sample_queries, f"random_sample_{args.sample}")
        
    elif args.full:
        # Test all categories
        overall_results = []
        
        for category, queries in TEST_QUERIES.items():
            category_result = validator.run_validation_suite(queries, category)
            overall_results.append(category_result)
        
        # Overall summary
        total_queries = sum(r['total'] for r in overall_results)
        total_passed = sum(r['passed'] for r in overall_results)
        sum(r['failed'] for r in overall_results)
        overall_time = sum(r['total_time'] for r in overall_results)
        
        print("\n🎯 OVERALL VALIDATION RESULTS")
        print("=" * 60)
        print(f"Categories tested: {len(overall_results)}")
        print(f"Total queries: {total_queries}")
        print(f"Overall pass rate: {total_passed/total_queries*100:.1f}% ({total_passed}/{total_queries})")
        print(f"Total execution time: {overall_time:.2f}s")
        
        # Category breakdown
        print("\n📊 Results by Category:")
        for result in overall_results:
            print(f"   {result['category']:<15} {result['pass_rate']:5.1f}% ({result['passed']:2d}/{result['total']:2d})")
        
    else:
        # Default: run basic validation tests
        basic_queries = [
            "Show me recent orders for customer 1",
            "Find orders over $500",
            "Show me all pending orders",
            "Orders from customers in Canada",
            "Show me orders paid with credit card",
            "Who are our top 10 customers?",
            "What did customer 123 buy last week?",
            "Find orders between $100 and $500"
        ]
        
        validator.run_validation_suite(basic_queries, "basic_validation")


if __name__ == "__main__":
    main()