#!/usr/bin/env python3
"""
Debug script to identify where query processing fails
"""

import os
import sys
import requests
from dotenv import load_dotenv, find_dotenv
from customer_order_rag import SemanticRAGSystem
import logging

# Set up debug logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def debug_query_processing():
    """Debug the query processing step by step"""
    print("🔍 Debugging Query Processing Pipeline...")
    
    # Load environment variables
    env_file = find_dotenv()
    if env_file:
        load_dotenv(env_file, override=True)
    
    # Initialize RAG system
    rag_system = SemanticRAGSystem()
    
    # Load templates
    print("📚 Loading templates...")
    rag_system.populate_chromadb("query_templates.yaml", clear_first=True)
    
    # Test query
    test_query = "Find orders for John Doe"
    print(f"\n🔍 Processing query: '{test_query}'")
    
    # Step 1: Pre-processing
    print("\n📝 Step 1: Pre-processing...")
    from plugin_system import PluginContext
    context = PluginContext(user_query=test_query)
    
    processed_query = rag_system.plugin_manager.execute_pre_processing(test_query, context)
    print(f"   Original: '{test_query}'")
    print(f"   Processed: '{processed_query}'")
    
    # Step 2: Template search
    print("\n📝 Step 2: Template search...")
    templates = rag_system.find_best_template(processed_query)
    print(f"   Found {len(templates)} templates")
    
    if not templates:
        print("   ❌ No templates found!")
        return
    
    for i, template_info in enumerate(templates):
        template = template_info['template']
        similarity = template_info['similarity']
        print(f"   {i+1}. {template['id']} - Similarity: {similarity:.3f}")
    
    # Step 3: Template reranking
    print("\n📝 Step 3: Template reranking...")
    reranked_templates = rag_system.rerank_templates(templates, processed_query, context)
    print(f"   Reranked {len(reranked_templates)} templates")
    
    for i, template_info in enumerate(reranked_templates):
        template = template_info['template']
        similarity = template_info['similarity']
        print(f"   {i+1}. {template['id']} - Similarity: {similarity:.3f}")
    
    # Step 4: Process each template
    print("\n📝 Step 4: Processing templates...")
    
    for i, template_info in enumerate(reranked_templates):
        template = template_info['template']
        similarity = template_info['similarity']
        
        print(f"\n   🔄 Processing template {i+1}: {template['id']} (similarity: {similarity:.3f})")
        
        # Update context
        context.template_id = template['id']
        context.similarity_score = similarity
        
        # Check similarity threshold
        if similarity < 0.3:
            print(f"   ❌ Similarity {similarity:.3f} below threshold 0.3")
            continue
        else:
            print(f"   ✅ Similarity {similarity:.3f} above threshold 0.3")
        
        # Plugin validation
        print(f"   🔌 Plugin validation...")
        plugin_valid = rag_system.plugin_manager.validate_template_with_plugins(template, context)
        if not plugin_valid:
            print(f"   ❌ Template rejected by plugins")
            continue
        else:
            print(f"   ✅ Template approved by plugins")
        
        # Parameter extraction
        print(f"   📊 Parameter extraction...")
        try:
            base_parameters = rag_system.parameter_extractor.extract_parameters(processed_query, template)
            plugin_parameters = rag_system.plugin_manager.extract_parameters_with_plugins(
                processed_query, template, context
            )
            parameters = {**base_parameters, **plugin_parameters}
            context.parameters = parameters
            print(f"   ✅ Parameters extracted: {parameters}")
        except Exception as e:
            print(f"   ❌ Parameter extraction failed: {e}")
            continue
        
        # Parameter validation
        print(f"   📋 Parameter validation...")
        try:
            valid, errors = rag_system.parameter_extractor.validate_parameters(parameters, template)
            if not valid:
                print(f"   ❌ Parameter validation failed: {errors}")
                continue
            else:
                print(f"   ✅ Parameters validated successfully")
        except Exception as e:
            print(f"   ❌ Parameter validation error: {e}")
            continue
        
        # LLM verification
        print(f"   🧠 LLM verification...")
        try:
            verification_result = rag_system._verify_template_match(processed_query, template, parameters, context)
            if verification_result['should_proceed']:
                print(f"   ✅ LLM verification passed: {verification_result['reason']}")
            else:
                print(f"   ❌ LLM verification failed: {verification_result['reason']}")
                continue
        except Exception as e:
            print(f"   ❌ LLM verification error: {e}")
            continue
        
        # If we get here, the template should work
        print(f"   ✅ Template {template['id']} should work!")
        
        # Try to execute the query
        print(f"   💾 Executing query...")
        try:
            results, error = rag_system.execute_template(template, parameters)
            if error:
                print(f"   ❌ Query execution failed: {error}")
                continue
            else:
                print(f"   ✅ Query executed successfully, {len(results)} results")
                return True
        except Exception as e:
            print(f"   ❌ Query execution error: {e}")
            continue
    
    print("\n❌ No templates worked!")
    return False


def main():
    """Main function"""
    print("🚀 Query Processing Debug Tool")
    print("=" * 50)
    
    success = debug_query_processing()
    
    if success:
        print("\n✅ Query processing should work!")
    else:
        print("\n❌ Query processing failed - see details above")


if __name__ == "__main__":
    main() 