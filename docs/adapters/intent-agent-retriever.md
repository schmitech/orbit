# Intent Agent Retriever Architecture

This document describes the Intent Agent Retriever, a specialized retriever that extends intent-based retrieval with function calling capabilities, enabling tool execution and response synthesis.

## Overview

The Intent Agent Retriever combines traditional intent template matching with **function calling** (tool use), inspired by multi-model architectures like FunctionGemma. It enables the LLM to execute built-in tools (calculator, date/time, JSON transformations) and synthesize natural language responses from tool results.

### Key Features

- **Function Calling**: Execute built-in tools based on matched templates
- **Multi-Model Support**: Optional separate function-calling model (FunctionGemma-style)
- **Built-in Tools**: Calculator, date/time, and JSON transformation operations
- **Response Synthesis**: Natural language responses from tool execution results
- **Sequential Execution**: Intent → Match → Execute → Synthesize flow
- **YAML-Configured Tools**: Define tools declaratively in template files

## Architecture

### Execution Flow

```text
                         +------------------+
                         |   User's Query   |
                         +------------------+
                                  |
                                  v
                  +-------------------------------+
                  |   IntentAgentRetriever        |
                  |   (extends IntentHTTPRetriever)|
                  +-------------------------------+
                                  |
                    1. Generate Query Embedding
                                  |
                                  v
                  +-------------------------------+
                  |   Template Store (ChromaDB)   |
                  |   - Query templates           |
                  |   - Function templates        |
                  +-------------------------------+
                                  |
                    2. Match Best Template
                                  |
                                  v
                  +-------------------------------+
                  |   Template Router             |
                  +-------------------------------+
                         |              |
              Query Template    Function Template
              (tool_type: query) (tool_type: function)
                         |              |
                         v              v
              +----------------+  +------------------+
              | HTTP Execution |  | ToolExecutor     |
              | (inherited)    |  | - Parse function |
              +----------------+  | - Execute tool   |
                         |        +------------------+
                         |              |
                         +------+-------+
                                |
                                v
                  +-------------------------------+
                  |   ResponseSynthesizer         |
                  |   (Optional natural language) |
                  +-------------------------------+
                                |
                                v
                  +-------------------------------+
                  |   Formatted Response          |
                  +-------------------------------+
```

### Component Architecture

```text
IntentAgentRetriever
├── ToolExecutor
│   ├── BuiltinTools
│   │   ├── calculator (percentage, add, subtract, multiply, divide, average, round)
│   │   ├── date_time (now, format, diff, add_days, parse)
│   │   └── json_transform (filter, sort, select, aggregate)
│   ├── Function Model Client (optional)
│   └── Template → OpenAI Function Schema Converter
├── ResponseSynthesizer
│   ├── Inference Model Client
│   └── Response Formatting
└── IntentHTTPRetriever (inherited)
    ├── HTTP Client Management
    ├── Vector Store (template matching)
    └── Domain Parameter Extraction
```

## How It Works

### 1. Template Matching

The retriever uses ChromaDB to find the best matching template for a user query. Templates can be of two types:

| Template Type | `tool_type` | Execution Path |
|---------------|-------------|----------------|
| Query Template | `query` | Inherited HTTP execution |
| Function Template | `function` | Tool execution via `ToolExecutor` |

### 2. Function Template Execution

When a function template is matched:

1. **Schema Conversion**: Template is converted to OpenAI-compatible function schema
2. **Function Calling**: Model generates function call with arguments
3. **Tool Execution**: Built-in tool executes with extracted parameters
4. **Result Formatting**: Results formatted as context items

### 3. Built-in Tools

#### Calculator Tool

| Operation | Description | Parameters |
|-----------|-------------|------------|
| `percentage` | Calculate percentage of a value | `value`, `total` |
| `add` | Add numbers | `values` (array) |
| `subtract` | Subtract numbers | `a`, `b` |
| `multiply` | Multiply numbers | `a`, `b` |
| `divide` | Divide numbers | `a`, `b` |
| `average` | Calculate average | `values` (array) |
| `round` | Round to decimal places | `value`, `decimals` |

#### Date/Time Tool

