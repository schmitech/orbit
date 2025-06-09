# Adapter Storage Strategy: MongoDB vs Config.yaml

## Overview

This document analyzes the best storage strategy for adapter configurations, comparing file-based (config.yaml) vs database-based (MongoDB) approaches, with a recommended hybrid solution.

## Current Approach: config.yaml

### Pros
- ✅ **Version Control**: Easy to track changes with Git
- ✅ **Simple Deployment**: Configuration as code
- ✅ **Fast Access**: No database queries needed
- ✅ **Infrastructure Separation**: Clear separation of system config
- ✅ **Backup/Restore**: Part of codebase backup

### Cons
- ❌ **Server Restart Required**: Changes need restart
- ❌ **Not Runtime Configurable**: No dynamic updates
- ❌ **Limited Multi-tenancy**: Hard to support per-tenant adapters
- ❌ **No User Interface**: Requires technical knowledge
- ❌ **No Approval Workflows**: Direct file changes only
- ❌ **Scaling Issues**: Large organizations with many adapters

## Proposed Approach: MongoDB-Based

### Pros
- ✅ **Runtime Configuration**: Changes without restart
- ✅ **Multi-Tenant Ready**: Per-organization adapters
- ✅ **User-Friendly Management**: Web UI possible
- ✅ **Approval Workflows**: Implement governance
- ✅ **Audit Trail**: Track who changed what when
- ✅ **Adapter Versioning**: History and rollback
- ✅ **Template System**: Inherit from base configurations
- ✅ **Enterprise Ready**: Departmental isolation

### Cons
- ❌ **Database Dependency**: Core functionality depends on DB
- ❌ **Bootstrap Complexity**: Chicken-egg problem
- ❌ **Performance Overhead**: Database queries required
- ❌ **Failure Scenarios**: Need graceful degradation

## Recommended: Hybrid Architecture

The optimal solution combines both approaches:

### Core System Adapters → config.yaml
```yaml
# config.yaml - Core system adapters (immutable)
system_adapters:
  - name: "default-qa-sql"
    type: "retriever"
    datasource: "sqlite"
    adapter: "qa"
    system: true  # Marks as system adapter
    config:
      confidence_threshold: 0.3
      max_results: 5
      
  - name: "default-qa-vector"
    type: "retriever"
    datasource: "chroma"
    adapter: "qa"
    system: true
    config:
      confidence_threshold: 0.3
      max_results: 5
```

### User/Tenant Adapters → MongoDB
```javascript
// MongoDB Collection: adapters
{
  "_id": ObjectId("..."),
  "name": "legal-department-sql",
  "organization_id": ObjectId("..."),  // Multi-tenant support
  "type": "retriever",
  "datasource": "postgres",
  "adapter": "qa",
  "implementation": "retrievers.implementations.qa.QAPostgresRetriever",
  "config": {
    "confidence_threshold": 0.4,
    "database": "legal_db",
    "table": "case_documents",
    "security_filter": "department_id = 'LEGAL'"
  },
  "created_by": "admin@company.com",
  "created_at": ISODate("..."),
  "updated_at": ISODate("..."),
  "version": 2,
  "active": true,
  "system": false,  // User-created adapter
  "parent_adapter": null,  // For inheritance
  "approval_status": "approved"
}
```

## Implementation Strategy

### 1. Enhanced Adapter Service

