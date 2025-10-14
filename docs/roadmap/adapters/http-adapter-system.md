# HTTP Adapter System Roadmap

## Overview

This roadmap outlines the strategic implementation of an HTTP adapter system for ORBIT, designed to enable seamless integration with HTTP-based data sources including REST APIs, webhooks, web scraping, and other web services. The system will follow the same template-based architecture as the existing SQL intent adapter, providing a consistent and extensible framework for HTTP data retrieval.

**Key Insight**: The HTTP adapter system follows a **two-layer architecture** just like the SQL intent adapter:
1. **Adapter Layer** (`server/adapters/intent/http_adapter.py`) - Manages HTTP domain configuration and template libraries
2. **Retriever Layer** (`server/retrievers/implementations/intent/intent_http_retriever.py`) - Processes natural language queries and executes HTTP requests

## Strategic Goals

- **Unified HTTP Interface**: Create a consistent abstraction layer for all HTTP-based data sources
- **Template-Driven Configuration**: Leverage YAML templates for HTTP endpoint definitions and parameter mapping
- **Intent-Based Query Processing**: Natural language to HTTP request translation using vector similarity matching
- **Extensible Architecture**: Support multiple HTTP adapter sub-types (REST, webhook, web scraping, GraphQL, etc.)
- **Enterprise Integration**: Enable seamless integration with enterprise APIs, microservices, and third-party services
- **Performance & Reliability**: Implement robust error handling, retry mechanisms, and caching strategies
- **Automated Template Generation**: Tools to generate HTTP templates from API specifications (OpenAPI/Swagger)

## Phase 1: Foundation & Core Architecture

### 1.1 HTTP Adapter Layer (Document Adapter)

**Objective**: Establish the HTTP document adapter that manages domain configuration and template libraries

**Deliverables**:
- `HttpAdapter` class extending `DocumentAdapter`
- HTTP domain configuration loading (YAML)
- HTTP template library loading and validation
- Multiple template library support
- Template metadata management

**Key Components**:
```python
# server/adapters/intent/http_adapter.py
class HttpAdapter(DocumentAdapter):
    """
    HTTP adapter that manages domain-specific knowledge for the HTTP intent retriever.
    Loads HTTP domain configuration and template libraries for natural language to HTTP translation.
    """
    def __init__(self,
                 domain_config_path: Optional[str] = None,
                 template_library_path: Optional[Union[str, List[str]]] = None,
                 base_url: Optional[str] = None,
                 auth_config: Optional[Dict[str, Any]] = None,
                 confidence_threshold: float = 0.1,
                 verbose: bool = False,
                 config: Dict[str, Any] = None,
                 **kwargs)

    def _load_yaml_config(self, path: str, config_type: str) -> Optional[Dict[str, Any]]
    def _load_multiple_template_libraries(self, paths: List[str]) -> Dict[str, Any]
    def get_domain_config(self) -> Optional[Dict[str, Any]]
    def get_template_library(self) -> Optional[Dict[str, Any]]
    def get_template_by_id(self, template_id: str) -> Optional[Dict[str, Any]]
    def get_all_templates(self) -> List[Dict[str, Any]]
    def format_document(self, raw_doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]
    async def initialize_embeddings(self, store_manager=None)
```

**Factory Registration**:
```python
# Register with DocumentAdapterFactory
DocumentAdapterFactory.register_adapter("http", lambda **kwargs: HttpAdapter(**kwargs))

# Register with global adapter registry
def register_http_adapter():
    ADAPTER_REGISTRY.register(
        adapter_type="retriever",
        datasource="http",
        adapter_name="intent",
        implementation='adapters.intent.http_adapter.HttpAdapter',
        config={'base_url': None, 'auth_config': None}
    )
```

### 1.2 HTTP Intent Retriever Layer (CRITICAL)

**Objective**: Implement the HTTP intent retriever that processes natural language queries

**Deliverables**:
- `IntentHTTPRetriever` base class extending `BaseRetriever`
- Vector store integration for HTTP template matching
- Embedding client integration for query/template similarity
- Inference client integration for parameter extraction
- HTTP request execution with fault tolerance
- Response processing and formatting

