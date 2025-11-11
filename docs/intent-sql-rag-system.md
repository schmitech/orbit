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

The system follows a layered architecture with clear separation of concerns, built on a unified base class hierarchy that eliminates code duplication across database implementations.

**Note**: The Intent SQL RAG system uses the refactored `IntentSQLRetriever` base classes that inherit from `BaseSQLDatabaseRetriever`, providing unified database operations, environment variable support, and automatic type conversion.

```
┌─────────────────────────────────────────────────────────────┐
│                    User Interface Layer                     │
│  ConversationalDemo, CLI Commands, Query Processing        │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   Orchestration Layer                      │
│              IntentSQLRetriever (Unified Base Class)       │
│  ├── IntentPostgreSQLRetriever                             │
│  ├── IntentMySQLRetriever                                  │
│  └── IntentSQLiteRetriever                                 │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                 Semantic Processing Layer                   │
│  DomainParameterExtractor, TemplateReranker,               │
│  DomainResponseGenerator, TemplateProcessor                │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                 Domain Strategy Layer                       │
│  DomainStrategyRegistry, GenericDomainStrategy,            │
│  Custom Strategies                                         │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   Configuration Layer                      │
│  IntentAdapter, DomainConfig, Template Library             │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   Infrastructure Layer                     │
│  ChromaDB, Ollama Clients, SQL Database Clients           │
│  (PostgreSQL, MySQL, SQLite via unified base)             │
└─────────────────────────────────────────────────────────────┘
```

### Unified Base Class Hierarchy

The system uses a inheritance hierarchy to minimize code duplication:

```
BaseRetriever
└── AbstractSQLRetriever
    └── BaseSQLDatabaseRetriever
        ├── SQLConnectionMixin
        ├── SQLTypeConversionMixin
        └── SQLQueryExecutionMixin
            └── IntentSQLRetriever (Unified Intent Base)
                ├── IntentPostgreSQLRetriever
                ├── IntentMySQLRetriever
                └── IntentSQLiteRetriever
```

**Key Benefits:**
- **Unified Interface**: All intent retrievers share common database operations
- **Environment Variables**: Full support for `${VAR}` in configurations
- **Automatic Type Conversion**: Database types converted to Python types
- **Connection Management**: Built-in retry logic and pooling
- **Query Monitoring**: Automatic logging of slow queries and large results

## Core Components

### 1. Intent Adapter (`intent_adapter.py`)

The foundation of the system's domain-agnostic design. Manages domain configuration and template libraries as a specialized document adapter.

#### Key Classes:

**IntentAdapter** (extends `DocumentAdapter`)
- Central class managing domain configuration and template libraries
- Loads YAML-based domain definitions and SQL templates
- Provides template retrieval and domain-specific filtering
- Supports multiple template library files
- Formats SQL query results into structured documents
- Integrates with the global adapter registry

#### Example Usage:
```python
# Create adapter with domain configuration
adapter = IntentAdapter(
    domain_config_path="config/domain.yaml",
    template_library_path=[
        "config/templates/basic_queries.yaml",
        "config/templates/analytics.yaml"
    ],
    confidence_threshold=0.1,
    verbose=True
)

# Get domain configuration
domain_config = adapter.get_domain_config()

# Get all templates
templates = adapter.get_all_templates()

# Get specific template
template = adapter.get_template_by_id("find_customer_by_name")

# Format query results
formatted_doc = adapter.format_document(raw_results, metadata)
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

### 3. AI-Powered Template Generator (`utils/sql-intent-template/`)

Template generation system that uses AI to analyze natural language queries and generate SQL templates.

#### Key Features:
- **AI Query Analysis**: Uses LLM to understand query intent and structure
- **Schema-Aware Generation**: Analyzes database schema to create accurate SQL
- **Query Grouping**: Groups similar queries to create reusable templates
- **Semantic Tagging**: Automatically generates semantic tags for better matching
- **Validation System**: Validates generated templates for correctness
- **Configuration-Driven**: Highly configurable generation parameters

#### Template Generator Components:

**TemplateGenerator** (`template_generator.py`)
- Main class for AI-powered template generation
- Analyzes natural language queries using LLM
- Groups similar queries and generates parameterized SQL
- Supports multiple inference providers (Ollama, OpenAI, etc.)

**Configuration System** (`configs/`)
- `template_generator_config.yaml`: Generation parameters and settings
- `config_selector.py`: Dynamic configuration selection
- Shell scripts for automated generation workflows

#### Example Usage:
```bash
# Generate templates from test queries
python utils/sql-intent-template/template_generator.py \
    --schema examples/postgres/customer-order.sql \
    --queries examples/postgres/test/test_queries.md \
    --output generated_templates.yaml \
    --provider ollama