```python
# server/services/adapter_service.py - NEW FILE

from typing import Dict, Any, List, Optional
import logging
from datetime import datetime, UTC
from bson import ObjectId
from services.mongodb_service import MongoDBService

logger = logging.getLogger(__name__)

class AdapterService:
    """Service for managing adapter configurations in MongoDB with config.yaml fallback"""
    
    def __init__(self, config: Dict[str, Any], mongodb_service: MongoDBService):
        self.config = config
        self.mongodb = mongodb_service
        self.collection_name = "adapters"
        self._adapter_cache = {}  # Cache for performance
        self._cache_ttl = 300  # 5 minutes
        
        # Load system adapters from config
        self.system_adapters = self._load_system_adapters()
    
    def _load_system_adapters(self) -> Dict[str, Dict[str, Any]]:
        """Load system adapters from config.yaml"""
        system_adapters = {}
        
        # Load from current config format
        for adapter in self.config.get('adapters', []):
            adapter_copy = adapter.copy()
            adapter_copy['system'] = True
            adapter_copy['active'] = True
            system_adapters[adapter['name']] = adapter_copy
            
        # Load from new system_adapters section if exists
        for adapter in self.config.get('system_adapters', []):
            adapter_copy = adapter.copy()
            adapter_copy['system'] = True
            adapter_copy['active'] = True
            system_adapters[adapter['name']] = adapter_copy
            
        return system_adapters
    
    async def get_adapter(self, adapter_name: str, organization_id: Optional[ObjectId] = None) -> Optional[Dict[str, Any]]:
        """Get adapter by name, checking user adapters first, then system adapters"""
        
        # Check cache first
        cache_key = f"{adapter_name}:{organization_id}"
        if cache_key in self._adapter_cache:
            cached_entry = self._adapter_cache[cache_key]
            if datetime.now().timestamp() - cached_entry['timestamp'] < self._cache_ttl:
                return cached_entry['adapter']
        
        # Try user/tenant adapters first
        if organization_id:
            user_adapter = await self._get_user_adapter(adapter_name, organization_id)
            if user_adapter:
                self._cache_adapter(cache_key, user_adapter)
                return user_adapter
        
        # Try global user adapters (no organization)
        global_adapter = await self._get_user_adapter(adapter_name, None)
        if global_adapter:
            self._cache_adapter(cache_key, global_adapter)
            return global_adapter
            
        # Fallback to system adapters
        system_adapter = self.system_adapters.get(adapter_name)
        if system_adapter:
            self._cache_adapter(cache_key, system_adapter)
            return system_adapter
            
        return None
    
    async def _get_user_adapter(self, adapter_name: str, organization_id: Optional[ObjectId]) -> Optional[Dict[str, Any]]:
        """Get user-defined adapter from MongoDB"""
        try:
            query = {
                "name": adapter_name,
                "active": True
            }
            
            if organization_id:
                query["organization_id"] = organization_id
            else:
                query["organization_id"] = {"$exists": False}
                
            adapter_doc = await self.mongodb.find_one(self.collection_name, query)
            return adapter_doc
            
        except Exception as e:
            logger.warning(f"Error fetching user adapter {adapter_name}: {str(e)}")
            return None
    
    def _cache_adapter(self, cache_key: str, adapter: Dict[str, Any]):
        """Cache adapter configuration"""
        self._adapter_cache[cache_key] = {
            'adapter': adapter,
            'timestamp': datetime.now().timestamp()
        }
    
    async def create_adapter(
        self,
        name: str,
        adapter_type: str,
        datasource: str,
        adapter_impl: str,
        implementation: str,
        config: Dict[str, Any],
        organization_id: Optional[ObjectId] = None,
        created_by: str = "system"
    ) -> Dict[str, Any]:
        """Create a new user adapter"""
        
        # Check if adapter name already exists
        existing = await self.get_adapter(name, organization_id)
        if existing:
            raise ValueError(f"Adapter '{name}' already exists")
        
        now = datetime.now(UTC)
        
        adapter_doc = {
            "name": name,
            "type": adapter_type,
            "datasource": datasource,
            "adapter": adapter_impl,
            "implementation": implementation,
            "config": config,
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
            "version": 1,
            "active": True,
            "system": False,
            "approval_status": "approved"  # Could implement approval workflow
        }
        
        if organization_id:
            adapter_doc["organization_id"] = organization_id
        
        await self.mongodb.insert_one(self.collection_name, adapter_doc)
        
        # Clear cache
        self._clear_cache_for_adapter(name)
        
        return adapter_doc
    
    async def update_adapter(
        self,
        adapter_name: str,
        updates: Dict[str, Any],
        organization_id: Optional[ObjectId] = None,
        updated_by: str = "system"
    ) -> bool:
        """Update an existing user adapter"""
        
        # Can't update system adapters
        existing = await self._get_user_adapter(adapter_name, organization_id)
        if not existing:
            raise ValueError(f"User adapter '{adapter_name}' not found")
        
        now = datetime.now(UTC)
        update_doc = {
            **updates,
            "updated_by": updated_by,
            "updated_at": now,
            "version": existing.get("version", 1) + 1
        }
        
        query = {"name": adapter_name}
        if organization_id:
            query["organization_id"] = organization_id
        else:
            query["organization_id"] = {"$exists": False}
        
        result = await self.mongodb.update_one(
            self.collection_name,
            query,
            {"$set": update_doc}
        )
        
        # Clear cache
        self._clear_cache_for_adapter(adapter_name)
        
        return result
    
    async def list_adapters(self, organization_id: Optional[ObjectId] = None) -> List[Dict[str, Any]]:
        """List all available adapters (system + user)"""
        adapters = []
        
        # Add system adapters
        adapters.extend(self.system_adapters.values())
        
        # Add user adapters
        try:
            query = {"active": True}
            if organization_id:
                # Include both org-specific and global adapters
                query = {
                    "active": True,
                    "$or": [
                        {"organization_id": organization_id},
                        {"organization_id": {"$exists": False}}
                    ]
                }
            else:
                query["organization_id"] = {"$exists": False}
                
            user_adapters = await self.mongodb.find_many(self.collection_name, query)
            adapters.extend(user_adapters)
            
        except Exception as e:
            logger.warning(f"Error fetching user adapters: {str(e)}")
        
        return adapters
    
    async def delete_adapter(self, adapter_name: str, organization_id: Optional[ObjectId] = None) -> bool:
        """Delete a user adapter (soft delete)"""
        
        # Can't delete system adapters
        adapter = await self._get_user_adapter(adapter_name, organization_id)
        if not adapter:
            raise ValueError(f"User adapter '{adapter_name}' not found")
        
        query = {"name": adapter_name}
        if organization_id:
            query["organization_id"] = organization_id
        else:
            query["organization_id"] = {"$exists": False}
        
        result = await self.mongodb.update_one(
            self.collection_name,
            query,
            {"$set": {"active": False, "deleted_at": datetime.now(UTC)}}
        )
        
        # Clear cache
        self._clear_cache_for_adapter(adapter_name)
        
        return result
    
    def _clear_cache_for_adapter(self, adapter_name: str):
        """Clear cache entries for a specific adapter"""
        keys_to_remove = [key for key in self._adapter_cache.keys() if key.startswith(f"{adapter_name}:")]
        for key in keys_to_remove:
            del self._adapter_cache[key]

    async def validate_adapter_config(self, adapter_config: Dict[str, Any]) -> List[str]:
        """Validate adapter configuration and return any errors"""
        errors = []
        
        required_fields = ['name', 'type', 'datasource', 'adapter']
        for field in required_fields:
            if field not in adapter_config:
                errors.append(f"Missing required field: {field}")
        
        # Validate datasource exists
        datasource = adapter_config.get('datasource')
        if datasource and datasource not in self.config.get('datasources', {}):
            errors.append(f"Unknown datasource: {datasource}")
        
        # Additional validation logic here...
        
        return errors
```