**Key Components**:
```python
# server/retrievers/base/intent_http_base.py
class IntentHTTPRetriever(BaseRetriever):
    """
    Unified base class for intent-based HTTP retrievers.
    Processes natural language queries and translates them to HTTP requests.
    """
    def __init__(self, config: Dict[str, Any], domain_adapter=None, **kwargs)

    # Initialization methods
    async def initialize(self) -> None
    async def _initialize_embedding_client(self)
    async def _initialize_inference_client(self)
    async def _initialize_vector_store(self)
    async def _load_templates(self)

    # Template matching and execution
    async def get_relevant_context(self, query: str, **kwargs) -> List[Dict[str, Any]]
    async def _find_best_templates(self, query: str) -> List[Dict[str, Any]]
    async def _extract_parameters(self, query: str, template: Dict) -> Dict[str, Any]
    async def _execute_template(self, template: Dict, parameters: Dict) -> Tuple[Any, Optional[str]]

    # HTTP-specific methods
    async def _build_http_request(self, template: Dict, parameters: Dict) -> Dict[str, Any]
    async def _execute_http_request(self, request: Dict) -> Any
    def _process_http_template(self, template: str, parameters: Dict) -> str
    def _format_http_response(self, response: Any, template: Dict) -> List[Dict[str, Any]]

    # Helper methods
    def _create_embedding_text(self, template: Dict[str, Any]) -> str
    def _create_template_metadata(self, template: Dict[str, Any]) -> Dict[str, Any]
```

**REST Implementation**:
```python
# server/retrievers/implementations/intent/intent_rest_retriever.py
class IntentRESTRetriever(IntentHTTPRetriever):
    """REST-specific intent retriever implementation."""

    def __init__(self, config: Dict[str, Any], domain_adapter=None, **kwargs)

    async def _execute_http_request(self, request: Dict) -> Any:
        """Execute REST API request with retries and error handling."""
        # Implementation with aiohttp/httpx
```

**HTTP Template Structure** (Comprehensive):
```yaml
# utils/http-intent-template/examples/github-api/github_api_templates.yaml
templates:
  - id: get_user_repositories
    version: "1.0.0"
    description: "Get all repositories for a GitHub user"

    # HTTP Request Configuration
    http_method: "GET"
    endpoint_template: "/users/{{username}}/repos"

    # Headers with variable substitution
    headers:
      Authorization: "Bearer {{auth_token}}"
      Accept: "application/vnd.github.v3+json"
      User-Agent: "ORBIT-HTTP-Adapter/1.0"

    # Query Parameters
    query_params:
      sort: "{{sort_by}}"
      direction: "{{direction}}"
      per_page: "{{limit}}"
      page: "{{page}}"

    # Template Parameters (extracted from natural language)
    parameters:
      - name: username
        type: string
        required: true
        description: "GitHub username"
        location: "path"  # path, query, header, body
        example: "octocat"

      - name: sort_by
        type: string
        required: false
        default: "created"
        description: "Sort repositories by"
        location: "query"
        allowed_values: ["created", "updated", "pushed", "full_name"]

      - name: direction
        type: string
        required: false
        default: "desc"
        description: "Sort direction"
        location: "query"
        allowed_values: ["asc", "desc"]

      - name: limit
        type: integer
        required: false
        default: 30
        description: "Results per page"
        location: "query"
        min: 1
        max: 100

      - name: page
        type: integer
        required: false
        default: 1
        description: "Page number"
        location: "query"
        min: 1

    # Response Processing
    response_mapping:
      items_path: "$"  # JSONPath to the list of items
      fields:
        - name: "name"
          path: "$.name"
          type: "string"
        - name: "description"
          path: "$.description"
          type: "string"
        - name: "stars"
          path: "$.stargazers_count"
          type: "integer"
        - name: "language"
          path: "$.language"
          type: "string"
        - name: "created_at"
          path: "$.created_at"
          type: "datetime"

    # Natural Language Examples for Intent Matching
    nl_examples:
      - "Show me repositories for octocat"
      - "Get repos for user torvalds"
      - "List all repositories for user defunkt"
      - "Find projects by user mojombo"
      - "What repositories does user pjhyett have?"

    # Semantic Tags for Template Matching
    semantic_tags:
      action: "list"
      primary_entity: "repository"
      secondary_entity: "user"
      qualifiers: ["owner", "public"]

    # Error Handling & Retry Configuration
    retry_config:
      max_retries: 3
      backoff_factor: 2
      retry_on_status: [429, 500, 502, 503, 504]

    timeout: 30

    # Response Format
    response_format: "json"
    result_format: "table"  # table, summary, list

    # Tags for categorization
    tags: ["github", "repository", "user", "list"]

    # Metadata
    category: "repository_queries"
    complexity: "simple"
    approved: true
    version: "1.0.0"
```

