# Adapter Architecture Implementation Guide

This guide explains how to implement and use the adapter architecture for retrievers in your project. The architecture is designed to be flexible, extensible, and easy to maintain.

## Architecture Overview

The adapter architecture separates concerns into the following components:

1. **Base Retrievers**: Abstract base classes that define common interfaces and functionality
   - `BaseRetriever`: Core retriever interface
   - `VectorDBRetriever`: For vector database implementations
   - `SQLRetriever`: For SQL-based implementations

2. **Domain Adapters**: Components that adapt documents for specific domains
   - `DocumentAdapter`: Base interface for all domain adapters
   - Specialized adapters (e.g., `QADocumentAdapter`, `GenericDocumentAdapter`)
   - Datasource-specific adapters (e.g., `ChromaQAAdapter`, `QASqliteAdapter`)

3. **Adapter Registry**: Central registry for managing adapter types, datasources, and implementations
   - `ADAPTER_REGISTRY`: Singleton instance managing adapter registration
   - Supports hierarchical structure: type -> datasource -> adapter name
   - Handles lazy loading of adapters

4. **Retriever Factory**: Factory for creating retriever instances
   - `RetrieverFactory`: Creates retrievers with appropriate domain adapters
   - Supports both direct instantiation and lazy loading

The configuration uses a clear hierarchy:
- `type`: The adapter type (e.g., "retriever", "parser")
- `datasource`: The datasource provider (e.g., "sqlite", "chroma")
- `adapter`: The domain adapter name (e.g., "qa", "generic")
- `implementation`: The implementation class path
- `config`: Adapter-specific configuration

## Using the Architecture

### 1. Configure Your Adapters

In your `config.yaml` file, define your adapters using the structure:

```yaml
adapters:
  - type: "retriever"
    datasource: "sqlite"
    adapter: "qa"
    implementation: "retrievers.implementations.sqlite.sqlite_retriever.SqliteRetriever"
    config:
      confidence_threshold: 0.5
      relevance_threshold: 0.5
      max_results: 5
      return_results: 3
      db_path: "./sqlite_db"
```

### 2. Load Adapters in Your Application

When your application starts, load the adapters from the configuration:

```python
from retrievers.adapters.registry import ADAPTER_REGISTRY

# Load configuration
with open('config.yaml', 'r') as file:
    config = yaml.safe_load(file)

# Register adapters from configuration
ADAPTER_REGISTRY.load_from_config(config)
```

### 3. Create Retrievers with Appropriate Domain Adapters

Use the retriever factory to create retrievers with the right domain adapter:

```python
from retrievers.base.base_retriever import RetrieverFactory

# Create SQLite retriever with QA domain adapter
retriever = RetrieverFactory.create_retriever(
    retriever_type="sqlite",
    config=config,
    datasource='sqlite',
    adapter_name='qa'
)

# Initialize the retriever
await retriever.initialize()

# Set the collection to use
await retriever.set_collection('qa_data')

# Use the retriever to get relevant context
results = await retriever.get_relevant_context(
    query="How do adapters work?"
)
```

## Extending the Architecture

### Creating a New Domain Adapter

To create a new domain adapter:

1. Create a new class that extends `DocumentAdapter`
2. Implement the required methods: `format_document()`, `extract_direct_answer()`, and `apply_domain_specific_filtering()`
3. Register the adapter with both the factory and registry

Example:

```python
from retrievers.adapters.domain_adapters import DocumentAdapter, DocumentAdapterFactory
from retrievers.adapters.registry import ADAPTER_REGISTRY

class CustomDomainAdapter(DocumentAdapter):
    """Custom domain adapter for specialized document handling"""
    
    def __init__(self, config: Dict[str, Any] = None, **kwargs):
        super().__init__(config=config, **kwargs)
        self.custom_threshold = self.config.get('custom_threshold', 0.6)
    
    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        # Custom document formatting logic
        item = {
            "raw_document": raw_doc,
            "content": raw_doc,
            "metadata": metadata.copy() if metadata else {},
            "custom_field": "custom value"
        }
        return item
    
    def extract_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        # Custom direct answer extraction logic
        if not context:
            return None
        return context[0].get("content", None)
    
    def apply_domain_specific_filtering(self, context_items: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        # Custom filtering logic
        filtered_items = [item for item in context_items 
                         if item.get("confidence", 0) >= self.custom_threshold]
        return filtered_items

# Register with the factory
DocumentAdapterFactory.register_adapter("custom", lambda **kwargs: CustomDomainAdapter(**kwargs))

# Register with the registry
ADAPTER_REGISTRY.register(
    adapter_type="retriever",
    datasource="sqlite",
    adapter_name="custom",
    factory_func=lambda **kwargs: CustomDomainAdapter(**kwargs)
)
```

### Creating a New Retriever Implementation

To create a new retriever implementation:

1. Create a new class that extends either `BaseRetriever`, `VectorDBRetriever`, or `SQLRetriever`
2. Implement the required methods:
   - `_get_datasource_name()`
   - `initialize()`
   - `close()`
   - `set_collection()`
   - `get_relevant_context()`
3. Register the retriever with the factory

Example:

```python
from retrievers.base.base_retriever import BaseRetriever, RetrieverFactory

class CustomRetriever(BaseRetriever):
    """Custom retriever implementation"""
    
    def __init__(self, config: Dict[str, Any], domain_adapter = None, **kwargs):
        super().__init__(config=config, domain_adapter=domain_adapter, **kwargs)
        self.custom_setting = self.datasource_config.get('custom_setting', 'default')
    
    def _get_datasource_name(self) -> str:
        return 'custom'
    
    async def initialize(self) -> None:
        await super().initialize()
        # Custom initialization logic
    
    async def close(self) -> None:
        await super().close()
        # Custom cleanup logic
    
    async def set_collection(self, collection_name: str) -> None:
        # Custom collection setting logic
        pass
    
    async def get_relevant_context(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        # Custom retrieval logic
        return []

# Register the retriever
RetrieverFactory.register_retriever("custom", CustomRetriever)
```