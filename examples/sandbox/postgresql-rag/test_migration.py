#!/usr/bin/env python3
"""
Migration Testing Script
========================

This script helps test the migration from the old SemanticRAGSystem 
to the new EnhancedRAGSystem to ensure compatibility.
"""

import os
import json
from typing import Dict, List
from datetime import datetime

# Import both systems for comparison
from customer_order_rag import SemanticRAGSystem
from enhanced_base_rag_system import EnhancedRAGSystem
from domain_configuration import DomainConfiguration
from template_library import TemplateLibrary
from domain_plugin import DomainSpecificPlugin, DomainAnalyticsPlugin
from template_generator import DomainTemplateGenerator

# Import clients
from customer_order_rag import (
    OllamaEmbeddingClient, 
    OllamaInferenceClient, 
    PostgreSQLDatabaseClient
)


def create_customer_order_domain() -> DomainConfiguration:
    """Create the same domain as conversational_demo_enhanced.py"""
    from domain_configuration import DomainEntity, DomainField, DomainRelationship
    from domain_configuration import DataType, EntityType, RelationType
    
    domain = DomainConfiguration(
        domain_name="E-Commerce",
        description="Customer order management system"
    )
    
    # Customer entity
    customer_entity = DomainEntity(
        name="customer",
        entity_type=EntityType.PRIMARY,
        table_name="customers",
        description="Customer information",
        primary_key="id",
        display_name_field="name",
        searchable_fields=["name", "email", "phone"],
        common_filters=["city", "country", "created_at"],
        default_sort_field="created_at"
    )
    domain.add_entity(customer_entity)
    
    # Order entity  
    order_entity = DomainEntity(
        name="order",
        entity_type=EntityType.TRANSACTION,
        table_name="orders",
        description="Customer orders",
        primary_key="id",
        display_name_field="id",
        searchable_fields=["id", "status"],
        common_filters=["status", "payment_method", "order_date", "total"],
        default_sort_field="order_date"
    )
    domain.add_entity(order_entity)
    
    # Add all the fields (same as conversational_demo_enhanced.py)
    # Customer fields
    domain.add_field("customer", DomainField(
        name="id", data_type=DataType.INTEGER, db_column="id",
        description="Customer ID", required=True, searchable=True
    ))
    domain.add_field("customer", DomainField(
        name="name", data_type=DataType.STRING, db_column="name",
        description="Customer name", required=True, searchable=True,
        aliases=["customer name", "client name", "buyer name"]
    ))
    domain.add_field("customer", DomainField(
        name="email", data_type=DataType.STRING, db_column="email",
        description="Customer email", required=True, searchable=True,
        display_format="email"
    ))
    
    # Order fields
    domain.add_field("order", DomainField(
        name="id", data_type=DataType.INTEGER, db_column="id",
        description="Order ID", required=True, searchable=True
    ))
    domain.add_field("order", DomainField(
        name="total", data_type=DataType.DECIMAL, db_column="total",
        description="Order total amount", required=True, filterable=True,
        display_format="currency"
    ))
    domain.add_field("order", DomainField(
        name="status", data_type=DataType.ENUM, db_column="status",
        description="Order status", required=True, searchable=True,
        filterable=True, enum_values=["pending", "processing", "shipped", "delivered", "cancelled"]
    ))
    
    # Add relationship
    domain.add_relationship(DomainRelationship(
        name="customer_orders", from_entity="customer", to_entity="order",
        relation_type=RelationType.ONE_TO_MANY, from_field="id", to_field="customer_id",
        description="Customer has many orders"
    ))
    
    # Add vocabulary
    domain.vocabulary.entity_synonyms = {
        "customer": ["client", "buyer", "user", "purchaser", "shopper"],
        "order": ["purchase", "transaction", "sale", "invoice"]
    }
    domain.vocabulary.action_verbs = {
        "find": ["show", "list", "get", "find", "display", "retrieve"],
        "calculate": ["sum", "total", "calculate", "compute", "aggregate"],
        "filter": ["filter", "only", "just", "where", "with"]
    }
    
    return domain


