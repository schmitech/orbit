# HTTP Intent Adapter Implementation Request Template

Use this template when requesting a new HTTP-based intent adapter implementation. HTTP intent adapters extend `IntentHTTPRetriever` and translate natural language queries into HTTP requests (REST APIs, GraphQL, SOAP, etc.).

## 1. Adapter Overview

### HTTP Adapter Type
- [ ] **REST API** (standard JSON REST endpoints)
- [ ] **GraphQL** (GraphQL query/mutation endpoints)
- [ ] **SOAP** (SOAP XML web services)
- [ ] **RPC-style** (JSON-RPC, XML-RPC)
- [ ] **Search Engine** (Elasticsearch, OpenSearch, Solr)
- [ ] **Document Database** (MongoDB with HTTP-like interface)
- [ ] **Other HTTP-based**: _____________________

### Adapter Name
- **Proposed Name**: `intent-http-{service}` (e.g., `intent-http-graphql`, `intent-http-soap`)
- **Alternative Names**: _____________________

### Service/API Documentation
- **API Documentation URL**: _____________________
- **Base URL Pattern**: _____________________
- **API Version**: _____________________

## 2. HTTP Configuration

### Base URL Configuration
- **Base URL**: _____________________
- **Environment Variable Support**: [ ] Yes [ ] No
- **Multiple Environments**: [ ] Dev [ ] Staging [ ] Production

### Authentication Method
- [ ] **None** (no authentication required)
- [ ] **API Key** (header or query parameter)
  - **Header Name**: _____________________ (e.g., `X-API-Key`)
  - **Query Parameter Name**: _____________________ (if query-based)
  - **Environment Variable**: _____________________
- [ ] **Bearer Token** (OAuth 2.0)
  - **Header Name**: `Authorization` (default)
  - **Token Prefix**: `Bearer` (default)
  - **Environment Variable**: _____________________
- [ ] **Basic Auth** (username/password)
  - **Username Environment Variable**: _____________________
  - **Password Environment Variable**: _____________________
- [ ] **OAuth 2.0 Client Credentials**
  - **Token Endpoint**: _____________________
  - **Client ID Environment Variable**: _____________________
  - **Client Secret Environment Variable**: _____________________
- [ ] **Custom Authentication**: _____________________

### HTTP Client Settings
- **Default Timeout**: _____________________ seconds (recommended: 30)
- **SSL Verification**: [ ] Enabled [ ] Disabled
- **Connection Pooling**: [ ] Enabled [ ] Disabled
  - **Max Connections**: _____________________
  - **Max Keepalive**: _____________________
- **Retry Logic**: [ ] Enabled [ ] Disabled
  - **Max Retries**: _____________________ (recommended: 3)
  - **Retry Delay**: _____________________ seconds (recommended: 1.0)
  - **Retry on Status Codes**: _____________________ (e.g., 500, 502, 503)

## 3. Request Format

### HTTP Method Support
- [ ] **GET** - Retrieve data (most common)
- [ ] **POST** - Create/submit data
- [ ] **PUT** - Update/replace data
- [ ] **PATCH** - Partial update
- [ ] **DELETE** - Remove data
- [ ] **Other**: _____________________

### Request Format Type
- [ ] **REST** - Standard REST API patterns
  - **Endpoint Pattern**: `/resource/{id}` or `/resource/{id}/subresource`
- [ ] **GraphQL** - GraphQL queries/mutations
  - **GraphQL Endpoint**: `/graphql` (default) or `/graphql/v1`
  - **Query Format**: [ ] Single Query [ ] Batch Queries [ ] Subscriptions
- [ ] **SOAP** - SOAP XML envelopes
  - **SOAP Action Header**: Required? [ ] Yes [ ] No
  - **WSDL URL**: _____________________
  - **SOAP Version**: [ ] 1.1 [ ] 1.2
- [ ] **JSON-RPC** - JSON-RPC 2.0 format
- [ ] **Custom Format**: _____________________

