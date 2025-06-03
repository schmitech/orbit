# Adapter-Based API Key Implementation Guide

## Step-by-Step Implementation

### 1. Update API Key Service

First, enhance the API key service to handle adapter references:

```python
# server/services/api_key_service.py - ENHANCED VERSION

class ApiKeyService:
    async def validate_api_key(self, api_key: str) -> Tuple[bool, Optional[str], Optional[ObjectId]]:
        """
        Validate API key and return adapter name instead of collection name
        
        Returns:
            Tuple of (is_valid, adapter_name, system_prompt_id)
        """
        key_doc = await self.mongodb.find_one(self.collection_name, {"api_key": api_key})
        
        if not key_doc or key_doc.get("active") is False:
            return False, None, None
            
        # NEW: Try adapter-based approach first
        adapter_name = key_doc.get("adapter_name")
        if adapter_name:
            # Validate adapter exists in configuration
            if self._validate_adapter_exists(adapter_name):
                return True, adapter_name, key_doc.get("system_prompt_id")
            else:
                logger.warning(f"API key references non-existent adapter: {adapter_name}")
                return False, None, None
            
        # BACKWARD COMPATIBILITY: Fallback to collection-based approach
        collection_name = key_doc.get("collection_name")
        if collection_name:
            adapter_name = self._map_collection_to_adapter(collection_name)
            return True, adapter_name, key_doc.get("system_prompt_id")
            
        return False, None, None
    
    def _validate_adapter_exists(self, adapter_name: str) -> bool:
        """Check if adapter exists in configuration"""
        adapters = self.config.get('adapters', [])
        return any(cfg.get('name') == adapter_name for cfg in adapters)
    
    def _map_collection_to_adapter(self, collection_name: str) -> str:
        """Map legacy collection names to adapter names"""
        # Get current default adapter from config
        default_adapter = self.config.get('general', {}).get('adapter', 'qa-sql')
        
        # Optional: Implement specific collection mappings
        collection_mappings = {
            'legal_docs': 'legal-documents-sql',
            'support_kb': 'support-kb-vector',
            'financial_data': 'financial-elastic'
        }
        
        return collection_mappings.get(collection_name, default_adapter)

    async def create_api_key(
        self, 
        adapter_name: str,  # CHANGED: adapter instead of collection
        client_name: str, 
        notes: Optional[str] = None,
        system_prompt_id: Optional[ObjectId] = None
    ) -> Dict[str, Any]:
        """Create API key with adapter association"""
        
        # Validate adapter exists
        if not self._validate_adapter_exists(adapter_name):
            raise HTTPException(
                status_code=400, 
                detail=f"Adapter '{adapter_name}' not found in configuration"
            )
        
        api_key = self._generate_api_key()
        now = datetime.now(UTC)
        
        key_doc = {
            "api_key": api_key,
            "adapter_name": adapter_name,  # NEW: Store adapter reference
            "client_name": client_name,
            "notes": notes,
            "active": True,
            "created_at": now
        }
        
        if system_prompt_id:
            key_doc["system_prompt_id"] = system_prompt_id
        
        await self.mongodb.insert_one(self.collection_name, key_doc)
        
        return {
            "api_key": api_key,
            "adapter_name": adapter_name,
            "client_name": client_name,
            "notes": notes,
            "active": True,
            "created_at": now.timestamp(),
            "system_prompt_id": str(system_prompt_id) if system_prompt_id else None
        }
```

### 2. Create Adapter-Aware Retriever Service