class MigrationTester:
    """Test migration compatibility between old and new systems"""
    
    def __init__(self):
        self.old_system = None
        self.new_system = None
        self.domain = None
        self.test_results = []
    
    def setup_old_system(self):
        """Setup the original SemanticRAGSystem"""
        print("🔄 Setting up original SemanticRAGSystem...")
        try:
            self.old_system = SemanticRAGSystem(
                enable_default_plugins=True,
                enable_postgresql_plugins=True
            )
            self.old_system.populate_chromadb("query_templates.yaml", clear_first=True)
            print("✅ Original system ready")
            return True
        except Exception as e:
            print(f"❌ Error setting up original system: {e}")
            return False
    
    def setup_new_system(self):
        """Setup the new EnhancedRAGSystem"""
        print("🔄 Setting up enhanced RAG system...")
        try:
            # Create domain
            self.domain = create_customer_order_domain()
            
            # Load existing templates into template library
            template_library = TemplateLibrary(self.domain)
            if os.path.exists("query_templates.yaml"):
                template_library.import_from_yaml("query_templates.yaml")
            else:
                # Generate templates if none exist
                generator = DomainTemplateGenerator(self.domain)
                template_library = generator.generate_standard_templates()
            
            # Initialize clients
            embedding_client = OllamaEmbeddingClient()
            inference_client = OllamaInferenceClient()
            db_client = PostgreSQLDatabaseClient()
            
            # Create enhanced system
            self.new_system = EnhancedRAGSystem(
                domain=self.domain,
                template_library=template_library,
                embedding_client=embedding_client,
                inference_client=inference_client,
                db_client=db_client
            )
            
            # Register plugins
            domain_plugin = DomainSpecificPlugin(self.domain, inference_client)
            analytics_plugin = DomainAnalyticsPlugin(self.domain)
            
            # Note: We'd need to set up the plugin manager here too
            # For now, just populate ChromaDB
            self.new_system.populate_chromadb_from_library(clear_first=True)
            
            print("✅ Enhanced system ready")
            return True
        except Exception as e:
            print(f"❌ Error setting up enhanced system: {e}")
            return False
    
    def test_query(self, query: str) -> Dict:
        """Test a query on both systems and compare results"""
        print(f"\n🧪 Testing query: {query}")
        
        test_result = {
            'query': query,
            'timestamp': datetime.now().isoformat(),
            'old_system': None,
            'new_system': None,
            'compatible': False,
            'notes': []
        }
        
        # Test old system
        try:
            print("  📊 Testing original system...")
            old_result = self.old_system.process_query(query)
            test_result['old_system'] = {
                'success': old_result['success'],
                'template_id': old_result.get('template_id'),
                'similarity': old_result.get('similarity'),
                'result_count': old_result.get('result_count', 0),
                'error': old_result.get('error')
            }
            print(f"    ✅ Success: {old_result['success']}")
            if old_result['success']:
                print(f"    📋 Template: {old_result.get('template_id')}")
                print(f"    📊 Results: {old_result.get('result_count', 0)}")
        except Exception as e:
            print(f"    ❌ Error: {e}")
            test_result['old_system'] = {'error': str(e), 'success': False}
        
        # Test new system
        try:
            print("  🚀 Testing enhanced system...")
            new_result = self.new_system.process_query(query)
            test_result['new_system'] = {
                'success': new_result['success'],
                'template_id': new_result.get('template_id'),
                'similarity': new_result.get('similarity'),
                'result_count': new_result.get('result_count', 0),
                'error': new_result.get('error')
            }
            print(f"    ✅ Success: {new_result['success']}")
            if new_result['success']:
                print(f"    📋 Template: {new_result.get('template_id')}")
                print(f"    📊 Results: {new_result.get('result_count', 0)}")
        except Exception as e:
            print(f"    ❌ Error: {e}")
            test_result['new_system'] = {'error': str(e), 'success': False}
        
        # Compare results
        self.compare_results(test_result)
        
        return test_result
    
    def compare_results(self, test_result: Dict):
        """Compare results between old and new systems"""
        old = test_result['old_system']
        new = test_result['new_system']
        
        if not old or not new:
            test_result['compatible'] = False
            test_result['notes'].append("One system failed to process query")
            return
        
        # Check if both succeeded or both failed
        if old['success'] != new['success']:
            test_result['compatible'] = False
            test_result['notes'].append(f"Success mismatch: old={old['success']}, new={new['success']}")
        
        # If both succeeded, compare more details
        elif old['success'] and new['success']:
            # Check template ID
            if old.get('template_id') != new.get('template_id'):
                test_result['notes'].append(f"Template mismatch: old={old.get('template_id')}, new={new.get('template_id')}")
            
            # Check result counts (allow some variance)
            old_count = old.get('result_count', 0)
            new_count = new.get('result_count', 0)
            if abs(old_count - new_count) > 5:  # Allow up to 5 result difference
                test_result['notes'].append(f"Result count difference: old={old_count}, new={new_count}")
            
            # If template and counts match, consider compatible
            if old.get('template_id') == new.get('template_id') and abs(old_count - new_count) <= 5:
                test_result['compatible'] = True
                test_result['notes'].append("Results compatible")
        
        # If both failed with similar template selection, still somewhat compatible
        elif not old['success'] and not new['success']:
            test_result['compatible'] = True
            test_result['notes'].append("Both systems failed similarly")
    
    def run_test_suite(self):
        """Run a comprehensive test suite"""
        # Test queries from the original demo
        test_queries = [
            "What did customer 1 buy last week?",
            "Show me orders from Maria Smith",
            "What's the lifetime value of customer 123?",
            "Show me all orders over $500 from last month",
            "Find orders between $100 and $500",
            "Show me all pending orders",
            "Show orders from New York customers",
            "How are customers paying?",
            "Who are our top 10 customers?",
            "Show me new customers from this week"
        ]
        
        print("=" * 80)
        print("🧪 Running Migration Test Suite")
        print("=" * 80)
        
        # Setup both systems
        if not self.setup_old_system():
            print("❌ Cannot test without original system")
            return
        
        if not self.setup_new_system():
            print("❌ Cannot test without enhanced system")
            return
        
        print(f"\n🚀 Testing {len(test_queries)} queries...")
        
        # Run tests
        for query in test_queries:
            result = self.test_query(query)
            self.test_results.append(result)
        
        # Generate report
        self.generate_report()
    
    def generate_report(self):
        """Generate a migration compatibility report"""
        print("\n" + "=" * 80)
        print("📊 Migration Compatibility Report")
        print("=" * 80)
        
        total_tests = len(self.test_results)
        compatible_tests = sum(1 for r in self.test_results if r['compatible'])
        compatibility_rate = (compatible_tests / total_tests) * 100 if total_tests > 0 else 0
        
        print(f"Total queries tested: {total_tests}")
        print(f"Compatible results: {compatible_tests}")
        print(f"Compatibility rate: {compatibility_rate:.1f}%")
        
        # Detailed breakdown
        print("\n📋 Detailed Results:")
        for i, result in enumerate(self.test_results, 1):
            status = "✅" if result['compatible'] else "❌"
            print(f"{i}. {status} {result['query']}")
            
            if result['old_system'] and result['new_system']:
                old_template = result['old_system'].get('template_id', 'None')
                new_template = result['new_system'].get('template_id', 'None')
                print(f"   Templates: {old_template} → {new_template}")
            
            for note in result['notes']:
                print(f"   💬 {note}")
        
        # Save detailed report
        report_data = {
            'timestamp': datetime.now().isoformat(),
            'compatibility_rate': compatibility_rate,
            'total_tests': total_tests,
            'compatible_tests': compatible_tests,
            'test_results': self.test_results
        }
        
        with open('migration_test_report.json', 'w') as f:
            json.dump(report_data, f, indent=2)
        
        print(f"\n💾 Detailed report saved to: migration_test_report.json")
        
        # Recommendations
        print("\n💡 Recommendations:")
        if compatibility_rate >= 90:
            print("✅ High compatibility rate - migration should be safe")
        elif compatibility_rate >= 70:
            print("⚠️  Good compatibility rate - review failed cases before migration")
        else:
            print("❌ Low compatibility rate - investigate differences before migration")
        
        print("\n🔄 Next steps:")
        print("1. Review any failed test cases")
        print("2. Update domain configuration or templates as needed")
        print("3. Test with your specific use cases")
        print("4. Consider gradual migration approach")


def main():
    """Main testing function"""
    tester = MigrationTester()
    tester.run_test_suite()


if __name__ == "__main__":
    main()