### 1.3 HTTP Domain Configuration

**Objective**: Define HTTP-specific domain configuration structure

**Domain Configuration Structure**:
```yaml
# utils/http-intent-template/examples/github-api/github_domain.yaml
domain_name: "github_api"
domain_type: "rest_api"
version: "1.0.0"

# Base API Configuration
api_config:
  base_url: "https://api.github.com"
  api_version: "v3"
  protocol: "https"
  default_timeout: 30
  rate_limit:
    requests_per_hour: 5000
    retry_after_header: "X-RateLimit-Reset"

# Authentication Configuration
authentication:
  type: "bearer_token"
  token_env: "GITHUB_TOKEN"
  header_name: "Authorization"
  token_prefix: "Bearer"
  scopes: ["repo", "user"]

# Entity Definitions (Similar to SQL entities)
entities:
  repository:
    entity_type: "resource"
    endpoint_base: "/repos"
    primary_key: "full_name"
    display_name: "Repository"
    display_name_field: "full_name"

    # HTTP Methods supported
    methods:
      - GET
      - POST
      - PATCH
      - DELETE

    # Searchable fields
    searchable_fields:
      - name
      - description
      - topics
      - language

    # Common filters
    common_filters:
      - field: "visibility"
        values: ["public", "private"]
      - field: "type"
        values: ["all", "owner", "member"]

    # Relationships to other entities
    relationships:
      - entity: "user"
        type: "belongs_to"
        foreign_key: "owner"
      - entity: "issue"
        type: "has_many"
        endpoint: "/repos/{owner}/{repo}/issues"

    # Response structure
    response_structure:
      list_wrapper: null  # null means array is at root
      item_id_field: "id"
      pagination:
        type: "link_header"
        page_param: "page"
        per_page_param: "per_page"
        default_per_page: 30
        max_per_page: 100

  issue:
    entity_type: "resource"
    endpoint_base: "/repos/{owner}/{repo}/issues"
    primary_key: "number"
    display_name: "Issue"
    display_name_field: "title"

    methods:
      - GET
      - POST
      - PATCH

    searchable_fields:
      - title
      - body
      - labels

    common_filters:
      - field: "state"
        values: ["open", "closed", "all"]
      - field: "labels"
        type: "array"

    relationships:
      - entity: "repository"
        type: "belongs_to"
        foreign_key: "repository"
      - entity: "user"
        type: "belongs_to"
        foreign_key: "assignee"

  user:
    entity_type: "resource"
    endpoint_base: "/users"
    primary_key: "login"
    display_name: "User"
    display_name_field: "login"

    methods:
      - GET

    searchable_fields:
      - login
      - name
      - email

# Vocabulary for Natural Language Understanding
vocabulary:
  entity_synonyms:
    repository: ["repo", "project", "codebase", "repository"]
    issue: ["bug", "ticket", "problem", "issue"]
    user: ["account", "profile", "developer", "user"]

  action_synonyms:
    list: ["show", "get", "find", "list", "display", "fetch"]
    create: ["create", "add", "new", "make"]
    update: ["update", "modify", "change", "edit"]
    delete: ["delete", "remove", "destroy"]

  qualifier_synonyms:
    recent: ["recent", "latest", "newest", "new"]
    popular: ["popular", "starred", "trending"]

# Error Handling Configuration
error_handling:
  retry_on_status: [429, 500, 502, 503, 504]
  max_retries: 3
  backoff_factor: 2
  timeout: 30

# Response Processing
response_processing:
  default_format: "json"
  content_types:
    - "application/json"
    - "application/vnd.github.v3+json"
  error_field: "message"
  pagination_headers: ["Link", "X-Total-Count"]
```

### 1.4 HTTP Template System & Categories

**Objective**: Define comprehensive template categorization for HTTP operations

**Template Categories**:
- **REST APIs**: Standard RESTful service integration
  - CRUD operations (GET, POST, PUT, PATCH, DELETE)
  - List/search endpoints
  - Nested resource access
  - Pagination and filtering

- **Webhooks**: Event-driven data retrieval
  - Event subscription
  - Payload parsing
  - Event filtering

- **Web Scraping**: HTML content extraction
  - Element selection
  - Content parsing
  - Multi-page navigation

- **GraphQL**: GraphQL query execution
  - Query templates
  - Mutation templates
  - Fragment composition

