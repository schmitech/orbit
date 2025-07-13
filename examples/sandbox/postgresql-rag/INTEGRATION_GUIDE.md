# Plugin System Integration Guide

This guide explains how to integrate the plugin system with your existing RAG system code.

## Integration Options

### Option 1: Use the New Enhanced System (Recommended)

The easiest way is to use the new `SemanticRAGSystem` class, which includes all your existing functionality plus plugin support:

```python
# Replace your existing import
# from semantic_rag_system import SemanticRAGSystem
from customer_order_rag import SemanticRAGSystem

# Replace your existing initialization
# rag_system = SemanticRAGSystem()
rag_system = SemanticRAGSystem(
    enable_default_plugins=True,
    enable_postgresql_plugins=True
)

# Your existing code works exactly the same
result = rag_system.process_query("Show me orders over $500")
print(result['response'])

# Plus you get plugin information
print(f"Plugins used: {result['plugins_used']}")
print(f"Execution time: {result.get('execution_time_ms', 0)}ms")
```

### Option 2: Extend Your Existing SemanticRAGSystem

If you want to keep your existing `SemanticRAGSystem` class, you can extend it with plugin support:

```python
# In your customer_order_rag.py file, add these imports at the top:
from plugin_system import (
    PluginManager, 
    PluginContext, 
    RAGPlugin,
    QueryNormalizationPlugin,
    ResultFilteringPlugin,
    DataEnrichmentPlugin,
    ResponseEnhancementPlugin,
    SecurityPlugin,
    LoggingPlugin
)
import time

# Then modify your SemanticRAGSystem.__init__ method:
class SemanticRAGSystem(BaseRAGSystem):
    def __init__(self, chroma_persist_directory: str = "./chroma_db", enable_plugins: bool = True):
        # Your existing initialization code...
        super().__init__(
            chroma_persist_directory=chroma_persist_directory,
            embedding_client=embedding_client,
            inference_client=inference_client,
            db_client=db_client,
            parameter_extractor=parameter_extractor,
            response_generator=response_generator
        )
        
        # Add plugin support
        if enable_plugins:
            self.plugin_manager = PluginManager()
            self._register_default_plugins()
        else:
            self.plugin_manager = None
    
    def _register_default_plugins(self):
        """Register default plugins"""
        default_plugins = [
            SecurityPlugin(),
            QueryNormalizationPlugin(),
            ResultFilteringPlugin(max_results=50),
            DataEnrichmentPlugin(),
            ResponseEnhancementPlugin(),
            LoggingPlugin()
        ]
        
        for plugin in default_plugins:
            self.plugin_manager.register_plugin(plugin)
        
        logger.info(f"Registered {len(default_plugins)} default plugins")
    
    # Add plugin management methods
    def register_plugin(self, plugin: RAGPlugin):
        """Register a custom plugin"""
        if self.plugin_manager:
            self.plugin_manager.register_plugin(plugin)
    
    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all registered plugins"""
        if not self.plugin_manager:
            return []
        
        plugins_info = []
        for plugin in self.plugin_manager.plugins:
            plugins_info.append({
                'name': plugin.get_name(),
                'version': plugin.get_version(),
                'priority': plugin.get_priority().name,
                'enabled': plugin.is_enabled()
            })
        return plugins_info
    
    # Override the process_query method to include plugin support
    def process_query(self, user_query: str, conversation_context: bool = True) -> Dict[str, Any]:
        """Process a user query with plugin support"""
        start_time = time.time()
        
        # If no plugin manager, use original method
        if not self.plugin_manager:
            return super().process_query(user_query, conversation_context)
        
        # Create plugin context
        context = PluginContext(user_query=user_query)
        
        try:
            # Apply pre-processing plugins
            processed_query = self.plugin_manager.execute_pre_processing(user_query, context)
            
            # Use your existing logic but with processed query
            templates = self.find_best_template(processed_query)
            
            if not templates:
                response = "I couldn't find a matching query pattern. Could you rephrase your question?"
                return {
                    'success': False,
                    'error': 'No matching query template found',
                    'response': response,
                    'plugins_used': self._get_used_plugins_info()
                }
            
            # Your existing template processing logic...
            templates = self.rerank_templates(templates, processed_query)
            
            for template_info in templates:
                template = template_info['template']
                similarity = template_info['similarity']
                
                # Update context
                context.template_id = template['id']
                context.similarity_score = similarity
                
                if similarity < 0.3:
                    continue
                
                # Validate template with plugins
                if not self.plugin_manager.validate_template_with_plugins(template, context):
                    continue
                
                # Extract parameters with plugin support
                base_parameters = self.parameter_extractor.extract_parameters(processed_query, template)
                plugin_parameters = self.plugin_manager.extract_parameters_with_plugins(
                    processed_query, template, context
                )
                parameters = {**base_parameters, **plugin_parameters}
                context.parameters = parameters
                
                # Your existing validation and execution logic...
                valid, errors = self.parameter_extractor.validate_parameters(parameters, template)
                
                if not valid:
                    if template_info == templates[0]:
                        suggestions = self.suggest_alternatives(processed_query, template)
                        return {
                            'success': False,
                            'error': 'Missing required parameters',
                            'validation_errors': errors,
                            'response': suggestions,
                            'template_id': template['id'],
                            'similarity': similarity,
                            'plugins_used': self._get_used_plugins_info()
                        }
                    continue
                
                # Execute query
                results, error = self.execute_template(template, parameters)
                
                if error:
                    response = self.response_generator.generate_response(
                        processed_query, results, template, error
                    )
                    enhanced_response = self.plugin_manager.execute_response_enhancement(
                        response, context
                    )
                    return {
                        'success': False,
                        'error': error,
                        'response': enhanced_response,
                        'template_id': template['id'],
                        'similarity': similarity,
                        'plugins_used': self._get_used_plugins_info()
                    }
                
                # Apply post-processing plugins
                processed_results = self.plugin_manager.execute_post_processing(results, context)
                
                # Generate response
                response = self.response_generator.generate_response(
                    processed_query, processed_results, template
                )
                
                # Apply response enhancement plugins
                enhanced_response = self.plugin_manager.execute_response_enhancement(
                    response, context
                )
                
                # Calculate execution time
                execution_time = (time.time() - start_time) * 1000
                
                # Add to conversation history
                if conversation_context:
                    self.conversation_history.append({
                        "role": "assistant", 
                        "content": enhanced_response,
                        "template_id": template['id'],
                        "result_count": len(processed_results),
                        "plugins_used": self._get_used_plugins_info()
                    })
                
                return {
                    'success': True,
                    'template_id': template['id'],
                    'similarity': similarity,
                    'parameters': parameters,
                    'results': processed_results,
                    'response': enhanced_response,
                    'result_count': len(processed_results),
                    'execution_time_ms': execution_time,
                    'plugins_used': self._get_used_plugins_info()
                }
            
            # No template worked
            response = "I understood your question but couldn't process it properly. Could you try rephrasing it?"
            return {
                'success': False,
                'error': 'No viable template found',
                'response': response,
                'plugins_used': self._get_used_plugins_info()
            }
            
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return {
                'success': False,
                'error': str(e),
                'response': "I encountered an error processing your request.",
                'plugins_used': self._get_used_plugins_info()
            }
    
    def _get_used_plugins_info(self) -> List[str]:
        """Get list of enabled plugin names"""
        if not self.plugin_manager:
            return []
        return [p.get_name() for p in self.plugin_manager.get_enabled_plugins()]
```

