# Refactor Datasource Factory with Registry Pattern

## Overview

Transform the monolithic `datasource_factory.py` into a modular registry-based system with automatic discovery, adding support for Oracle, MySQL, SQL Server, MongoDB, Cassandra, and MariaDB.

## Architecture Changes

### 1. Create Base Datasource Class

**File**: `server/datasources/base/base_datasource.py`

- Abstract base class defining the interface for all datasource implementations
- Methods: `initialize()`, `get_client()`, `health_check()`, `close()`
- Properties: `datasource_name`, `config`, `logger`

### 2. Create Datasource Registry

**File**: `server/datasources/registry.py`

- Similar to `server/adapters/registry.py` pattern
- Auto-discovery of datasource implementations
- Registration and instantiation methods
- Support for dynamic loading of datasource classes

### 3. Separate Datasource Implementations

Create individual files under `server/datasources/implementations/`:

- **relational/**
  - `oracle_datasource.py` - Oracle Database
  - `mysql_datasource.py` - MySQL
  - `mariadb_datasource.py` - MariaDB (similar to MySQL)
  - `sqlserver_datasource.py` - Microsoft SQL Server
  - `postgres_datasource.py` - PostgreSQL (migrate from factory)
  - `sqlite_datasource.py` - SQLite (migrate from factory)
  - `supabase_datasource.py` - Supabase (PostgreSQL-based)

- **nosql/**
  - `mongodb_datasource.py` - MongoDB document database
  - `cassandra_datasource.py` - Apache Cassandra

- **vector/**
  - `chroma_datasource.py` - ChromaDB (migrate from factory)
  - `milvus_datasource.py` - Milvus (currently stub)

### 4. Update Configuration

**File**: `config/datasources.yaml`

Add configuration sections for new datasources:

```yaml
datasources:
  oracle:
    host: ${DATASOURCE_ORACLE_HOST}
    port: ${DATASOURCE_ORACLE_PORT}
    service_name: ${DATASOURCE_ORACLE_SERVICE}
    username: ${DATASOURCE_ORACLE_USERNAME}
    password: ${DATASOURCE_ORACLE_PASSWORD}
  
  mysql:
    host: ${DATASOURCE_MYSQL_HOST}
    port: ${DATASOURCE_MYSQL_PORT}
    database: ${DATASOURCE_MYSQL_DATABASE}
    username: ${DATASOURCE_MYSQL_USERNAME}
    password: ${DATASOURCE_MYSQL_PASSWORD}
  
  mariadb:
    host: ${DATASOURCE_MARIADB_HOST}
    port: ${DATASOURCE_MARIADB_PORT}
    database: ${DATASOURCE_MARIADB_DATABASE}
    username: ${DATASOURCE_MARIADB_USERNAME}
    password: ${DATASOURCE_MARIADB_PASSWORD}
  
  sqlserver:
    host: ${DATASOURCE_SQLSERVER_HOST}
    port: ${DATASOURCE_SQLSERVER_PORT}
    database: ${DATASOURCE_SQLSERVER_DATABASE}
    username: ${DATASOURCE_SQLSERVER_USERNAME}
    password: ${DATASOURCE_SQLSERVER_PASSWORD}
    driver: "ODBC Driver 18 for SQL Server"
  
  supabase:
    host: ${DATASOURCE_SUPABASE_HOST}
    port: ${DATASOURCE_SUPABASE_PORT}
    database: ${DATASOURCE_SUPABASE_DATABASE}
    username: ${DATASOURCE_SUPABASE_USERNAME}
    password: ${DATASOURCE_SUPABASE_PASSWORD}
    sslmode: require
  
  cassandra:
    contact_points: ${DATASOURCE_CASSANDRA_HOSTS}
    port: ${DATASOURCE_CASSANDRA_PORT}
    keyspace: ${DATASOURCE_CASSANDRA_KEYSPACE}
    username: ${DATASOURCE_CASSANDRA_USERNAME}
    password: ${DATASOURCE_CASSANDRA_PASSWORD}
```

### 5. Refactor DatasourceFactory

**File**: `server/datasources/datasource_factory.py`

- Keep as thin wrapper around registry
- Main method: `initialize_datasource_client(provider)` delegates to registry
- Backward compatible with existing code

### 6. Update Package Initialization

**File**: `server/datasources/__init__.py`

- Export registry and factory
- Auto-discover and register implementations on import

### 7. Add Database Client Dependencies

**File**: `install/dependencies.toml`

Add to the `minimal` profile:

```toml
"oracledb>=3.4.0",           # Oracle Database client (modern)
"mysql-connector-python>=9.4.0",  # MySQL client
"pymssql>=2.3.8",             # SQL Server client
"cassandra-driver>=3.29.2",   # Apache Cassandra client
```

Note: MariaDB uses the same `mysql-connector-python` package as MySQL. MongoDB's `pymongo` and `motor` are already included. Supabase uses `psycopg2-binary` (already included).

## Implementation Details

Each datasource implementation will:

- Inherit from `BaseDatasource`
- Implement `initialize()` with connection logic
- Return appropriate client/connection object
- Handle missing dependencies gracefully (log warning if package not installed)
- Include basic error handling and logging

## Key Files to Modify

- `server/datasources/datasource_factory.py` (refactor)
- `server/datasources/__init__.py` (update exports)
- `config/datasources.yaml` (add new datasources)

## Key Files to Create

- `server/datasources/base/__init__.py`
- `server/datasources/base/base_datasource.py`
- `server/datasources/registry.py`
- `server/datasources/implementations/__init__.py`
- `server/datasources/implementations/relational/__init__.py`
- `server/datasources/implementations/relational/*.py` (7 files)
- `server/datasources/implementations/nosql/__init__.py`
- `server/datasources/implementations/nosql/*.py` (2 files)
- `server/datasources/implementations/vector/__init__.py`
- `server/datasources/implementations/vector/*.py` (2 files)

## Benefits

- Scalable: Easy to add new datasources
- Maintainable: Each datasource in its own file
- Discoverable: Auto-registration via registry
- Consistent: All follow same base interface
- Backward Compatible: Existing code continues to work

## Implementation Status

✅ **Completed**:
- [x] Create base datasource class and directory structure
- [x] Implement datasource registry with auto-discovery
- [x] Migrate existing datasources (SQLite, PostgreSQL, ChromaDB, Milvus) to new structure
- [x] Implement Oracle, MySQL, MariaDB, and SQL Server datasources
- [x] Implement MongoDB and Cassandra datasources
- [x] Add Supabase datasource implementation
- [x] Add new datasource configurations to datasources.yaml
- [x] Refactor DatasourceFactory to use registry pattern
- [x] Update package initialization with auto-discovery and exports
- [x] Update dependencies with latest versions

## Future Enhancements

- **Data Warehouse Integration**: See `datawarehouse-datalake-datasources.md` for advanced data warehouse and data lake support
- **Connection Pooling**: Advanced connection pooling and caching
- **Health Monitoring**: Enhanced health checks and monitoring
- **Performance Optimization**: Query optimization and result caching
- **Enterprise Security**: OAuth, SAML, and advanced authentication
