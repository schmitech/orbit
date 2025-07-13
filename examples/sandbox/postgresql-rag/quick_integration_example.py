#!/usr/bin/env python3
"""
Quick Integration Example
=========================

This example shows the fastest way to integrate the plugin system with your existing code.
"""

from customer_order_rag import SemanticRAGSystem
from example_plugins import CustomerSegmentationPlugin, RevenueAnalyticsPlugin

def main():
    """Demonstrate quick plugin integration"""
    
    print("🚀 Quick Plugin Integration Example")
    print("=" * 50)
    
    # Option 1: Use the enhanced system (easiest)
    print("\n1️⃣ Using Enhanced System (Recommended):")
    print("-" * 40)
    
    # Initialize with plugins enabled
    rag_system = SemanticRAGSystem(
        enable_default_plugins=True,
        enable_postgresql_plugins=True
    )
    
    # Populate with templates
    rag_system.populate_chromadb("query_templates.yaml", clear_first=True)
    
    # Test a query
    result = rag_system.process_query("Show me orders over $500")
    
    print(f"✅ Success: {result['success']}")
    print(f"📋 Template: {result.get('template_id', 'N/A')}")
    print(f"📊 Results: {result.get('result_count', 0)} records")
    print(f"⏱️ Execution time: {result.get('execution_time_ms', 0):.2f}ms")
    print(f"🔌 Plugins used: {', '.join(result.get('plugins_used', []))}")
    print(f"💬 Response: {result['response'][:100]}...")
    
    # Option 2: Add custom plugins
    print("\n2️⃣ Adding Custom Plugins:")
    print("-" * 40)
    
    # Register additional custom plugins
    rag_system.register_plugin(CustomerSegmentationPlugin())
    rag_system.register_plugin(RevenueAnalyticsPlugin())
    
    # Test with custom plugins
    result = rag_system.process_query("Show customer 123's orders")
    
    print(f"✅ Success: {result['success']}")
    print(f"🔌 Plugins used: {', '.join(result.get('plugins_used', []))}")
    
    # Check if custom data was added
    if result.get('success') and result.get('results'):
        first_result = result['results'][0]
        if 'customer_segment' in first_result:
            print(f"🎯 Customer Segment: {first_result['customer_segment']}")
        if 'revenue_analytics' in first_result:
            print(f"💰 Revenue Analytics: Available")
    
    # Option 3: Plugin management
    print("\n3️⃣ Plugin Management:")
    print("-" * 40)
    
    # List all plugins
    plugins = rag_system.list_plugins()
    print("Registered plugins:")
    for plugin in plugins:
        status = "✅" if plugin['enabled'] else "❌"
        print(f"  {status} {plugin['name']} v{plugin['version']} ({plugin['priority']})")
    
    # Enable/disable plugins
    rag_system.disable_plugin("Logging")
    rag_system.enable_plugin("QueryExpansion")
    
    print("\nAfter enabling/disabling:")
    plugins = rag_system.list_plugins()
    for plugin in plugins:
        status = "✅" if plugin['enabled'] else "❌"
        print(f"  {status} {plugin['name']}")
    
    # Option 4: Performance comparison
    print("\n4️⃣ Performance Comparison:")
    print("-" * 40)
    
    # Test without plugins
    rag_system_no_plugins = SemanticRAGSystem(enable_default_plugins=False)
    rag_system_no_plugins.populate_chromadb("query_templates.yaml", clear_first=False)
    
    import time
    
    # Test with plugins
    start_time = time.time()
    result_with_plugins = rag_system.process_query("Show me orders over $500")
    time_with_plugins = (time.time() - start_time) * 1000
    
    # Test without plugins
    start_time = time.time()
    result_no_plugins = rag_system_no_plugins.process_query("Show me orders over $500")
    time_no_plugins = (time.time() - start_time) * 1000
    
    print(f"⏱️ Time with plugins: {time_with_plugins:.2f}ms")
    print(f"⏱️ Time without plugins: {time_no_plugins:.2f}ms")
    print(f"📈 Plugin overhead: {((time_with_plugins - time_no_plugins) / time_no_plugins * 100):.1f}%")
    
    # Option 5: Backward compatibility
    print("\n5️⃣ Backward Compatibility:")
    print("-" * 40)
    
    # Your existing code still works
    result = rag_system.process_query("Show me orders over $500")
    
    # All existing fields are still there
    print(f"✅ Success: {result['success']}")
    print(f"📋 Template: {result.get('template_id', 'N/A')}")
    print(f"🎯 Similarity: {result.get('similarity', 0):.3f}")
    print(f"🔍 Parameters: {result.get('parameters', {})}")
    print(f"📊 Results: {result.get('result_count', 0)} records")
    print(f"💬 Response: {result['response'][:100]}...")
    
    # New fields are added
    print(f"🔌 Plugins used: {', '.join(result.get('plugins_used', []))}")
    print(f"⏱️ Execution time: {result.get('execution_time_ms', 0):.2f}ms")
    
    print("\n🎉 Integration complete! Your existing code works with enhanced functionality.")

if __name__ == "__main__":
    main() 