| Operation | Description | Parameters |
|-----------|-------------|------------|
| `now` | Get current datetime | `format` (optional) |
| `format` | Format a date | `date`, `format_string` |
| `diff` | Days between dates | `date1`, `date2`, `unit` |
| `add_days` | Add days to date | `date`, `days` |
| `parse` | Parse date string | `date_string`, `format` |

#### JSON Transform Tool

| Operation | Description | Parameters |
|-----------|-------------|------------|
| `filter` | Filter array by condition | `data`, `field`, `operator`, `value` |
| `sort` | Sort array by field | `data`, `field`, `order` |
| `select` | Select specific fields | `data`, `fields` |
| `aggregate` | Aggregate values | `data`, `field`, `operation` |

### 4. HTTP API Tools

In addition to built-in tools, the agent supports HTTP API function calls for external services. These are configured with `execution.type: "http_call"`.

#### Weather Tools

| Function | Description | Parameters |
|----------|-------------|------------|
| `get_current_weather` | Get current weather conditions | `location`, `units` |
| `get_weather_forecast` | Get multi-day forecast | `location`, `days`, `units` |

#### Location Tools

| Function | Description | Parameters |
|----------|-------------|------------|
| `search_locations` | Geocoding and place search | `query`, `limit` |

#### Finance Tools

| Function | Description | Parameters |
|----------|-------------|------------|
| `get_stock_quote` | Get current stock price | `symbol` |
| `convert_currency` | Convert between currencies | `amount`, `from_currency`, `to_currency` |

#### Productivity Tools

| Function | Description | Parameters |
|----------|-------------|------------|
| `send_notification` | Send alerts/notifications | `message`, `channel`, `priority` |
| `create_task` | Create todo items | `title`, `description`, `due_date`, `priority` |

> **Note:** HTTP API tools require configuration of actual API endpoints and credentials. The provided templates include placeholder URLs that must be replaced with your API endpoints.

### 5. Response Synthesis

When `synthesize_response: true` is configured, the `ResponseSynthesizer` uses the inference model to generate a natural language response from tool results:

```text
Tool Result: {"result": 30, "operation": "percentage", "input": {"value": 150, "percentage": 20}}
     ↓
ResponseSynthesizer (using inference model)
     ↓
"20% of 150 is **30**."
```

## Configuration

### Adapter Configuration

Add to `config/adapters/intent.yaml`:

```yaml
- name: "intent-agent-example"
  enabled: true
  type: "retriever"
  datasource: "http"
  adapter: "intent"
  implementation: "retrievers.implementations.intent.IntentAgentRetriever"
  
  # Embedding provider for template matching
  embedding_provider: "ollama"
  embedding_model: "nomic-embed-text"
  
  # Inference model for response generation
  inference_model_provider: "ollama"
  inference_model: "gemma3:270m"
  
  config:
    # Domain configuration
    domain_config_path: "examples/intent-templates/agent-template/domain.yaml"
    
    # Tool templates
    template_library_path:
      - "examples/intent-templates/agent-template/tools.yaml"
    
    # Confidence threshold for template matching
    confidence_threshold: 0.6
    
    # Maximum templates to consider
    max_templates: 5
    
    # Agent-specific settings
    agent:
      # Optional: Dedicated function-calling model
      function_model_provider: "ollama"
      function_model: "functiongemma"
      
      # Generate natural language responses
      synthesize_response: true
      
      # Timeout for tool execution (seconds)
      tool_timeout: 30
      
      # Enable verbose logging
      verbose: false
```

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `agent.function_model_provider` | string | null | Provider for function-calling model |
| `agent.function_model` | string | null | Function-calling model name |
| `agent.synthesize_response` | bool | true | Generate natural language responses |
| `agent.tool_timeout` | float | 30.0 | Timeout for tool execution |
| `agent.verbose` | bool | false | Enable detailed logging |

### Model Configuration

The retriever supports two model configurations:

#### Single Model (Shared)

Use the same model for inference and function calling:

```yaml
inference_model_provider: "ollama"
inference_model: "llama3.2"

config:
  agent:
    # No function_model specified - uses inference_model
    synthesize_response: true
```

#### Multi-Model (Separate)

Use dedicated models for each task (FunctionGemma-style):