# Quick generation with defaults
./utils/sql-intent-template/quick_generate.sh

# Full generation workflow
./utils/sql-intent-template/generate_templates.sh
```

#### Generated Template Structure:
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
    approved: false
```

### 4. Domain-Aware Components

#### DomainParameterExtractor (`domain/extraction/extractor.py`)
- Orchestrates parameter extraction using composable services
- Uses pattern-based extraction for common data types (IDs, emails, dates, etc.)
- Integrates with domain strategies for specialized extraction
- Provides LLM fallback for complex parameter extraction
- Supports semantic type extraction with domain-specific patterns

#### DomainResponseGenerator (`domain/response/generator.py`)
- Generates contextual responses using domain configuration
- Formats results based on field display rules (currency, dates, etc.)
- Supports different response strategies (table vs summary)
- Integrates conversation context for better responses
- Uses domain strategy priorities for field ordering

#### TemplateReranker (`template_reranker.py`)
- Reranks templates using domain-specific rules and vocabulary
- Applies domain-specific boosting for better template selection
- Uses semantic tags and natural language examples for scoring
- Integrates with domain strategy registry for specialized reranking
- Supports both generic and domain-specific reranking strategies

#### TemplateProcessor (`template_processor.py`)
- Processes and validates templates before execution
- Handles template parameter validation
- Manages template metadata and configuration
- Integrates with domain configuration for processing rules

### 5. Domain Strategy System

The system uses a domain strategy architecture for specialized template reranking and parameter extraction:

**DomainStrategyRegistry** (`domain_strategies/registry.py`)
- Manages built-in and custom domain strategies
- Automatically selects appropriate strategy based on domain name/type
- Falls back to `GenericDomainStrategy` when no specific strategy found
- Supports dynamic strategy registration

**Built-in Strategies:**
- **GenericDomainStrategy**: Configuration-driven strategy for all domains (automatically used as fallback)

**Custom Strategy Support:**
- Register custom strategies for specialized domains
- Extend `DomainStrategy` base class
- Implement domain-specific pattern matching and boosting

#### Key Components:

**DomainStrategy** (Abstract Base Class)
- `get_domain_names()`: Return list of handled domain names
- `calculate_domain_boost()`: Calculate domain-specific template boosting
- `get_pattern_matchers()`: Return domain-specific pattern matching functions
- `extract_domain_parameters()`: Extract domain-specific parameters
- `get_semantic_extractors()`: Return semantic type extractors
- `get_summary_field_priority()`: Get field priority for summaries

**Query Processing Flow:**
1. **Domain Strategy Selection**: Registry selects appropriate strategy
2. **Template Matching**: Vector search finds best matching templates
3. **Domain Reranking**: Domain-specific rules adjust template scores
4. **Parameter Extraction**: Extract parameters using domain patterns + LLM
5. **Validation**: Validate parameters against domain rules
6. **Execution**: Execute SQL query with parameters
7. **Response Generation**: Generate natural language response with domain formatting

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
python validate_rag_results.py

# Category-specific testing
./run_validation_tests.sh customer
./run_validation_tests.sh orders
./run_validation_tests.sh analytics

# Comprehensive testing
./run_validation_tests.sh full

# Debug mode
python validate_rag_results.py --debug --custom "Your query here"
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

Create a domain strategy for specialized reranking and parameter extraction:

