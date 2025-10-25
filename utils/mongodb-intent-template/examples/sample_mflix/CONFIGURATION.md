# MongoDB Intent Template Configuration Guide

This guide explains how to configure the MongoDB intent retriever adapter for the sample_mflix database.

## Configuration Separation

The MongoDB intent adapter uses a three-layer configuration approach:

### 1. Connection Configuration (`config/datasources.yaml`)

MongoDB connection details and pooling settings:

```yaml
datasources:
  mongodb:
    enabled: true
    # Option 1: Connection string (recommended for Atlas)
    connection_string: ${MONGODB_URI}
    
    # Option 2: Individual parameters (for local MongoDB)
    host: ${DATASOURCE_MONGODB_HOST:-localhost}
    port: ${DATASOURCE_MONGODB_PORT:-27017}
    database: ${DATASOURCE_MONGODB_DATABASE:-sample_mflix}
    username: ${DATASOURCE_MONGODB_USERNAME}
    password: ${DATASOURCE_MONGODB_PASSWORD}
    auth_source: ${DATASOURCE_MONGODB_AUTH_SOURCE:-admin}
    
    # Connection settings
    timeout: 30
    tls: ${DATASOURCE_MONGODB_TLS:-false}
    retry_writes: true
    w: "majority"
```

### 2. Domain Configuration (`mflix_domain.yaml`)

Database schema, vocabulary, and query patterns:

```yaml
domain_name: "sample_mflix"
domain_type: "mongodb"
database: "sample_mflix"

collections:
  movies:
    primary_key: "_id"
    display_name: "Movies"
    searchable_fields: [...]
    common_filters: [...]
```

### 3. Adapter Configuration (`config/adapters.yaml`)

Adapter-specific settings and template paths:

```yaml
- name: "intent-mongodb-mflix"
  enabled: true
  type: "retriever"
  datasource: "mongodb"
  adapter: "intent"
  implementation: "retrievers.implementations.intent.intent_mongodb_retriever.IntentMongoDBRetriever"
  config:
    adapter_config:
      # Vector store for template storage
      store_name: "chroma_local"
      template_collection_name: "intent_mongodb_templates"
      
      # Domain configuration paths
      domain_config_path: "utils/mongodb-intent-template/examples/sample_mflix/templates/mflix_domain.yaml"
      template_library_path: "utils/mongodb-intent-template/examples/sample_mflix/templates/mflix_templates.yaml"
      
      # Intent matching settings
      confidence_threshold: 0.75
      max_templates: 5
      reload_templates_on_start: true
      
      # MongoDB-specific settings
      default_collection: "movies"
      default_limit: 100
      max_limit: 1000
      enable_text_search: true
      case_insensitive_regex: true
```

## MongoDB Atlas Setup

### 1. Create Atlas Cluster