```yaml
inference_model_provider: "ollama"
inference_model: "gemma3:270m"  # Text generation

embedding_provider: "ollama"
embedding_model: "nomic-embed-text"  # Embeddings

config:
  agent:
    function_model_provider: "ollama"
    function_model: "functiongemma"  # Function calling
```

## Tool Template Format

### Function Template Definition

Templates with `tool_type: function` are executed as tools:

```yaml
templates:
  - id: "calculate_percentage"
    description: "Calculate a percentage of a given value"
    tool_type: "function"  # Marks this as a function template
    
    nl_examples:
      - "What is 15% of 200?"
      - "Calculate 20 percent of 500"
      - "Find 10% of 1000"
    
    # Tool configuration
    tool_name: "calculator"
    tool_operation: "percentage"
    
    # Parameter definitions
    parameters:
      - name: "value"
        type: "number"
        description: "The base value"
        required: true
        extraction_patterns:
          - "(?:of|from)\\s+([\\d,]+(?:\\.\\d+)?)"
      
      - name: "percentage"
        type: "number"
        description: "The percentage to calculate"
        required: true
        extraction_patterns:
          - "([\\d.]+)\\s*(?:%|percent)"
    
    # Response format
    response_template: "{{ percentage }}% of {{ value }} is **{{ result }}**"
```

### HTTP API Function Template

Templates with `execution.type: "http_call"` make external API calls:

```yaml
templates:
  - id: "get_current_weather"
    version: "1.0.0"
    description: "Get current weather conditions for a location"
    tool_type: "function"
    
    function_schema:
      name: "get_current_weather"
      description: "Retrieve current weather data including temperature and conditions"
      parameters:
        - name: location
          type: string
          required: true
          description: "City name or location"
          example: "London"
        - name: units
          type: string
          required: false
          description: "Temperature units: 'metric' or 'imperial'"
          default: "metric"
          enum: ["metric", "imperial"]
    
    execution:
      type: "http_call"
      http_method: "GET"
      endpoint_template: "https://api.openweathermap.org/data/2.5/weather?q={location}&units={units}"
      headers:
        Content-Type: "application/json"
        X-API-Key: "${WEATHER_API_KEY}"  # Environment variable
    
    nl_examples:
      - "What's the weather in London?"
      - "Current weather in New York"
      - "How's the weather in Paris today?"
    
    tags: ["weather", "api", "external"]
```

### Query Template Definition

Standard HTTP query templates (inherited behavior):

```yaml
templates:
  - id: "get_weather"
    description: "Get current weather for a location"
    tool_type: "query"  # Standard HTTP query
    
    nl_examples:
      - "What's the weather in Paris?"
      - "Show me weather for New York"
    
    method: "GET"
    endpoint: "/weather"
    query_params:
      location: "{{ location }}"
```

## Domain Configuration

### domain.yaml Structure

```yaml
domain:
  name: "agent-tools"
  description: "Agent with built-in tool capabilities"
  version: "1.0"

# Parameter extraction patterns
parameter_patterns:
  number:
    patterns:
      - '[\d,]+(?:\.\d+)?'
    normalizers:
      - type: "remove_commas"
      - type: "to_float"
  
  date:
    patterns:
      - '\d{4}-\d{2}-\d{2}'
      - '\d{1,2}/\d{1,2}/\d{4}'
    normalizers:
      - type: "parse_date"

# Response formatting
response_config:
  default_language: "en"
  supported_languages:
    - "en"
    - "fr"
  
  format_templates:
    calculation_result: "The result is **{{ result }}**"
    date_result: "The date is {{ formatted_date }}"
```

## Response Format

### Tool Execution Response

```json
{
  "content": "20% of 150 is **30**.",
  "metadata": {
    "source": "intent",
    "template_id": "calculate_percentage",
    "tool_execution": {
      "tool_name": "calculator",
      "operation": "percentage",
      "parameters": {
        "value": 150,
        "percentage": 20
      },
      "result": {
        "result": 30,
        "operation": "percentage",
        "input": {
          "value": 150,
          "percentage": 20
        }
      },
      "execution_time_ms": 2,
      "status": "success"
    },
    "synthesized": true
  },
  "confidence": 0.92
}
```