### Parameter Location
Parameters can be passed in different locations:
- [ ] **Path Parameters** - `/users/{user_id}/posts`
- [ ] **Query Parameters** - `?filter=value&sort=asc`
- [ ] **Request Body** - JSON/XML in POST/PUT/PATCH
- [ ] **Headers** - Custom headers
- [ ] **Cookie Parameters** - Session-based (rare)

## 4. Request Template Structure

### Endpoint Template Format
**REST Example:**
```yaml
endpoint_template: "/users/{{user_id}}/repos"
# OR
endpoint_template: "/users/{user_id}/repos"
```

**GraphQL Example:**
```yaml
query_template: |
  query GetUser($userId: ID!) {
    user(id: $userId) {
      id
      name
      email
    }
  }
```

**SOAP Example:**
```yaml
soap_action: "http://example.com/GetUser"
body_template: |
  <soap:Envelope>
    <soap:Body>
      <GetUser>
        <userId>{{user_id}}</userId>
      </GetUser>
    </soap:Body>
  </soap:Envelope>
```

**Your Format:**
```yaml
endpoint_template: _____________________
# OR
query_template: _____________________
# OR
body_template: _____________________
```

### Template Variable Syntax
- [ ] **Jinja2/Django** - `{{param_name}}`
- [ ] **Simple Substitution** - `{param_name}`
- [ ] **GraphQL Variables** - `$variableName`
- [ ] **SOAP Namespace** - With namespace prefixes
- **Other**: _____________________

## 5. Response Format

### Response Content Type
- [ ] **JSON** - `application/json`
- [ ] **XML** - `application/xml` or `text/xml`
- [ ] **GraphQL JSON** - GraphQL response format
- [ ] **SOAP XML** - SOAP envelope format
- [ ] **Plain Text** - `text/plain`
- [ ] **Other**: _____________________

### Response Structure
**Simple Response:**
```json
{
  "data": [...]
}
```

**Paginated Response:**
```json
{
  "results": [...],
  "total": 100,
  "page": 1,
  "per_page": 20
}
```

**GraphQL Response:**
```json
{
  "data": {
    "users": [...]
  },
  "errors": []
}
```

**Your Response Structure:**
Describe the typical response format:
_____________________
_____________________

### Response Mapping
- **Items Path**: _____________________ (e.g., `$.data.items`, `$.results`, `$`)
  - `$` means root level
  - Use dot notation for nested paths: `data.results`
- **Error Path**: _____________________ (e.g., `$.errors`, `$.error.message`)
- **Pagination Support**: [ ] Yes [ ] No
  - **Next Page Path**: _____________________
  - **Total Count Path**: _____________________

### Field Mapping (Optional)
If you need to map response fields to standardized names:
```yaml
field_mapping:
  - name: "user_id"
    path: "data.id"
  - name: "user_name"
    path: "data.name"
```

## 6. Implementation Requirements

### Base Class
- **Extends**: `IntentHTTPRetriever` (from `retrievers.base.intent_http_base`)

### Required Methods to Implement

#### `_execute_template()` - **REQUIRED**
Processes template and executes HTTP request.

```python
async def _execute_template(
    self, 
    template: Dict[str, Any],
    parameters: Dict[str, Any]
) -> Tuple[Any, Optional[str]]:
    """
    Execute HTTP template with parameters.
    
    Returns:
        Tuple of (results, error_message)
    """
```

**Implementation Checklist:**
- [ ] Extract HTTP method from template
- [ ] Process endpoint/query/body template with parameters
- [ ] Build query parameters
- [ ] Build request headers
- [ ] Build request body (if needed)
- [ ] Execute HTTP request
- [ ] Parse response
- [ ] Handle errors appropriately
- [ ] Return results and error tuple

#### `_format_http_results()` - **REQUIRED**
Formats HTTP response into context documents.

```python
def _format_http_results(
    self, 
    results: Any, 
    template: Dict,
    parameters: Dict, 
    similarity: float
) -> List[Dict[str, Any]]:
    """
    Format HTTP results into context documents.
    
    Returns:
        List of formatted context items with content and metadata
    """
```

**Implementation Checklist:**
- [ ] Handle empty results
- [ ] Format results based on template configuration
- [ ] Build metadata dictionary
- [ ] Return standardized context format

### Optional Helper Methods