```python
# server/services/adapter_retriever_service.py - NEW FILE

from typing import Dict, Any, Optional
import logging
from retrievers.base.base_retriever import RetrieverFactory
from retrievers.adapters.registry import ADAPTER_REGISTRY

logger = logging.getLogger(__name__)

class AdapterRetrieverService:
    """Service for creating retrievers based on adapter configurations"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.adapters_config = config.get('adapters', [])
        self._retriever_cache = {}  # Cache retrievers for performance
    
    async def get_retriever_for_adapter(self, adapter_name: str):
        """Get or create retriever for specified adapter"""
        
        # Check cache first
        if adapter_name in self._retriever_cache:
            return self._retriever_cache[adapter_name]
        
        adapter_config = self._get_adapter_config(adapter_name)
        if not adapter_config:
            raise ValueError(f"Adapter '{adapter_name}' not found in configuration")
        
        # Handle different adapter types
        adapter_type = adapter_config.get('type', 'retriever')
        
        if adapter_type == 'multi_retriever':
            retriever = await self._create_multi_source_retriever(adapter_config)
        else:
            retriever = await self._create_single_source_retriever(adapter_config)
        
        # Cache the retriever
        self._retriever_cache[adapter_name] = retriever
        return retriever
    
    async def _create_single_source_retriever(self, adapter_config: Dict[str, Any]):
        """Create a single-source retriever"""
        datasource = adapter_config.get('datasource')
        implementation = adapter_config.get('implementation')
        config = adapter_config.get('config', {})
        
        # Merge adapter config with global datasource config
        datasource_config = self.config.get('datasources', {}).get(datasource, {})
        merged_config = {**datasource_config, **config}
        
        # Create retriever using the implementation class
        if implementation:
            # Dynamic import and instantiation
            module_path, class_name = implementation.rsplit('.', 1)
            module = __import__(module_path, fromlist=[class_name])
            retriever_class = getattr(module, class_name)
            
            retriever = retriever_class(
                config=self.config,
                datasource_config=merged_config
            )
        else:
            # Use factory method
            retriever = RetrieverFactory.create_retriever(
                retriever_type=datasource,
                config=self.config,
                datasource_config=merged_config
            )
        
        await retriever.initialize()
        return retriever
    
    async def _create_multi_source_retriever(self, adapter_config: Dict[str, Any]):
        """Create a multi-source retriever that combines multiple adapters"""
        sources = adapter_config.get('sources', [])
        config = adapter_config.get('config', {})
        
        # Create individual retrievers for each source
        source_retrievers = []
        for source in sources:
            source_adapter = source.get('adapter')
            weight = source.get('weight', 1.0)
            
            retriever = await self.get_retriever_for_adapter(source_adapter)
            source_retrievers.append({
                'retriever': retriever,
                'weight': weight,
                'adapter_name': source_adapter
            })
        
        # Create multi-source retriever wrapper
        multi_retriever = MultiSourceRetriever(
            source_retrievers=source_retrievers,
            merge_strategy=config.get('merge_strategy', 'weighted_confidence'),
            max_total_results=config.get('max_total_results', 10)
        )
        
        return multi_retriever
    
    def _get_adapter_config(self, adapter_name: str) -> Optional[Dict[str, Any]]:
        """Get adapter configuration by name"""
        return next(
            (cfg for cfg in self.adapters_config if cfg.get('name') == adapter_name), 
            None
        )
    
    async def close_all_retrievers(self):
        """Close all cached retrievers"""
        for retriever in self._retriever_cache.values():
            if hasattr(retriever, 'close'):
                await retriever.close()
        self._retriever_cache.clear()


class MultiSourceRetriever:
    """Retriever that combines results from multiple source adapters"""
    
    def __init__(self, source_retrievers, merge_strategy='weighted_confidence', max_total_results=10):
        self.source_retrievers = source_retrievers
        self.merge_strategy = merge_strategy
        self.max_total_results = max_total_results
    
    async def get_relevant_context(self, query: str, **kwargs):
        """Get combined results from all source retrievers"""
        all_results = []
        
        # Get results from each source
        for source in self.source_retrievers:
            retriever = source['retriever']
            weight = source['weight']
            adapter_name = source['adapter_name']
            
            try:
                results = await retriever.get_relevant_context(query, **kwargs)
                
                # Apply weight to confidence scores
                for result in results:
                    if 'confidence' in result:
                        result['confidence'] *= weight
                    result['source_adapter'] = adapter_name
                
                all_results.extend(results)
                
            except Exception as e:
                logger.warning(f"Error from adapter {adapter_name}: {str(e)}")
                continue
        
        # Merge and sort results
        if self.merge_strategy == 'weighted_confidence':
            all_results.sort(key=lambda x: x.get('confidence', 0), reverse=True)
        
        # Return top results
        return all_results[:self.max_total_results]
```

