#!/usr/bin/env python3
"""
Interactive Demo for Semantic RAG System
Test the system with your own queries
"""

from semantic_rag_system import SemanticRAGSystem
import sys

def main():
    """Interactive demo"""
    print("🚀 Semantic RAG System - Interactive Demo")
    print("=" * 50)
    print("This system uses:")
    print("- ChromaDB for vector storage")
    print("- Ollama (nomic-embed-text) for embeddings")
    print("- Ollama (gemma3:1b) for inference")
    print("- PostgreSQL for data storage")
    print()
    
    # Initialize the RAG system
    try:
        rag_system = SemanticRAGSystem()
        print("✅ System initialized successfully!")
    except Exception as e:
        print(f"❌ Error initializing system: {e}")
        print("Make sure:")
        print("1. Ollama is running (http://localhost:11434)")
        print("2. nomic-embed-text model is pulled: ollama pull nomic-embed-text")
        print("3. gemma3:1b model is pulled: ollama pull gemma3:1b")
        print("4. PostgreSQL is accessible with your .env configuration")
        return
    
    # Populate ChromaDB (only if empty)
    try:
        rag_system.populate_chromadb("query_templates.yaml")
        print("✅ Templates loaded into ChromaDB")
    except Exception as e:
        print(f"❌ Error loading templates: {e}")
        return
    
    print("\n💡 Example queries you can try:")
    print("- What did customer 1 buy last week?")
    print("- Show me all orders over $500 from last month")
    print("- Find delivered orders from last week")
    print("- Give me a summary for customer 5")
    print("- Show orders from New York customers")
    print("- What orders were paid with credit card?")
    print()
    
    # Interactive loop
    while True:
        try:
            # Get user input
            user_query = input("🤔 Enter your query (or 'quit' to exit): ").strip()
            
            if user_query.lower() in ['quit', 'exit', 'q']:
                print("👋 Goodbye!")
                break
            
            if not user_query:
                continue
            
            # Process the query
            result = rag_system.process_query(user_query)
            
            if result['success']:
                print(f"\n✅ Success!")
                print(f"📋 Template: {result['template_id']}")
                print(f"🎯 Similarity: {result['similarity']:.3f}")
                print(f"🔍 Parameters: {result['parameters']}")
                print(f"📊 Results: {result['result_count']} records")
                print(f"\n💬 Response:")
                print(result['response'])
            else:
                print(f"\n❌ Error: {result['error']}")
            
            print("\n" + "="*50)
            
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")
            print("="*50)

if __name__ == "__main__":
    main() 