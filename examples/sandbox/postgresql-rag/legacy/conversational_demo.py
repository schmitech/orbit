#!/usr/bin/env python3
"""
Enhanced Interactive Demo for Semantic RAG System
Features conversation memory, query suggestions, and improved UX
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

from customer_order_rag import SemanticRAGSystem
import readline  # For better input handling
from typing import List, Dict
import json
from datetime import datetime


class ConversationalDemo:
    """Enhanced demo with conversation features and better UX"""
    
    def __init__(self):
        self.rag_system = None
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
        print("🤖 Semantic RAG System - Conversational Database Interface")
        print("="*80)
        print("This system allows you to query your database using natural language!")
        print("\nFeatures:")
        print("✨ Natural language understanding")
        print("🔌 Plugin architecture for extensibility")
        print("💬 Conversational context")
        print("🔍 Intelligent parameter extraction")
        print("📊 Smart result formatting")
        print("💡 Query suggestions")
        print("🛡️ Security validation")
        print("⚡ Performance optimization")
        print("📈 Business intelligence")
        print("\nSystem Components:")
        print("- ChromaDB for semantic search")
        print(f"- Ollama ({os.getenv('OLLAMA_EMBEDDING_MODEL', 'nomic-embed-text')}) for embeddings")
        print(f"- Ollama ({os.getenv('OLLAMA_INFERENCE_MODEL', 'gemma3:1b')}) for natural language generation")
        print("- PostgreSQL for data storage")
        print("- Plugin system for enhanced functionality")
        print(f"\nConfiguration:")
        print(f"- Ollama Server: {os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')}")
        print("="*80)
    
    def print_help(self):
        """Print help information"""
        print("\n📚 Help Menu")
        print("-" * 40)
        print("Commands:")
        print("  help     - Show this help menu")
        print("  examples - Show example queries")
        print("  stats    - Show session statistics")
        print("  plugins  - Show plugin status")
        print("  clear    - Clear conversation history")
        print("  quit     - Exit the demo")
        print("  exit     - Exit the demo")
        print("  bye      - Exit the demo")
        print("\nTips:")
        print("- Use natural language to query your database")
        print("- Be specific about what you want")
        print("- Include time periods, amounts, names, etc.")
        print("- Press TAB for query suggestions")
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
            
            # Show enhanced results if available
            if result.get('results'):
                first_result = result['results'][0]
                enhanced_fields = []
                
                if 'customer_segment' in first_result:
                    enhanced_fields.append(f"Customer Segment: {first_result['customer_segment']}")
                if 'revenue_analytics' in first_result:
                    enhanced_fields.append("Revenue Analytics: Available")
                if 'time_insights' in first_result:
                    enhanced_fields.append("Time Insights: Available")
                if 'geographic_insights' in first_result:
                    enhanced_fields.append("Geographic Insights: Available")
                if 'business_flags' in first_result:
                    enhanced_fields.append("Business Rules: Applied")
                
                if enhanced_fields:
                    print(f"🎯 Enhanced data: {', '.join(enhanced_fields)}")
            
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
            
            # If verification failed, show the LLM's reason
            if result.get('verification_failed'):
                print(f"\n⚠️  Template verification failed.")
                if result.get('verification_reason'):
                    print(f"LLM reason: {result['verification_reason']}")
                else:
                    print(f"The system determined the selected template did not match your intent.")
            
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
    
    def run(self):
        """Run the interactive demo"""
        self.print_header()
        
        # Initialize the RAG system with plugins
        print("\n🚀 Initializing system with plugins...")
        try:
            self.rag_system = SemanticRAGSystem(
                enable_default_plugins=True,
                enable_postgresql_plugins=True
            )
            print("✅ System initialized successfully!")
        except Exception as e:
            print(f"❌ Error initializing system: {e}")
            print("\nTroubleshooting:")
            print(f"1. Ensure Ollama is running ({os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')})")
            print("2. Pull required models:")
            print(f"   ollama pull {os.getenv('OLLAMA_EMBEDDING_MODEL', 'nomic-embed-text')}")
            print(f"   ollama pull {os.getenv('OLLAMA_INFERENCE_MODEL', 'gemma3:1b')}")
            print("3. Check PostgreSQL connection settings in .env")
            return
        
        # Load templates
        try:
            print("📚 Loading query templates...")
            self.rag_system.populate_chromadb("query_templates.yaml", clear_first=True)
            print("✅ Templates loaded successfully!")
        except Exception as e:
            print(f"❌ Error loading templates: {e}")
            return
        
        # Show plugin status
        plugins = self.rag_system.list_plugins()
        enabled_plugins = [p['name'] for p in plugins if p['enabled']]
        print(f"🔌 Enabled plugins: {', '.join(enabled_plugins)}")
        
        print("\n💡 Type 'help' for commands or 'examples' for query examples")
        print("🎯 Press TAB for query suggestions")
        print("🔌 Type 'plugins' to show plugin status")
        print("\nReady to answer your questions about the database with enhanced plugin features!\n")
        
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
                    print("\n👋 Thank you for using the Semantic RAG System!")
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
                elif user_input.lower() == 'plugins':
                    plugins = self.rag_system.list_plugins()
                    print(f"\n🔌 Plugin Status:")
                    for plugin in plugins:
                        status = "✅" if plugin['enabled'] else "❌"
                        print(f"   {status} {plugin['name']} v{plugin['version']} ({plugin['priority']})")
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
                print("\n\n👋 Interrupted. Thank you for using the Semantic RAG System!")
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