### 3. Update CLI Commands

```python
# bin/orbit.py - ENHANCED VERSION

class OrbitCLI:
    def _add_key_commands(self, subparsers):
        """Enhanced API key management commands"""
        key_parser = subparsers.add_parser('key', help='API key management')
        key_subparsers = key_parser.add_subparsers(dest='key_command')
        
        # Enhanced create command
        create_parser = key_subparsers.add_parser('create', help='Create a new API key')
        create_parser.add_argument('--adapter', required=True, 
                                 help='Adapter name to associate with the key')
        create_parser.add_argument('--name', required=True, help='Client name')
        create_parser.add_argument('--notes', help='Optional notes')
        create_parser.add_argument('--prompt-id', help='System prompt ID to associate')
        create_parser.add_argument('--prompt-file', help='Path to prompt file')
        create_parser.add_argument('--prompt-name', help='Name for new prompt')
        
        # BACKWARD COMPATIBILITY: Keep collection-based creation
        create_parser.add_argument('--collection', 
                                 help='[DEPRECATED] Collection name (use --adapter instead)')
        
        # List adapters command
        list_adapters_parser = key_subparsers.add_parser('list-adapters', 
                                                       help='List available adapters')
        
    async def create_api_key_enhanced(self, args):
        """Enhanced API key creation with adapter support"""
        api_manager = self.get_api_manager(args.server_url)
        
        # Determine adapter name
        if args.adapter:
            adapter_name = args.adapter
        elif args.collection:
            # Backward compatibility - map collection to adapter
            print("⚠️  WARNING: --collection is deprecated. Use --adapter instead.")
            adapter_name = self._map_collection_to_adapter(args.collection)
            print(f"📍 Mapping collection '{args.collection}' to adapter '{adapter_name}'")
        else:
            raise ValueError("Either --adapter or --collection must be specified")
        
        # Create the API key
        result = api_manager.create_api_key_with_adapter(
            adapter_name=adapter_name,
            client_name=args.name,
            notes=args.notes,
            prompt_id=args.prompt_id,
            prompt_name=args.prompt_name,
            prompt_file=args.prompt_file
        )
        
        print(json.dumps(result, indent=2))
        print(f"\n✅ API key created successfully for adapter '{adapter_name}'")
        return 0

    def _map_collection_to_adapter(self, collection_name: str) -> str:
        """Map legacy collection names to adapter names"""
        mappings = {
            'legal': 'legal-documents-sql',
            'support': 'support-kb-vector',
            'docs': 'qa-vector',
            'city': 'qa-sql'
        }
        return mappings.get(collection_name, 'qa-sql')  # Default adapter
```

### 4. Enhanced Configuration Examples