### Option 3: Minimal Integration (Plugin Support Only)

If you want to add just basic plugin support without changing your existing logic:

```python
# Add to your existing SemanticRAGSystem class
def __init__(self, chroma_persist_directory: str = "./chroma_db", enable_plugins: bool = False):
    # Your existing initialization...
    
    # Optional plugin support
    self.plugin_manager = None
    if enable_plugins:
        self.plugin_manager = PluginManager()
        self._register_default_plugins()

def process_query(self, user_query: str, conversation_context: bool = True) -> Dict[str, Any]:
    """Your existing process_query method with optional plugin support"""
    # If plugins are disabled, use original method
    if not self.plugin_manager:
        return super().process_query(user_query, conversation_context)
    
    # Apply pre-processing plugins
    context = PluginContext(user_query=user_query)
    processed_query = self.plugin_manager.execute_pre_processing(user_query, context)
    
    # Use your existing logic with processed query
    result = super().process_query(processed_query, conversation_context)
    
    # Apply post-processing if successful
    if result.get('success') and 'results' in result:
        result['results'] = self.plugin_manager.execute_post_processing(
            result['results'], context
        )
    
    # Apply response enhancement
    if 'response' in result:
        result['response'] = self.plugin_manager.execute_response_enhancement(
            result['response'], context
        )
    
    # Add plugin information
    result['plugins_used'] = self._get_used_plugins_info()
    
    return result
```