- **SOAP**: Legacy SOAP service integration
  - WSDL parsing
  - SOAP envelope construction

### 1.5 Registry Integration & Configuration

**Objective**: Integrate HTTP adapters with existing registry and configuration system

**Adapter Registration**:
```python
# server/adapters/intent/http_adapter.py
from adapters.factory import DocumentAdapterFactory
from adapters.registry import ADAPTER_REGISTRY

# Register with DocumentAdapterFactory
DocumentAdapterFactory.register_adapter("http", lambda **kwargs: HttpAdapter(**kwargs))

# Register with global adapter registry
def register_http_adapter():
    """Register HTTP adapter with the global adapter registry."""
    ADAPTER_REGISTRY.register(
        adapter_type="retriever",
        datasource="http",
        adapter_name="intent",
        implementation='adapters.intent.http_adapter.HttpAdapter',
        config={'base_url': None, 'auth_config': None}
    )

# Auto-register on module import
register_http_adapter()
```

**Retriever Registration**:
```python
# server/retrievers/implementations/intent/intent_rest_retriever.py
from retrievers.base.base_retriever import RetrieverFactory

# Register the REST HTTP retriever
RetrieverFactory.register_retriever('intent_rest', IntentRESTRetriever)
```

**Configuration in config/adapters.yaml**:
```yaml
adapters:
  # GitHub API Integration Example
  - name: "intent-http-github"
    enabled: true
    type: "retriever"
    datasource: "http"
    adapter: "intent"
    implementation: "retrievers.implementations.intent.IntentRESTRetriever"
    inference_provider: "openai"
    model: "gpt-4"
    embedding_provider: "openai"
    config:
      # Domain and template configuration
      domain_config_path: "utils/http-intent-template/examples/github-api/github_domain.yaml"
      template_library_path:
        - "utils/http-intent-template/examples/github-api/github_templates.yaml"

      # Vector store configuration
      template_collection_name: "github_http_templates"
      store_name: "chroma"

      # Intent matching configuration
      confidence_threshold: 0.4
      max_templates: 5
      return_results: 10

      # Template loading settings
      reload_templates_on_start: false
      force_reload_templates: false

      # HTTP-specific configuration
      base_url: "https://api.github.com"
      auth:
        type: "bearer_token"
        token_env: "GITHUB_TOKEN"

      # Fault tolerance settings
      fault_tolerance:
        operation_timeout: 30.0
        failure_threshold: 5
        recovery_timeout: 60.0
        max_retries: 3
        retry_delay: 1.0

  # Stripe API Integration Example
  - name: "intent-http-stripe"
    enabled: true
    type: "retriever"
    datasource: "http"
    adapter: "intent"
    implementation: "retrievers.implementations.intent.IntentRESTRetriever"
    inference_provider: "openai"
    embedding_provider: "openai"
    config:
      domain_config_path: "utils/http-intent-template/examples/stripe-api/stripe_domain.yaml"
      template_library_path:
        - "utils/http-intent-template/examples/stripe-api/stripe_templates.yaml"
      template_collection_name: "stripe_http_templates"
      store_name: "chroma"
      confidence_threshold: 0.4
      max_templates: 5
      base_url: "https://api.stripe.com/v1"
      auth:
        type: "bearer_token"
        token_env: "STRIPE_API_KEY"
```

**Datasource Configuration in config/datasources.yaml**:
```yaml
datasources:
  http:
    github:
      enabled: true
      base_url: "https://api.github.com"
      api_version: "v3"
      auth:
        type: "bearer_token"
        token_env: "GITHUB_TOKEN"
      rate_limit:
        requests_per_hour: 5000
      timeout: 30

    stripe:
      enabled: true
      base_url: "https://api.stripe.com/v1"
      auth:
        type: "bearer_token"
        token_env: "STRIPE_API_KEY"
      rate_limit:
        requests_per_second: 100
      timeout: 30
```

## Phase 2: REST API Adapter

### 2.1 REST Adapter Implementation

**Objective**: Implement the primary REST API adapter

**Features**:
- Full CRUD operation support
- Dynamic parameter injection
- Authentication handling (Bearer, API Key, Basic Auth)
- Response parsing and formatting
- Error handling and status code management

**Key Methods**:
```python
class RestAdapter(HttpAdapter):
    def _build_url(self, template: Dict, params: Dict) -> str
    def _build_headers(self, template: Dict, params: Dict) -> Dict[str, str]
    def _handle_response(self, response: Response, template: Dict) -> Dict[str, Any]
    def _handle_error(self, error: Exception, template: Dict) -> Dict[str, Any]
```

