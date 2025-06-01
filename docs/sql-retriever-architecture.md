# SQL Retriever Architecture Summary

The `AbstractSQLRetriever` architecture is designed to be **database-agnostic** and supports any SQL database. The base class provides common functionality while allowing database-specific optimizations and domain specializations.

## Architecture Hierarchy

```
BaseRetriever (abstract base for all retrievers)
└── AbstractSQLRetriever (database-agnostic SQL functionality)
    ├── relational/
    │   ├── SQLiteRetriever (SQLite-specific implementation)
    │   ├── PostgreSQLRetriever (PostgreSQL-specific implementation)
    │   └── MySQLRetriever (MySQL-specific implementation)
    └── qa/
        └── QASSQLRetriever (QA domain specialization of SQLite)
```

## Supported Databases

### ✅ Currently Implemented

| Database | Implementation | Status | Special Features | Domain Specializations |
|----------|----------------|---------|------------------|------------------------|
| **SQLite** | `relational.SQLiteRetriever` | ✅ Complete | File-based, FTS5 support | `qa.QASSQLRetriever` (Q&A) |
| **PostgreSQL** | `relational.PostgreSQLRetriever` | ✅ Complete | Full-text search, JSON ops | *Easy to add* |
| **MySQL** | `relational.MySQLRetriever` | ✅ Complete | FULLTEXT indexes, optimized LIKE | *Easy to add* |


## 🔄 Details

```
BaseRetriever (core functionality for all retrievers)
│
└── AbstractSQLRetriever (database-agnostic SQL base)
    │   • Common SQL functionality
    │   • Text tokenization & similarity
    │   • Domain adapter integration
    │   • Abstract methods for DB-specific implementation
    │
    ├── relational/
    │   ├── SQLiteRetriever (SQLite-specific implementation)
    │   │   • SQLite connection management
    │   │   • SQLite query execution
    │   │   • SQLite schema verification
    │   │
    │   ├── PostgreSQLRetriever (PostgreSQL-specific)
    │   │   • Full-text search with ts_vector
    │   │   • PostgreSQL connection via psycopg2
    │   │   • Advanced query optimizations
    │   │
    │   └── MySQLRetriever (MySQL-specific)
    │       • FULLTEXT indexes with MATCH() AGAINST()
    │       • MySQL connection via mysql-connector
    │       • Optimized LIKE search fallback
    │
    └── qa/
        └── QASSQLRetriever (QA domain specialization)
            • Question/Answer field prioritization
            • QA-optimized similarity scoring
            • Token-based search for FAQ scenarios
            • QA-specific result formatting
```

### Code Reuse
- `QASSQLRetriever` inherits all SQLite functionality from `SQLiteRetriever`
- No duplication of connection management, query execution, etc.
- Focuses only on QA-specific enhancements

### Separation of Concerns
- **Database Logic**: Handled by `SQLiteRetriever`, `PostgreSQLRetriever`, etc.
- **Domain Logic**: Handled by specializations like `QASSQLRetriever`
- **Common Logic**: Handled by `AbstractSQLRetriever`

### Extensibility
- Easy to add new databases: extend `AbstractSQLRetriever`
- Easy to add domain specializations: extend any database implementation
- Future: `LegalPostgreSQLRetriever`, `MedicalMySQLRetriever`, etc.


### Example
```python
# QASSQLRetriever focuses only on Question / Answer RAG
class QASSQLRetriever(SQLiteRetriever):
    def __init__(self, ...):
        super().__init__(...)
        self.confidence_threshold = ...
        
    def _get_search_query(self, ...):
        if "question" in self.default_search_fields:
            # QA-optimized search logic
        return super()._get_search_query(...)
```

## 🌍 Database Compatibility

### Currently Supported
- **SQLite**: `SQLiteRetriever` + `QASSQLRetriever` (QA specialization)
- **PostgreSQL**: `PostgreSQLRetriever` (full-text search, JSON ops)
- **MySQL**: `MySQLRetriever` (FULLTEXT indexes, MATCH() AGAINST())

### Other DBs
- **Oracle**: Extend `AbstractSQLRetriever`, use `cx_Oracle`
- **SQL Server**: Extend `AbstractSQLRetriever`, use `pyodbc`
- **MariaDB**: Minor tweaks to `MySQLRetriever`

### Performance Considerations

| Database | Best For | Performance Notes | QA Specialization |
|----------|----------|-------------------|-------------------|
| **SQLite** | Dev, small datasets | Fast for < 100MB, single-user | ✅ Available |
| **PostgreSQL** | Production, complex queries | Excellent FTS, JSON support | Easy to add |
| **MySQL** | Web applications | Good FULLTEXT, wide adoption | Easy to add |
| **Oracle** | Enterprise, large scale | Advanced text search, optimization | Easy to add |