### Error Response

```json
{
  "content": "I couldn't complete the calculation. Please check your input.",
  "metadata": {
    "source": "intent",
    "template_id": "calculate_percentage",
    "tool_execution": {
      "tool_name": "calculator",
      "operation": "percentage",
      "status": "error",
      "error_message": "Division by zero"
    }
  },
  "confidence": 0.92
}
```

## Pydantic Models

### ToolDefinition

```python
class ToolDefinition(BaseModel):
    """Definition of a tool available for function calling."""
    name: str
    description: str
    parameters: List[ToolParameter]
    
    def to_openai_schema(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling format."""
        ...
```

### ToolParameter

```python
class ToolParameter(BaseModel):
    """Parameter definition for a tool."""
    name: str
    type: Literal["string", "number", "boolean", "array", "object"]
    description: str
    required: bool = True
    enum: Optional[List[str]] = None
    default: Optional[Any] = None
```

### ToolResult

```python
class ToolResult(BaseModel):
    """Result of tool execution."""
    tool_name: str
    operation: str
    status: ToolResultStatus  # success, error, timeout
    result: Optional[Any] = None
    error_message: Optional[str] = None
    execution_time_ms: float
    parameters: Dict[str, Any]
```

## Testing

### Unit Tests

The test suite covers:

- Tool definitions and schema conversion
- Built-in tool operations (calculator, date_time, json_transform)
- Response synthesis
- Template routing (query vs function)
- Error handling

Run tests:

```bash
pytest server/tests/test_retrievers/test_intent_agent_retriever.py -v
```

### Integration Testing

Test the full flow with the example adapter:

```bash
# 1. Start Ollama with required models
ollama pull gemma3:270m
ollama pull nomic-embed-text
ollama pull functiongemma  # Optional

# 2. Start ORBIT server
./bin/orbit.sh start

# 3. Create API key for the agent adapter
./utils/scripts/generate-sample-api-keys.sh --adapter intent-agent-example

# 4. Test via API
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer agent" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is 15% of 200?"}'
```

## Performance Considerations

### Model Selection

| Model Type | Latency | Accuracy | Cost |
|------------|---------|----------|------|
| Shared model | Lower | Good | Lower |
| Separate function model | Higher | Better | Higher |

### Tool Execution

| Tool | Typical Latency | Notes |
|------|-----------------|-------|
| Calculator | <5ms | Pure computation |
| Date/Time | <5ms | Local operations |
| JSON Transform | 5-50ms | Depends on data size |

### Recommendations

- For simple use cases: Use shared model
- For production with many tools: Use dedicated function model
- For complex JSON operations: Consider pagination

## Extending with Custom Tools

### Adding a New Built-in Tool

1. Add tool class to `BuiltinTools` in `tool_executor.py`:

```python
class BuiltinTools:
    @staticmethod
    def my_custom_tool(operation: str, **kwargs) -> Dict[str, Any]:
        if operation == "my_operation":
            # Your logic here
            return {"result": computed_value}
        raise ValueError(f"Unknown operation: {operation}")
```

2. Register in `ToolExecutor._execute_builtin_tool()`:

```python
elif tool_name == "my_custom_tool":
    return BuiltinTools.my_custom_tool(operation, **parameters)
```

3. Add templates in your tools.yaml:

```yaml
- id: "my_custom_operation"
  description: "Perform my custom operation"
  tool_type: "function"
  tool_name: "my_custom_tool"
  tool_operation: "my_operation"
  # ...
```

## Limitations

1. **Sequential Execution Only**: One tool call per request (no multi-step chains)
2. **Built-in Tools Only**: External API tools require HTTP template fallback
3. **No Tool Composition**: Cannot chain multiple tools in a single request
4. **Local Execution**: Tools run locally; no external service integration

## Related Documentation

- [Adapters Overview](./adapters.md) - General adapter architecture
- [Adapter Configuration](./adapter-configuration.md) - Configuration management
- [Composite Intent Retriever](./composite-intent-retriever.md) - Multi-source routing
- [Intent-SQL RAG System](./intent-sql-rag-system.md) - Intent adapter internals
