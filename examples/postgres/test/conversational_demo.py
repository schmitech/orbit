#!/usr/bin/env python3
"""
Interactive Demo for Domain-Agnostic RAG System
Features conversation memory, query suggestions, and domain configuration support
"""

import sys
import os

# Ensure proper Unicode handling for terminal output
if sys.platform.startswith('win'):
    # Windows Unicode support
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.detach())
else:
    # Unix-like systems
    import locale
    try:
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
    except locale.Error:
        try:
            locale.setlocale(locale.LC_ALL, 'C.UTF-8')
        except locale.Error:
            pass  # Use default locale

from base_rag_system import RAGSystem
from domain_configuration import DomainConfiguration
from template_library import TemplateLibrary
from domain_plugin import DomainSpecificPlugin, DomainAnalyticsPlugin
from template_generator import DomainTemplateGenerator
from plugin_system import PluginManager
from shared_domain_config import create_customer_order_domain
from shared_template_loader import load_or_generate_templates

# Import the actual implementations
from clients import (
    OllamaEmbeddingClient, 
    OllamaInferenceClient, 
    PostgreSQLDatabaseClient
)

from plugin_system import (
    SecurityPlugin,
    QueryNormalizationPlugin,
    ResultFilteringPlugin,
    DataEnrichmentPlugin,
    ResponseEnhancementPlugin,
    LoggingPlugin
)

# Import example plugins if available
try:
    from examples.example_plugins import (
        CustomerSegmentationPlugin,
        RevenueAnalyticsPlugin,
        TimeBasedInsightsPlugin,
        GeographicInsightsPlugin,
        BusinessRulesPlugin
    )
    EXAMPLE_PLUGINS_AVAILABLE = True
except ImportError:
    EXAMPLE_PLUGINS_AVAILABLE = False

import readline  # For better input handling
from typing import List, Dict, Optional
import json
from datetime import datetime
import yaml


# Domain creation function moved to shared_domain_config.py for consistency


