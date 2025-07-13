#!/usr/bin/env python3
"""
Test Query Expansion Plugin
===========================

This script demonstrates the query expansion functionality.
"""

import logging
from customer_order_rag import SemanticRAGSystem
from query_expansion_plugin import QueryExpansionPlugin

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_query_expansion():
    """Test the query expansion plugin with the RAG system"""
    
    print("🚀 Testing Query Expansion Plugin")
    print("=" * 60)
    
    # Initialize RAG system with query expansion plugin
    rag_system = SemanticRAGSystem(
        enable_default_plugins=False,  # Disable default plugins to test only query expansion
        enable_postgresql_plugins=False
    )
    
    # Register the query expansion plugin
    expansion_plugin = QueryExpansionPlugin(
        enable_sentence_transformers=True,
        enable_synonyms=True,
        max_variations=5
    )
    rag_system.register_plugin(expansion_plugin)
    
    print("✅ Query expansion plugin registered")
    
    # Populate ChromaDB with templates
    rag_system.populate_chromadb("query_templates.yaml", clear_first=True)
    
    # Test queries
    test_queries = [
        "Show me orders from Maria Smith",
        "Find customer purchases over $500",
        "Display recent transactions for client 123",
        "Get high-value orders from last month",
        "Show pending orders"
    ]
    
    print("\n🧪 Testing Query Expansion:")
    print("=" * 60)
    
    for query in test_queries:
        print(f"\n📝 Original Query: {query}")
        
        # Process the query
        result = rag_system.process_query(query)
        
        print(f"✅ Success: {result['success']}")
        if result['success']:
            print(f"📋 Template: {result['template_id']}")
            print(f"🎯 Similarity: {result['similarity']:.3f}")
            print(f"🔍 Parameters: {result['parameters']}")
            print(f"📊 Results: {result['result_count']} records")
            print(f"🔌 Plugins used: {', '.join(result.get('plugins_used', []))}")
        else:
            print(f"❌ Error: {result.get('error', 'Unknown error')}")
        
        print(f"\n💬 Response:\n{result['response']}")
        print("-" * 60)


def test_plugin_directly():
    """Test the query expansion plugin directly"""
    
    print("\n🔧 Testing Plugin Directly:")
    print("=" * 60)
    
    # Create plugin instance
    plugin = QueryExpansionPlugin(
        enable_sentence_transformers=True,
        enable_synonyms=True,
        max_variations=5
    )
    
    # Test queries
    test_queries = [
        "Show me orders from Maria Smith",
        "Find customer purchases over $500",
        "Display recent transactions"
    ]
    
    for query in test_queries:
        print(f"\n📝 Testing: {query}")
        
        # Create context
        from plugin_system import PluginContext
        context = PluginContext(user_query=query)
        
        # Test pre-processing
        processed_query = plugin.pre_process_query(query, context)
        print(f"✅ Processed: {processed_query}")
        
        if hasattr(context, 'query_variations'):
            print(f"🔄 Generated {len(context.query_variations)} variations:")
            for i, variation in enumerate(context.query_variations, 1):
                print(f"   {i}. {variation}")
        
        print("-" * 40)


def test_with_dependencies():
    """Test what happens when dependencies are missing"""
    
    print("\n⚠️ Testing with Missing Dependencies:")
    print("=" * 60)
    
    # Test with sentence transformers disabled
    plugin_no_st = QueryExpansionPlugin(
        enable_sentence_transformers=False,
        enable_synonyms=True,
        max_variations=3
    )
    
    query = "Show me orders from Maria Smith"
    context = PluginContext(user_query=query)
    
    processed_query = plugin_no_st.pre_process_query(query, context)
    print(f"📝 Query: {query}")
    print(f"✅ Processed: {processed_query}")
    
    if hasattr(context, 'query_variations'):
        print(f"🔄 Variations (no sentence transformers): {len(context.query_variations)}")
        for i, variation in enumerate(context.query_variations, 1):
            print(f"   {i}. {variation}")


if __name__ == "__main__":
    # Test the plugin directly first
    test_plugin_directly()
    
    # Test with missing dependencies
    test_with_dependencies()
    
    # Test with the full RAG system
    test_query_expansion() 