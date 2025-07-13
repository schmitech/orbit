# Base RAG System Architecture

This directory now contains a reusable base RAG system that can be extended for any domain-specific implementation.

## Architecture Overview

The system is built around a modular architecture with clear separation of concerns:

```
base_rag_system.py          # Core reusable functionality
├── BaseRAGSystem           # Main orchestrator class
├── BaseEmbeddingClient     # Abstract embedding interface
├── BaseInferenceClient     # Abstract inference interface
├── BaseDatabaseClient      # Abstract database interface
├── BaseParameterExtractor  # Abstract parameter extraction
└── BaseResponseGenerator   # Abstract response generation

customer_order_rag.py      # PostgreSQL-specific implementation
├── SemanticRAGSystem       # Extends BaseRAGSystem
├── OllamaEmbeddingClient   # Implements BaseEmbeddingClient
├── OllamaInferenceClient   # Implements BaseInferenceClient
├── PostgreSQLDatabaseClient # Implements BaseDatabaseClient
├── PostgreSQLParameterExtractor # Implements BaseParameterExtractor
└── PostgreSQLResponseGenerator  # Implements BaseResponseGenerator

example_mysql_rag_system.py # Example MySQL implementation
├── MySQLRAGSystem          # Extends BaseRAGSystem
├── MySQLDatabaseClient     # Implements BaseDatabaseClient
├── MySQLParameterExtractor # Implements BaseParameterExtractor
└── MySQLResponseGenerator  # Implements BaseResponseGenerator
```

## Key Benefits

1. **Reusability**: Core RAG functionality is shared across all implementations
2. **Extensibility**: Easy to add new database types or domains
3. **Maintainability**: Changes to core logic benefit all implementations
4. **Consistency**: All implementations follow the same interface
5. **Flexibility**: Each implementation can customize behavior as needed

## Base Classes

### BaseRAGSystem
The main orchestrator that handles:
- ChromaDB template storage and retrieval
- Template matching and ranking
- Query processing pipeline
- Conversation management
- Configuration management

### BaseEmbeddingClient
Abstract interface for embedding generation:
- `get_embedding(text: str) -> List[float]`

### BaseInferenceClient
Abstract interface for text generation:
- `generate_response(prompt: str, system_prompt: str = "", temperature: float = 0.7) -> str`

### BaseDatabaseClient
Abstract interface for database operations:
- `execute_query(sql: str, params: Dict[str, Any] = None) -> Tuple[List[Dict], Optional[str]]`

### BaseParameterExtractor
Abstract interface for parameter extraction:
- `extract_parameters(user_query: str, template: Dict) -> Dict[str, Any]`
- `validate_parameters(parameters: Dict[str, Any], template: Dict) -> Tuple[bool, List[str]]`

### BaseResponseGenerator
Abstract interface for response generation:
- `generate_response(user_query: str, results: List[Dict], template: Dict, error: Optional[str] = None) -> str`

## Creating a New Domain Implementation

To create a new domain-specific RAG system:

1. **Create domain-specific client classes**:
   ```python
   class MyDatabaseClient(BaseDatabaseClient):
       def execute_query(self, sql: str, params: Dict[str, Any] = None):
           # Implement database-specific logic
           pass
   
   class MyParameterExtractor(BaseParameterExtractor):
       def extract_parameters(self, user_query: str, template: Dict):
           # Implement domain-specific parameter extraction
           pass
   
   class MyResponseGenerator(BaseResponseGenerator):
       def generate_response(self, user_query: str, results: List[Dict], template: Dict, error: Optional[str] = None):
           # Implement domain-specific response generation
           pass
   ```

2. **Create the main RAG system class**:
   ```python
   class MyRAGSystem(BaseRAGSystem):
       def __init__(self, chroma_persist_directory: str = "./my_chroma_db"):
           # Initialize domain-specific clients
           embedding_client = OllamaEmbeddingClient()  # Reuse or create new
           inference_client = OllamaInferenceClient()  # Reuse or create new
           db_client = MyDatabaseClient()
           parameter_extractor = MyParameterExtractor(inference_client)
           response_generator = MyResponseGenerator(inference_client)
           
           # Initialize base class
           super().__init__(
               chroma_persist_directory=chroma_persist_directory,
               embedding_client=embedding_client,
               inference_client=inference_client,
               db_client=db_client,
               parameter_extractor=parameter_extractor,
               response_generator=response_generator
           )
       
       def rerank_templates(self, templates: List[Dict], user_query: str) -> List[Dict]:
           # Implement domain-specific template ranking
           pass
       
       def print_configuration(self):
           # Implement domain-specific configuration display
           pass
   ```

3. **Use the system**:
   ```python
   # Initialize your domain-specific RAG system
   my_rag = MyRAGSystem()
   
   # Load templates
   my_rag.populate_chromadb("my_templates.yaml", clear_first=True)
   
   # Process queries
   result = my_rag.process_query("Your natural language query")
   print(result['response'])
   ```

## Example Implementations

### PostgreSQL RAG System (`customer_order_rag.py`)
- Full-featured implementation with advanced parameter extraction
- PostgreSQL-specific database client with proper error handling
- Enhanced response generation with detailed formatting
- Domain-specific template ranking

### MySQL RAG System (`example_mysql_rag_system.py`)
- Simplified example showing how to extend the base system
- MySQL-specific database client
- Basic parameter extraction and response generation
- Demonstrates reusability of Ollama clients

## Configuration

All implementations use environment variables for configuration:

```bash
# Ollama Configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
OLLAMA_INFERENCE_MODEL=gemma3:1b

# PostgreSQL Configuration
DATASOURCE_POSTGRES_HOST=localhost
DATASOURCE_POSTGRES_PORT=5432
DATASOURCE_POSTGRES_DATABASE=orbit
DATASOURCE_POSTGRES_USERNAME=postgres
DATASOURCE_POSTGRES_PASSWORD=postgres
DATASOURCE_POSTGRES_SSL_MODE=require

# MySQL Configuration (for MySQL implementation)
DATASOURCE_MYSQL_HOST=localhost
DATASOURCE_MYSQL_PORT=3306
DATASOURCE_MYSQL_DATABASE=orbit
DATASOURCE_MYSQL_USERNAME=root
DATASOURCE_MYSQL_PASSWORD=
```

## Usage Examples

### PostgreSQL RAG System
```python
from customer_order_rag import SemanticRAGSystem

# Initialize
rag = SemanticRAGSystem()

# Load templates
rag.populate_chromadb("query_templates.yaml", clear_first=True)

# Query
result = rag.process_query("What did customer 123 buy last week?")
print(result['response'])
```

### MySQL RAG System
```python
from example_mysql_rag_system import MySQLRAGSystem

# Initialize
mysql_rag = MySQLRAGSystem()

# Load templates
mysql_rag.populate_chromadb("mysql_templates.yaml", clear_first=True)

# Query
result = mysql_rag.process_query("Show me user 456's recent activity")
print(result['response'])
```

## Extending the System

The base system is designed to be easily extensible:

1. **New Database Types**: Implement `BaseDatabaseClient` for any database
2. **New Embedding Models**: Implement `BaseEmbeddingClient` for different embedding services
3. **New Inference Models**: Implement `BaseInferenceClient` for different LLM providers
4. **Custom Parameter Extraction**: Implement `BaseParameterExtractor` for domain-specific logic
5. **Custom Response Generation**: Implement `BaseResponseGenerator` for specialized formatting

This architecture provides a solid foundation for building RAG systems across different domains while maintaining consistency and reusability. 