# Domain-Agnostic Semantic RAG System - Technical Documentation

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Core Components](#core-components)
4. [Extending to New Domains](#extending-to-new-domains)
5. [Development Guide](#development-guide)
6. [API Reference](#api-reference)
7. [Best Practices](#best-practices)

## Overview

This is a semantic RAG (Retrieval-Augmented Generation) system designed to provide natural language querying capabilities over structured databases. The system is built with domain-agnostic principles, allowing it to be rapidly adapted to different business contexts without code changes.

### Key Features
- **Domain-Agnostic Architecture**: Configure for any business domain through declarative configuration
- **Semantic Query Matching**: Uses vector embeddings to match natural language to SQL templates
- **Template-Based Translation**: YAML-based template system for natural language to SQL conversion
- **Conversation Context**: Maintains conversation history for contextual responses
- **Auto-Template Generation**: Automatically creates query templates from domain configuration
- **Smart Parameter Extraction**: Domain-aware parameter extraction with LLM fallback

### Technology Stack
- **Vector Database**: ChromaDB for semantic search
- **Embeddings**: Ollama with configurable models (default: nomic-embed-text)
- **LLM**: Ollama for inference (default: gemma3:1b)
- **Database**: PostgreSQL, MySQL, SQLite (unified base class with mixins)
- **Configuration**: YAML-based domain and template configuration
- **Validation**: External validation suite for accuracy testing
- **Base Architecture**: Unified IntentSQLRetriever with database-specific implementations

## Architecture

The system follows a layered architecture with clear separation of concerns:

**Note**: The Intent SQL RAG system uses the refactored `IntentSQLRetriever` base classes that inherit from `BaseSQLDatabaseRetriever`, providing unified database operations, environment variable support, and automatic type conversion.

```
┌─────────────────────────────────────────────────────────────┐
│                    User Interface Layer                     │
│  ConversationalDemo, CLI Commands, Query Processing        │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   Orchestration Layer                      │
│              IntentSQLRetriever (Main System Class)        │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                 Semantic Processing Layer                   │
│  Template Matching, Parameter Extraction, Response Gen     │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   Configuration Layer                      │
│  IntentAdapter, Domain Configuration, Template Library     │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   Infrastructure Layer                     │
│  ChromaDB, Ollama Clients, SQL Database Clients           │
│  (PostgreSQL, MySQL, SQLite via unified base)             │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Intent Adapter (`intent_adapter.py`)

The foundation of the system's domain-agnostic design. Manages domain configuration and template libraries.

#### Key Classes:

**IntentAdapter**
- Central class managing domain configuration and template libraries
- Loads YAML-based domain definitions and SQL templates
- Provides template retrieval and domain-specific filtering
- Supports multiple template library files

#### Example Usage:
```python
# Create adapter with domain configuration
adapter = IntentAdapter(
    domain_config_path="config/domain.yaml",
    template_library_path=[
        "config/templates/basic_queries.yaml",
        "config/templates/analytics.yaml"
    ],
    confidence_threshold=0.75,
    verbose=True
)

# Get domain configuration
domain_config = adapter.get_domain_config()

# Get all templates
templates = adapter.get_all_templates()

# Get specific template
template = adapter.get_template_by_id("find_customer_by_name")
```

### 2. Template Library (YAML-based)

Manages query templates that map natural language intent to SQL queries using YAML configuration.

#### Template Structure:
```yaml
templates:
  - id: "find_customer_by_name"
    description: "Find customer by name"
    nl_examples:
      - "Show customer John Smith"
      - "Find customer named Jane"
    parameters:
      - name: "customer_name"
        type: "string"
        description: "Customer name to search for"
        required: true
    sql: "SELECT * FROM customers WHERE name ILIKE %(customer_name)s"
    semantic_tags:
      action: "find"
      primary_entity: "customer"
    result_format: "table"
    version: "1.0.0"
    approved: true
```

### 3. Template Generator (`template_generator.py`)

Automatically generates standard query templates from domain configuration.

#### Key Features:
- **Entity-based Templates**: Creates CRUD operations for each entity
- **Relationship Templates**: Generates join queries based on relationships
- **Aggregation Templates**: Creates summary and analytical queries
- **Filtering Templates**: Generates filtered queries based on entity fields

#### Example Generated Templates:
```python
generator = DomainTemplateGenerator(domain)
library = generator.generate_standard_templates()

# Automatically creates templates like:
# - find_customer_by_id
# - list_orders_by_customer
# - find_orders_by_status
# - calculate_total_revenue
# - find_orders_in_date_range
```

### 4. Domain-Aware Components

#### DomainAwareParameterExtractor
- Extracts parameters using domain knowledge and patterns
- Pattern-based extraction for common data types (IDs, emails, dates, etc.)
- LLM fallback for complex parameter extraction
- Domain vocabulary integration for better matching

#### DomainAwareResponseGenerator
- Generates contextual responses using domain configuration
- Formats results based on field display rules (currency, dates, etc.)
- Supports different response strategies (table vs summary)
- Integrates conversation context for better responses

#### TemplateReranker
- Reranks templates using domain-specific rules and vocabulary
- Applies domain-specific boosting for better template selection
- Uses semantic tags and natural language examples for scoring
- Supports pluggable domain strategies

### 5. Intent SQL System

The intent-based SQL RAG system includes refactored retrievers with unified base classes:

**IntentSQLRetriever Hierarchy:**
```
BaseSQLDatabaseRetriever
└── IntentSQLRetriever (unified base class)
    ├── IntentPostgreSQLRetriever
    ├── IntentMySQLRetriever
    └── IntentSQLiteRetriever (potential)
```

**Legacy Hierarchy (still exists):**
```
BaseRetriever
└── BaseIntentSQLRetriever (legacy base)
    └── [Legacy implementations]
```

**Key Benefits:**
- **Unified Interface**: All intent retrievers share common database operations
- **Environment Variables**: Full support for ${VAR} in configurations
- **Automatic Type Conversion**: Database types converted to Python types
- **Connection Management**: Built-in retry logic and pooling
- **Query Monitoring**: Automatic logging of slow queries and large results

#### Key Components:

**IntentSQLRetriever**
- Main system class coordinating all components
- Manages ChromaDB for semantic search
- Handles conversation context and history
- Integrates domain-aware components

**Query Processing Flow:**
1. **Template Matching**: Vector search finds best matching templates
2. **Reranking**: Domain-specific rules adjust template scores
3. **Parameter Extraction**: Extract parameters using domain patterns + LLM
4. **Validation**: Validate parameters against domain rules
5. **Execution**: Execute SQL query with parameters
6. **Response Generation**: Generate natural language response

### 6. Validation System

A comprehensive validation suite that ensures RAG system responses match actual database results.

#### Key Components:

**RAG Validator (`validate_rag_results.py`)**
- Compares RAG responses with equivalent SQL queries
- Validates result counts and response accuracy
- Provides detailed error analysis and debugging information
- Supports category-based testing and sampling

**SQL Validation Templates (`sql_validation_templates.py`)**
- Mirror RAG query templates with equivalent SQL
- Ensure accurate comparison between RAG and direct SQL results
- Handle different query types (customer, orders, analytics, etc.)

**Test Runner (`run_validation_tests.sh`)**
- Easy-to-use script for running validation tests
- Supports different test categories and sample sizes
- Provides clear pass/fail results with detailed analysis

#### Validation Features:
- **Accuracy Testing**: Verify RAG results match SQL results
- **Count Validation**: Check result count consistency (within tolerance)
- **Template Verification**: Ensure correct template selection
- **Parameter Testing**: Validate parameter extraction accuracy
- **Performance Monitoring**: Track query execution times
- **Error Analysis**: Detailed debugging for failed queries

#### Usage:
```bash
# Basic validation tests
python3 validate_rag_results.py

# Category-specific testing
./run_validation_tests.sh customer
./run_validation_tests.sh orders
./run_validation_tests.sh analytics

# Comprehensive testing
./run_validation_tests.sh full

# Debug mode
python3 validate_rag_results.py --debug --custom "Your query here"
```

#### Validation Results:
```
✅ PASS | RAG:15 SQL:14 | 0.45s | Show orders from customer 123...
❌ FAIL | RAG:0  SQL:25 | 0.32s | Find orders over $500...

📊 Validation Summary:
   Total queries: 8
   Passed: 7 (87.5%)  
   Failed: 1 (12.5%)
   Average time: 0.43s per query
```

## Extending to New Domains

### Step 1: Define Your Domain Configuration

Create a YAML domain configuration file:

```yaml
# healthcare_domain.yaml
domain_name: "Healthcare"
description: "Medical records and patient management system"

entities:
  patient:
    entity_type: "PRIMARY"
    table_name: "patients"
    description: "Patient information"
    primary_key: "patient_id"
    display_name_field: "full_name"
    searchable_fields: ["full_name", "medical_record_number"]
    common_filters: ["date_of_birth", "insurance_provider"]
    default_sort_field: "last_visit_date"

fields:
  patient:
    medical_record_number:
      data_type: "STRING"
      db_column: "mrn"
      description: "Medical Record Number"
      required: true
      searchable: true
      validation_rules:
        - type: "pattern"
          value: "^MR\\d{6}$"
      aliases: ["MRN", "record number", "patient ID"]
    
    full_name:
      data_type: "STRING"
      db_column: "full_name"
      description: "Patient full name"
      required: true
      searchable: true
      display_format: "name"

relationships:
  - name: "patient_appointments"
    from_entity: "patient"
    to_entity: "appointment"
    relation_type: "ONE_TO_MANY"
    from_field: "patient_id"
    to_field: "patient_id"
    description: "Patient has many appointments"

vocabulary:
  entity_synonyms:
    patient: ["client", "individual", "person", "case"]
    appointment: ["visit", "consultation", "session"]
    diagnosis: ["condition", "illness", "disorder"]
  
  action_verbs:
    find: ["locate", "search", "lookup", "retrieve", "show"]
    schedule: ["book", "arrange", "set up", "plan"]
    diagnose: ["identify", "determine", "assess"]
  
  time_expressions:
    "last visit": "30"
    "recent": "7"
    "this quarter": "90"
    "past year": "365"
```

### Step 2: Create Domain-Specific Templates

Create YAML template files:

```yaml
# healthcare_templates.yaml
templates:
  - id: "patient_medical_history"
    description: "Get comprehensive medical history for a patient"
    nl_examples:
      - "Show medical history for patient MR123456"
      - "Get all records for John Smith"
      - "Patient history for MRN MR789012"
    parameters:
      - name: "patient_identifier"
        type: "string"
        description: "Patient MRN or name"
        required: true
    sql: |
      SELECT p.full_name, p.date_of_birth, 
             a.appointment_date, a.chief_complaint,
             d.diagnosis_code, d.diagnosis_description,
             pr.procedure_name, pr.procedure_date
      FROM patients p
      LEFT JOIN appointments a ON p.patient_id = a.patient_id
      LEFT JOIN diagnoses d ON a.appointment_id = d.appointment_id
      LEFT JOIN procedures pr ON a.appointment_id = pr.appointment_id
      WHERE p.medical_record_number = %(patient_identifier)s 
         OR p.full_name ILIKE %(patient_identifier)s
      ORDER BY a.appointment_date DESC
    semantic_tags:
      action: "find"
      primary_entity: "patient"
      secondary_entity: "appointment"
      qualifiers: ["medical_history", "comprehensive"]
    result_format: "summary"
    version: "1.0.0"
    approved: true
```

### Step 3: Create Domain-Specific Strategy

Create a domain strategy for specialized reranking:

```python
# domain_strategies/healthcare.py
from typing import Dict, Any
from .base import DomainStrategy

class HealthcareDomainStrategy(DomainStrategy):
    """Healthcare-specific domain strategy for template reranking"""
    
    def calculate_domain_boost(self, template_info: Dict, user_query: str, domain_config: Dict) -> float:
        """Calculate domain-specific boost for healthcare queries"""
        boost = 0.0
        template = template_info['template']
        query_lower = user_query.lower()
        
        # Medical terminology boosting
        medical_terms = ['diagnosis', 'treatment', 'medication', 'symptoms', 'prescription']
        for term in medical_terms:
            if term in query_lower:
                boost += 0.1
        
        # Patient-specific boosting
        if 'patient' in query_lower and 'patient' in template.get('semantic_tags', {}).get('primary_entity', ''):
            boost += 0.15
        
        # Emergency/urgent boosting
        urgent_terms = ['emergency', 'urgent', 'critical', 'immediate']
        if any(term in query_lower for term in urgent_terms):
            boost += 0.2
        
        return boost
```

### Step 4: Configure the Retriever

Update your configuration to use the new domain:

```yaml
# config/adapters.yaml
datasources:
  healthcare_intent:
    type: "intent"
    provider: "postgres"
    config:
      domain_config_path: "config/healthcare_domain.yaml"
      template_library_path: 
        - "config/healthcare_templates.yaml"
        - "config/healthcare_analytics.yaml"
      template_collection_name: "healthcare_query_templates"
      confidence_threshold: 0.75
      max_templates: 5
      chroma_persist: true
      chroma_persist_path: "./chroma_db/healthcare_templates"
```

### Step 5: Create Validation Templates

Create corresponding SQL validation templates:

```python
# healthcare_validation_templates.py
class HealthcareValidationTemplates:
    @staticmethod
    def get_patient_history_sql(parameters: Dict[str, Any]) -> Tuple[str, List]:
        sql = """
            SELECT p.full_name, p.date_of_birth, 
                   a.appointment_date, a.chief_complaint,
                   d.diagnosis_code, d.diagnosis_description
            FROM patients p
            LEFT JOIN appointments a ON p.patient_id = a.patient_id
            LEFT JOIN diagnoses d ON a.appointment_id = d.appointment_id
            WHERE 1=1
        """
        
        params = []
        if 'patient_identifier' in parameters:
            sql += " AND (p.medical_record_number = %s OR p.full_name ILIKE %s)"
            params.extend([parameters['patient_identifier'], f"%{parameters['patient_identifier']}%"])
        
        sql += " ORDER BY a.appointment_date DESC LIMIT 100"
        return sql, params
```

## Development Guide

### Setting Up Development Environment

1. **Install Dependencies**
```bash
pip install -r requirements.txt
```

2. **Set Up Environment Variables**
```bash
# Copy example environment file
cp env.example .env

# Configure your settings
export OLLAMA_BASE_URL="http://localhost:11434"
export OLLAMA_EMBEDDING_MODEL="nomic-embed-text"
export OLLAMA_INFERENCE_MODEL="gemma3:1b"
export POSTGRES_HOST="localhost"
export POSTGRES_PORT="5432"
export POSTGRES_DB="your_database"
export POSTGRES_USER="your_user"
export POSTGRES_PASSWORD="your_password"
```

3. **Initialize Database**
```python
# Run setup script
python setup_schema.py
```

4. **Test Connection**
```python
# Test all components
python test_connection.py
```

### Testing Your Domain

1. **Unit Tests for Domain Configuration**
```python
def test_domain_configuration():
    # Load domain configuration
    adapter = IntentAdapter(domain_config_path="config/your_domain.yaml")
    domain_config = adapter.get_domain_config()
    
    # Test entity creation
    assert "your_entity" in domain_config['entities']
    assert domain_config['entities']["your_entity"]['table_name'] == "your_table"
    
    # Test field validation
    field = domain_config['fields']["your_entity"]["your_field"]
    assert field['data_type'] == "STRING"
    assert field['required'] == True
```

2. **Integration Tests**
```python
def test_end_to_end_query():
    # Initialize system
    config = {
        "type": "intent",
        "provider": "postgres",
        "config": {
            "domain_config_path": "config/your_domain.yaml",
            "template_library_path": "config/your_templates.yaml"
        }
    }
    
    retriever = IntentPostgreSQLRetriever(config)
    await retriever.initialize()
    
    # Test query processing
    result = await retriever.get_relevant_context("Find customer John Smith")
    
    assert len(result) > 0
    assert result[0]['confidence'] > 0.5
```

3. **Template Testing**
```python
def test_template_loading():
    adapter = IntentAdapter(
        domain_config_path="config/your_domain.yaml",
        template_library_path="config/your_templates.yaml"
    )
    
    templates = adapter.get_all_templates()
    
    # Verify expected templates were loaded
    expected_templates = [
        "find_customer_by_id",
        "list_orders_by_customer",
        "find_orders_by_status"
    ]
    
    template_ids = [t['id'] for t in templates]
    for template_id in expected_templates:
        assert template_id in template_ids
```

### Performance Optimization

1. **Embedding Cache**
```python
# Implement embedding caching for better performance
class CachedEmbeddingClient(OllamaEmbeddingClient):
    def __init__(self):
        super().__init__()
        self.cache = {}
    
    def get_embedding(self, text: str):
        if text in self.cache:
            return self.cache[text]
        
        embedding = super().get_embedding(text)
        self.cache[text] = embedding
        return embedding
```

2. **Template Indexing**
```python
# Create indexes for better template matching
def optimize_chromadb(retriever):
    # Pre-warm embedding cache
    all_queries = [
        "common query pattern 1",
        "common query pattern 2",
        # ... add your common patterns
    ]
    
    for query in all_queries:
        retriever.embedding_client.get_embedding(query)
```

3. **Database Query Optimization**
```python
# Add indexes to your database
CREATE INDEX idx_customers_name ON customers(name);
CREATE INDEX idx_orders_customer_id ON orders(customer_id);
CREATE INDEX idx_orders_date ON orders(order_date);
```

## API Reference

### Core Classes

#### IntentAdapter
```python
class IntentAdapter:
    def __init__(self, domain_config_path: str, template_library_path: str, 
                 confidence_threshold: float = 0.75, verbose: bool = False)
    def get_domain_config(self) -> Optional[Dict[str, Any]]
    def get_template_library(self) -> Optional[Dict[str, Any]]
    def get_template_by_id(self, template_id: str) -> Optional[Dict[str, Any]]
    def get_all_templates(self) -> List[Dict[str, Any]]
```

#### IntentSQLRetriever
```python
class IntentSQLRetriever(BaseSQLDatabaseRetriever):
    def __init__(self, config: Dict[str, Any], domain_adapter=None, connection: Any = None)
    
    async def initialize(self) -> None
    async def get_relevant_context(self, query: str, api_key: Optional[str] = None,
                                 collection_name: Optional[str] = None, **kwargs) -> List[Dict[str, Any]]
    async def close(self) -> None
```

#### DomainAwareParameterExtractor
```python
class DomainAwareParameterExtractor:
    def __init__(self, inference_client, domain_config: Optional[Dict[str, Any]] = None)
    
    async def extract_parameters(self, user_query: str, template: Dict) -> Dict[str, Any]
    def validate_parameters(self, parameters: Dict[str, Any], template: Dict) -> Tuple[bool, List[str]]
```

#### DomainAwareResponseGenerator
```python
class DomainAwareResponseGenerator:
    def __init__(self, inference_client, domain_config: Optional[Dict[str, Any]] = None)
    
    async def generate_response(self, user_query: str, results: List[Dict], template: Dict, 
                         error: Optional[str] = None, conversation_context: Optional[str] = None) -> str
```

#### TemplateReranker
```python
class TemplateReranker:
    def __init__(self, domain_config: Optional[Dict[str, Any]] = None)
    
    def rerank_templates(self, templates: List[Dict], user_query: str) -> List[Dict]
    def explain_ranking(self, templates: List[Dict]) -> str
```

### Configuration Structure

#### Domain Configuration (YAML)
```yaml
domain_name: "Your Domain"
description: "Domain description"

entities:
  entity_name:
    entity_type: "PRIMARY"
    table_name: "table_name"
    description: "Entity description"
    primary_key: "id"
    searchable_fields: ["field1", "field2"]

fields:
  entity_name:
    field_name:
      data_type: "STRING"
      db_column: "column_name"
      description: "Field description"
      required: true
      searchable: true
      validation_rules:
        - type: "pattern"
          value: "^regex$"
      aliases: ["alias1", "alias2"]

relationships:
  - name: "relationship_name"
    from_entity: "entity1"
    to_entity: "entity2"
    relation_type: "ONE_TO_MANY"
    from_field: "field1"
    to_field: "field2"

vocabulary:
  entity_synonyms:
    entity: ["synonym1", "synonym2"]
  action_verbs:
    find: ["locate", "search", "lookup"]
  time_expressions:
    "recent": "7"
```

#### Template Configuration (YAML)
```yaml
templates:
  - id: "template_id"
    description: "Template description"
    nl_examples:
      - "Example query 1"
      - "Example query 2"
    parameters:
      - name: "param_name"
        type: "string"
        description: "Parameter description"
        required: true
    sql: "SELECT * FROM table WHERE condition = %(param_name)s"
    semantic_tags:
      action: "find"
      primary_entity: "entity"
    result_format: "table"
    version: "1.0.0"
    approved: true
```

## Best Practices

### Domain Design
1. **Start Simple**: Begin with core entities and relationships
2. **Use Consistent Naming**: Follow consistent naming conventions across entities
3. **Define Clear Relationships**: Ensure all entity relationships are properly defined
4. **Comprehensive Vocabulary**: Include all synonyms and action verbs users might use
5. **Validation Rules**: Add appropriate validation rules for data integrity

### Template Creation
1. **Natural Examples**: Provide diverse, natural language examples
2. **Clear Parameters**: Use descriptive parameter names and clear validation
3. **Semantic Tags**: Use semantic tags for better intent matching
4. **SQL Optimization**: Ensure SQL queries are optimized with proper indexes
5. **Error Handling**: Include proper error handling in SQL queries

### Performance
1. **Index Strategy**: Create appropriate database indexes
2. **Caching**: Implement caching for embeddings and frequent queries
3. **Batch Processing**: Use batch operations where possible
4. **Monitor Performance**: Track query performance and optimize bottlenecks
5. **Resource Management**: Properly manage database connections and memory

### Security
1. **SQL Injection Prevention**: Always use parameterized queries
2. **Access Control**: Implement proper access control through configuration
3. **Data Validation**: Validate all user inputs
4. **Audit Logging**: Log all queries and results for audit purposes
5. **Sensitive Data**: Handle sensitive data appropriately

This comprehensive documentation should enable new developers to understand the system architecture and successfully extend it to new domains. The system's domain-agnostic design makes it highly adaptable while maintaining consistency and best practices across different business contexts.