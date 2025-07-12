# Adapter Migration Strategy: From Collection-Based to Adapter-Based API Keys

## Overview

This document outlines the strategy for migrating from collection-name-based API key associations to a flexible adapter-based architecture that provides better flexibility, multi-source capabilities, and future-proofing.

## Current Architecture Issues

### Current Limitations
- API keys are tied to single collection names
- No separation between storage type and data organization
- Limited flexibility for multi-tenant or multi-source scenarios
- Tight coupling between API keys and specific storage implementations

### Current Flow
```
API Key → Collection Name → Hard-coded Storage Type
```

## Proposed Architecture

### New Flexible Flow
```
API Key → Adapter Configuration → Dynamic Storage + Settings
```

### Benefits
1. **Storage Agnostic**: API keys work with any configured adapter
2. **Multi-Source**: One API key can access multiple data sources
3. **Configuration-Driven**: All settings contained in adapter config
4. **Tenant Isolation**: Better support for multi-tenant scenarios
5. **Future-Proof**: Easy to add new storage types

## Implementation Strategy

### Phase 1: Database Schema Enhancement

#### Add Adapter Reference to API Keys
```javascript
// MongoDB Document Structure (Enhanced)
{
  "_id": ObjectId("..."),
  "api_key": "orbit_abc123...",
  "client_name": "Legal Department",
  "adapter_name": "legal-documents-sql",  // NEW: Reference to adapter config
  "collection_name": "legal_docs",        // DEPRECATED: Keep for backward compatibility
  "system_prompt_id": ObjectId("..."),
  "active": true,
  "created_at": ISODate("..."),
  "notes": "Legal team access to case documents"
}
```

### Phase 2: Service Layer Updates

#### Enhanced API Key Service
```python
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
            
        # Try new adapter-based approach first
        adapter_name = key_doc.get("adapter_name")
        if adapter_name:
            return True, adapter_name, key_doc.get("system_prompt_id")
            
        # Fallback to legacy collection-based approach
        collection_name = key_doc.get("collection_name")
        if collection_name:
            # Convert legacy collection to default adapter
            adapter_name = self._get_default_adapter_for_collection(collection_name)
            return True, adapter_name, key_doc.get("system_prompt_id")
            
        return False, None, None
    
    def _get_default_adapter_for_collection(self, collection_name: str) -> str:
        """Convert legacy collection name to default adapter name"""
        # This provides backward compatibility
        general_config = self.config.get('general', {})
        default_adapter = general_config.get('adapter', 'qa-vector')
        
        # Could implement collection-to-adapter mapping here
        collection_adapter_map = {
            'legal_docs': 'legal-documents-sql',
            'support_kb': 'support-kb-vector',
            # Add other mappings as needed
        }
        
        return collection_adapter_map.get(collection_name, default_adapter)
```

#### Dynamic Retriever Factory
```python
class AdapterAwareRetrieverService:
    async def get_retriever_for_adapter(self, adapter_name: str) -> BaseRetriever:
        """Get configured retriever for specified adapter"""
        adapter_config = self._get_adapter_config(adapter_name)
        
        if not adapter_config:
            raise ValueError(f"Adapter '{adapter_name}' not found in configuration")
            
        # Handle multi-source adapters
        if adapter_config.get('type') == 'multi_retriever':
            return await self._create_multi_source_retriever(adapter_config)
            
        # Handle single-source adapters
        return await self._create_single_source_retriever(adapter_config)
    
    def _get_adapter_config(self, adapter_name: str) -> Dict[str, Any]:
        """Get adapter configuration by name"""
        adapters = self.config.get('adapters', [])
        return next((cfg for cfg in adapters if cfg.get('name') == adapter_name), None)
```

### Phase 4: API Updates

#### Enhanced API Key Creation
```python
# CLI Command Enhancement
async def create_api_key_with_adapter(
    adapter_name: str,
    client_name: str,
    notes: Optional[str] = None,
    system_prompt_id: Optional[ObjectId] = None
) -> Dict[str, Any]:
    """Create API key associated with specific adapter"""
    
    # Validate adapter exists
    adapter_config = self._get_adapter_config(adapter_name)
    if not adapter_config:
        raise ValueError(f"Adapter '{adapter_name}' not found")
    
    # Create API key with adapter association
    return await self.api_key_service.create_api_key(
        adapter_name=adapter_name,  # NEW: Adapter instead of collection
        client_name=client_name,
        notes=notes,
        system_prompt_id=system_prompt_id
    )
```

### Phase 5: Backward Compatibility

#### Migration Strategy
```python
class ApiKeyMigration:
    async def migrate_collection_based_keys(self):
        """Migrate existing collection-based API keys to adapter-based"""
        
        # Get all API keys without adapter_name
        legacy_keys = await self.mongodb.find_many(
            "api_keys", 
            {"adapter_name": {"$exists": False}}
        )
        
        for key_doc in legacy_keys:
            collection_name = key_doc.get("collection_name")
            if collection_name:
                # Map collection to appropriate adapter
                adapter_name = self._map_collection_to_adapter(collection_name)
                
                # Update the document
                await self.mongodb.update_one(
                    "api_keys",
                    {"_id": key_doc["_id"]},
                    {"$set": {"adapter_name": adapter_name}}
                )
                
                logger.info(f"Migrated API key {key_doc['api_key']} from collection '{collection_name}' to adapter '{adapter_name}'")
```

## Implementation Timeline

### Schema and Configuration
- [ ] Update MongoDB schema
- [ ] Extend adapter configuration format
- [ ] Create migration scripts

### Service Layer
- [ ] Update ApiKeyService
- [ ] Create AdapterAwareRetrieverService
- [ ] Implement backward compatibility

### API and CLI Updates
- [ ] Update CLI commands
- [ ] Update REST API endpoints
- [ ] Add adapter validation

### Testing and Migration
- [ ] Comprehensive testing
- [ ] Migration of existing API keys
- [ ] Documentation updates

## Future Extensions

### Advanced Adapter Features
1. **Adapter Chaining**: Sequential processing through multiple adapters
2. **Conditional Routing**: Route queries to different adapters based on content
3. **Adapter Pools**: Load balancing across multiple instances
4. **Dynamic Reconfiguration**: Hot-reload adapter configurations

### Enterprise Features
1. **Audit Logging**: Track adapter usage per API key
2. **Rate Limiting**: Per-adapter rate limiting
3. **Cost Tracking**: Track usage costs per adapter
4. **Performance Monitoring**: Adapter-specific performance metrics