### 2.2 Authentication System

**Objective**: Implement comprehensive authentication support

**Supported Methods**:
- **Bearer Token**: OAuth2, JWT tokens
- **API Key**: Header-based and query parameter authentication
- **Basic Auth**: Username/password authentication
- **Custom Headers**: Flexible header-based authentication
- **OAuth2 Flow**: Complete OAuth2 authorization flow

**Configuration Example**:
```yaml
auth_config:
  type: "bearer_token"
  token: "{env:API_TOKEN}"
  header_name: "Authorization"
  token_prefix: "Bearer"
```

### 2.3 Response Processing

**Objective**: Handle various response formats and data structures

**Features**:
- JSON response parsing
- XML response handling
- CSV data processing
- Binary content handling
- Pagination support
- Data transformation and mapping

## Phase 3: HTTP Template Generator Tool (CRITICAL - NEW)

**Objective**: Create comprehensive tooling for generating HTTP templates from API specifications

**This phase is analogous to `utils/sql-intent-template/` but for HTTP APIs**

### 3.1 HTTP Template Generator Directory Structure

```
utils/http-intent-template/
├── README.md                           # Comprehensive usage guide
├── template_generator.py               # Main template generation script
├── api_spec_parser.py                  # Parse OpenAPI/Swagger specifications
├── create_request_template.py          # Create individual HTTP templates
├── config_selector.py                  # Auto-select config based on API type
├── compare_structures.py               # Compare generated vs existing templates
├── validate_output.py                  # Validate generated templates
├── test_adapter_loading.py             # Test HTTP adapter configuration
├── generate_templates.sh               # Shell script for template generation
├── run_example.sh                      # Quick start example script
│
├── configs/
│   ├── rest-api-config.yaml           # REST API configuration
│   ├── graphql-config.yaml            # GraphQL API configuration
│   ├── webhook-config.yaml            # Webhook configuration
│   └── template_generator_config.yaml  # Default configuration
│
├── examples/
│   ├── github-api/
│   │   ├── openapi-spec.yaml          # GitHub API OpenAPI spec
│   │   ├── github_domain.yaml         # Domain configuration
│   │   ├── github_templates.yaml      # Generated templates
│   │   └── test_requests.md           # Natural language test requests
│   │
│   ├── stripe-api/
│   │   ├── openapi-spec.yaml
│   │   ├── stripe_domain.yaml
│   │   ├── stripe_templates.yaml
│   │   └── test_requests.md
│   │
│   └── simple-rest/
│       ├── api-spec.yaml
│       ├── domain.yaml
│       └── templates.yaml
│
└── docs/
    ├── TUTORIAL.md                     # Step-by-step tutorial
    ├── API_SPEC_GUIDE.md              # Guide to API specifications
    └── TEMPLATE_STRUCTURE.md           # Template structure reference
```

### 3.2 Template Generator Script

**File**: `utils/http-intent-template/template_generator.py`

**Features**:
- Parse OpenAPI/Swagger specifications
- Generate HTTP request templates from API endpoints
- Create natural language examples using AI
- Generate domain configuration files
- Support for multiple AI providers (OpenAI, Anthropic, Ollama, Groq)
- Batch template generation
- Template grouping by semantic similarity

**Usage**:
```bash
# Generate templates from OpenAPI spec
python template_generator.py \
    --spec examples/github-api/openapi-spec.yaml \
    --requests examples/github-api/test_requests.md \
    --config configs/rest-api-config.yaml \
    --output examples/github-api/github_templates.yaml

# Generate domain configuration
python template_generator.py \
    --spec examples/github-api/openapi-spec.yaml \
    --generate-domain \
    --output examples/github-api/github_domain.yaml

# Auto-detect API type and use appropriate config
python config_selector.py --spec examples/github-api/openapi-spec.yaml
```

**Key Functions**:
```python
class HTTPTemplateGenerator:
    def __init__(self, config: Dict[str, Any], inference_client: Any):
        """Initialize the HTTP template generator."""

    def parse_openapi_spec(self, spec_path: str) -> Dict[str, Any]:
        """Parse OpenAPI/Swagger specification."""

    def generate_templates_from_spec(self, spec: Dict) -> List[Dict]:
        """Generate HTTP templates from API specification."""

    def generate_domain_config(self, spec: Dict) -> Dict[str, Any]:
        """Generate domain configuration from API spec."""

    def generate_nl_examples(self, endpoint: Dict) -> List[str]:
        """Generate natural language examples using LLM."""

    def group_similar_templates(self, templates: List[Dict]) -> List[Dict]:
        """Group semantically similar templates."""

    def validate_templates(self, templates: List[Dict]) -> Dict[str, Any]:
        """Validate generated templates."""
```

