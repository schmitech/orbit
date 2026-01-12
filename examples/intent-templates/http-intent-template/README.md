# HTTP Intent Template Generator

This tool helps you generate HTTP intent templates for the ORBIT HTTP adapter system. It allows you to quickly create domain configurations and template libraries for REST APIs.

## Architecture Note

**Important**: HTTP JSON adapters use `datasource: "http"` for adapter registry lookup, but they do NOT use centralized datasource connections like SQL or Elasticsearch adapters. Each HTTP adapter manages its own HTTP client and connects directly to its configured `base_url` (e.g., https://api.github.com). You may see a warning about "Datasource implementation not found: http" - this is expected and harmless since HTTP adapters manage their own connections.

**Scope**: The `IntentHTTPJSONRetriever` supports any JSON-based HTTP API - RESTful, RPC-style, or other HTTP+JSON endpoints. It's not limited to strictly RESTful APIs.

## Overview

The HTTP Intent Template Generator enables you to:
- Generate HTTP templates from natural language examples
- Create domain configurations for any JSON-based HTTP API
- Support multiple API integrations (GitHub, Stripe, etc.)
- Automate template creation using AI-powered parameter extraction

## Directory Structure

```
utils/http-intent-template/
├── README.md                    # This file
├── template_generator.py        # Main template generation script
├── create_request_template.py   # Create individual HTTP templates
├── validate_output.py           # Validate generated templates
├── test_adapter_loading.py      # Test HTTP adapter configuration
├── configs/
│   └── rest-api-config.yaml    # REST API generator configuration
├── examples/
│   └── github-api/
│       ├── templates/
│       │   ├── github_domain.yaml      # Domain configuration
│       │   └── github_templates.yaml   # Template library
│       └── test_requests.md    # Natural language test requests
└── docs/
    └── TUTORIAL.md             # Step-by-step tutorial
```

## Quick Start

### 1. Create Natural Language Test Requests

Create a file with natural language examples of API requests you want to make:

```markdown
# examples/github-api/test_requests.md

## Repository Queries

### List User Repositories
1. "Show me repositories for octocat"
2. "Get all repos for user torvalds"
3. "List repositories owned by defunkt"
```

### 2. Generate Templates

Run the template generator:

```bash
cd utils/http-intent-template

python create_request_template.py \
    --api-name github \
    --base-url "https://api.github.com" \
    --requests examples/github-api/test_requests.md \
    --output examples/github-api/templates/github_templates.yaml
```

### 3. Add to Configuration

Add the adapter configuration to `config/adapters.yaml`:

```yaml
adapters:
  - name: "intent-http-github"
    enabled: true
    type: "retriever"
    datasource: "http"  # Registered in adapter registry
    adapter: "intent"
    implementation: "retrievers.implementations.intent.IntentHTTPJSONRetriever"
    inference_provider: "openai"
    embedding_provider: "openai"
    config:
      domain_config_path: "utils/http-intent-template/examples/github-api/templates/github_domain.yaml"
      template_library_path:
        - "utils/http-intent-template/examples/github-api/templates/github_templates.yaml"
      template_collection_name: "github_http_templates"
      store_name: "chroma"
      confidence_threshold: 0.4
      max_templates: 5
      base_url: "https://api.github.com"
      auth:
        type: "bearer_token"
        token_env: "GITHUB_TOKEN"
```

### 4. Test Your Integration

```bash
python test_adapter_loading.py \
    --adapter-name "intent-http-github" \
    --query "Show me repositories for octocat"
```

## Template Structure

### Domain Configuration

Domain configuration defines the API structure, entities, and vocabulary:

```yaml
# examples/github-api/templates/github_domain.yaml
domain_name: "github_api"
domain_type: "rest_api"
version: "1.0.0"

api_config:
  base_url: "https://api.github.com"
  api_version: "v3"
  protocol: "https"
  default_timeout: 30

authentication:
  type: "bearer_token"
  token_env: "GITHUB_TOKEN"
  header_name: "Authorization"
  token_prefix: "Bearer"

entities:
  repository:
    entity_type: "resource"
    endpoint_base: "/repos"
    primary_key: "full_name"
    display_name: "Repository"

vocabulary:
  entity_synonyms:
    repository: ["repo", "project", "codebase"]
  action_synonyms:
    list: ["show", "get", "find", "list"]
```

### Template Library

Template library contains individual HTTP request templates:

```yaml
# examples/github-api/templates/github_templates.yaml
templates:
  - id: get_user_repositories
    version: "1.0.0"
    description: "Get all repositories for a GitHub user"

    http_method: "GET"
    endpoint_template: "/users/{username}/repos"

    headers:
      Accept: "application/vnd.github.v3+json"

    query_params:
      sort: "{{sort_by}}"
      direction: "{{direction}}"
      per_page: "{{limit}}"

    parameters:
      - name: username
        type: string
        required: true
        description: "GitHub username"
        location: "path"
        example: "octocat"

      - name: sort_by
        type: string
        required: false
        default: "created"
        location: "query"
        allowed_values: ["created", "updated", "pushed"]

      - name: limit
        type: integer
        required: false
        default: 30
        location: "query"
        min: 1
        max: 100

    response_mapping:
      items_path: "$"
      fields:
        - name: "name"
          path: "$.name"
        - name: "description"
          path: "$.description"
        - name: "stars"
          path: "$.stargazers_count"

    nl_examples:
      - "Show me repositories for octocat"
      - "Get repos for user torvalds"
      - "List repositories for defunkt"

    semantic_tags:
      action: "list"
      primary_entity: "repository"
      secondary_entity: "user"

    result_format: "table"
    tags: ["github", "repository", "user", "list"]
```

## Authentication Support

The HTTP adapter supports multiple authentication methods:

### Bearer Token (OAuth2, JWT)
```yaml
auth:
  type: "bearer_token"
  token_env: "GITHUB_TOKEN"
```

### API Key
```yaml
auth:
  type: "api_key"
  api_key_env: "API_KEY"
  header_name: "X-API-Key"
```

### Basic Auth
```yaml
auth:
  type: "basic_auth"
  username_env: "API_USERNAME"
  password_env: "API_PASSWORD"
```

## Parameter Locations

Parameters can be placed in different parts of the HTTP request:

- **path**: Path parameters (`/users/{username}`)
- **query**: Query string parameters (`?sort=created&limit=30`)
- **header**: HTTP headers
- **body**: Request body (for POST/PUT/PATCH)

## Response Mapping

Configure how to extract data from API responses:

```yaml
response_mapping:
  # Path to list of items in response
  items_path: "$"  # or "data.results"

  # Fields to extract from each item
  fields:
    - name: "id"
      path: "$.id"
      type: "integer"
    - name: "title"
      path: "$.title"
      type: "string"
```

## Examples

See the `examples/` directory for complete examples:
- **github-api**: GitHub REST API integration
- More examples coming soon (Stripe, Slack, etc.)

## Tools

### create_request_template.py

Create individual HTTP templates interactively or from examples.

```bash
python create_request_template.py \
    --api-name <api_name> \
    --base-url <base_url> \
    --requests <requests_file> \
    --output <output_file>
```

### validate_output.py

Validate generated templates for correctness.

```bash
python validate_output.py \
    --templates <templates_file> \
    --domain <domain_file>
```

### test_adapter_loading.py

Test adapter loading and query execution.

```bash
python test_adapter_loading.py \
    --adapter-name <adapter_name> \
    --query "<natural language query>"
```

## Best Practices

1. **Organize by API**: Create separate directories for each API
2. **Use semantic tags**: Help the NLU system match queries to templates
3. **Provide examples**: Include 3-5 natural language examples per template
4. **Map responses**: Define clear response mappings for consistent output
5. **Set limits**: Always set reasonable default limits for list queries
6. **Handle errors**: Consider error cases in your templates

## Troubleshooting

### Template Not Matching

- Check similarity threshold in adapter config
- Add more natural language examples to template
- Verify semantic tags are correct
- Use more specific entity and action synonyms

### Parameter Extraction Failing

- Verify parameter descriptions are clear
- Add examples to parameter definitions
- Check parameter types match expected values
- Ensure required parameters are marked correctly

### API Request Failing

- Verify base_url is correct
- Check authentication configuration
- Ensure endpoint_template syntax is correct
- Verify query parameters are properly formatted

## Next Steps

1. Review existing examples in `examples/github-api/`
2. Follow the tutorial in `docs/TUTORIAL.md`
3. Create your first API integration
4. Test with natural language queries
5. Refine templates based on results

## Support

For issues, questions, or contributions:
- Check the main ORBIT documentation
- Review the HTTP Adapter Implementation Status
- See the HTTP Adapter System Roadmap

Happy template building! 🚀