### 2. Updated API Key Service Integration

```python
# server/services/api_key_service.py - ENHANCED WITH ADAPTER SERVICE

class ApiKeyService:
    def __init__(self, config: Dict[str, Any], mongodb_service: MongoDBService, adapter_service: AdapterService):
        self.config = config
        self.mongodb = mongodb_service
        self.adapter_service = adapter_service  # NEW: Inject adapter service
        self.collection_name = config.get('mongodb', {}).get('apikey_collection', 'api_keys')
    
    async def validate_api_key(self, api_key: str) -> Tuple[bool, Optional[str], Optional[ObjectId], Optional[ObjectId]]:
        """
        Validate API key and return adapter name, system prompt ID, and organization ID
        
        Returns:
            Tuple of (is_valid, adapter_name, system_prompt_id, organization_id)
        """
        key_doc = await self.mongodb.find_one(self.collection_name, {"api_key": api_key})
        
        if not key_doc or key_doc.get("active") is False:
            return False, None, None, None
            
        organization_id = key_doc.get("organization_id")
        
        # Try adapter-based approach first
        adapter_name = key_doc.get("adapter_name")
        if adapter_name:
            # Validate adapter exists (checking both user and system adapters)
            adapter = await self.adapter_service.get_adapter(adapter_name, organization_id)
            if adapter:
                return True, adapter_name, key_doc.get("system_prompt_id"), organization_id
            else:
                logger.warning(f"API key references non-existent adapter: {adapter_name}")
                return False, None, None, None
            
        # Fallback to legacy collection-based approach
        collection_name = key_doc.get("collection_name")
        if collection_name:
            adapter_name = self._map_collection_to_adapter(collection_name)
            return True, adapter_name, key_doc.get("system_prompt_id"), organization_id
            
        return False, None, None, None
```

### 3. Enhanced CLI Commands

