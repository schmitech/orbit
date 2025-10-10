# Retriever Architecture

This document describes the architecture of the retriever system, which is responsible for retrieving relevant documents from various data sources and adapting them to specific domains.

## Core Components

### 1. RetrieverFactory
The factory pattern implementation that creates retriever instances based on configuration. Currently supports:
- ChromaRetriever
- SQLiteRetriever

### 2. BaseRetriever
Abstract base class that defines the retriever interface:
- `initialize()`: Initialize the retriever
- `retrieve()`: Retrieve documents based on a query
- `apply_domain_filtering()`: Apply domain-specific filtering to results

### 3. DocumentAdapterFactory
Factory for creating domain-specific document adapters. Currently supports:
- "qa" adapter (ChromaQAAdapter)
- "generic" adapter (GenericDocumentAdapter)

### 4. DocumentAdapter
Abstract base class for document adapters that defines the interface:
- `format_document()`: Format raw documents into domain-specific format
- `extract_direct_answer()`: Extract direct answers from context
- `apply_domain_specific_filtering()`: Apply domain-specific filtering

## Extending the Architecture

### Adding a New Retriever

1. Create a new retriever class that inherits from `BaseRetriever`:
```python
from retrievers.base.base_retriever import BaseRetriever

class NewRetriever(BaseRetriever):
    def __init__(self, config, domain_adapter, **kwargs):
        super().__init__(config, domain_adapter)
        # Initialize your retriever
        
    def initialize(self):
        # Initialize your retriever
        
    def retrieve(self, query, collection_name, **kwargs):
        # Implement retrieval logic
        
    def apply_domain_filtering(self, context_items, query):
        # Delegate to domain adapter
        return self.domain_adapter.apply_domain_filtering(context_items, query)
```

2. Register the retriever in `retrievers/__init__.py`:
```python
from retrievers.base.base_retriever import RetrieverFactory
from .implementations.new_retriever import NewRetriever

RetrieverFactory.register_retriever("new", NewRetriever)
```

### Adding a New Document Adapter

1. Create a new adapter class that inherits from `DocumentAdapter`:
```python
from adapters.base import DocumentAdapter

class NewDomainAdapter(DocumentAdapter):
    def __init__(self, **kwargs):
        # Initialize your adapter
        
    def format_document(self, raw_doc, metadata):
        # Format documents for your domain
        
    def extract_direct_answer(self, context):
        # Extract direct answers
        
    def apply_domain_specific_filtering(self, context_items, query):
        # Apply domain-specific filtering
```

2. Create a factory function:
```python
def create_new_adapter(config: Dict[str, Any]) -> NewDomainAdapter:
    # Extract configuration
    return NewDomainAdapter(**adapter_params)
```

3. Register the adapter in your module:
```python
from adapters.factory import DocumentAdapterFactory

DocumentAdapterFactory.register_adapter("new_domain", create_new_adapter)
```

## Configuration

Retrievers and adapters are configured through the main configuration file (`config.yaml`). Example:

```yaml
general:
  datasource_provider: chroma  # or sqlite, or your new retriever
  verbose: true

datasources:
  chroma:
    domain_adapter: qa  # or generic, or your new adapter
    confidence_threshold: 0.85
    relevance_threshold: 0.7
    adapter_params:
      verbose: true
```

## Best Practices

1. **Error Handling**: Always implement proper error handling in your retrievers and adapters.
2. **Logging**: Use the provided logging system to track important events and debug issues.
3. **Configuration**: Make your components configurable through the main config file.
4. **Testing**: Write unit tests for your new components.
5. **Documentation**: Document your new components and their configuration options.

## Example Usage

```python
from retrievers.base.base_retriever import RetrieverFactory

# Create a retriever instance
retriever = RetrieverFactory.create_retriever(
    retriever_type="chroma",
    config=config,
    domain_adapter_type="qa"
)

# Initialize the retriever
await retriever.initialize()

# Retrieve documents
results = await retriever.retrieve(
    query="What is the capital of France?",
    collection_name="my_collection"
)
```

## Troubleshooting

Common issues and solutions:

1. **Adapter not found**: Ensure your adapter is properly registered in the factory.
2. **Configuration errors**: Check your config.yaml for correct settings.
3. **Connection issues**: Verify that your data source (ChromaDB, SQLite, etc.) is running and accessible.
4. **Performance issues**: Consider implementing caching or optimizing your retrieval logic.