#### Custom Parameter Processing
- [ ] `_process_endpoint_template()` - Custom endpoint processing
- [ ] `_process_query_template()` - GraphQL/query-specific processing
- [ ] `_process_body_template()` - Body template processing
- [ ] `_build_query_params()` - Query parameter building
- [ ] `_build_request_headers()` - Header building (if custom logic)
- [ ] `_build_request_body()` - Body building (if complex)
- **Other Custom Methods**: _____________________

#### Response Processing
- [ ] `_parse_response()` - Response parsing (if complex)
- [ ] `_extract_items_from_response()` - Item extraction
- [ ] `_map_response_fields()` - Field mapping
- [ ] `_handle_pagination()` - Pagination handling
- [ ] `_handle_errors()` - Error response handling
- **Other Custom Methods**: _____________________

## 7. Template Files Structure

### Template Directory Location
```
utils/http-{service}-intent-template/
├── README.md
├── docs/
│   └── {service}-specific-guide.md
└── examples/
    └── {domain}/
        ├── {domain}_domain.yaml           # [ ] Required
        ├── {domain}_templates.yaml        # [ ] Required
        ├── {domain}_test_queries.md       # [ ] Recommended
        └── test_{domain}_queries.sh       # [ ] Optional (if CLI available)
```

### Domain Configuration (`{domain}_domain.yaml`)
**Required Sections:**
- [ ] `domain_name`: Service domain identifier
- [ ] `description`: Domain description
- [ ] `semantic_types`: Type definitions
- [ ] `vocabulary`: Service-specific terms
- [ ] `entities`: Entity definitions with fields

**Service-Specific Information:**
- **API Resource Entities**: _____________________
- **Key Fields per Entity**: _____________________
- **Data Types**: _____________________
- **Relationships**: _____________________

### Template Library (`{domain}_templates.yaml`)

#### Template Structure for HTTP Adapters

**REST API Template:**
```yaml
- id: "get_user_repos"
  description: "Get repositories for a user"
  http_method: "GET"
  endpoint_template: "/users/{{username}}/repos"
  query_params:
    sort: "{{sort}}"
    per_page: "{{limit}}"
  parameters:
    - name: "username"
      type: "string"
      location: "path"
      required: true
    - name: "sort"
      type: "string"
      location: "query"
      allowed_values: ["created", "updated", "pushed", "full_name"]
    - name: "limit"
      type: "integer"
      location: "query"
      default: 30
  response_mapping:
    items_path: "$"
    fields:
      - name: "repo_name"
        path: "name"
      - name: "description"
        path: "description"
  nl_examples:
    - "Show me repositories for user john"
    - "List john's repos sorted by date"
```

**GraphQL Template:**
```yaml
- id: "get_user_profile"
  description: "Get user profile information"
  http_method: "POST"
  endpoint_template: "/graphql"
  body_template: |
    query GetUser($userId: ID!) {
      user(id: $userId) {
        id
        name
        email
        profile {
          bio
          avatar
        }
      }
    }
  parameters:
    - name: "userId"
      type: "string"
      location: "body"
      graphql_type: "ID!"
      required: true
  response_mapping:
    items_path: "data.user"
  nl_examples:
    - "Get profile for user 123"
    - "Show me user 123's information"
```

**SOAP Template:**
```yaml
- id: "get_user_details"
  description: "Get user details via SOAP"
  http_method: "POST"
  endpoint_template: "/soap/UserService"
  soap_action: "http://example.com/GetUserDetails"
  headers:
    SOAPAction: "http://example.com/GetUserDetails"
    Content-Type: "text/xml; charset=utf-8"
  body_template: |
    <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
      <soap:Body>
        <GetUserDetails xmlns="http://example.com/">
          <UserId>{{user_id}}</UserId>
        </GetUserDetails>
      </soap:Body>
    </soap:Envelope>
  parameters:
    - name: "user_id"
      type: "string"
      location: "body"
      required: true
  response_mapping:
    items_path: "Body.GetUserDetailsResponse.UserDetails"
  nl_examples:
    - "Get details for user 12345"
```