```python
# domain_strategies/healthcare.py
from typing import Dict, Any, Optional
from .base import DomainStrategy

class HealthcareDomainStrategy(DomainStrategy):
    """Healthcare-specific domain strategy for template reranking and parameter extraction"""
    
    def get_domain_names(self) -> list:
        """Return list of domain names this strategy handles"""
        return ['healthcare', 'medical', 'patient', 'clinical']
    
    def calculate_domain_boost(self, template_info: Dict, query: str, domain_config: Dict) -> float:
        """Calculate domain-specific boost for healthcare queries"""
        boost = 0.0
        template = template_info['template']
        query_lower = query.lower()
        
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
    
    def get_pattern_matchers(self) -> Dict[str, Any]:
        """Return healthcare-specific pattern matching functions"""
        return {
            'medical_context': self._is_medical_context,
            'patient_context': self._is_patient_context,
            'urgent_context': self._is_urgent_context
        }
    
    def extract_domain_parameters(self, query: str, param: Dict, domain_config: Any) -> Optional[Any]:
        """Extract healthcare-specific parameters"""
        param_name = param.get('name', '').lower()
        
        # Extract MRN (Medical Record Number)
        if 'mrn' in param_name or 'medical_record' in param_name:
            return self._extract_mrn(query)
        
        # Extract diagnosis codes
        if 'diagnosis' in param_name or 'icd' in param_name:
            return self._extract_diagnosis_code(query)
        
        return None
    
    def get_semantic_extractors(self) -> Dict[str, callable]:
        """Return semantic type extractors for healthcare domain"""
        return {
            'mrn': self._extract_mrn,
            'diagnosis_code': self._extract_diagnosis_code,
            'medication_name': self._extract_medication_name
        }
    
    def get_summary_field_priority(self, field_name: str, field_config: Any) -> int:
        """Get field priority for healthcare summaries"""
        healthcare_priorities = {
            'patient_id': 100,
            'full_name': 95,
            'diagnosis': 90,
            'medication': 85,
            'visit_date': 80
        }
        return healthcare_priorities.get(field_name, 50)
    
    def _is_medical_context(self, text: str) -> bool:
        """Check if text is in medical context"""
        medical_indicators = ['patient', 'diagnosis', 'treatment', 'medication', 'symptoms']
        return any(term in text.lower() for term in medical_indicators)
    
    def _extract_mrn(self, query: str) -> Optional[str]:
        """Extract Medical Record Number from query"""
        import re
        mrn_pattern = r'MRN\s*[:#-]?\s*([A-Z]?\d{6,8})'
        match = re.search(mrn_pattern, query, re.IGNORECASE)
        return match.group(1) if match else None
```

### Step 4: Register the Custom Strategy

Register your custom strategy with the domain strategy registry:

```python
# In your application initialization
from retrievers.implementations.intent.domain_strategies.registry import DomainStrategyRegistry
from retrievers.implementations.intent.domain_strategies.healthcare import HealthcareDomainStrategy

# Register the custom strategy
DomainStrategyRegistry.register_strategy("healthcare", HealthcareDomainStrategy)
DomainStrategyRegistry.register_strategy("medical", HealthcareDomainStrategy)
DomainStrategyRegistry.register_strategy("patient", HealthcareDomainStrategy)
```

### Step 5: Configure the Retriever

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
      confidence_threshold: 0.1
      max_templates: 5
      chroma_persist: true
      chroma_persist_path: "./chroma_db/healthcare_templates"
```

### Step 6: Create Validation Templates

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
./install/setup.sh --profile development
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
    assert result[0]['confidence'] > 0.1  # Updated threshold
```

3. **Domain Strategy Tests**
```python
def test_custom_domain_strategy():
    # Test custom domain strategy
    from retrievers.implementations.intent.domain_strategies.registry import DomainStrategyRegistry
    from retrievers.implementations.intent.domain_strategies.healthcare import HealthcareDomainStrategy
    
    # Register strategy
    DomainStrategyRegistry.register_strategy("healthcare", HealthcareDomainStrategy)
    
    # Test strategy selection
    strategy = DomainStrategyRegistry.get_strategy("healthcare", None)
    assert isinstance(strategy, HealthcareDomainStrategy)
    
    # Test domain names
    assert "healthcare" in strategy.get_domain_names()
    assert "medical" in strategy.get_domain_names()
```

4. **Template Testing**
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
class IntentAdapter(DocumentAdapter):
    def __init__(self, domain_config_path: Optional[str] = None,
                 template_library_path: Optional[Union[str, List[str]]] = None,
                 confidence_threshold: float = 0.1, verbose: bool = False,
                 config: Dict[str, Any] = None, **kwargs)
    
    def get_domain_config(self) -> Optional[Dict[str, Any]]
    def get_template_library(self) -> Optional[Dict[str, Any]]
    def get_template_by_id(self, template_id: str) -> Optional[Dict[str, Any]]
    def get_all_templates(self) -> List[Dict[str, Any]]
    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]
    def extract_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]
    def apply_domain_specific_filtering(self, context_items: List[Dict[str, Any]], 
                                      query: str) -> List[Dict[str, Any]]
```

#### IntentSQLRetriever
```python
class IntentSQLRetriever(BaseSQLDatabaseRetriever):
    def __init__(self, config: Dict[str, Any], domain_adapter=None, connection: Any = None, **kwargs)
    
    async def initialize(self) -> None
    async def get_relevant_context(self, query: str, api_key: Optional[str] = None,
                                 collection_name: Optional[str] = None, **kwargs) -> List[Dict[str, Any]]
    async def close(self) -> None