### 3.3 API Specification Parser

**File**: `utils/http-intent-template/api_spec_parser.py`

**Supported Formats**:
- OpenAPI 3.x
- Swagger 2.x
- RAML
- API Blueprint
- Postman Collections

**Features**:
```python
class APISpecParser:
    def parse_openapi(self, spec_path: str) -> APISpec:
        """Parse OpenAPI specification."""

    def extract_endpoints(self, spec: Dict) -> List[Endpoint]:
        """Extract all endpoints from specification."""

    def extract_authentication(self, spec: Dict) -> Dict:
        """Extract authentication configuration."""

    def extract_schemas(self, spec: Dict) -> Dict:
        """Extract data schemas and models."""

    def extract_parameters(self, operation: Dict) -> List[Parameter]:
        """Extract parameters from operation."""
```

### 3.4 Shell Script for Automation

**File**: `utils/http-intent-template/generate_templates.sh`

```bash
#!/bin/bash
# HTTP Template Generation Script

# Usage examples:
./generate_templates.sh \
    --spec examples/github-api/openapi-spec.yaml \
    --requests examples/github-api/test_requests.md \
    --config configs/rest-api-config.yaml

# Auto-detect API type
./generate_templates.sh \
    --spec examples/stripe-api/openapi-spec.yaml \
    --requests examples/stripe-api/test_requests.md

# Generate with specific provider
./generate_templates.sh \
    --spec examples/github-api/openapi-spec.yaml \
    --requests examples/github-api/test_requests.md \
    --provider openai \
    --model gpt-4
```

### 3.5 Configuration Files

**File**: `utils/http-intent-template/configs/rest-api-config.yaml`

```yaml
# REST API Template Generator Configuration

generator:
  version: "1.0.0"
  type: "rest_api"

# API Analysis Settings
api_analysis:
  detect_entities: true
  detect_relationships: true
  detect_pagination: true
  detect_auth_type: true

# Template Generation Settings
template_generation:
  # Generate templates for all HTTP methods
  http_methods:
    - GET
    - POST
    - PUT
    - PATCH
    - DELETE

  # Template categories to generate
  categories:
    - "resource_list"
    - "resource_get"
    - "resource_create"
    - "resource_update"
    - "resource_delete"
    - "search_queries"
    - "filter_queries"

  # Natural language example generation
  nl_examples:
    count_per_template: 5
    use_ai_generation: true
    include_synonyms: true

  # Parameter extraction
  parameters:
    extract_path_params: true
    extract_query_params: true
    extract_header_params: true
    extract_body_params: true
    include_optional: true
    include_defaults: true

# Grouping Configuration
grouping:
  enabled: true
  similarity_threshold: 0.85
  features:
    - http_method
    - endpoint_pattern
    - parameters
    - response_structure
  feature_weights:
    http_method: 0.2
    endpoint_pattern: 0.4
    parameters: 0.2
    response_structure: 0.2

# Validation Rules
validation:
  require_nl_examples: true
  require_descriptions: true
  require_parameters: true
  min_nl_examples: 3
  check_endpoint_validity: true
  check_parameter_types: true
```

### 3.6 Example: GitHub API Integration

**File**: `utils/http-intent-template/examples/github-api/test_requests.md`

```markdown
# GitHub API - Test Requests

## Repository Queries

### List User Repositories
1. "Show me repositories for octocat"
2. "Get all repos for user torvalds"
3. "List repositories owned by defunkt"
4. "Find projects by user mojombo"
5. "What repositories does pjhyett have?"

### Search Repositories
1. "Find repositories about machine learning"
2. "Search for React projects"
3. "Show me popular Python repositories"
4. "Find repositories with topic 'api'"

### Get Repository Details
1. "Show me details for octocat/Hello-World"
2. "Get info about torvalds/linux repository"
3. "Tell me about the facebook/react project"

## Issue Queries

### List Issues
1. "Show me open issues for facebook/react"
2. "List all bugs in microsoft/vscode"
3. "Get closed issues for nodejs/node"
4. "Find issues labeled 'good first issue' in rust-lang/rust"

### Create Issue
1. "Create a new bug report for facebook/react"
2. "File an issue about documentation in microsoft/typescript"
3. "Report a problem in nodejs/node repository"

### Update Issue
1. "Close issue #123 in facebook/react"
2. "Add label 'bug' to issue #456 in microsoft/vscode"
3. "Assign issue #789 to user octocat"

## User Queries

### Get User Info
1. "Show me profile for user octocat"
2. "Get information about torvalds"
3. "Tell me about user defunkt"

### List User Activity
1. "Show me recent activity for octocat"
2. "Get events for user torvalds"
3. "What has defunkt been working on?"
```