**Template Categories Needed:**
- [ ] Basic queries (GET, retrieve)
- [ ] Filtered queries (with parameters)
- [ ] Paginated queries
- [ ] Mutation/Write operations (POST, PUT, PATCH)
- [ ] Delete operations
- [ ] Complex queries (with joins/relationships)
- **Additional Template Types**: _____________________

**Estimated Template Count**: _____________________

## 8. Configuration Files

### `config/datasources.yaml`
**Entry Required (if new datasource):**
```yaml
http_{service}:
  base_url: "https://api.example.com"
  timeout: 30
  verify_ssl: true
  # Service-specific connection settings
```

**Note**: HTTP intent adapters may not need a datasource entry if they're fully configured in adapter config.

### `config/adapters.yaml`
**Adapter Entry Required:**
```yaml
- name: "intent-http-{service}-{domain}"
  enabled: true
  type: "retriever"
  datasource: "http"  # Generic HTTP datasource or service-specific
  adapter: "intent"
  implementation: "retrievers.implementations.intent.IntentHTTP{Service}Retriever"
  inference_provider: "{provider}"
  model: "{model_name}"
  embedding_provider: "{provider}"
  config:
    # Domain and template configuration
    domain_config_path: "utils/http-{service}-intent-template/examples/{domain}/{domain}_domain.yaml"
    template_library_path:
      - "utils/http-{service}-intent-template/examples/{domain}/{domain}_templates.yaml"
    
    # Vector store configuration
    template_collection_name: "{service}_{domain}_templates"
    store_name: "chroma"  # References stores.yaml
    
    # Intent matching configuration
    confidence_threshold: 0.4
    max_templates: 5
    return_results: 10
    
    # HTTP-specific configuration
    base_url: "https://api.example.com"  # Required
    default_timeout: 30
    enable_retries: true
    max_retries: 3
    retry_delay: 1.0
    
    # Authentication (if required)
    auth:
      type: "bearer_token"  # or "api_key", "basic_auth", "oauth2"
      token_env: "{SERVICE}_API_KEY"
      header_name: "Authorization"
      token_prefix: "Bearer"
    
    # Service-specific settings
    # GraphQL: graphql_endpoint, schema_url
    # SOAP: wsdl_url, soap_version, namespace_mappings
    # Other: [specify]
```

## 9. Registration Requirements

### Files Requiring Updates
- [ ] `server/retrievers/implementations/intent/__init__.py` - Add import and export
- [ ] `server/adapters/intent/adapter.py` - Register adapter for HTTP datasource (if needed)
- [ ] **Other Registration Points**: _____________________

### Factory Registration
```python
# At end of implementation file:
RetrieverFactory.register_retriever('intent_http_{service}', IntentHTTP{Service}Retriever)
logger.info("Registered IntentHTTP{Service}Retriever as 'intent_http_{service}'")
```

## 10. Testing Requirements

### Unit Tests
- [ ] Create `server/tests/test_intent_http_{service}_retriever.py`
- [ ] Test HTTP client initialization
- [ ] Test endpoint/query/body template processing
- [ ] Test parameter extraction and substitution
- [ ] Test request building (headers, body, query params)
- [ ] Test HTTP request execution
- [ ] Test response parsing
- [ ] Test error handling
- [ ] Test authentication
- [ ] Test retry logic
- **Additional Test Cases**: _____________________

### Integration Tests
- [ ] End-to-end query flow
- [ ] Template matching
- [ ] Parameter extraction
- [ ] Response formatting
- [ ] Error scenarios (4xx, 5xx)
- [ ] Network failure handling
- **Additional Integration Tests**: _____________________

### Mock Service Setup
- [ ] Mock HTTP server for testing (e.g., `responses`, `httpx_mock`)
- [ ] Test fixtures for sample responses
- [ ] Error response fixtures
- **Mock Requirements**: _____________________

## 11. Special HTTP Considerations

### Request Formatting
- **Content-Type Headers**: _____________________
- **Accept Headers**: _____________________
- **Custom Headers Required**: _____________________
- **Request Body Format**: [ ] JSON [ ] XML [ ] Form-encoded [ ] Other