## Migration Steps

### Step 1: Choose Your Integration Approach

1. **Quick Migration**: Use `SemanticRAGSystem` (Option 1)
2. **Full Control**: Extend your existing class (Option 2)
3. **Minimal Change**: Add basic plugin support (Option 3)

### Step 2: Update Your Code

```python
# Before (your existing code)
from semantic_rag_system import SemanticRAGSystem

rag_system = SemanticRAGSystem()
result = rag_system.process_query("Show me orders over $500")

# After (with plugins)
from semantic_rag_system import SemanticRAGSystem

rag_system = SemanticRAGSystem(enable_default_plugins=True)
result = rag_system.process_query("Show me orders over $500")

# New features available
print(f"Plugins used: {result['plugins_used']}")
print(f"Execution time: {result.get('execution_time_ms', 0)}ms")
```

### Step 3: Add Custom Plugins (Optional)

```python
from example_plugins import CustomerSegmentationPlugin

# Register custom plugins
rag_system.register_plugin(CustomerSegmentationPlugin())

# Your queries now include customer segmentation
result = rag_system.process_query("Show customer 123's orders")
# Results will include customer_segment and segment_insights fields
```

### Step 4: Configure Plugins

```python
# List all plugins
plugins = rag_system.list_plugins()
for plugin in plugins:
    print(f"{plugin['name']}: {plugin['enabled']}")

# Enable/disable specific plugins
rag_system.enable_plugin("QueryExpansion")
rag_system.disable_plugin("Logging")

# Configure plugin parameters
filtering_plugin = rag_system.get_plugin("ResultFiltering")
if filtering_plugin:
    filtering_plugin.max_results = 25
```

## Testing Your Integration

### Basic Test

```python
def test_plugin_integration():
    # Test with plugins enabled
    rag_system = SemanticRAGSystem(enable_default_plugins=True)
    
    result = rag_system.process_query("Show me orders over $500")
    
    # Verify plugin information is included
    assert 'plugins_used' in result
    assert 'execution_time_ms' in result
    assert len(result['plugins_used']) > 0
    
    print("✅ Plugin integration test passed!")

# Test with plugins disabled
def test_backward_compatibility():
    rag_system = SemanticRAGSystem(enable_default_plugins=False)
    
    result = rag_system.process_query("Show me orders over $500")
    
    # Should work without plugins
    assert result['success'] in [True, False]
    print("✅ Backward compatibility test passed!")
```

### Performance Test

```python
def test_performance():
    import time
    
    # Test without plugins
    start_time = time.time()
    rag_system_no_plugins = SemanticRAGSystem(enable_default_plugins=False)
    result_no_plugins = rag_system_no_plugins.process_query("Show me orders over $500")
    time_no_plugins = time.time() - start_time
    
    # Test with plugins
    start_time = time.time()
    rag_system_with_plugins = SemanticRAGSystem(enable_default_plugins=True)
    result_with_plugins = rag_system_with_plugins.process_query("Show me orders over $500")
    time_with_plugins = time.time() - start_time
    
    print(f"Time without plugins: {time_no_plugins:.3f}s")
    print(f"Time with plugins: {time_with_plugins:.3f}s")
    print(f"Plugin overhead: {((time_with_plugins - time_no_plugins) / time_no_plugins * 100):.1f}%")
```

## Troubleshooting

### Common Issues

1. **Import Errors**: Make sure all plugin files are in the same directory
2. **Plugin Not Working**: Check if plugins are enabled with `rag_system.list_plugins()`
3. **Performance Issues**: Disable unnecessary plugins or adjust priorities
4. **Memory Issues**: Some plugins cache data - monitor memory usage

### Debug Mode

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# This will show detailed plugin execution logs
rag_system = SemanticRAGSystem(enable_default_plugins=True)
result = rag_system.process_query("test query")
```

## Benefits of Integration

1. **Enhanced Functionality**: Query normalization, security validation, data enrichment
2. **Better Performance**: Caching, result filtering, optimized processing
3. **Extensibility**: Easy to add custom business logic
4. **Monitoring**: Execution time tracking, plugin usage metrics
5. **Security**: Built-in SQL injection detection and template validation

The plugin system is designed to be backward compatible, so your existing code will continue to work while gaining access to powerful new features. 