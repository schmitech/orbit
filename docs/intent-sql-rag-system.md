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
- **Plugin System**: Extensible processing pipeline with custom plugins
- **Conversation Context**: Maintains conversation history for contextual responses
- **Auto-Template Generation**: Automatically creates query templates from domain configuration
- **Smart Parameter Extraction**: Domain-aware parameter extraction with LLM fallback

### Technology Stack
- **Vector Database**: ChromaDB for semantic search
- **Embeddings**: Ollama with configurable models (default: nomic-embed-text)
- **LLM**: Ollama for inference (default: gemma3:1b)
- **Database**: PostgreSQL (extensible to other databases)
- **Configuration**: YAML-based domain and template configuration
- **Consistency**: Shared configuration modules for demo consistency
- **Validation**: Comprehensive validation suite for accuracy testing

## Architecture

The system follows a layered architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                    User Interface Layer                     │
│  ConversationalDemo, CLI Commands, Query Processing        │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   Orchestration Layer                      │
│              RAGSystem (Main System Class)                 │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Plugin System Layer                     │
│  PluginManager, Pre/Post Processing, Enhancement Plugins   │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                 Semantic Processing Layer                   │
│  Template Matching, Parameter Extraction, Response Gen     │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   Configuration Layer                      │
│  DomainConfiguration, TemplateLibrary, Vocabulary         │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   Infrastructure Layer                     │
│    ChromaDB, Ollama Clients, PostgreSQL Client            │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Domain Configuration (`domain_configuration.py`)

The foundation of the system's domain-agnostic design. Defines business entities, relationships, and vocabulary.

#### Key Classes:

**DomainConfiguration**
- Central class managing the entire domain definition
- Contains entities, fields, relationships, and vocabulary
- Supports YAML serialization for configuration management

**DomainEntity**
- Represents business entities (e.g., Customer, Order, Product)
- Defines entity type, database mapping, and searchable fields
- Supports different entity types: PRIMARY, SECONDARY, TRANSACTION, LOOKUP

**DomainField**
- Defines entity attributes with comprehensive metadata
- Includes data types, validation rules, display formatting
- Supports aliases for natural language matching

**DomainRelationship**
- Models relationships between entities
- Supports ONE_TO_MANY, MANY_TO_ONE, MANY_TO_MANY relationships
- Used for automatic join generation in templates

#### Example Usage:
```python
# Create domain
domain = DomainConfiguration("E-Commerce", "Customer order management")

# Add entity
customer_entity = DomainEntity(
    name="customer",
    entity_type=EntityType.PRIMARY,
    table_name="customers",
    description="Customer information",
    primary_key="id",
    searchable_fields=["name", "email"]
)
domain.add_entity(customer_entity)

# Add field with validation
domain.add_field("customer", DomainField(
    name="email",
    data_type=DataType.STRING,
    db_column="email",
    description="Customer email",
    validation_rules=[{"type": "pattern", "value": r"^[\w\.-]+@[\w\.-]+\.\w+$"}],
    display_format="email"
))
```

### 2. Template Library (`template_library.py`)

Manages query templates that map natural language intent to SQL queries.

#### Key Classes:

**QueryTemplateBuilder**
- Fluent API for creating query templates
- Supports method chaining for intuitive template construction
- Handles semantic tagging and parameter definition

**TemplateLibrary**
- Container for managing collections of templates
- Provides search, filtering, and organization capabilities
- Supports YAML import/export for template management

**TemplateParameter**
- Advanced parameter definitions with validation
- Supports different parameter types and constraints
- Includes default values and required flags