```

#### DomainParameterExtractor
```python
class DomainParameterExtractor:
    def __init__(self, inference_client, domain_config: Optional[Dict[str, Any]] = None)
    
    async def extract_parameters(self, user_query: str, template: Dict) -> Dict[str, Any]
    def validate_parameters(self, parameters: Dict[str, Any], template: Dict) -> Tuple[bool, List[str]]
    def _initialize_components(self) -> None
```

#### DomainResponseGenerator
```python
class DomainResponseGenerator:
    def __init__(self, domain_config: Any, domain_strategy: Optional[Any] = None)
    
    async def generate_response(self, user_query: str, results: List[Dict], template: Dict, 
                         error: Optional[str] = None, conversation_context: Optional[str] = None) -> str
```

#### TemplateReranker
```python
class TemplateReranker:
    def __init__(self, domain_config: Any)
    
    def rerank_templates(self, templates: List[Dict], user_query: str) -> List[Dict]
    def explain_ranking(self, templates: List[Dict]) -> str
```

#### DomainStrategyRegistry
```python
class DomainStrategyRegistry:
    _builtin_strategies = []  # All domains now use GenericDomainStrategy with YAML config
    _custom_strategies: Dict[str, Type[DomainStrategy]] = {}
    
    @classmethod
    def get_strategy(cls, domain_name: Optional[str], domain_config: Optional[Any] = None) -> Optional[DomainStrategy]
    
    @classmethod
    def register_strategy(cls, domain_name: str, strategy_class: Type[DomainStrategy])
    
    @classmethod
    def list_available_domains(cls) -> list
```

#### DomainStrategy (Abstract Base Class)
```python
class DomainStrategy(ABC):
    @abstractmethod
    def get_domain_names(self) -> list
    
    @abstractmethod
    def calculate_domain_boost(self, template_info: Dict, query: str, domain_config: Dict) -> float
    
    @abstractmethod
    def get_pattern_matchers(self) -> Dict[str, Any]
    
    @abstractmethod
    def extract_domain_parameters(self, query: str, param: Dict, domain_config: Any) -> Optional[Any]
    
    @abstractmethod
    def get_semantic_extractors(self) -> Dict[str, callable]
    
    @abstractmethod
    def get_summary_field_priority(self, field_name: str, field_config: Any) -> int
```

### Configuration Structure

#### Domain Configuration (YAML)
```yaml
domain_name: "E-Commerce"
description: "Customer order management system"

# Domain metadata for strategy selection
domain_type: ecommerce
semantic_types:
  order_identifier:
    description: "Unique identifier for an order"
    patterns: ["order", "id", "number", "#"]
    regex_patterns:
      - 'order\s+(?:number\s+|#\s*|id\s+)?(\d+)'
      - '#\s*(\d+)'
      - '\b(\d{4,})\b'
  customer_identifier:
    description: "Unique identifier for a customer"
    patterns: ["customer", "client", "buyer", "user"]
    regex_patterns:
      - 'customer\s+(?:number\s+|#\s*|id\s+)?(\d+)'
  monetary_amount:
    description: "Currency amounts"
    patterns: ["amount", "total", "price", "cost", "sum"]
    regex_patterns:
      - '\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)'
      - '(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:dollars?|usd)'

entities:
  customer:
    name: customer
    entity_type: primary
    table_name: customers
    description: Customer information
    primary_key: id
    display_name_field: name
    searchable_fields:
      - name
      - email
      - phone
    common_filters:
      - city
      - country
      - created_at
    default_sort_field: created_at
    default_sort_order: DESC

fields:
  customer:
    name:
      name: name
      data_type: string
      db_column: name
      description: Customer name
      required: true
      searchable: true
      filterable: true
      sortable: true
      aliases:
        - customer name
        - client name
        - buyer name
      # NEW: Semantic metadata
      semantic_type: person_name
      summary_priority: 9
      extraction_hints:
        look_for_quotes: true
        capitalization_required: true
    email:
      name: email
      data_type: string
      db_column: email
      description: Customer email
      required: true
      searchable: true
      filterable: true
      sortable: true
      display_format: email
      semantic_type: email_address
      summary_priority: 8

relationships:
  - name: "customer_orders"
    from_entity: "customer"
    to_entity: "order"
    relation_type: "ONE_TO_MANY"
    from_field: "id"
    to_field: "customer_id"
    description: "Customer has many orders"

vocabulary:
  entity_synonyms:
    customer: ["client", "buyer", "user", "person"]
    order: ["purchase", "transaction", "sale"]
  action_verbs:
    find: ["locate", "search", "lookup", "retrieve", "show"]
    calculate: ["compute", "total", "sum", "count"]
  time_expressions:
    "recent": "7"
    "last month": "30"
    "this quarter": "90"
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