# Semantic Intent System Integration Plan

## Overview
This document outlines the integration of the semantic RAG intent system with the existing ORBIT retriever architecture.

## Architecture Integration

### 1. New Adapter Type: SemanticIntentAdapter

```python
# server/retrievers/adapters/intent/semantic_intent_adapter.py
class SemanticIntentAdapter(DocumentAdapter):
    """
    Adapter that uses semantic search to map user queries to pre-approved SQL templates
    """
    
    def __init__(self, config: Dict[str, Any], **kwargs):
        self.chroma_client = self._initialize_chroma_client(config)
        self.embedding_client = self._initialize_embedding_client(config)
        self.inference_client = self._initialize_inference_client(config)
        self.templates_collection = self._get_or_create_templates_collection()
        self.templates_loaded = False
        
    def get_search_conditions(self, query: str, collection_name: str) -> Dict[str, Any]:
        """
        Override to use semantic search instead of text matching
        """
        # Find best matching template
        best_template = self.find_best_template(query)
        
        if not best_template:
            raise ValueError("No matching query template found")
            
        # Extract parameters using LLM
        parameters = self.extract_parameters(query, best_template['template'])
        
        # Return formatted SQL with parameters
        return {
            "sql": best_template['template']['sql_template'],
            "params": parameters,
            "template_id": best_template['template']['id'],
            "confidence": best_template['similarity']
        }
        
    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format results using LLM to generate natural language responses
        """
        template = metadata.get('template', {})
        user_query = metadata.get('user_query', '')
        
        # Generate contextual response using LLM
        response = self.generate_response(user_query, raw_doc, template)
        
        return {
            "content": response,
            "metadata": metadata,
            "template_used": template.get('id', ''),
            "confidence": metadata.get('confidence', 0.0)
        }
```

### 2. Configuration Integration

```yaml
# config/adapters.yaml
adapters:
  - name: "semantic-intent-sql"
    type: "retriever"
    datasource: "postgres"  # or sqlite, mysql
    adapter: "semantic_intent"
    implementation: "retrievers.implementations.relational.SemanticIntentSQLRetriever"
    config:
      # Template management
      templates_file: "query_templates.yaml"
      templates_collection: "query_templates"
      
      # Embedding configuration
      embedding_provider: "ollama"
      embedding_model: "nomic-embed-text"
      embedding_url: "http://localhost:11434"
      
      # Inference configuration
      inference_provider: "ollama"
      inference_model: "gemma3:1b"
      inference_url: "http://localhost:11434"
      
      # ChromaDB configuration
      chroma_persist_directory: "./chroma_db"
      
      # Security settings
      confidence_threshold: 0.7
      max_results: 100
      query_timeout: 15000
      approved_by_admin: true
      
      # Performance settings
      cache_ttl: 1800
      enable_query_monitoring: true
```

### 3. Retriever Implementation

```python
# server/retrievers/implementations/relational/semantic_intent_sql_retriever.py
class SemanticIntentSQLRetriever(AbstractSQLRetriever):
    """
    SQL retriever that uses semantic intent understanding
    """
    
    def __init__(self, config: Dict[str, Any], **kwargs):
        super().__init__(config=config, **kwargs)
        
        # Initialize semantic intent adapter
        if self.domain_adapter is None:
            self.domain_adapter = SemanticIntentAdapter(config.get('config', {}))
            
        # Load templates on initialization
        self._load_templates()
        
    def _load_templates(self):
        """Load query templates into ChromaDB"""
        templates_file = self.datasource_config.get('templates_file')
        if templates_file and self.domain_adapter:
            self.domain_adapter.populate_templates(templates_file)
            
    async def get_relevant_context(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Override to use semantic intent matching
        """
        try:
            # Use semantic adapter to get SQL and parameters
            search_config = self.domain_adapter.get_search_conditions(query, self.collection)
            
            # Execute the templated query
            results = await self.execute_query(
                search_config['sql'], 
                search_config['params']
            )
            
            # Format results with natural language response
            formatted_results = []
            for result in results:
                metadata = {
                    'template': search_config.get('template_id'),
                    'confidence': search_config.get('confidence'),
                    'user_query': query
                }
                
                formatted_result = self.domain_adapter.format_document(
                    json.dumps(result), 
                    metadata
                )
                formatted_results.append(formatted_result)
                
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error in semantic intent retrieval: {str(e)}")
            return []
```

### 4. Service Factory Integration

```python
# server/services/service_factory.py (additions)
async def _initialize_semantic_intent_service(self, app: FastAPI) -> None:
    """Initialize semantic intent service components"""
    
    # Initialize ChromaDB for templates
    chroma_config = self.config.get('semantic_intent', {})
    
    if chroma_config.get('enabled', False):
        from services.semantic_intent_service import SemanticIntentService
        
        app.state.semantic_intent_service = SemanticIntentService(
            config=self.config,
            mongodb_service=app.state.mongodb_service
        )
        
        await app.state.semantic_intent_service.initialize()
        logger.info("Semantic Intent Service initialized successfully")
```

## Implementation Steps

### Phase 1: Core Integration
1. Create `SemanticIntentAdapter` class
2. Implement `SemanticIntentSQLRetriever` 
3. Add configuration support in `adapters.yaml`
4. Register adapter with `ADAPTER_REGISTRY`

### Phase 2: Enhanced Features
1. Template management UI/API
2. Template validation and approval workflow
3. Query performance monitoring
4. Response caching and optimization

### Phase 3: Advanced Features
1. Multi-language support
2. Custom embedding models
3. Query suggestion system
4. Analytics and usage tracking

## Migration Strategy

### Gradual Migration
1. **Coexistence**: Run both systems simultaneously
2. **A/B Testing**: Route queries to different adapters
3. **Fallback**: Fall back to traditional adapters if semantic fails
4. **Monitoring**: Compare performance and accuracy

### Configuration Example
```yaml
general:
  adapter: "semantic-intent-sql"  # Primary adapter
  fallback_adapter: "qa-sql"      # Fallback adapter

adapters:
  - name: "semantic-intent-sql"
    # ... semantic intent configuration
  - name: "qa-sql" 
    # ... traditional QA configuration
```

## Benefits of This Integration

1. **Seamless Integration**: Works with existing architecture
2. **Security Maintained**: Templates ensure query safety
3. **Flexibility**: Easy to add new query patterns
4. **Performance**: Semantic search + SQL execution
5. **Natural Language**: Conversational query interface
6. **Monitoring**: Full integration with existing validation

## Technical Considerations

1. **Dependencies**: ChromaDB, Ollama, additional Python packages
2. **Performance**: Vector search overhead vs. improved UX
3. **Scaling**: ChromaDB scaling for large template sets
4. **Maintenance**: Template management and updates
5. **Fallback**: Handling semantic search failures

This integration provides a powerful bridge between natural language queries and structured database operations while maintaining the security and performance characteristics of the existing system. 