class ConversationalDemo:
    """Demo with domain configuration support"""
    
    def __init__(self):
        self.rag_system = None
        self.domain = None
        self.template_library = None
        self.query_history = []
        self.setup_readline()
    
    def setup_readline(self):
        """Setup readline for better input experience"""
        # Configure readline for proper input handling
        readline.parse_and_bind('tab: complete')
        readline.parse_and_bind('bind ^I rl_complete')
        
        # Set input mode for proper backspace handling
        readline.parse_and_bind('set input-meta on')
        readline.parse_and_bind('set output-meta on')
        readline.parse_and_bind('set convert-meta off')
        
        # Enable history
        readline.set_completer(self.completer)
        
        # Load history if exists
        try:
            readline.read_history_file('.rag_history')
        except FileNotFoundError:
            pass
    
    def completer(self, text: str, state: int) -> str:
        """Tab completion for common query patterns"""
        suggestions = [
            "What did customer",
            "Show me orders",
            "Find orders over $",
            "Show orders from",
            "Who are our top",
            "Give me a summary",
            "How are sales",
            "Show inactive customers",
            "Payment method",
            "Orders by status",
            "Show orders shipped to",
            "International orders",
            "Orders from Toronto",
            "Canadian customers",
            "Revenue by country",
            "Shipping to Europe",
            "Asian market orders",
        ]
        
        matches = [s for s in suggestions if s.lower().startswith(text.lower())]
        
        try:
            return matches[state]
        except IndexError:
            return None
    
    def save_history(self):
        """Save command history"""
        try:
            readline.write_history_file('.rag_history')
        except:
            pass
    
    def print_header(self):
        """Print welcome header"""
        print("\n" + "="*80)
        print("🤖 Domain-Agnostic RAG System - Conversational Database Interface")
        print("="*80)
        print("This system uses domain configuration for flexibility!")
        print("\nFeatures:")
        print("✨ Domain configuration driven")
        print("📋 Template SDK for query generation")
        print("🔌 Plugin architecture for extensibility")
        print("💬 Conversational context")
        print("🔍 Domain-aware parameter extraction")
        print("📊 Smart result formatting")
        print("💡 Query suggestions")
        print("🛡️ Security validation")
        print("⚡ Performance optimization")
        print("\nSystem Components:")
        print("- Domain Configuration for business logic")
        print("- Template Library for query management")
        print("- ChromaDB for semantic search")
        print(f"- Ollama ({os.getenv('OLLAMA_EMBEDDING_MODEL', 'nomic-embed-text')}) for embeddings")
        print(f"- Ollama ({os.getenv('OLLAMA_INFERENCE_MODEL', 'gemma3:1b')}) for natural language generation")
        print("- PostgreSQL for data storage")
        print("- Plugin system for functionality")
        print(f"\nConfiguration:")
        print(f"- Ollama Server: {os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')}")
        print("="*80)
    
    def print_help(self):
        """Print help information"""
        print("\n📚 Help Menu")
        print("-" * 40)
        print("Commands:")
        print("  help        - Show this help menu")
        print("  examples    - Show example queries")
        print("  stats       - Show session statistics")
        print("  plugins     - Show plugin status")
        print("  domain      - Show domain configuration")
        print("  templates   - Show available templates")
        print("  clear       - Clear conversation history")
        print("  quit        - Exit the demo")
        print("  exit        - Exit the demo")
        print("  bye         - Exit the demo")
        print("\nTips:")
        print("- Use natural language to query your database")
        print("- Be specific about what you want")
        print("- Include time periods, amounts, names, etc.")
        print("- Press TAB for query suggestions")
        print("- Domain configuration defines entities and relationships")
        print("- Plugins enhance results with additional insights")
    
    def print_examples(self):
        """Print categorized example queries"""
        examples = {
            "🛍️ Customer Queries": [
                "What did customer 123 buy last week?",
                "Show me orders from John Smith",
                "Give me a summary for customer 5",
                "What's the lifetime value of customer 42?",
                "Show customer segmentation for all customers",
                "Find customers with more than 5 orders"
            ],
            "💰 Order Value Queries": [
                "Show me all orders over $500",
                "Find orders between $100 and $500",
                "What are the biggest orders this month?",
                "Show small orders under $50",
                "Revenue analytics for high-value orders",
                "Average order value by customer"
            ],
            "📦 Order Status": [
                "Show me all pending orders",
                "Which orders are delivered?",
                "Find cancelled orders from last week",
                "What orders need attention?",
                "Business rules analysis for order status",
                "Orders shipped to international destinations"
            ],
            "🌍 International Shipping": [
                "Show orders shipped to the United States",
                "Orders delivered to European countries",
                "International orders over $200",
                "Shipping to Asian countries",
                "Canadian customers shipping abroad",
                "Orders with international shipping addresses"
            ],
            "📍 Location-Based": [
                "Show orders from Toronto customers",
                "Orders from customers in Canada",
                "Which cities are ordering the most?",
                "Geographic analysis of customer distribution",
                "Customers from Vancouver",
                "Orders shipped to specific countries"
            ],
            "💳 Payment Analysis": [
                "How are customers paying?",
                "Show me credit card orders",
                "PayPal transactions from last month",
                "Payment method distribution",
                "High-value credit card orders",
                "International payment methods"
            ],
            "📈 Analytics & Trends": [
                "Who are our top 10 customers?",
                "Show me new customers this week",
                "How are sales trending?",
                "What were yesterday's sales?",
                "Show inactive customers",
                "Time-based insights for recent orders",
                "Revenue by shipping destination"
            ],
            "🔌 Plugin-Specific Queries": [
                "Customer segmentation analysis",
                "Revenue analytics breakdown",
                "Geographic insights for orders",
                "Time-based order patterns",
                "Business rules recommendations",
                "International shipping analytics"
            ]
        }
        
        print("\n📋 Example Queries by Category")
        print("=" * 60)
        
        for category, queries in examples.items():
            print(f"\n{category}")
            for query in queries:
                print(f"  • {query}")
    
    def print_domain_info(self):
        """Print domain configuration information"""
        if not self.domain:
            print("❌ No domain loaded")
            return
        
        print(f"\n🏢 Domain: {self.domain.domain_name}")
        print(f"Description: {self.domain.description}")
        print("\n📊 Entities:")
        for entity_name, entity in self.domain.entities.items():
            print(f"\n  {entity_name} ({entity.entity_type.value}):")
            print(f"    Table: {entity.table_name}")
            print(f"    Primary Key: {entity.primary_key}")
            print(f"    Searchable: {', '.join(entity.searchable_fields)}")
            print(f"    Filters: {', '.join(entity.common_filters)}")
            
            # Show fields
            fields = self.domain.fields.get(entity_name, {})
            if fields:
                print(f"    Fields:")
                for field_name, field in fields.items():
                    print(f"      - {field_name} ({field.data_type.value})")
        
        print("\n🔗 Relationships:")
        for rel in self.domain.relationships:
            print(f"  {rel.name}: {rel.from_entity} -> {rel.to_entity} ({rel.relation_type.value})")
    
    def print_templates_info(self):
        """Print template library information"""
        if not self.template_library:
            print("❌ No templates loaded")
            return
        
        print(f"\n📋 Template Library")
        print(f"Total templates: {len(self.template_library.templates)}")
        
        # Group by category
        categories = {}
        for template_id, template in self.template_library.templates.items():
            if 'semantic_tags' in template:
                action = template['semantic_tags'].get('action', 'other')
            else:
                action = 'other'
            
            if action not in categories:
                categories[action] = []
            categories[action].append(template)
        
        for category, templates in sorted(categories.items()):
            print(f"\n{category.replace('_', ' ').title()}:")
            for template in templates[:5]:  # Show first 5
                print(f"  - {template['id']}: {template['description']}")
            if len(templates) > 5:
                print(f"  ... and {len(templates) - 5} more")
    
    def print_stats(self):
        """Print session statistics"""
        print("\n📊 Session Statistics")
        print("-" * 40)
        print(f"Total queries: {len(self.query_history)}")
        
        if self.query_history:
            successful = sum(1 for q in self.query_history if q['success'])
            print(f"Successful queries: {successful}")
            print(f"Failed queries: {len(self.query_history) - successful}")
            print(f"Success rate: {(successful/len(self.query_history))*100:.1f}%")
            
            # Plugin usage statistics
            plugin_usage = {}
            for q in self.query_history:
                if q['success'] and 'plugins_used' in q:
                    for plugin in q['plugins_used']:
                        plugin_usage[plugin] = plugin_usage.get(plugin, 0) + 1
            
            if plugin_usage:
                print(f"\n🔌 Plugin Usage:")
                for plugin, count in sorted(plugin_usage.items(), key=lambda x: x[1], reverse=True):
                    print(f"   {plugin}: {count} times")
            
            # Most used templates
            template_counts = {}
            for q in self.query_history:
                if q['success'] and 'template_id' in q:
                    template_id = q['template_id']
                    template_counts[template_id] = template_counts.get(template_id, 0) + 1
            
            if template_counts:
                print(f"\n📋 Most used query types:")
                for template, count in sorted(template_counts.items(), 
                                            key=lambda x: x[1], reverse=True)[:5]:
                    print(f"  • {template}: {count} times")
    
    def format_response(self, result: Dict) -> None:
        """Format and print query response"""
        if result['success']:
            print(f"\n✅ Query processed successfully!")
            print(f"📋 Query type: {result['template_id']}")
            print(f"🎯 Confidence: {result['similarity']:.1%}")
            
            # Show plugins used
            plugins_used = result.get('plugins_used', [])
            if plugins_used:
                print(f"🔌 Plugins used: {', '.join(plugins_used)}")
            
            # Show parameters in a nice format
            if result['parameters']:
                print(f"🔍 Extracted parameters:")
                for key, value in result['parameters'].items():
                    print(f"   • {key}: {value}")
            
            print(f"📊 Found {result['result_count']} results")
            
            # Show the response with proper Unicode handling
            print(f"\n💬 Response:")
            print("-" * 60)
            # Ensure proper Unicode output
            response_text = result['response']
            if isinstance(response_text, str):
                print(response_text)
            else:
                print(str(response_text))
            print("-" * 60)
            
        else:
            print(f"\n❌ Query failed")
            print(f"Reason: {result.get('error', 'Unknown error')}")
            
            if 'validation_errors' in result:
                print(f"\n⚠️ Missing information:")
                for error in result['validation_errors']:
                    print(f"   • {error}")
            
            if 'response' in result:
                print(f"\n💡 Suggestion:")
                # Ensure proper Unicode output
                response_text = result['response']
                if isinstance(response_text, str):
                    print(response_text)
                else:
                    print(str(response_text))
    
    def suggest_followup(self, last_result: Dict) -> List[str]:
        """Suggest follow-up queries based on the last result"""
        suggestions = []
        
        if last_result.get('success'):
            template_id = last_result.get('template_id', '')
            
            if 'customer' in template_id:
                suggestions.extend([
                    "Show me their lifetime value",
                    "What's their average order size?",
                    "When was their last order?",
                    "Show their international shipping history"
                ])
            elif 'orders' in template_id:
                suggestions.extend([
                    "Show me the top customers from these results",
                    "What's the average order value?",
                    "Break this down by payment method",
                    "Show shipping destinations for these orders"
                ])
            elif 'payment' in template_id:
                suggestions.extend([
                    "Which payment method is most popular?",
                    "Show trends over time",
                    "Compare with last month",
                    "Payment methods by country"
                ])
            elif 'international' in template_id or 'shipping' in template_id:
                suggestions.extend([
                    "Show revenue by shipping destination",
                    "Which countries order the most?",
                    "International payment methods used",
                    "Shipping costs by region"
                ])
            elif 'location' in template_id or 'city' in template_id:
                suggestions.extend([
                    "Show international shipping from this location",
                    "Compare with other cities",
                    "Revenue by geographic region",
                    "Shipping patterns by location"
                ])
        
        return suggestions[:3]  # Return top 3 suggestions
    
    def load_templates(self) -> TemplateLibrary:
        """Generate templates from domain configuration using shared loader"""
        print("🔨 Generating templates from domain configuration...")
        return load_or_generate_templates(self.domain)
    
    def run(self):
        """Run the interactive demo"""
        self.print_header()
        
        # Initialize domain configuration
        print("\n🏢 Initializing domain configuration...")
        try:
            self.domain = create_customer_order_domain()
            # Save for reference
            self.domain.to_yaml("customer_order_domain.yaml")
            print("✅ Domain configuration created")
        except Exception as e:
            print(f"❌ Error creating domain: {e}")
            return
        
        # Initialize clients
        print("\n🔧 Initializing system components...")
        try:
            embedding_client = OllamaEmbeddingClient()
            inference_client = OllamaInferenceClient()
            db_client = PostgreSQLDatabaseClient()
            print("✅ Clients initialized")
        except Exception as e:
            print(f"❌ Error initializing clients: {e}")
            print("\nTroubleshooting:")
            print(f"1. Ensure Ollama is running ({os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')})")
            print("2. Pull required models:")
            print(f"   ollama pull {os.getenv('OLLAMA_EMBEDDING_MODEL', 'nomic-embed-text')}")
            print(f"   ollama pull {os.getenv('OLLAMA_INFERENCE_MODEL', 'gemma3:1b')}")
            print("3. Check PostgreSQL connection settings in ../.env")
            return
        
        # Load or generate templates
        try:
            self.template_library = self.load_templates()
            print(f"✅ Loaded {len(self.template_library.templates)} templates")
        except Exception as e:
            print(f"❌ Error loading templates: {e}")
            return
        
        # Initialize the RAG system
        print("\n🚀 Initializing RAG system...")
        try:
            self.rag_system = RAGSystem(
                domain=self.domain,
                template_library=self.template_library,
                embedding_client=embedding_client,
                inference_client=inference_client,
                db_client=db_client
            )
            print("✅ RAG system initialized")
        except Exception as e:
            print(f"❌ Error initializing RAG system: {e}")
            return
        
        # Register plugins
        print("\n🔌 Registering plugins...")
        plugin_manager = PluginManager()
        
        # Register default plugins
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
        
        # Register domain-specific plugin
        domain_plugin = DomainSpecificPlugin(self.domain, inference_client)
        plugin_manager.register_plugin(domain_plugin)
        
        analytics_plugin = DomainAnalyticsPlugin(self.domain)
        plugin_manager.register_plugin(analytics_plugin)
        
        # Register example plugins if available
        if EXAMPLE_PLUGINS_AVAILABLE:
            example_plugins = [
                CustomerSegmentationPlugin(),
                RevenueAnalyticsPlugin(),
                TimeBasedInsightsPlugin(),
                GeographicInsightsPlugin(),
                BusinessRulesPlugin()
            ]
            for plugin in example_plugins:
                plugin_manager.register_plugin(plugin)
        
        # Attach plugin manager to RAG system
        self.rag_system.plugin_manager = plugin_manager
        
        enabled_plugins = [p.get_name() for p in plugin_manager.get_enabled_plugins()]
        print(f"✅ Registered {len(enabled_plugins)} plugins: {', '.join(enabled_plugins)}")
        
        # Populate ChromaDB
        try:
            print("\n📚 Loading templates into ChromaDB...")
            self.rag_system.populate_chromadb_from_library(clear_first=True)
            print("✅ Templates loaded into vector database")
        except Exception as e:
            print(f"❌ Error populating ChromaDB: {e}")
            return
        
        print("\n💡 Type 'help' for commands or 'examples' for query examples")
        print("🎯 Press TAB for query suggestions")
        print("🏢 Type 'domain' to see domain configuration")
        print("📋 Type 'templates' to see available templates")
        print("\nReady to answer your questions about the database!\n")
        
        # Main interaction loop
        last_result = None
        
        while True:
            try:
                # Show follow-up suggestions if available
                if last_result and last_result.get('success'):
                    suggestions = self.suggest_followup(last_result)
                    if suggestions:
                        print("\n💭 You might also want to ask:")
                        for i, suggestion in enumerate(suggestions, 1):
                            print(f"   {i}. {suggestion}")
                
                # Get user input
                user_input = input("\n🤔 Your question: ").strip()
                
                # Handle empty input
                if not user_input:
                    continue
                
                # Handle commands
                if user_input.lower() in ['quit', 'exit', 'bye']:
                    print("\n👋 Thank you for using the Domain-Agnostic RAG System!")
                    self.save_history()
                    break
                elif user_input.lower() == 'help':
                    self.print_help()
                    continue
                elif user_input.lower() == 'examples':
                    self.print_examples()
                    continue
                elif user_input.lower() == 'stats':
                    self.print_stats()
                    continue
                elif user_input.lower() == 'domain':
                    self.print_domain_info()
                    continue
                elif user_input.lower() == 'templates':
                    self.print_templates_info()
                    continue
                elif user_input.lower() == 'plugins':
                    plugins = plugin_manager.get_enabled_plugins()
                    print(f"\n🔌 Plugin Status:")
                    for plugin in plugins:
                        print(f"   ✅ {plugin.get_name()} v{plugin.get_version()} ({plugin.get_priority().name})")
                    continue
                elif user_input.lower() == 'clear':
                    self.rag_system.clear_conversation()
                    self.query_history = []
                    print("✅ Conversation history cleared")
                    continue
                
                # Process the query
                print("\n⏳ Processing your query...")
                result = self.rag_system.process_query(user_input)
                
                # Store in history
                self.query_history.append({
                    'timestamp': datetime.now().isoformat(),
                    'query': user_input,
                    'success': result['success'],
                    'template_id': result.get('template_id'),
                    'plugins_used': result.get('plugins_used', [])
                })
                
                # Format and display response
                self.format_response(result)
                
                # Update last result for follow-up suggestions
                last_result = result
                
            except KeyboardInterrupt:
                print("\n\n👋 Interrupted. Thank you for using the Domain-Agnostic RAG System!")
                self.save_history()
                break
            except Exception as e:
                print(f"\n❌ Unexpected error: {e}")
                print("Please try rephrasing your question.")


def main():
    """Main entry point"""
    demo = ConversationalDemo()
    demo.run()


if __name__ == "__main__":
    main()