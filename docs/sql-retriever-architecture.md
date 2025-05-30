# SQL Retriever Architecture Summary

```
BaseRetriever (core functionality for all retrievers)
│
└── AbstractSQLRetriever (database-agnostic SQL base)
    │   • Common SQL functionality
    │   • Text tokenization & similarity
    │   • Domain adapter integration
    │   • Abstract methods for DB-specific implementation
    │
    ├── SQLiteRetriever (SQLite-specific implementation)
    │   │   • SQLite connection management
    │   │   • SQLite query execution
    │   │   • SQLite schema verification
    │   │
    │   └── QASSQLRetriever (QA domain specialization)
    │       • Question/Answer field prioritization
    │       • QA-optimized similarity scoring
    │       • Token-based search for FAQ scenarios
    │       • QA-specific result formatting
    │
    ├── PostgreSQLRetriever (PostgreSQL-specific)
    │   • Full-text search with ts_vector
    │   • PostgreSQL connection via psycopg2
    │   • Advanced query optimizations
    │
    └── MySQLRetriever (MySQL-specific)
        • FULLTEXT indexes with MATCH() AGAINST()
        • MySQL connection via mysql-connector
        • Optimized LIKE search fallback
```

## 🔄 Details

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

### For New Databases
```python
class OracleRetriever(AbstractSQLRetriever):
    def _get_datasource_name(self) -> str:
        return 'oracle'
    
    async def execute_query(self, sql, params):
        # Oracle-specific implementation
    
    async def initialize(self):
        # Oracle connection setup
    
    async def close(self):
        # Oracle cleanup
```

### For Domain Specializations
```python
class LegalPostgreSQLRetriever(PostgreSQLRetriever):
    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        # Legal-specific configuration
    
    def _get_search_query(self, query, collection):
        # Legal-specific query optimizations
        return super()._get_search_query(query, collection)
```

### Example Future Extensions
```python
# Multi-domain support
class LegalQAPostgreSQLRetriever(PostgreSQLRetriever):
    """Combines legal document search with Q&A capabilities"""

# Cross-database federation  
class FederatedSQLRetriever(AbstractSQLRetriever):
    """Searches across multiple SQL databases"""

# AI-enhanced search
class AIEnhancedMySQLRetriever(MySQLRetriever):
    """Adds semantic similarity using embeddings"""
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

## Design Principles

**Single Responsibility**: Each class has one clear purpose
**Open/Closed**: Open for extension, closed for modification  
**Liskov Substitution**: All SQL retrievers work interchangeably
**Interface Segregation**: Clean abstract interfaces
**Dependency Inversion**: Depend on abstractions, not concretions