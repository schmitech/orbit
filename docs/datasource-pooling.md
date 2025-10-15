# Datasource Pooling Implementation

## Overview

In-memory datasource pooling with reference counting to optimize resource usage when multiple adapters share the same database connection.

## Features

### 1. **Automatic Connection Sharing**
- Multiple adapters connecting to the same database automatically share a single datasource instance
- Reduces memory footprint and connection overhead
- Thread-safe with locking mechanism

### 2. **Reference Counting**
- Tracks how many adapters are using each datasource
- Automatically closes datasources when reference count reaches 0
- Prevents premature closure of shared connections

### 3. **Smart Cache Keys**
Datasources are pooled based on connection parameters:

```yaml
# SQLite: Database file path
sqlite:../demos/data.db

# PostgreSQL/MySQL: Host, port, database, username
postgres:localhost:5432:mydb:user

# ChromaDB: Host and port OR path for persistent
chroma:localhost:8000
chroma:path:/data/chroma

# Qdrant: Host and port
qdrant:localhost:6333

# Pinecone: Environment and index
pinecone:production:my-index
```

## Usage Example

### Before (Without Pooling)
```
Adapter 1: qa-sql (SQLite) → Creates connection #1
Adapter 2: intent-sql (SQLite) → Creates connection #2
Adapter 3: qa-sql-2 (SQLite) → Creates connection #3
Result: 3 separate connections to same database
```

### After (With Pooling)
```
Adapter 1: qa-sql (SQLite) → Creates connection #1 (refs: 1)
Adapter 2: intent-sql (SQLite) → Reuses connection #1 (refs: 2)
Adapter 3: qa-sql-2 (SQLite) → Reuses connection #1 (refs: 3)
Result: 1 shared connection, 3 references
```

## API

### Datasource Registry Methods

```python
# Get or create a datasource (automatically pooled)
datasource = registry.get_or_create_datasource(
    datasource_name='postgres',
    config=config,
    logger_instance=logger
)

# Release a datasource reference
registry.release_datasource(
    datasource_name='postgres',
    config=config,  # Used to generate same cache key
    logger_instance=logger
)

# Get pool statistics
stats = registry.get_pool_stats()
# Returns:
# {
#     "total_cached_datasources": 2,
#     "datasource_keys": ["sqlite:data.db", "postgres:localhost:5432:mydb:user"],
#     "reference_counts": {"sqlite:data.db": 3, "postgres:localhost:5432:mydb:user": 1},
#     "total_references": 4
# }

# Shutdown pool (force close all)
await registry.shutdown_pool(logger_instance=logger)
```

### Health Check Integration

Pool statistics are included in the adapter manager health check:

```python
health = await adapter_manager.health_check()
print(health['datasource_pool'])
# {
#     "total_cached_datasources": 2,
#     "reference_counts": {...},
#     ...
# }
```

## Lifecycle

### Adapter Creation
1. Dynamic Adapter Manager requests datasource from registry
2. Registry checks if datasource exists in pool (by cache key)
3. If exists: Return cached datasource, increment reference count
4. If not: Create new datasource, add to pool with reference count = 1

### Adapter Removal
1. Adapter manager calls `release_datasource()`
2. Registry decrements reference count
3. If count reaches 0: Close datasource and remove from pool
4. If count > 0: Keep datasource in pool for other adapters

### Server Shutdown
1. Adapter manager closes all adapters (releases all references)
2. Registry's `shutdown_pool()` force-closes any remaining datasources
3. Ensures clean shutdown even if reference counts aren't zero

## Benefits

### Memory Savings
- **Before**: 7 adapters × ~5MB per connection = ~35MB
- **After**: ~2-3 unique connections × ~5MB = ~10-15MB
- **Savings**: ~20-25MB (60-70% reduction)

### Connection Pool Efficiency
- PostgreSQL default max connections: 100
- Without pooling: Each adapter uses 1-5 connections
- With pooling: All adapters sharing same DB use same pool
- Prevents "too many connections" errors

### Performance
- No overhead on queries (direct memory access)
- Minimal overhead on adapter init (~1μs for dict lookup)
- Faster warmup (shared connections already initialized)

## Monitoring

### Log Messages
```
# Creation
INFO: Created new datasource 'postgres' (key: postgres:localhost:5432:mydb:user, refs: 1)

# Reuse
INFO: Reusing cached datasource 'postgres' (key: postgres:localhost:5432:mydb:user, refs: 2)

# Release
INFO: Released datasource 'postgres' (key: postgres:localhost:5432:mydb:user, refs: 1)

# Closure
INFO: Closed datasource 'postgres' (key: postgres:localhost:5432:mydb:user, refs: 0)
```

## Thread Safety

- Uses `threading.Lock` for pool operations
- Safe for concurrent adapter loading
- Lock is held only during cache lookup/modification (not during connection operations)

## Edge Cases Handled

1. **Adapter creation failure**: Reference not incremented if retriever init fails
2. **Double release**: Silently handles release of non-existent datasource
3. **Shutdown with active references**: Force-closes all datasources regardless of reference count
4. **Unknown datasource types**: Falls back to non-pooled behavior (logs warning)

## Future Enhancements

Potential improvements for high-scale deployments:

1. **Health check integration**: Verify pooled datasources are still healthy
2. **Automatic reconnection**: Detect stale connections and refresh
3. **TTL-based expiration**: Close idle datasources after timeout
4. **Max pool size**: Limit total number of pooled datasources
5. **Metrics collection**: Track pool hit rate, connection churn

## Testing

To verify pooling is working, check logs during startup:

```bash
# Should see "Created new datasource" for first adapter
# Then "Reusing cached datasource" for subsequent adapters using same DB
grep "datasource" server/logs/orbit.log
```

Or check health endpoint:
```bash
curl http://localhost:8000/health | jq '.datasource_pool'
```
