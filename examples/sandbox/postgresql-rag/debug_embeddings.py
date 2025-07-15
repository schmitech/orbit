#!/usr/bin/env python3
"""
Debug script to test embedding generation and ChromaDB functionality
"""

import os
import sys
import requests
from dotenv import load_dotenv, find_dotenv
from customer_order_rag import OllamaEmbeddingClient, SemanticRAGSystem
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_ollama_connection():
    """Test Ollama server connection"""
    print("🔍 Testing Ollama Connection...")
    
    # Load environment variables
    env_file = find_dotenv()
    if env_file:
        load_dotenv(env_file, override=True)
        print(f"✅ Loaded environment from: {env_file}")
    
    base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    embedding_model = os.getenv('OLLAMA_EMBEDDING_MODEL', 'nomic-embed-text')
    
    print(f"🌐 Ollama URL: {base_url}")
    print(f"🤖 Embedding Model: {embedding_model}")
    
    # Test server availability
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=10)
        response.raise_for_status()
        models = response.json()
        print(f"✅ Ollama server is running")
        print(f"📋 Available models: {[m['name'] for m in models.get('models', [])]}")
        
        # Check if embedding model is available
        model_names = [m['name'] for m in models.get('models', [])]
        if embedding_model in model_names:
            print(f"✅ Embedding model '{embedding_model}' is available")
        else:
            print(f"❌ Embedding model '{embedding_model}' is NOT available")
            print(f"💡 Please run: ollama pull {embedding_model}")
            return False
            
    except Exception as e:
        print(f"❌ Cannot connect to Ollama server: {e}")
        print(f"💡 Please ensure Ollama is running on {base_url}")
        return False
    
    return True


def test_embedding_generation():
    """Test embedding generation"""
    print("\n🔍 Testing Embedding Generation...")
    
    client = OllamaEmbeddingClient()
    
    # Test with a simple query
    test_query = "Find orders for John Doe"
    print(f"🧪 Testing query: '{test_query}'")
    
    try:
        embedding = client.get_embedding(test_query)
        if embedding:
            print(f"✅ Embedding generated successfully")
            print(f"📏 Embedding dimensions: {len(embedding)}")
            print(f"🔢 First 5 values: {embedding[:5]}")
            return True
        else:
            print(f"❌ No embedding generated (empty result)")
            return False
    except Exception as e:
        print(f"❌ Error generating embedding: {e}")
        return False


def test_chromadb_population():
    """Test ChromaDB population"""
    print("\n🔍 Testing ChromaDB Population...")
    
    try:
        # Initialize RAG system
        rag_system = SemanticRAGSystem()
        
        # Check if templates file exists
        templates_file = "query_templates.yaml"
        if not os.path.exists(templates_file):
            print(f"❌ Templates file not found: {templates_file}")
            return False
        
        print(f"✅ Templates file found: {templates_file}")
        
        # Load templates
        print("🔄 Loading templates into ChromaDB...")
        rag_system.populate_chromadb(templates_file, clear_first=True)
        
        # Check collection count
        collection_count = rag_system.collection.count()
        print(f"📊 Templates loaded: {collection_count}")
        
        if collection_count == 0:
            print("❌ No templates loaded into ChromaDB")
            return False
        
        print("✅ ChromaDB populated successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error populating ChromaDB: {e}")
        return False


def test_template_search():
    """Test template search"""
    print("\n🔍 Testing Template Search...")
    
    try:
        # Initialize RAG system
        rag_system = SemanticRAGSystem()
        
        # Load templates
        rag_system.populate_chromadb("query_templates.yaml", clear_first=True)
        
        # Test search
        test_query = "Find orders for John Doe"
        print(f"🔍 Searching for: '{test_query}'")
        
        templates = rag_system.find_best_template(test_query)
        
        if templates:
            print(f"✅ Found {len(templates)} templates")
            for i, template_info in enumerate(templates):
                template = template_info['template']
                similarity = template_info['similarity']
                print(f"  {i+1}. {template['id']} - Similarity: {similarity:.3f}")
                print(f"     Description: {template['description']}")
                
                # Check if it's the expected template
                if template['id'] == 'customer_orders_by_name':
                    print(f"     ✅ Found expected template!")
                    print(f"     📋 NL Examples: {template['nl_examples']}")
                    
                    # Check if our query is in the examples
                    if test_query in template['nl_examples']:
                        print(f"     ✅ Query matches example exactly!")
                    else:
                        print(f"     ❓ Query doesn't match examples exactly")
                
                print()
            
            return True
        else:
            print("❌ No templates found")
            return False
            
    except Exception as e:
        print(f"❌ Error testing template search: {e}")
        return False


def test_full_query_processing():
    """Test full query processing"""
    print("\n🔍 Testing Full Query Processing...")
    
    try:
        # Initialize RAG system
        rag_system = SemanticRAGSystem()
        
        # Load templates
        rag_system.populate_chromadb("query_templates.yaml", clear_first=True)
        
        # Test query
        test_query = "Find orders for John Doe"
        print(f"🔍 Processing query: '{test_query}'")
        
        result = rag_system.process_query(test_query)
        
        print(f"📊 Result:")
        print(f"  Success: {result['success']}")
        if result['success']:
            print(f"  Template: {result['template_id']}")
            print(f"  Similarity: {result['similarity']:.3f}")
            print(f"  Parameters: {result['parameters']}")
            print(f"  Results: {result['result_count']} records")
        else:
            print(f"  Error: {result.get('error', 'Unknown error')}")
            if 'validation_errors' in result:
                print(f"  Validation errors: {result['validation_errors']}")
        
        print(f"  Response: {result['response']}")
        
        return result['success']
        
    except Exception as e:
        print(f"❌ Error in full query processing: {e}")
        return False


def main():
    """Main diagnostic function"""
    print("🚀 RAG System Diagnostic Tool")
    print("=" * 50)
    
    tests = [
        ("Ollama Connection", test_ollama_connection),
        ("Embedding Generation", test_embedding_generation),
        ("ChromaDB Population", test_chromadb_population),
        ("Template Search", test_template_search),
        ("Full Query Processing", test_full_query_processing)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n🧪 Running: {test_name}")
        print("-" * 30)
        success = test_func()
        results.append((test_name, success))
        
        if not success:
            print(f"❌ {test_name} failed - stopping here")
            break
    
    print("\n📊 Test Results Summary:")
    print("=" * 50)
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
    
    if all(success for _, success in results):
        print("\n🎉 All tests passed!")
    else:
        print("\n❌ Some tests failed. Please address the issues above.")


if __name__ == "__main__":
    main() 