### 🎯 Other Domain Examples:
- **QA Systems**: `QASSQLRetriever` (available for SQLite)
- **Legal**: `LegalPostgreSQLRetriever` (easy to create)
- **Medical**: `MedicalMySQLRetriever` (easy to create)
- **E-commerce**: `ProductSearchRetriever` (easy to create)

## 🛠️ Implementation Pattern

### 🔧 Database-Specific Optimizations

Each implementation can leverage unique database features:

```python
# PostgreSQL: Advanced full-text search
ts_rank(to_tsvector('english', content), plainto_tsquery('english', ?))

# MySQL: FULLTEXT indexes  
MATCH(content, question) AGAINST(? IN NATURAL LANGUAGE MODE)

# SQLite: FTS5 virtual tables
content MATCH ? ORDER BY rank

# Oracle: Text indexing
CONTAINS(content, ?, 1) > 0 ORDER BY SCORE(1) DESC
```

### 🎯 Domain Specializations

Domain-specific retrievers extend database implementations:

```python
# QA specialization of SQLite
class QASSQLRetriever(SQLiteRetriever):
    """Adds QA-specific functionality to SQLite retriever"""
    
    # QA-specific enhancements:
    - Question/Answer field prioritization
    - QA-optimized similarity scoring
    - Token-based search for FAQ scenarios
    - QA-specific result formatting
```

## Implementation Examples

### SQLite with QA Specialization

```python
from retrievers.implementations.qa_sql_retriever import QASSQLRetriever

# Configuration  
config = {
    "datasources": {
        "sqlite": {
            "db_path": "./data/qa_knowledge.db",
            "max_results": 50
        }
    },
    "adapters": [{
        "type": "retriever",
        "datasource": "sqlite", 
        "adapter": "qa",
        "config": {
            "confidence_threshold": 0.3
        }
    }]
}

# Initialize QA-specialized SQLite retriever
retriever = QASSQLRetriever(config=config)
await retriever.initialize()

# Optimized for Q&A scenarios
results = await retriever.get_relevant_context("How do I configure the system?")
```

### PostgreSQL with Full-Text Search

```python
from retrievers.implementations.postgresql_retriever import PostgreSQLRetriever
import psycopg2

# Configuration
config = {
    "datasources": {
        "postgresql": {
            "host": "localhost",
            "database": "mydb", 
            "username": "user",
            "password": "pass",
            "use_full_text_search": True,
            "text_search_config": "english"
        }
    }
}

# Create connection
conn = psycopg2.connect(
    host="localhost",
    database="mydb",
    user="user", 
    password="pass"
)

# Initialize retriever
retriever = PostgreSQLRetriever(config=config, connection=conn)
await retriever.initialize()

# Use with advanced PostgreSQL features
results = await retriever.get_relevant_context("machine learning algorithms")
```

### MySQL with FULLTEXT Indexes

```python  
from retrievers.implementations.mysql_retriever import MySQLRetriever
import mysql.connector

# Configuration
config = {
    "datasources": {
        "mysql": {
            "host": "localhost",
            "database": "knowledge_base",
            "username": "root",
            "password": "password",
            "use_full_text_search": True,
            "engine": "InnoDB"
        }
    }
}

# Create connection
conn = mysql.connector.connect(
    host="localhost",
    database="knowledge_base",
    user="root",
    password="password"
)

# Initialize retriever  
retriever = MySQLRetriever(config=config, connection=conn)
await retriever.initialize()

# Leverage MySQL FULLTEXT search
results = await retriever.get_relevant_context("database optimization")
```

### Basic SQLite (without QA specialization)

```python
from retrievers.implementations.sqlite_retriever import SQLiteRetriever

# Configuration  
config = {
    "datasources": {
        "sqlite": {
            "db_path": "./data/general_knowledge.db",
            "max_results": 50
        }
    }
}

# Initialize basic SQLite retriever
retriever = SQLiteRetriever(config=config)
await retriever.initialize()

# General-purpose document retrieval
results = await retriever.get_relevant_context("python programming")
```

## Creating New Database Support

### Step 1: Inherit from AbstractSQLRetriever

```python
from retrievers.base.sql_retriever import AbstractSQLRetriever

class OracleRetriever(AbstractSQLRetriever):
    def _get_datasource_name(self) -> str:
        return 'oracle'
```

### Step 2: Implement Required Abstract Methods