#### Example Usage:
```python
# Build template using fluent API
template = (QueryTemplateBuilder("find_customer_by_name")
    .with_description("Find customer by name")
    .with_examples("Show customer John Smith", "Find customer named Jane")
    .with_parameter("customer_name", ParameterType.STRING, 
                   "Customer name to search for", required=True)
    .with_sql("SELECT * FROM customers WHERE name ILIKE %(customer_name)s")
    .with_semantic_tags(action="find", primary_entity="customer")
    .build())

# Add to library
library = TemplateLibrary(domain)
library.add_template(template)
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

### 4. Plugin System (`plugin_system.py`)

Extensible pipeline for customizing query processing at any stage.

#### Plugin Types:
- **Pre-processing**: Query normalization, intent analysis
- **Post-processing**: Result filtering, data enrichment
- **Response Enhancement**: Formatting, additional insights
- **Security**: Validation, access control

#### Built-in Plugins:
- **SecurityPlugin**: Validates queries for security concerns
- **QueryNormalizationPlugin**: Standardizes query format
- **ResultFilteringPlugin**: Limits and filters results
- **DataEnrichmentPlugin**: Adds computed fields
- **ResponseEnhancementPlugin**: Improves response formatting
- **LoggingPlugin**: Comprehensive logging and metrics

#### Creating Custom Plugins:
```python
class CustomAnalyticsPlugin(BaseRAGPlugin):
    def get_name(self) -> str:
        return "CustomAnalytics"
    
    def post_process_results(self, results: List[Dict], context: PluginContext) -> List[Dict]:
        # Add custom analytics
        for result in results:
            result['analytics_score'] = self.calculate_score(result)
        return results
    
    def enhance_response(self, response: str, context: PluginContext) -> str:
        # Add analytical insights to response
        insights = self.generate_insights(context.metadata.get('results', []))
        return f"{response}\n\n💡 Analytical Insights:\n{insights}"
```

### 5. Shared Configuration Modules (New)

**Shared Domain Configuration (`shared_domain_config.py`)**
- Single source of truth for domain definitions
- Ensures consistent domain configuration across all demos
- Prevents configuration drift between conversational and Streamlit demos

**Shared Template Loader (`shared_template_loader.py`)**
- Consistent template loading logic across demos
- Eliminates duplicate template generation code
- Ensures identical template libraries in all interfaces

#### Benefits:
- **Consistency**: Both demos use identical configurations
- **Maintainability**: Single place to update domain definitions
- **Reliability**: Eliminates configuration mismatches
- **Testing**: Easier to validate system behavior

#### Usage:
```python
from shared_domain_config import create_customer_order_domain
from shared_template_loader import load_or_generate_templates

# Both demos use the same functions
domain = create_customer_order_domain()
templates = load_or_generate_templates(domain)
```

### 6. RAG System (`base_rag_system.py`)

The main orchestration class that brings all components together.

#### Key Components:

**DomainAwareParameterExtractor**
- Extracts parameters using domain knowledge
- Pattern-based extraction for common data types
- LLM fallback for complex parameter extraction
- Domain vocabulary integration

**DomainAwareResponseGenerator**
- Generates contextual responses using domain configuration
- Formats results based on field display rules
- Supports different response strategies (table vs summary)
- Integrates conversation context

**RAGSystem**
- Main system class coordinating all components
- Manages ChromaDB for semantic search
- Handles conversation context and history
- Integrates plugin pipeline

#### Query Processing Flow:
1. **Pre-processing**: Plugins normalize and validate query
2. **Template Matching**: Vector search finds best matching templates
3. **Reranking**: Domain-specific rules adjust template scores
4. **Parameter Extraction**: Extract parameters using domain patterns + LLM
5. **Validation**: Validate parameters against domain rules
6. **Execution**: Execute SQL query with parameters
7. **Post-processing**: Plugins enrich and filter results
8. **Response Generation**: Generate natural language response
9. **Enhancement**: Plugins enhance final response

### 7. Validation System (New)

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

### Step 1: Define Your Domain

Create a shared domain configuration function in a new file (following the pattern of `shared_domain_config.py`):

```python
def create_healthcare_domain() -> DomainConfiguration:
    domain = DomainConfiguration(
        domain_name="Healthcare",
        description="Medical records and patient management system"
    )
    
    # Define entities
    patient_entity = DomainEntity(
        name="patient",
        entity_type=EntityType.PRIMARY,
        table_name="patients",
        description="Patient information",
        primary_key="patient_id",
        display_name_field="full_name",
        searchable_fields=["full_name", "medical_record_number"],
        common_filters=["date_of_birth", "insurance_provider"],
        default_sort_field="last_visit_date"
    )
    domain.add_entity(patient_entity)
    
    # Define fields
    domain.add_field("patient", DomainField(
        name="medical_record_number",
        data_type=DataType.STRING,
        db_column="mrn",
        description="Medical Record Number",
        required=True,
        searchable=True,
        validation_rules=[{"type": "pattern", "value": r"^MR\d{6}$"}],
        aliases=["MRN", "record number", "patient ID"]
    ))
    
    # Define relationships
    domain.add_relationship(DomainRelationship(
        name="patient_appointments",
        from_entity="patient",
        to_entity="appointment",
        relation_type=RelationType.ONE_TO_MANY,
        from_field="patient_id",
        to_field="patient_id",
        description="Patient has many appointments"
    ))
    
    # Define vocabulary
    domain.vocabulary.entity_synonyms = {
        "patient": ["client", "individual", "person", "case"],
        "appointment": ["visit", "consultation", "session"],
        "diagnosis": ["condition", "illness", "disorder"]
    }
    
    domain.vocabulary.action_verbs = {
        "find": ["locate", "search", "lookup", "retrieve", "show"],
        "schedule": ["book", "arrange", "set up", "plan"],
        "diagnose": ["identify", "determine", "assess"]
    }
    
    domain.vocabulary.time_expressions = {
        "last visit": "30",
        "recent": "7",
        "this quarter": "90",
        "past year": "365"
    }
    
    return domain
