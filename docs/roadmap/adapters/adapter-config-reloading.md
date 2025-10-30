# Adapter Hot Reload Implementation

## Overview

Implement a `/admin/reload-adapters` endpoint that reloads `adapters.yaml` and performs hot-swap of adapters - only adding/removing/updating changed adapters while waiting for in-flight requests on old adapters to complete.

## Implementation Steps

### 1. Add Reload Method to DynamicAdapterManager

**File**: `server/services/dynamic_adapter_manager.py`

Add a new method `reload_adapter_configs()` that:

- Reloads the adapters.yaml file from disk
- Compares new configs with existing `_adapter_configs`
- Identifies: new adapters, removed adapters, and changed adapters
- For changed adapters: marks old instances for deprecation and clears from cache
- For removed adapters: marks for cleanup (wait for in-flight requests)
- For new adapters: adds to `_adapter_configs`
- Returns a summary dict with counts of added/removed/updated adapters

Key logic:

```python
async def reload_adapter_configs(self, config_path: str) -> Dict[str, Any]:
    """Reload adapter configurations from file and perform hot-swap"""
    # 1. Reload config file
    # 2. Process imports to get new adapter configs
    # 3. Compare with existing _adapter_configs
    # 4. Remove old adapters from cache
    # 5. Update _adapter_configs dict
    # 6. Return summary
```

### 2. Add Reload Method to FaultTolerantAdapterManager

**File**: `server/services/fault_tolerant_adapter_manager.py`

Add a wrapper method that delegates to the base `DynamicAdapterManager`:

```python
async def reload_adapters(self, config_path: str) -> Dict[str, Any]:
    """Reload adapters via base adapter manager"""
    return await self.base_adapter_manager.reload_adapter_configs(config_path)
```

### 3. Update Config Manager for Reloadable Imports

**File**: `server/config/config_manager.py`

Add a new function `reload_adapters_config()` that:

- Reads the config.yaml to find the adapter import path
- Loads and processes the adapters.yaml file
- Returns the processed adapter configurations
- Does NOT use `@lru_cache` (separate from main config loading)
```python
def reload_adapters_config(config_path: str) -> Dict[str, Any]:
    """Reload only the adapters configuration from adapters.yaml"""
    # Load main config to find adapter import
    # Load adapters.yaml
    # Process imports and return
```


### 4. Create Admin Reload Endpoint

**File**: `server/routes/admin_routes.py`

Add new endpoint after the existing admin routes (around line 590):

```python
@admin_router.post("/reload-adapters")
async def reload_adapters(
    request: Request,
    adapter_name: Optional[str] = None,
    authorized: bool = Depends(admin_auth_check)
):
    """
    Reload adapter configurations from adapters.yaml without server restart.
    
    This endpoint performs hot-swap of adapters:
    - If adapter_name is None: reloads all adapters
    - If adapter_name is provided: reloads only that specific adapter
    
    For all adapters:
    - Adds new adapters
    - Removes disabled adapters
    - Updates changed adapter configurations
    - Preserves in-flight requests on old adapters
    
    For specific adapter:
    - Updates only the named adapter configuration
    - Returns error if adapter not found in config
    
    Requires admin authentication.
    
    Query Parameters:
        adapter_name: Optional name of specific adapter to reload
    """
    # Get config path from app state
    # Get adapter manager from app state
    # Call reload method with adapter_name
    # Return summary with counts
```

Response format for all adapters:

```json
{
  "status": "success",
  "message": "Adapters reloaded successfully",
  "summary": {
    "added": 2,
    "removed": 1,
    "updated": 3,
    "unchanged": 5,
    "total": 9
  },
  "timestamp": "2025-01-01T12:00:00Z"
}
```

Response format for specific adapter:

```json
{
  "status": "success",
  "message": "Adapter 'qa-sql' reloaded successfully",
  "summary": {
    "adapter_name": "qa-sql",
    "action": "updated",
    "previous_config": {...},
    "new_config": {...}
  },
  "timestamp": "2025-01-01T12:00:00Z"
}
```

### 5. Store Config Path in App State

**File**: `server/inference_server.py`

In the `__init__` method (around line 107), store the resolved config path:

```python
self.config_path = config_path or self._find_config_path()
```

In the lifespan startup, add to app state:

```python
app.state.config_path = self.config_path
```

### 6. Add CLI Command to orbit.py

**File**: `bin/orbit.py`

Add a new admin command `reload-adapters`:

```python
def _add_admin_commands(self, subparsers):
    """Add admin management commands"""
    admin_parser = subparsers.add_parser('admin', help='Admin operations')
    admin_subparsers = admin_parser.add_subparsers(dest='admin_command')
    
    reload_parser = admin_subparsers.add_parser(
        'reload-adapters',
        help='Reload adapter configurations'
    )
    reload_parser.set_defaults(func=self.handle_reload_adapters_command)

def handle_reload_adapters_command(self, args):
    """Handler for 'admin reload-adapters' command"""
    api_manager = self.get_api_manager(args.server_url)
    # Call POST /admin/reload-adapters
    # Display summary
```

### 7. Add Response Model

**File**: `server/models/schema.py`

Add response model for the reload endpoint:

```python
class AdapterReloadResponse(BaseModel):
    status: str
    message: str
    summary: Dict[str, int]
    timestamp: str
```

## Testing Approach

1. Start server with initial adapters.yaml
2. Modify adapters.yaml (add/remove/change adapters)
3. Call reload endpoint via CLI: `orbit admin reload-adapters`
4. Verify adapters are reloaded without server restart
5. Test with in-flight requests to ensure graceful handling

## Error Handling

- Invalid YAML syntax: return 400 with parse error
- File not found: return 500 with file path
- Adapter initialization errors: log but continue with valid adapters
- Auth failures: return 401/403 as per existing admin routes