### 3.7 Quick Start Example Script

**File**: `utils/http-intent-template/run_example.sh`

```bash
#!/bin/bash
# Quick start example for HTTP template generation

echo "🚀 HTTP Template Generator - Quick Start Example"
echo "================================================"
echo ""
echo "This script demonstrates HTTP template generation using the GitHub API."
echo ""

# Step 1: Generate domain configuration
echo "📋 Step 1: Generating domain configuration..."
python template_generator.py \
    --spec examples/github-api/openapi-spec.yaml \
    --generate-domain \
    --output examples/github-api/github_domain.yaml

# Step 2: Generate templates
echo ""
echo "🔧 Step 2: Generating HTTP templates..."
python template_generator.py \
    --spec examples/github-api/openapi-spec.yaml \
    --requests examples/github-api/test_requests.md \
    --config configs/rest-api-config.yaml \
    --output examples/github-api/github_templates.yaml

# Step 3: Validate output
echo ""
echo "✅ Step 3: Validating generated templates..."
python validate_output.py \
    --templates examples/github-api/github_templates.yaml \
    --domain examples/github-api/github_domain.yaml

echo ""
echo "✨ Done! Generated files:"
echo "   - examples/github-api/github_domain.yaml"
echo "   - examples/github-api/github_templates.yaml"
echo ""
echo "Next steps:"
echo "   1. Review the generated templates"
echo "   2. Add to config/adapters.yaml"
echo "   3. Test with: python test_adapter_loading.py"
```

## Phase 4: Webhook Adapter

### 4.1 Webhook Integration

**Objective**: Enable real-time data retrieval through webhooks

**Features**:
- Webhook endpoint registration
- Event filtering and routing
- Payload validation and processing
- Real-time data streaming
- Webhook security and verification

**Template Structure**:
```yaml
templates:
  - id: github_webhook
    version: "1.0.0"
    description: "GitHub repository webhook events"
    webhook_config:
      endpoint: "/webhooks/github"
      events: ["push", "pull_request", "issues"]
      secret: "{env:GITHUB_WEBHOOK_SECRET}"
    payload_mapping:
      repository: "repository.full_name"
      event_type: "action"
      timestamp: "head_commit.timestamp"
```

### 3.2 Event Processing

**Objective**: Process and store webhook events for retrieval

**Features**:
- Event deduplication
- Event filtering and transformation
- Temporal data storage
- Event replay capabilities
- Real-time notifications

## Phase 5: Web Scraping Adapter

### 5.1 Web Scraping Framework

**Objective**: Enable web content extraction and processing

**Features**:
- HTML parsing and content extraction
- CSS selector and XPath support
- JavaScript rendering (Selenium/Playwright integration)
- Content cleaning and normalization
- Rate limiting and respectful scraping

**Template Structure**:
```yaml
templates:
  - id: news_scraper
    version: "1.0.0"
    description: "Scrape news articles from news website"
    scraping_config:
      url_template: "https://news.example.com/articles/{category}"
      selectors:
        title: "h1.article-title"
        content: ".article-body p"
        author: ".author-name"
        date: ".publish-date"
      wait_for: ".article-body"
      javascript: true
    parameters:
      - name: category
        type: string
        required: true
        options: ["technology", "business", "sports"]
```

### 5.2 Content Processing

**Objective**: Process and structure scraped content

**Features**:
- Text extraction and cleaning
- Image and media handling
- Link extraction and following
- Content categorization
- Duplicate detection

## Phase 6: Advanced HTTP Features

### 6.1 GraphQL Adapter

**Objective**: Support GraphQL query execution

**Features**:
- GraphQL query templates
- Variable substitution
- Query optimization
- Response field selection
- Schema introspection