```

### Step 2: Create Domain-Specific Templates

```python
def create_healthcare_templates(domain: DomainConfiguration) -> TemplateLibrary:
    library = TemplateLibrary(domain)
    
    # Auto-generate standard templates
    generator = DomainTemplateGenerator(domain)
    library = generator.generate_standard_templates()
    
    # Add domain-specific templates
    medical_history_template = (QueryTemplateBuilder("patient_medical_history")
        .with_description("Get comprehensive medical history for a patient")
        .with_examples(
            "Show medical history for patient MR123456",
            "Get all records for John Smith",
            "Patient history for MRN MR789012"
        )
        .with_parameter("patient_identifier", ParameterType.STRING, 
                       "Patient MRN or name", required=True)
        .with_sql("""
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
        """)
        .with_semantic_tags(
            action="find",
            primary_entity="patient",
            secondary_entity="appointment",
            qualifiers=["medical_history", "comprehensive"]
        )
        .with_result_format("summary")
        .build())
    
    library.add_template(medical_history_template)
    return library
```

### Step 3: Create Domain-Specific Plugins

```python
class MedicalDataEnrichmentPlugin(BaseRAGPlugin):
    def get_name(self) -> str:
        return "MedicalDataEnrichment"
    
    def get_version(self) -> str:
        return "1.0.0"
    
    def get_priority(self) -> PluginPriority:
        return PluginPriority.MEDIUM
    
    def post_process_results(self, results: List[Dict], context: PluginContext) -> List[Dict]:
        """Add medical-specific data enrichment"""
        for result in results:
            # Add age calculation
            if 'date_of_birth' in result:
                result['age'] = self._calculate_age(result['date_of_birth'])
                result['age_group'] = self._categorize_age(result['age'])
            
            # Add risk categorization
            if 'diagnosis_code' in result:
                result['risk_level'] = self._assess_risk(result['diagnosis_code'])
            
            # Add days since last visit
            if 'last_visit_date' in result:
                result['days_since_visit'] = self._days_since(result['last_visit_date'])
        
        return results
    
    def enhance_response(self, response: str, context: PluginContext) -> str:
        """Add medical insights to response"""
        results = context.metadata.get('results', [])
        
        # Add medical insights
        insights = []
        if results:
            high_risk_count = sum(1 for r in results if r.get('risk_level') == 'high')
            if high_risk_count > 0:
                insights.append(f"🚨 {high_risk_count} high-risk cases identified")
            
            overdue_count = sum(1 for r in results if r.get('days_since_visit', 0) > 365)
            if overdue_count > 0:
                insights.append(f"⏰ {overdue_count} patients overdue for visits")
        
        if insights:
            response += f"\n\n🏥 Medical Insights:\n" + "\n".join(f"• {insight}" for insight in insights)
        
        return response
    
    def _calculate_age(self, date_of_birth):
        from datetime import date
        today = date.today()
        birth_date = date.fromisoformat(str(date_of_birth)[:10])
        return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    
    def _categorize_age(self, age):
        if age < 18:
            return "pediatric"
        elif age < 65:
            return "adult"
        else:
            return "geriatric"
    
    def _assess_risk(self, diagnosis_code):
        # Simplified risk assessment
        high_risk_codes = ['I21', 'I20', 'E11', 'C78']  # Heart attack, angina, diabetes, cancer
        return "high" if any(code in diagnosis_code for code in high_risk_codes) else "low"
    
    def _days_since(self, date_value):
        from datetime import date
        if date_value:
            visit_date = date.fromisoformat(str(date_value)[:10])
            return (date.today() - visit_date).days
        return 0
