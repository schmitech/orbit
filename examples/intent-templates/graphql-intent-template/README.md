# GraphQL Intent Template Utility

This utility provides tools for creating intent-based GraphQL templates that enable natural language queries to be translated into GraphQL operations.

## Overview

The GraphQL intent template system works similarly to the HTTP intent template system but is specifically designed for GraphQL APIs. It allows users to query any GraphQL API using natural language, with the system automatically matching queries to appropriate GraphQL operations and extracting parameters.

## Directory Structure

```
graphql-intent-template/
├── README.md                           # This file
├── create_graphql_template.py          # Template generation tool
├── validate_output.py                  # Template validation tool
├── test_adapter_loading.py             # Integration testing tool
└── examples/
    └── spacex/
        └── templates/
            ├── spacex_domain.yaml      # Domain configuration
            └── spacex_templates.yaml   # GraphQL operation templates
```

## Quick Start

### 1. Create Templates

You can create templates manually or use the generator:

```bash
# Interactive mode
python create_graphql_template.py \
    --api-name myapi \
    --base-url "https://api.example.com/graphql" \
    --interactive

# From a GraphQL file
python create_graphql_template.py \
    --api-name myapi \
    --base-url "https://api.example.com/graphql" \
    --graphql operations.graphql \
    --output templates/myapi_templates.yaml
```

### 2. Validate Templates

```bash
# Validate templates only
python validate_output.py --templates templates/spacex_templates.yaml

# Validate with domain configuration
python validate_output.py \
    --templates templates/spacex_templates.yaml \
    --domain templates/spacex_domain.yaml

# Strict mode (warnings become errors)
python validate_output.py --templates templates.yaml --strict
```

### 3. Test Adapter Loading

```bash
# List all GraphQL adapters
python test_adapter_loading.py --list

# Test adapter initialization
python test_adapter_loading.py --adapter-name intent-graphql-spacex

# Test query matching
python test_adapter_loading.py \
    --adapter-name intent-graphql-spacex \
    --query "Show me SpaceX rockets"

# Execute against live API
python test_adapter_loading.py \
    --adapter-name intent-graphql-spacex \
    --query "What rockets does SpaceX have?" \
    --execute
```

## Template Structure

### Domain Configuration (`*_domain.yaml`)

The domain configuration provides context about the GraphQL API:

```yaml
domain_name: SpaceX API
domain_type: graphql
version: "1.0.0"
description: SpaceX launch and spacecraft data API

api_config:
  base_url: "https://spacex-production.up.railway.app"
  graphql_endpoint: "/graphql"
  supports_introspection: true

entities:
  launch:
    entity_type: resource
    graphql_type: Launch
    primary_key: id
    display_name_field: mission_name
    searchable_fields: [mission_name, rocket.rocket_name]

vocabulary:
  entity_synonyms:
    launch: [launch, mission, flight, liftoff]
    rocket: [rocket, booster, vehicle, spacecraft]
  action_synonyms:
    find: [find, get, show, list, display, retrieve]
    latest: [latest, most recent, newest, last]
```

### Template Library (`*_templates.yaml`)

Templates define specific GraphQL operations:

```yaml
templates:
  - id: get_launches
    version: "1.0.0"
    description: "Get SpaceX launches with optional limit"

    # GraphQL operation
    graphql_type: query
    operation_name: GetLaunches
    graphql_template: |
      query GetLaunches($limit: Int) {
        launches(limit: $limit) {
          id
          mission_name
          launch_date_utc
          launch_success
          rocket {
            rocket_name
          }
        }
      }

    # Parameter definitions
    parameters:
      - name: limit
        type: integer
        graphql_type: Int
        description: "Maximum number of launches to return"
        required: false
        default: 10
        location: variable

    # Natural language examples (critical for matching)
    nl_examples:
      - "Show me SpaceX launches"
      - "Get the last 5 launches"
      - "List recent SpaceX missions"

    # Semantic tags for template matching
    semantic_tags:
      action: list
      primary_entity: launch
      qualifiers: [recent, multiple]

    # Response mapping
    response_mapping:
      items_path: "data.launches"
      fields:
        - name: mission
          path: "$.mission_name"
        - name: date
          path: "$.launch_date_utc"

    display_fields: [mission, date, success, rocket]
    result_format: table
```

## Key Differences from HTTP Templates

| HTTP Template | GraphQL Template | Notes |
|---------------|------------------|-------|
| `http_method` | `graphql_type` | query, mutation, subscription |
| `endpoint_template` | `graphql_template` | Full GraphQL operation |
| `query_params` | N/A | Variables replace query params |
| `body_template` | N/A | GraphQL query IS the body |
| `parameters[].location` | Always "variable" | GraphQL uses variables only |
| N/A | `operation_name` | Optional GraphQL operation name |
| N/A | `graphql_type` on params | ID!, String, Int, etc. |