```yaml
# config.yaml - ENHANCED ADAPTER SECTION

adapters:
  # Legal Department - PostgreSQL with row-level security
  - name: "legal-documents-sql"
    type: "retriever"
    datasource: "postgres"
    adapter: "qa"
    implementation: "retrievers.implementations.qa.QAPostgresRetriever"
    config:
      confidence_threshold: 0.4
      max_results: 10
      return_results: 5
      database: "legal_db"
      schema: "documents"
      table: "case_documents"
      # Security: Only show documents for user's department
      security_filter: "department_id = {user.department_id}"

  # Marketing Team - Vector search on content library
  - name: "marketing-content-vector"
    type: "retriever"
    datasource: "chroma"
    adapter: "qa"
    implementation: "retrievers.implementations.qa.QAChromaRetriever"
    config:
      confidence_threshold: 0.3
      max_results: 8
      return_results: 4
      collection: "marketing_assets"
      embedding_provider: "openai"
      # Custom context for marketing queries
      context_enhancement: true

  # Customer Support - Multi-source knowledge base
  - name: "support-knowledge-multi"
    type: "multi_retriever"
    sources:
      - adapter: "support-faq-sql"
        weight: 0.7
      - adapter: "support-docs-vector"
        weight: 0.3
    config:
      merge_strategy: "weighted_confidence"
      max_total_results: 8
      deduplicate_results: true

  # Development Environment - SQLite for testing
  - name: "dev-qa-sql"
    type: "retriever"
    datasource: "sqlite"
    adapter: "qa"
    implementation: "retrievers.implementations.qa.QASSQLRetriever"
    config:
      confidence_threshold: 0.2  # Lower threshold for dev
      max_results: 15
      return_results: 8
      db_path: "dev_data/qa_test.db"

general:
  adapter: "qa-sql"  # Default adapter for backward compatibility
```

### 5. Migration Script

```python
# scripts/migrate_api_keys.py - NEW FILE

import asyncio
import yaml
from services.mongodb_service import MongoDBService
from services.api_key_service import ApiKeyService

class ApiKeyMigration:
    def __init__(self, config_path: str):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.mongodb_service = MongoDBService(self.config)
        self.api_key_service = ApiKeyService(self.config, self.mongodb_service)
    
    async def migrate_collection_to_adapter(self):
        """Migrate existing collection-based API keys"""
        await self.mongodb_service.initialize()
        
        # Collection to adapter mappings
        mappings = {
            'legal': 'legal-documents-sql',
            'support': 'support-kb-vector', 
            'docs': 'qa-vector',
            'city': 'qa-sql'
        }
        
        # Find all API keys without adapter_name
        legacy_keys = await self.mongodb_service.find_many(
            "api_keys",
            {"adapter_name": {"$exists": False}}
        )
        
        print(f"Found {len(legacy_keys)} legacy API keys to migrate")
        
        for key_doc in legacy_keys:
            collection_name = key_doc.get("collection_name", "")
            adapter_name = mappings.get(collection_name, "qa-sql")
            
            # Update the document
            result = await self.mongodb_service.update_one(
                "api_keys",
                {"_id": key_doc["_id"]},
                {"$set": {"adapter_name": adapter_name}}
            )
            
            if result:
                print(f"✅ Migrated API key {key_doc['api_key'][:12]}... "
                      f"from collection '{collection_name}' to adapter '{adapter_name}'")
            else:
                print(f"❌ Failed to migrate API key {key_doc['api_key'][:12]}...")

if __name__ == "__main__":
    async def main():
        migration = ApiKeyMigration("config.yaml")
        await migration.migrate_collection_to_adapter()
    
    asyncio.run(main())
```

## Usage Examples

### Creating Adapter-Based API Keys

```bash
# Create API key for legal team with PostgreSQL adapter
orbit key create --adapter legal-documents-sql --name "Legal Team" \
  --notes "Access to case documents and precedents"

# Create API key for support team with multi-source adapter
orbit key create --adapter support-knowledge-multi --name "Support Team" \
  --prompt-file prompts/support.txt --prompt-name "Support Assistant"

# Create API key for development with SQLite adapter
orbit key create --adapter dev-qa-sql --name "Development Testing"

# List available adapters
orbit key list-adapters
```

### Backward Compatibility

```bash
# Legacy command still works
orbit key create --collection legal --name "Legal Dept"
# ⚠️  WARNING: --collection is deprecated. Use --adapter instead.
# 📍 Mapping collection 'legal' to adapter 'legal-documents-sql'
```