### Response Handling
- **Status Code Handling**: 
  - Success: _____________________ (e.g., 200, 201, 204)
  - Client Errors: _____________________ (e.g., 400, 404, 422)
  - Server Errors: _____________________ (e.g., 500, 502, 503)
- **Error Response Format**: _____________________
- **Rate Limiting**: [ ] Yes [ ] No
  - **Rate Limit Headers**: _____________________
  - **Rate Limit Handling**: _____________________

### GraphQL-Specific
- **Schema Introspection**: [ ] Supported [ ] Not Supported
- **Variables**: [ ] Required [ ] Optional
- **Fragments**: [ ] Supported [ ] Not Supported
- **Subscriptions**: [ ] Required [ ] Not Supported

### SOAP-Specific
- **WSDL Location**: _____________________
- **SOAP Version**: [ ] 1.1 [ ] 1.2
- **Namespace Prefixes**: _____________________
- **Action Header**: [ ] Required [ ] Optional
- **Fault Handling**: _____________________

### Pagination
- **Pagination Method**: [ ] Offset/Limit [ ] Cursor-based [ ] Page-based [ ] None
- **Parameters**:
  - **Page/Offset Parameter**: _____________________
  - **Limit/Size Parameter**: _____________________
  - **Cursor Parameter**: _____________________
- **Response Indicators**:
  - **Total Count**: _____________________
  - **Has More/Next**: _____________________
  - **Next Page URL**: _____________________

## 12. Example Use Case

### Use Case Description
**Brief Description**: _____________________

**Example Queries:**
1. _____________________
2. _____________________
3. _____________________

**Expected HTTP Request:**
```http
GET /api/resource?param=value HTTP/1.1
Host: api.example.com
Authorization: Bearer token123
```

**Expected Response:**
```json
{
  "data": [...],
  "meta": {...}
}
```

### API Documentation
- **API Docs URL**: _____________________
- **OpenAPI/Swagger**: [ ] Available [ ] Not Available
- **GraphQL Schema**: [ ] Available [ ] Not Available
- **WSDL**: [ ] Available [ ] Not Available

## 13. Dependencies

### Required Python Packages
- **httpx**: HTTP client (already in base)
- **Additional**: _____________________
  - **Installation**: `pip install _____________________`

### Optional Dependencies
- **XML Parser** (for SOAP): `lxml`, `xml.etree`
- **GraphQL Client**: `gql`, `graphql-core`
- **Other**: _____________________

## 14. Implementation Checklist

Track progress during implementation:

- [ ] Implementation class created extending `IntentHTTPRetriever`
- [ ] `_execute_template()` implemented
- [ ] `_format_http_results()` implemented
- [ ] Custom helper methods implemented (if needed)
- [ ] HTTP client configuration implemented
- [ ] Authentication implemented
- [ ] Template processing implemented
- [ ] Response parsing implemented
- [ ] Error handling implemented
- [ ] Domain configuration created
- [ ] Template library created
- [ ] Configuration files updated
- [ ] Adapter registered in all required locations
- [ ] Unit tests created and passing
- [ ] Integration tests created and passing
- [ ] Documentation written
- [ ] Example queries validated

## 15. Additional Notes

**Any other information relevant to implementation:**

_____________________
_____________________
_____________________

---

## Example Completed Requests

### GraphQL Adapter Example
- **Type**: GraphQL API
- **Base URL**: `https://api.github.com/graphql`
- **Auth**: Bearer Token (GitHub Personal Access Token)
- **Templates**: 20+ GraphQL queries for GitHub API
- **Special**: Variable substitution, query validation

### SOAP Adapter Example
- **Type**: SOAP Web Service
- **WSDL**: `http://example.com/service?wsdl`
- **Auth**: Basic Auth
- **Templates**: 15+ SOAP operations
- **Special**: XML namespace handling, SOAP fault parsing

### REST API Adapter Example (JSONPlaceholder)
- **Type**: REST API
- **Base URL**: `https://jsonplaceholder.typicode.com`
- **Auth**: None
- **Templates**: 10+ REST operations
- **Special**: Simple JSON response handling

---

**Use this template for all HTTP-based intent adapter implementations to ensure consistency and completeness.**