```python
# bin/orbit.py - ADAPTER MANAGEMENT COMMANDS

class OrbitCLI:
    def _add_adapter_commands(self, subparsers):
        """Add adapter management commands"""
        adapter_parser = subparsers.add_parser('adapter', help='Adapter management')
        adapter_subparsers = adapter_parser.add_subparsers(dest='adapter_command')
        
        # List adapters
        list_parser = adapter_subparsers.add_parser('list', help='List all adapters')
        list_parser.add_argument('--org-id', help='Organization ID filter')
        
        # Create adapter
        create_parser = adapter_subparsers.add_parser('create', help='Create new adapter')
        create_parser.add_argument('--name', required=True, help='Adapter name')
        create_parser.add_argument('--type', default='retriever', help='Adapter type')
        create_parser.add_argument('--datasource', required=True, help='Datasource type')
        create_parser.add_argument('--adapter', required=True, help='Adapter implementation')
        create_parser.add_argument('--implementation', required=True, help='Implementation class')
        create_parser.add_argument('--config-file', help='JSON config file')
        create_parser.add_argument('--org-id', help='Organization ID')
        
        # Update adapter
        update_parser = adapter_subparsers.add_parser('update', help='Update adapter')
        update_parser.add_argument('--name', required=True, help='Adapter name')
        update_parser.add_argument('--config-file', help='Updated JSON config file')
        update_parser.add_argument('--org-id', help='Organization ID')
        
        # Delete adapter
        delete_parser = adapter_subparsers.add_parser('delete', help='Delete adapter')
        delete_parser.add_argument('--name', required=True, help='Adapter name')
        delete_parser.add_argument('--org-id', help='Organization ID')
```

### 4. Web UI for Adapter Management

```python
# server/routes/admin/adapters.py - NEW WEB UI ENDPOINTS

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel

router = APIRouter(prefix="/admin/adapters", tags=["Adapter Management"])

class AdapterRequest(BaseModel):
    name: str
    type: str = "retriever"
    datasource: str
    adapter: str
    implementation: str
    config: dict
    organization_id: Optional[str] = None

@router.get("/")
async def list_adapters(org_id: Optional[str] = None):
    """List all adapters for organization"""
    adapter_service = get_adapter_service()
    organization_id = ObjectId(org_id) if org_id else None
    adapters = await adapter_service.list_adapters(organization_id)
    return adapters

@router.post("/")
async def create_adapter(adapter_request: AdapterRequest):
    """Create new adapter"""
    adapter_service = get_adapter_service()
    
    # Validate configuration
    errors = await adapter_service.validate_adapter_config(adapter_request.dict())
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})
    
    organization_id = ObjectId(adapter_request.organization_id) if adapter_request.organization_id else None
    
    adapter = await adapter_service.create_adapter(
        name=adapter_request.name,
        adapter_type=adapter_request.type,
        datasource=adapter_request.datasource,
        adapter_impl=adapter_request.adapter,
        implementation=adapter_request.implementation,
        config=adapter_request.config,
        organization_id=organization_id
    )
    
    return {"message": "Adapter created successfully", "adapter": adapter}

@router.put("/{adapter_name}")
async def update_adapter(adapter_name: str, updates: dict, org_id: Optional[str] = None):
    """Update existing adapter"""
    adapter_service = get_adapter_service()
    organization_id = ObjectId(org_id) if org_id else None
    
    result = await adapter_service.update_adapter(adapter_name, updates, organization_id)
    if not result:
        raise HTTPException(status_code=404, detail="Adapter not found")
    
    return {"message": "Adapter updated successfully"}

@router.delete("/{adapter_name}")
async def delete_adapter(adapter_name: str, org_id: Optional[str] = None):
    """Delete adapter"""
    adapter_service = get_adapter_service()
    organization_id = ObjectId(org_id) if org_id else None
    
    result = await adapter_service.delete_adapter(adapter_name, organization_id)
    if not result:
        raise HTTPException(status_code=404, detail="Adapter not found")
    
    return {"message": "Adapter deleted successfully"}
```

## Benefits of Hybrid Approach

### 1. **Best of Both Worlds**
- System adapters remain stable and version-controlled
- User adapters provide runtime flexibility

### 2. **Graceful Degradation**
- If MongoDB is down, system adapters still work
- Progressive enhancement model

### 3. **Enterprise Ready**
- Multi-tenant adapter isolation
- Approval workflows possible
- Audit trails for compliance

### 4. **Developer Friendly**
- Core adapters in code for easy development
- User adapters for customization

### 5. **Performance Optimized**
- Caching layer for database adapters
- Fast access to system adapters

## Migration Path

### Phase 1: Implement Hybrid Service
1. Create AdapterService with MongoDB + config.yaml support
2. Update existing services to use AdapterService
3. Maintain full backward compatibility

### Phase 2: Add Management UI
1. Create web UI for adapter management
2. Add CLI commands for adapter CRUD
3. Implement validation and error handling

### Phase 3: Enhanced Features
1. Add organization/tenant support
2. Implement approval workflows
3. Add adapter templates and inheritance