```

### Step 4: Create the Demo Application

```python
def create_healthcare_demo():
    """Create healthcare-specific demo"""
    
    def create_healthcare_demo_app():
        class HealthcareDemo(ConversationalDemo):
            def create_domain(self):
                return create_healthcare_domain()
            
            def create_templates(self, domain):
                return create_healthcare_templates(domain)
            
            def create_custom_plugins(self):
                return [
                    MedicalDataEnrichmentPlugin(),
                    PatientPrivacyPlugin(),
                    ClinicalDecisionSupportPlugin()
                ]
            
            def get_example_queries(self):
                return {
                    "👥 Patient Queries": [
                        "Show medical history for patient MR123456",
                        "Find patients with diabetes",
                        "List all patients seen this week",
                        "Show overdue patients for checkups"
                    ],
                    "📅 Appointment Queries": [
                        "Show today's appointments",
                        "Find available slots next week",
                        "List cancelled appointments",
                        "Show emergency visits this month"
                    ],
                    "🩺 Clinical Queries": [
                        "Patients with high blood pressure",
                        "Show vaccination records for John Smith",
                        "Find patients on medication X",
                        "List surgical procedures this month"
                    ]
                }
        
        return HealthcareDemo()
    
    return create_healthcare_demo_app()

# Usage
if __name__ == "__main__":
    demo = create_healthcare_demo()
    demo.run()
```

### Step 5: Create Validation Templates

Create corresponding SQL validation templates for accuracy testing:

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

### Step 6: Validation Testing

Create validation tests for your new domain:

```bash
# Test your healthcare domain
python3 validate_rag_results.py --custom "Show medical history for patient MR123456"
python3 validate_rag_results.py --custom "Find patients with diabetes"

# Create domain-specific test categories
# Edit validate_rag_results.py to add healthcare queries
```

### Step 7: Configuration Management

Create YAML configuration files for easy management:

**healthcare_domain.yaml**
```yaml
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
  
  action_verbs:
    find: ["locate", "search", "lookup", "retrieve"]
    schedule: ["book", "arrange", "set up"]
  
  time_expressions:
    "last visit": "30"
    "recent": "7"
    "this quarter": "90"
```

Load configuration:
```python
def load_healthcare_domain():
    domain = DomainConfiguration.from_yaml("healthcare_domain.yaml")
    return domain
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
    domain = create_your_domain()
    
    # Test entity creation
    assert "your_entity" in domain.entities
    assert domain.entities["your_entity"].table_name == "your_table"
    
    # Test field validation
    field = domain.fields["your_entity"]["your_field"]
    assert field.data_type == DataType.STRING
    assert field.required == True
    
    # Test relationships
    relationships = domain.get_relationships_for_entity("your_entity")
    assert len(relationships) > 0