## Parameter Types

### GraphQL Type Mapping

| GraphQL Type | Template Type | Notes |
|--------------|---------------|-------|
| `Int` | `integer` | 32-bit integer |
| `Float` | `float` | Double precision |
| `String` | `string` | UTF-8 string |
| `Boolean` | `boolean` | true/false |
| `ID` | `string` | Unique identifier |
| `[Type]` | `array` | List of items |
| `Type!` | required: true | Non-null type |

### Parameter Definition

```yaml
parameters:
  - name: id                    # Variable name (matches GraphQL $id)
    type: string                # Template type for extraction
    graphql_type: ID!           # Full GraphQL type notation
    description: "Launch ID"    # For NLU extraction
    required: true              # Matches ! in GraphQL type
    location: variable          # Always 'variable' for GraphQL
    example: "5eb87cd9ffd86e000604b32a"
```

## Response Mapping

GraphQL responses follow a predictable structure:

```json
{
  "data": {
    "launches": [
      {"id": "1", "mission_name": "Mission 1"},
      {"id": "2", "mission_name": "Mission 2"}
    ]
  },
  "errors": []
}
```

The `items_path` specifies how to navigate to the actual data:

```yaml
response_mapping:
  items_path: "data.launches"    # Navigate to the array
  fields:
    - name: mission              # Output field name
      path: "$.mission_name"     # JSONPath within each item
    - name: rocket
      path: "$.rocket.rocket_name"  # Nested field access
```

## Adapter Configuration

Add GraphQL adapters to `config/adapters/intent.yaml`:

```yaml
- name: "intent-graphql-spacex"
  enabled: true
  type: "retriever"
  datasource: "http"
  adapter: "intent"
  implementation: "retrievers.implementations.intent.IntentGraphQLRetriever"
  inference_provider: "cohere"
  embedding_provider: "openai"
  config:
    domain_config_path: "utils/graphql-intent-template/examples/spacex/templates/spacex_domain.yaml"
    template_library_path:
      - "utils/graphql-intent-template/examples/spacex/templates/spacex_templates.yaml"

    template_collection_name: "graphql_spacex_templates"
    store_name: "qdrant"
    confidence_threshold: 0.4
    max_templates: 5
    return_results: 20

    reload_templates_on_start: true
    force_reload_templates: true

    # GraphQL-specific configuration
    base_url: "https://spacex-production.up.railway.app"
    graphql_endpoint: "/graphql"
    supports_introspection: true
    default_timeout: 30
```

## Best Practices

### 1. Natural Language Examples

Provide diverse, realistic examples:

```yaml
nl_examples:
  - "Show me SpaceX launches"           # Casual
  - "Get the last 5 launches"           # With parameters
  - "List recent SpaceX missions"       # Synonym usage
  - "What launches has SpaceX done?"    # Question form
  - "Display SpaceX launch history"     # Formal
```

### 2. Semantic Tags

Include meaningful tags for better matching:

```yaml
semantic_tags:
  action: list                    # What the template does
  primary_entity: launch          # Main entity type
  secondary_entity: rocket        # Related entity
  qualifiers:
    - recent                      # Time qualifier
    - multiple                    # Returns list
    - by_rocket                   # Filter type
```

### 3. Parameter Validation

Set appropriate constraints:

```yaml
parameters:
  - name: limit
    type: integer
    required: false
    default: 10
    min: 1
    max: 100
    allowed_values: null  # Or specific allowed values
```

### 4. Response Mapping

Map fields to user-friendly names:

```yaml
response_mapping:
  items_path: "data.rockets"
  fields:
    - name: name
      path: "$.name"
    - name: success_rate
      path: "$.success_rate_pct"
      type: integer
    - name: height_meters
      path: "$.height.meters"
      type: float
```

## Troubleshooting

### Template Not Matching

1. Check `nl_examples` - add more diverse examples
2. Lower `confidence_threshold` in adapter config
3. Verify `semantic_tags` match query intent

### Parameter Extraction Failing

1. Verify parameter `description` is clear
2. Add `example` values to parameters
3. Check `graphql_type` matches the schema

### GraphQL Errors

1. Validate GraphQL syntax: `python validate_output.py --templates ...`
2. Check variable names match parameter names
3. Verify required parameters have `!` in `graphql_type`

### Schema Validation

If `supports_introspection: true`, the retriever can validate templates against the live schema:

```python
# In code:
errors = await retriever.validate_template_against_schema(template)
```

## Example Queries

With the SpaceX templates, users can ask:

- "Show me SpaceX launches" → `get_launches`
- "What was the latest mission?" → `get_latest_launch`
- "List all rockets" → `get_rockets`
- "Get details for Falcon 9" → `get_rocket_by_id`
- "Show me active capsules" → `get_capsules`
- "What launch pads does SpaceX use?" → `get_launchpads`