**Template Structure**:
```yaml
templates:
  - id: github_graphql
    version: "1.0.0"
    description: "Query GitHub repositories using GraphQL"
    graphql_config:
      endpoint: "https://api.github.com/graphql"
      query: |
        query GetRepositories($username: String!, $limit: Int!) {
          user(login: $username) {
            repositories(first: $limit) {
              nodes {
                name
                description
                stargazerCount
                createdAt
              }
            }
          }
        }
      variables:
        username: "{username}"
        limit: "{limit}"
```

### 6.2 SOAP Adapter

**Objective**: Support legacy SOAP service integration

**Features**:
- WSDL parsing and service discovery
- SOAP envelope construction
- XML namespace handling
- SOAP fault processing
- Service method invocation

### 6.3 Advanced Features

**Objective**: Implement enterprise-grade features

**Features**:
- **Circuit Breaker Pattern**: Prevent cascading failures
- **Rate Limiting**: Respect API rate limits
- **Caching**: Intelligent response caching
- **Monitoring**: Request/response metrics
- **Security**: Request signing, encryption

## Phase 7: Integration & Testing

### 7.1 System Integration

**Objective**: Integrate HTTP adapters with existing ORBIT components

**Integration Points**:
- Vector store integration for HTTP response indexing
- LLM integration for natural language query processing
- Pipeline integration for end-to-end workflows
- Configuration management integration

### 7.2 Testing Framework

**Objective**: Comprehensive testing for HTTP adapters

**Test Coverage**:
- Unit tests for individual adapters
- Integration tests with mock HTTP services
- End-to-end tests with real APIs
- Performance and load testing
- Security testing

**Test Structure**:
```
tests/retrievers/implementations/intent/
├── test_intent_http_retriever.py
├── test_http_template_processor.py
├── test_http_parameter_extractor.py
└── test_http_response_processor.py

tests/adapters/intent/
└── test_http_adapter.py

utils/http-intent-template/
├── test_template_generator.py
├── test_api_spec_parser.py
└── test_adapter_loading.py
```

### 7.3 Documentation & Examples

**Objective**: Provide comprehensive documentation and examples

**Deliverables**:
- API documentation
- Configuration guides
- Template examples
- Integration tutorials
- Best practices guide
- Troubleshooting guide

## Phase 8: Enterprise Features

### 8.1 Security Enhancements

**Objective**: Implement enterprise-grade security features

**Features**:
- **API Key Management**: Secure key storage and rotation
- **Request Signing**: HMAC and other signing mechanisms
- **Encryption**: End-to-end encryption for sensitive data
- **Audit Logging**: Comprehensive request/response logging
- **Compliance**: GDPR, HIPAA, SOX compliance support

### 8.2 Performance Optimization

**Objective**: Optimize for enterprise-scale usage

**Features**:
- **Connection Pooling**: Efficient HTTP connection management
- **Async Processing**: Non-blocking HTTP operations
- **Caching Strategies**: Multi-level caching implementation
- **Load Balancing**: Distribute requests across multiple endpoints
- **Monitoring**: Real-time performance metrics

### 8.3 Advanced Configuration

**Objective**: Provide flexible configuration options

**Features**:
- **Environment-specific Configs**: Dev, staging, production configurations
- **Dynamic Configuration**: Runtime configuration updates
- **Template Versioning**: Version control for HTTP templates
- **A/B Testing**: Template variant testing
- **Feature Flags**: Gradual feature rollout

## Success Metrics

### Technical Metrics
- **Response Time**: < 200ms for cached responses, < 2s for API calls
- **Reliability**: 99.9% uptime for HTTP adapter operations
- **Throughput**: Support 1000+ concurrent HTTP requests
- **Error Rate**: < 0.1% error rate for properly configured adapters

### Metrics
- **Integration Time**: < 1 hour to integrate new REST API
- **Template Library**: 100+ pre-built HTTP templates
- **Developer Experience**: < 5 minutes to create new HTTP adapter

## Risk Mitigation

### Technical Risks
- **API Rate Limits**: Implement rate limiting and caching
- **Service Downtime**: Circuit breaker patterns and fallback mechanisms
- **Data Security**: Comprehensive encryption and audit logging
- **Performance**: Async processing and connection pooling

### Business Risks
- **Vendor Lock-in**: Abstract API differences through templates
- **Compliance**: Built-in compliance features for major regulations
- **Scalability**: Cloud-native architecture with auto-scaling
- **Maintenance**: Comprehensive monitoring and alerting