```

2. **Integration Tests**
```python
def test_end_to_end_query():
    # Initialize system
    domain = create_your_domain()
    rag_system = create_rag_system(domain)
    
    # Test query processing
    result = rag_system.process_query("Find customer John Smith")
    
    assert result['success'] == True
    assert len(result['results']) > 0
    assert 'John Smith' in str(result['results'])
```

3. **Template Testing**
```python
def test_template_generation():
    domain = create_your_domain()
    generator = DomainTemplateGenerator(domain)
    library = generator.generate_standard_templates()
    
    # Verify expected templates were created
    expected_templates = [
        "find_customer_by_id",
        "list_orders_by_customer",
        "find_orders_by_status"
    ]
    
    for template_id in expected_templates:
        assert template_id in library.templates
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
def optimize_chromadb(rag_system):
    # Pre-warm embedding cache
    all_queries = [
        "common query pattern 1",
        "common query pattern 2",
        # ... add your common patterns
    ]
    
    for query in all_queries:
        rag_system.embedding_client.get_embedding(query)
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

#### DomainConfiguration
```python
class DomainConfiguration:
    def __init__(self, domain_name: str, description: str)
    def add_entity(self, entity: DomainEntity)
    def add_field(self, entity_name: str, field: DomainField)
    def add_relationship(self, relationship: DomainRelationship)
    def to_yaml(self, file_path: str)
    @classmethod
    def from_yaml(cls, file_path: str) -> 'DomainConfiguration'
```

#### RAGSystem
```python
class RAGSystem:
    def __init__(self, domain: DomainConfiguration, 
                 template_library: TemplateLibrary,
                 embedding_client: BaseEmbeddingClient,
                 inference_client: BaseInferenceClient,
                 db_client: BaseDatabaseClient)
    
    def process_query(self, user_query: str) -> Dict[str, Any]
    def populate_chromadb_from_library(self, clear_first: bool = False)
    def clear_conversation(self)
    def print_configuration(self)
```

#### QueryTemplateBuilder
```python
class QueryTemplateBuilder:
    def with_description(self, description: str) -> 'QueryTemplateBuilder'
    def with_examples(self, *examples: str) -> 'QueryTemplateBuilder'
    def with_parameter(self, name: str, param_type: ParameterType, 
                      description: str, **kwargs) -> 'QueryTemplateBuilder'
    def with_sql(self, sql: str) -> 'QueryTemplateBuilder'
    def with_semantic_tags(self, **tags) -> 'QueryTemplateBuilder'
    def build(self) -> Dict[str, Any]
```

### Plugin Interface

```python
class BaseRAGPlugin:
    def get_name(self) -> str
    def get_version(self) -> str
    def get_priority(self) -> PluginPriority
    def is_enabled(self) -> bool
    
    def pre_process_query(self, query: str, context: PluginContext) -> str
    def post_process_results(self, results: List[Dict], context: PluginContext) -> List[Dict]
    def enhance_response(self, response: str, context: PluginContext) -> str
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

### Plugin Development
1. **Single Responsibility**: Each plugin should have a single, clear purpose
2. **Performance Conscious**: Avoid heavy computation in plugins
3. **Error Resilient**: Plugins should handle errors gracefully
4. **Configurable**: Make plugins configurable through parameters
5. **Well Documented**: Provide clear documentation for plugin functionality

### Performance
1. **Index Strategy**: Create appropriate database indexes
2. **Caching**: Implement caching for embeddings and frequent queries
3. **Batch Processing**: Use batch operations where possible
4. **Monitor Performance**: Track query performance and optimize bottlenecks
5. **Resource Management**: Properly manage database connections and memory

### Security
1. **SQL Injection Prevention**: Always use parameterized queries
2. **Access Control**: Implement proper access control through plugins
3. **Data Validation**: Validate all user inputs
4. **Audit Logging**: Log all queries and results for audit purposes
5. **Sensitive Data**: Handle sensitive data appropriately

This comprehensive documentation should enable new developers to understand the system architecture and successfully extend it to new domains. The system's domain-agnostic design makes it highly adaptable while maintaining consistency and best practices across different business contexts.