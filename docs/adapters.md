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

## Architecture Strengths

This adapter architecture provides several significant advantages:

1. **Clear Separation of Concerns**
   - Base retriever classes handle core functionality (retrieval mechanisms)
   - Domain adapters handle domain-specific document processing and formatting
   - Registry manages component lifecycles and relationships
   - Factory creates properly configured components on demand

2. **Extensibility**
   - New retrievers can be added without modifying existing ones
   - Domain adapters make it easy to support new data types and use cases
   - The registry handles dynamic loading and instantiation of components
   - Extending the system to new domains requires minimal changes to core code

3. **Dependency Inversion**
   - High-level components depend on abstractions, not implementation details
   - Interface-based design through abstract base classes ensures loose coupling
   - Components are easily swappable without breaking dependent code
   - Testing is simplified through the ability to mock or substitute implementations

4. **Configuration-driven**
   - Clean YAML configuration separates behavior from code
   - Dynamic loading of components based on configuration
   - Configurable thresholds and behavior parameters for each component
   - Business logic can be adjusted without code changes

5. **Lazy Loading**
   - Efficient resource usage by only instantiating components when needed
   - Makes it easy to handle heavyweight components like database connections
   - Reduces startup time and memory usage for unused components

The hierarchical structure (type → datasource → adapter name) provides clear organization and avoids naming conflicts while the registry pattern centralizes component management. This architecture scales well as the system grows in complexity.

## Using the Architecture

### 1. Configure Your Adapters

In your `config.yaml` file, define your adapters using the structure:

```yaml
adapters:
  - name: "qa-sqlite"
    type: "retriever"
    datasource: "sqlite"
    adapter: "qa"
    implementation: "retrievers.implementations.qa_sqlite_retriever.QASqliteRetriever"
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

# Orbit Adapter Roadmap

## Current Adapters
Orbit currently supports two main types of adapters:

- SQL retriever for question answering
- Vector database retriever for question answering

Each adapter implements the same core interface but is optimized for its specific database technology.

## Future Adapter Roadmap

### Enterprise Data Integration Adapters
Connect Orbit with enterprise systems to provide AI capabilities on organizational data.

| Adapter | Description |
|---------|-------------|
| SAP Connector | Integrate with SAP ERP systems for business process intelligence |
| Salesforce Adapter | Connect with CRM data to enhance customer interactions |
| Microsoft 365 Integration | Access SharePoint, Teams, and Office data for internal knowledge |
| Enterprise Database Connectors | Support for Teradata, Oracle, SQL Server to query enterprise data |

### Specialized Knowledge Adapters
Domain-specific adapters for industries with specialized requirements.

| Adapter | Description |
|---------|-------------|
| Legal Document Analyzer | Process legal documents with citation support and compliance features |
| Financial Data Adapter | Handle financial reports with regulatory compliance and data security |
| Healthcare Knowledge Base | Process medical literature and patient data with HIPAA compliance |
| Scientific Research Connector | Access and query scientific papers and research databases |

### Multimodal Adapters
Extend Orbit beyond text to handle various data types.

| Adapter | Description |
|---------|-------------|
| Document OCR Processor | Extract text from images and documents for analysis |
| Audio Transcription | Convert meeting recordings and calls to searchable text |
| Video Content Analysis | Extract insights from video content |
| Chart/Graph Interpreter | Understand and explain visual data representations |

### Real-time Adapters
Connect to live data sources for up-to-date intelligence.

| Adapter | Description |
|---------|-------------|
| Market Data Connector | Access real-time financial market data |
| Customer Support Integration | Connect to live customer service platforms |
| IoT Sensor Data | Process information from connected devices and sensors |
| Social Media Monitor | Track brand mentions and sentiment in real time |

### Advanced Analytics Adapters
Add sophisticated analytical capabilities to Orbit.

| Adapter | Description |
|---------|-------------|
| Time-series Forecasting | Predict future trends based on historical data |
| BI Dashboard Connector | Integrate with business intelligence platforms |
| Anomaly Detection | Identify unusual patterns in operational data |
| Sentiment Analysis | Analyze customer feedback and communications |

### Workflow Automation Adapters
Integrate AI capabilities into business processes.

| Adapter | Description |
|---------|-------------|
| Business Process Modeling | Model and optimize workflows with AI assistance |
| Approval Workflow Integration | Streamline document and request approvals |
| Document Generation | Create reports and documents from templates and data |
| Task Management | AI-assisted project and task management |

## Implementation Guidelines

Each new adapter should follow Orbit's adapter pattern:

```yaml
- name: "adapter-name"
  type: "retriever"
  datasource: "data-source-type"
  adapter: "adapter-type"
  implementation: "path.to.implementation.Class"
  config:
    # Adapter-specific configuration options
    confidence_threshold: 0.5
    max_results: 5
    return_results: 3
    # Other adapter-specific settings
```

## Development Priorities

1. Focus first on enterprise integrations that unlock organizational data
2. Prioritize industry-specific adapters based on customer demand
3. Develop multimodal capabilities to handle diverse data types
4. Add real-time adapters for time-sensitive applications
5. Implement advanced analytics for deeper insights
6. Create workflow automation to streamline business processes

## Contributing

Interested in developing a new adapter? Please follow these steps:
1. Check the roadmap to see if your adapter is already planned
2. Open an issue to discuss the adapter requirements
3. Follow the adapter implementation guidelines
4. Submit a pull request with thorough documentation