```python
async def execute_query(self, sql: str, params: List[Any] = None) -> List[Dict[str, Any]]:
    """Oracle-specific query execution with cx_Oracle"""
    cursor = self.connection.cursor()
    cursor.execute(sql, params or [])
    
    # Convert Oracle rows to dictionaries
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    return [dict(zip(columns, row)) for row in rows]

async def initialize(self) -> None:
    """Oracle-specific initialization"""
    if not self.connection:
        import cx_Oracle
        self.connection = cx_Oracle.connect(self.connection_string)
    
    await self._verify_database_structure()

async def close(self) -> None:
    """Oracle-specific cleanup"""
    if self.connection:
        self.connection.close()
        self.connection = None
```

### Step 3: Add Database-Specific Optimizations

```python  
def _get_search_query(self, query: str, collection_name: str) -> Dict[str, Any]:
    """Oracle-specific search with Text indexing"""
    if self.use_oracle_text_search:
        return {
            "sql": f"""
                SELECT *, SCORE(1) as relevance
                FROM {collection_name}
                WHERE CONTAINS(content, ?, 1) > 0
                ORDER BY SCORE(1) DESC
                ROWNUM <= ?
            """,
            "params": [query, self.max_results],
            "fields": self.default_search_fields + ['relevance']
        }
    
    return super()._get_search_query(query, collection_name)
```

### Step 4: Register with Factory

```python
from retrievers.base.base_retriever import RetrieverFactory
RetrieverFactory.register_retriever('oracle', OracleRetriever)
```

## Creating Domain Specializations

### Step 1: Extend a Database Implementation

```python
from retrievers.implementations.postgresql_retriever import PostgreSQLRetriever

class QAPostgreSQLRetriever(PostgreSQLRetriever):
    """QA specialization of PostgreSQL retriever"""
    
    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        # Add QA-specific configuration
        self.qa_confidence_threshold = 0.3
        self.qa_fields = ['question', 'answer', 'title', 'content']
```

### Step 2: Add Domain-Specific Enhancements

```python
def _get_search_query(self, query: str, collection_name: str) -> Dict[str, Any]:
    """QA-enhanced PostgreSQL search"""
    if "question" in self.qa_fields:
        # Use PostgreSQL FTS optimized for Q&A
        return {
            "sql": f"""
                SELECT *, 
                       ts_rank(to_tsvector('english', question || ' ' || coalesce(answer, '')), 
                              plainto_tsquery('english', %s)) as qa_rank
                FROM {collection_name} 
                WHERE to_tsvector('english', question || ' ' || coalesce(answer, '')) 
                      @@ plainto_tsquery('english', %s)
                ORDER BY qa_rank DESC
                LIMIT %s
            """,
            "params": [query, query, self.max_results],
            "fields": self.qa_fields + ['qa_rank']
        }
    
    return super()._get_search_query(query, collection_name)
```

## Configuration Examples

### Multi-Database Configuration

```yaml
# config.yaml
datasources:
  # Production PostgreSQL
  postgresql:
    host: "prod-db.company.com"
    port: 5432
    database: "knowledge_base"
    username: "app_user"
    password: "secure_password"
    use_full_text_search: true
    text_search_config: "english"
    max_results: 100
    
  # Development SQLite  
  sqlite:
    db_path: "./dev_data/knowledge.db"
    max_results: 20
    
  # QA-specific SQLite
  sqlite_qa:
    db_path: "./qa_data/faq.db"
    max_results: 15
    
  # Analytics MySQL
  mysql:
    host: "analytics-db.company.com"
    port: 3306
    database: "analytics"
    username: "readonly_user"
    password: "readonly_pass"
    use_full_text_search: true
    engine: "InnoDB"
```

### Environment-Based Selection

```python
import os
from retrievers.base.base_retriever import RetrieverFactory

# Select database based on environment
db_type = os.getenv('DATABASE_TYPE', 'sqlite')
retriever = RetrieverFactory.create_retriever(db_type, config=config)
```

## Migration Between Databases

The abstract interface makes it easy to migrate between databases:

```python
# Development: SQLite with QA specialization
dev_retriever = QASSQLRetriever(config=dev_config)

# Production: PostgreSQL (could add QA specialization later)  
prod_retriever = PostgreSQLRetriever(config=prod_config)

# Same interface, different optimizations
for retriever in [dev_retriever, prod_retriever]:
    results = await retriever.get_relevant_context("search query")
    # Process results identically
```

## Design Principles

**Single Responsibility**: Each class has one clear purpose
**Open/Closed**: Open for extension, closed for modification  
**Liskov Substitution**: All SQL retrievers work interchangeably
**Interface Segregation**: Clean abstract interfaces
**Dependency Inversion**: Depend on abstractions, not concretions