#!/usr/bin/env python3
"""
Enhanced Interactive Demo for Semantic RAG System
Features conversation memory, query suggestions, and improved UX
"""

from semantic_rag_system import SemanticRAGSystem
import sys
import readline  # For better input handling
from typing import List, Dict
import json
from datetime import datetime
import os


class ConversationalDemo:
    """Enhanced demo with conversation features and better UX"""
    
    def __init__(self):
        self.rag_system = None
        self.query_history = []
        self.setup_readline()
    
    def setup_readline(self):
        """Setup readline for better input experience"""
        # Enable tab completion and history
        readline.parse_and_bind('tab: complete')
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
        print("💬 Conversational context")
        print("🔍 Intelligent parameter extraction")
        print("📊 Smart result formatting")
        print("💡 Query suggestions")
        print("\nSystem Components:")
        print("- ChromaDB for semantic search")
        print(f"- Ollama ({os.getenv('OLLAMA_EMBEDDING_MODEL', 'nomic-embed-text')}) for embeddings")
        print(f"- Ollama ({os.getenv('OLLAMA_INFERENCE_MODEL', 'gemma3:1b')}) for natural language generation")
        print("- PostgreSQL for data storage")
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
        print("  clear    - Clear conversation history")
        print("  quit     - Exit the demo")
        print("\nTips:")
        print("- Use natural language to query your database")
        print("- Be specific about what you want")
        print("- Include time periods, amounts, names, etc.")
        print("- Press TAB for query suggestions")
    
    def print_examples(self):
        """Print categorized example queries"""
        examples = {
            "🛍️ Customer Queries": [
                "What did customer 123 buy last week?",
                "Show me orders from John Smith",
                "Give me a summary for customer 5",
                "What's the lifetime value of customer 42?"
            ],
            "💰 Order Value Queries": [
                "Show me all orders over $500",
                "Find orders between $100 and $500",
                "What are the biggest orders this month?",
                "Show small orders under $50"
            ],
            "📦 Order Status": [
                "Show me all pending orders",
                "Which orders are delivered?",
                "Find cancelled orders from last week",
                "What orders need attention?"
            ],
            "📍 Location-Based": [
                "Show orders from New York customers",
                "Orders from customers in Canada",
                "Which cities are ordering the most?"
            ],
            "💳 Payment Analysis": [
                "How are customers paying?",
                "Show me credit card orders",
                "PayPal transactions from last month"
            ],
            "📈 Analytics & Trends": [
                "Who are our top 10 customers?",
                "Show me new customers this week",
                "How are sales trending?",
                "What were yesterday's sales?",
                "Show inactive customers"
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
            
            # Most used templates
            template_counts = {}
            for q in self.query_history:
                if q['success'] and 'template_id' in q:
                    template_id = q['template_id']
                    template_counts[template_id] = template_counts.get(template_id, 0) + 1
            
            if template_counts:
                print("\nMost used query types:")
                for template, count in sorted(template_counts.items(), 
                                            key=lambda x: x[1], reverse=True)[:5]:
                    print(f"  • {template}: {count} times")
    
    def format_response(self, result: Dict) -> None:
        """Format and print query response"""
        if result['success']:
            print(f"\n✅ Query processed successfully!")
            print(f"📋 Query type: {result['template_id']}")
            print(f"🎯 Confidence: {result['similarity']:.1%}")
            
            # Show parameters in a nice format
            if result['parameters']:
                print(f"🔍 Extracted parameters:")
                for key, value in result['parameters'].items():
                    print(f"   • {key}: {value}")
            
            print(f"📊 Found {result['result_count']} results")
            
            # Show the response
            print(f"\n💬 Response:")
            print("-" * 60)
            print(result['response'])
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
                print(result['response'])
    
    def suggest_followup(self, last_result: Dict) -> List[str]:
        """Suggest follow-up queries based on the last result"""
        suggestions = []
        
        if last_result.get('success'):
            template_id = last_result.get('template_id', '')
            
            if 'customer' in template_id:
                suggestions.extend([
                    "Show me their lifetime value",
                    "What's their average order size?",
                    "When was their last order?"
                ])
            elif 'orders' in template_id:
                suggestions.extend([
                    "Show me the top customers from these results",
                    "What's the average order value?",
                    "Break this down by payment method"
                ])
            elif 'payment' in template_id:
                suggestions.extend([
                    "Which payment method is most popular?",
                    "Show trends over time",
                    "Compare with last month"
                ])
        
        return suggestions[:3]  # Return top 3 suggestions
    
    def run(self):
        """Run the interactive demo"""
        self.print_header()
        
        # Initialize the RAG system
        print("\n🚀 Initializing system...")
        try:
            self.rag_system = SemanticRAGSystem()
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
        
        print("\n💡 Type 'help' for commands or 'examples' for query examples")
        print("🎯 Press TAB for query suggestions")
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
                if user_input.lower() == 'quit':
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
                elif user_input.lower() == 'clear':
                    self.rag_system.clear_conversation()
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
                    'template_id': result.get('template_id')
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