1. Sign up at [mongodb.com/atlas](https://www.mongodb.com/atlas)
2. Create a new project
3. Build a new cluster (M0 free tier is sufficient)
4. Wait for cluster to be ready

### 2. Load Sample Data

1. In Atlas dashboard, click "..." next to your cluster
2. Select "Load Sample Dataset"
3. Confirm and wait for data to load
4. Verify `sample_mflix` database appears in your cluster

### 3. Create Database User

1. Go to "Database Access" in Atlas
2. Click "Add New Database User"
3. Choose "Password" authentication
4. Set username and password
5. Grant "Read and write to any database" permissions
6. Click "Add User"

### 4. Configure Network Access

1. Go to "Network Access" in Atlas
2. Click "Add IP Address"
3. Choose "Allow Access from Anywhere" (0.0.0.0/0) for testing
4. Or add your specific IP address for production
5. Click "Confirm"

### 5. Get Connection String

1. Go to "Clusters" and click "Connect"
2. Choose "Connect your application"
3. Select "Python" and version "3.6 or later"
4. Copy the connection string
5. Replace `<password>` with your database user password

## Environment Variables

Create a `.env` file or set environment variables:

```bash
# MongoDB Atlas Connection
MONGODB_URI="mongodb+srv://username:password@cluster.mongodb.net/sample_mflix?retryWrites=true&w=majority"
MONGODB_DATABASE="sample_mflix"

# Alternative: Individual parameters
MONGODB_HOST="cluster.mongodb.net"
MONGODB_USERNAME="your_username"
MONGODB_PASSWORD="your_password"
MONGODB_TLS="true"
```

## Adapter Configuration Options

### Basic Settings

```yaml
config:
  adapter_config:
    # Vector store configuration
    store_name: "chroma_local"  # or "qdrant", "pinecone"
    template_collection_name: "intent_mongodb_templates"
    
    # Template management
    reload_templates_on_start: true
    force_reload_templates: false
    
    # Intent matching
    confidence_threshold: 0.75
    max_templates: 5
```

### MongoDB-Specific Settings

```yaml
config:
  adapter_config:
    # Collection defaults
    default_collection: "movies"
    database: "sample_mflix"  # Override domain default
    
    # Query limits
    default_limit: 100
    max_limit: 1000
    
    # Text search options
    enable_text_search: true
    case_insensitive_regex: true
    
    # Performance tuning
    query_timeout: 30
    enable_connection_pooling: true
```

### Advanced Settings

```yaml
config:
  adapter_config:
    # Debugging
    verbose: true
    
    # Template processing
    preserve_unknown_parameters: false
    
    # Result formatting
    include_metadata: true
    max_display_fields: 10
    truncate_long_fields: true
    max_field_length: 200
```

## Testing Configuration

### 1. Test MongoDB Connection

```python
from motor.motor_asyncio import AsyncIOMotorClient

async def test_connection():
    client = AsyncIOMotorClient("your_connection_string")
    try:
        await client.admin.command('ping')
        print("MongoDB connection successful")
        
        # Test sample_mflix database
        db = client['sample_mflix']
        collections = await db.list_collection_names()
        print(f"Collections: {collections}")
        
        # Test movies collection
        movies = db['movies']
        count = await movies.count_documents({})
        print(f"Movies count: {count}")
        
    except Exception as e:
        print(f"Connection failed: {e}")
    finally:
        client.close()
```

### 2. Test Adapter

```python
# Test the adapter configuration
from adapters.registry import ADAPTER_REGISTRY

async def test_adapter():
    try:
        adapter = ADAPTER_REGISTRY.create(
            adapter_type="retriever",
            datasource="mongodb",
            adapter_name="intent",
            config=your_config
        )
        await adapter.initialize()
        print("Adapter initialized successfully")
        
        # Test a simple query
        results = await adapter.get_relevant_context("find action movies")
        print(f"Query results: {len(results)} items")
        
    except Exception as e:
        print(f"Adapter test failed: {e}")
```

## Troubleshooting

### Common Configuration Issues

1. **Template Not Loading**
   - Check file paths in `domain_config_path` and `template_library_path`
   - Verify YAML syntax in template files
   - Check vector store configuration

2. **MongoDB Connection Failed**
   - Verify connection string format
   - Check network access in Atlas
   - Confirm database user permissions

3. **Query Execution Errors**
   - Check MongoDB query syntax in templates
   - Verify collection and field names
   - Test queries in MongoDB Compass

4. **Low Template Matching**
   - Adjust `confidence_threshold`
   - Add more natural language examples
   - Check embedding model configuration

### Debug Commands

```bash
# Check MongoDB connection
mongosh "your_connection_string"

# Test specific collection
use sample_mflix
db.movies.findOne()

# Check adapter logs
tail -f logs/orbit.log | grep -i mongodb
```

## Production Considerations

1. **Security**
   - Use specific IP whitelist in Atlas
   - Create dedicated database user with minimal permissions
   - Enable MongoDB authentication

2. **Performance**
   - Create appropriate indexes for query fields
   - Use connection pooling
   - Monitor query performance

3. **Monitoring**
   - Enable MongoDB Atlas monitoring
   - Set up alerts for connection issues
   - Monitor adapter performance metrics
