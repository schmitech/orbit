# RAG System Plugin Architecture

This document explains the plugin architecture for the RAG system, which allows you to extend functionality without modifying the core system.

## Overview

The plugin system provides a flexible way to add custom functionality to the RAG system through a well-defined interface. Plugins can:

- **Pre-process queries** before template matching
- **Post-process results** after database queries
- **Enhance responses** with additional formatting or context
- **Validate templates** before execution
- **Extract parameters** with custom logic

## Architecture

### Core Components

1. **`RAGPlugin` Protocol** - Interface that all plugins must implement
2. **`BaseRAGPlugin`** - Base class with default implementations
3. **`PluginManager`** - Manages plugin registration and execution
4. **`PluggableRAGSystem`** - Enhanced RAG system with plugin support

### Plugin Lifecycle

```
User Query → Pre-processing Plugins → Template Matching → 
Parameter Extraction → Query Execution → Post-processing Plugins → 
Response Generation → Response Enhancement Plugins → Final Response
```

## Built-in Plugins

### Security Plugin
- **Priority**: Critical
- **Function**: Validates queries and templates for security
- **Features**: SQL injection detection, template approval checking

### Query Normalization Plugin
- **Priority**: High
- **Function**: Normalizes and cleans user queries
- **Features**: Whitespace removal, case conversion, punctuation cleaning

### Query Expansion Plugin
- **Priority**: Normal
- **Function**: Expands queries with synonyms
- **Features**: Synonym mapping for better template matching

### Result Filtering Plugin
- **Priority**: Normal
- **Function**: Filters and limits results
- **Features**: Result count limiting, sorting

### Data Enrichment Plugin
- **Priority**: Low
- **Function**: Adds computed fields to results
- **Features**: Formatted currency, time calculations, status icons

### Response Enhancement Plugin
- **Priority**: Low
- **Function**: Enhances generated responses
- **Features**: Execution time, confidence scores, template info

### Logging Plugin
- **Priority**: Low
- **Function**: Comprehensive logging
- **Features**: Query logging, result logging, response logging

## Creating Custom Plugins

### Basic Plugin Structure

```python
from plugin_system import BaseRAGPlugin, PluginContext, PluginPriority

class MyCustomPlugin(BaseRAGPlugin):
    def __init__(self):
        super().__init__("MyCustomPlugin", "1.0.0", PluginPriority.NORMAL)
    
    def pre_process_query(self, query: str, context: PluginContext) -> str:
        """Modify query before processing"""
        # Your custom logic here
        return modified_query
    
    def post_process_results(self, results: List[Dict], context: PluginContext) -> List[Dict]:
        """Transform results after query execution"""
        # Your custom logic here
        return modified_results
    
    def enhance_response(self, response: str, context: PluginContext) -> str:
        """Enhance the generated response"""
        # Your custom logic here
        return enhanced_response
```

### Plugin Priority Levels

- **CRITICAL** (4): Security, validation (executed first)
- **HIGH** (3): Query normalization, essential processing
- **NORMAL** (2): Standard business logic
- **LOW** (1): Enhancement, formatting (executed last)

### Plugin Context

The `PluginContext` provides information about the current query:

```python
@dataclass
class PluginContext:
    user_query: str
    template_id: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    similarity_score: Optional[float] = None
    execution_time_ms: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None
```

## Usage Examples

### Basic Usage

```python
from customer_order_rag import SemanticRAGSystem

# Create system with default plugins
rag_system = SemanticRAGSystem(enable_default_plugins=True)

# Process a query
result = rag_system.process_query("Show me orders over $500")
print(result['response'])
print(f"Plugins used: {result['plugins_used']}")
```

### Custom Plugin Registration

```python
from example_plugins import CustomerSegmentationPlugin

# Create system without default plugins
rag_system = SemanticRAGSystem(enable_default_plugins=False)

# Register custom plugins
rag_system.register_plugin(CustomerSegmentationPlugin())

# Process query
result = rag_system.process_query("Show customer 123's orders")
```

### Plugin Management

```python
# List all plugins
plugins = rag_system.list_plugins()
for plugin in plugins:
    print(f"{plugin['name']}: {plugin['enabled']}")

# Enable/disable plugins
rag_system.enable_plugin("QueryExpansion")
rag_system.disable_plugin("Logging")

# Get specific plugin
plugin = rag_system.get_plugin("Security")
if plugin:
    print(f"Security plugin version: {plugin.get_version()}")
```

## Example Plugins

### Customer Segmentation Plugin

Adds customer segmentation analysis to results:

