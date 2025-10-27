# Action Adapter System Implementation

## Overview

Create a new `action` adapter type under `server/adapters/` that enables task execution (emails, REST calls, etc.) similar to AI agents, with configurable confirmation, dual interfaces (chat + slash commands), and full integration with the existing adapter registry.

## Architecture Components

### 1. Base Action Adapter (`server/adapters/action/base.py`)

Create abstract base class `ActionAdapter` inheriting from `DocumentAdapter`:

- `execute_action(action_params, confirmation_mode)` - Execute the action with optional confirmation
- `validate_parameters(action_params)` - Validate action parameters
- `format_action_result(result, metadata)` - Format execution results
- `requires_confirmation()` - Check if action needs user approval
- `get_action_schema()` - Return action parameter schema for LLM/validation

Configuration options:

- `confirmation_required`: boolean or "auto" (let LLM decide based on risk)
- `timeout`: action execution timeout
- `retry_policy`: retry configuration for failed actions

### 2. Specific Action Implementations

#### Email Action Adapter (`server/adapters/action/email_adapter.py`)

- Integrate with SMTP or email service APIs
- Parameters: recipient, subject, body, attachments (optional)
- Confirmation: configurable (default: required for external recipients)
- Result: delivery status, message ID, timestamp

#### REST Action Adapter (`server/adapters/action/rest_adapter.py`)

- Execute HTTP requests (GET, POST, PUT, DELETE, PATCH)
- Parameters: url, method, headers, body, auth
- Confirmation: configurable per endpoint pattern (whitelist/blacklist)
- Result: HTTP status, response body, headers
- Template support: predefined REST actions from YAML config

#### Generic Action Adapter (`server/adapters/action/generic_adapter.py`)

- Extensible base for custom actions
- Plugin-style registration for new action types
- Schema-driven parameter validation

### 3. Action Registry & Factory

Update `server/adapters/registry.py`:

- Add `action` as new adapter type alongside `retriever` and `passthrough`
- Register action adapters: `(type="action", datasource="email|rest|generic", adapter="[name]")`

Update `server/adapters/__init__.py`:

- Import and register action adapters in `register_adapters()`

### 4. Action Execution Flow

#### A. Chat Pipeline Integration (`server/ai_services/pipeline/stages/`)

Create new pipeline stage: `ActionExecutionStage`

- Detect action intents from LLM response
- Extract action parameters
- Check confirmation requirements
- Execute or queue for confirmation
- Format results back to chat context

Update `ProcessingContext` to include:

- `pending_actions`: actions awaiting confirmation
- `action_results`: completed action results
- `action_mode`: "auto" | "confirm" | "disabled"

#### B. Dedicated Action Routes (`server/routes/action_routes.py`)

New endpoints:

- `POST /v1/actions/execute` - Execute action with parameters
- `POST /v1/actions/confirm/{action_id}` - Confirm pending action
- `GET /v1/actions/pending` - List pending confirmations
- `GET /v1/actions/history` - Action execution history
- `DELETE /v1/actions/{action_id}` - Cancel pending action

Slash command support:

- `/action [type] [params]` - Direct action invocation
- `/confirm [action_id]` - Confirm pending action
- `/cancel [action_id]` - Cancel pending action

### 5. Configuration

#### `config/adapters.yaml` - Add action adapter examples:

```yaml
adapters:
  - name: "action-email-smtp"
    enabled: false
    type: "action"
    datasource: "email"
    adapter: "smtp"
    implementation: "adapters.action.email_adapter.EmailActionAdapter"
    config:
      confirmation_required: true
      smtp_host: "${SMTP_HOST}"
      smtp_port: 587
      smtp_user: "${SMTP_USER}"
      smtp_password: "${SMTP_PASSWORD}"
      allowed_recipients: []  # empty = all allowed
      
  - name: "action-rest-generic"
    enabled: false
    type: "action"
    datasource: "rest"
    adapter: "generic"
    implementation: "adapters.action.rest_adapter.RestActionAdapter"
    config:
      confirmation_required: auto  # LLM decides based on action
      timeout: 30
      allowed_domains: []  # whitelist domains
      blocked_domains: ["internal.company.com"]
      template_library_path: "config/action_templates/rest_actions.yaml"
```

#### New config file: `config/action_templates/rest_actions.yaml`

Define reusable REST action templates similar to intent templates:

```yaml
actions:
  - id: "create_ticket"
    description: "Create support ticket"
    endpoint: "${SUPPORT_API_URL}/tickets"
    method: "POST"
    confirmation_required: false
    parameters: [title, description, priority]
```

### 6. Action Storage & History

Extend MongoDB schema or create new collection:

- `action_executions` collection
    - action_id, adapter_name, parameters, status, result, timestamp
    - user_id, session_id, confirmation_status
    - execution_time, retry_count

Update `server/services/conversation_service.py`:

- Store action results with conversation history
- Link actions to messages for context

### 7. Security & Validation

Create `server/adapters/action/security.py`:

- Parameter sanitization
- Domain/recipient whitelisting
- Rate limiting per action type
- Audit logging for sensitive actions
- API key scoping (restrict which keys can execute actions)

Update API key model to include:

- `allowed_action_types`: list of permitted action types
- `action_rate_limit`: executions per time window

## Implementation Files

New files to create:

1. `server/adapters/action/__init__.py`
2. `server/adapters/action/base.py`
3. `server/adapters/action/email_adapter.py`
4. `server/adapters/action/rest_adapter.py`
5. `server/adapters/action/generic_adapter.py`
6. `server/adapters/action/security.py`
7. `server/routes/action_routes.py`
8. `server/ai_services/pipeline/stages/action_execution_stage.py`
9. `server/models/action_execution.py`
10. `config/action_templates/rest_actions.yaml`

Files to modify:

1. `server/adapters/registry.py` - Add action type support
2. `server/adapters/__init__.py` - Register action adapters
3. `config/adapters.yaml` - Add example action adapter configs
4. `server/routes/routes_configurator.py` - Include action routes
5. `server/ai_services/pipeline/pipeline.py` - Add action stage
6. `server/models/__init__.py` - Export action models
7. `server/services/dynamic_adapter_manager.py` - Handle action adapters

## Testing Strategy

Create test files:

1. `server/tests/test_action_adapters.py` - Unit tests for action adapters
2. `server/tests/test_action_routes.py` - API endpoint tests
3. `server/tests/test_action_execution.py` - End-to-end action flow tests

Test scenarios:

- Action parameter validation
- Confirmation flow (required, optional, auto)
- Security constraints (whitelisting, rate limiting)
- Error handling and retries
- Integration with chat pipeline
- Slash command parsing

## To-dos

- [ ] Create base action adapter abstract class with core interfaces
- [ ] Implement email action adapter with SMTP support
- [ ] Implement REST action adapter with template support
- [ ] Update adapter registry to support action type
- [ ] Create action routes with slash command support
- [ ] Create action execution pipeline stage for chat integration
- [ ] Implement security validation and rate limiting
- [ ] Create data models for action execution storage
- [ ] Add example action adapter configurations
- [ ] Create comprehensive test suite for action adapters