```python
class CustomerSegmentationPlugin(BaseRAGPlugin):
    def post_process_results(self, results: List[Dict], context: PluginContext) -> List[Dict]:
        for result in results:
            # Calculate customer metrics
            total_orders = result.get('total_orders', 0)
            lifetime_value = result.get('lifetime_value', 0)
            
            # Determine segment
            segment = self._determine_segment(total_orders, lifetime_value)
            result['customer_segment'] = segment
        
        return results
```

### Revenue Analytics Plugin

Adds revenue analytics to results:

```python
class RevenueAnalyticsPlugin(BaseRAGPlugin):
    def post_process_results(self, results: List[Dict], context: PluginContext) -> List[Dict]:
        total_revenue = sum(r.get('total', 0) for r in results)
        avg_order_value = total_revenue / len(results) if results else 0
        
        for result in results:
            result['revenue_analytics'] = {
                'total_revenue': total_revenue,
                'avg_order_value': avg_order_value,
                'revenue_percentage': (result.get('total', 0) / total_revenue * 100)
            }
        
        return results
```

### Business Rules Plugin

Applies business rules and generates recommendations:

```python
class BusinessRulesPlugin(BaseRAGPlugin):
    def post_process_results(self, results: List[Dict], context: PluginContext) -> List[Dict]:
        for result in results:
            # Apply business rules
            result['business_flags'] = self._apply_business_rules(result)
            
            # Generate recommendations
            result['recommendations'] = self._generate_recommendations(result)
        
        return results
```

## Best Practices

### 1. Plugin Design

- **Single Responsibility**: Each plugin should have one clear purpose
- **Stateless**: Plugins should not maintain state between calls
- **Error Handling**: Always handle exceptions gracefully
- **Logging**: Use appropriate logging levels for debugging

### 2. Performance

- **Efficient Processing**: Keep plugin operations fast
- **Caching**: Use caching for expensive operations
- **Batch Processing**: Process multiple items together when possible

### 3. Security

- **Input Validation**: Always validate inputs
- **Output Sanitization**: Sanitize outputs to prevent injection
- **Access Control**: Implement proper access controls if needed

### 4. Testing

```python
def test_my_plugin():
    plugin = MyCustomPlugin()
    context = PluginContext(user_query="test query")
    
    # Test pre-processing
    result = plugin.pre_process_query("test", context)
    assert result == "expected_result"
    
    # Test post-processing
    results = [{"test": "data"}]
    processed = plugin.post_process_results(results, context)
    assert len(processed) == 1
```

## Configuration

### Environment Variables

```bash
# Enable/disable specific plugins
ENABLE_SECURITY_PLUGIN=true
ENABLE_LOGGING_PLUGIN=false

# Plugin-specific configuration
QUERY_EXPANSION_SYNONYMS_FILE=./synonyms.json
RESULT_FILTERING_MAX_RESULTS=100
```

### Plugin Configuration

```python
# Configure plugins with parameters
rag_system = PluggableRAGSystem()

# Configure result filtering
filtering_plugin = rag_system.get_plugin("ResultFiltering")
if filtering_plugin:
    filtering_plugin.max_results = 50

# Configure query expansion
expansion_plugin = rag_system.get_plugin("QueryExpansion")
if expansion_plugin:
    expansion_plugin.synonyms.update({
        'product': ['item', 'goods', 'merchandise']
    })
```

## Troubleshooting

### Common Issues

1. **Plugin not executing**: Check if plugin is enabled
2. **Performance issues**: Review plugin priority and efficiency
3. **Memory leaks**: Ensure plugins don't accumulate state
4. **Security concerns**: Validate all inputs and outputs

### Debugging

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Check plugin execution
result = rag_system.process_query("test query")
print(f"Plugins used: {result['plugins_used']}")
print(f"Execution time: {result.get('execution_time_ms', 0)}ms")
```

## Extending the System

### Adding New Plugin Types

To add new plugin types, extend the `RAGPlugin` protocol:

```python
@runtime_checkable
class RAGPlugin(Protocol):
    # ... existing methods ...
    
    def new_plugin_method(self, data: Any, context: PluginContext) -> Any:
        """New plugin method"""
        ...
```

### Integration with External Systems

Plugins can integrate with external systems:

```python
class ExternalAPIPlugin(BaseRAGPlugin):
    def __init__(self, api_url: str, api_key: str):
        super().__init__("ExternalAPI", "1.0.0")
        self.api_url = api_url
        self.api_key = api_key
    
    def post_process_results(self, results: List[Dict], context: PluginContext) -> List[Dict]:
        # Call external API
        enriched_data = self._call_external_api(results)
        return self._merge_results(results, enriched_data)
```

This plugin architecture provides a powerful and flexible way to extend the RAG system with custom functionality while maintaining clean separation of concerns and easy testing. 