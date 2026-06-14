# Example 8: Agent with Function Calling

The Agent Retriever extends the intent pattern with *tool execution*. Instead of returning retrieved documents, it runs built-in tools (calculator, date/time, JSON transforms) or calls external APIs (weather, finance, location) and synthesizes the result.

### How it works

1. User asks: "What is 15% of 200?"
2. ORBIT matches the query to a function template.
3. The function-calling model emits a tool call with parameters.
4. A built-in tool executes.
5. ORBIT synthesizes a natural-language reply.

### Built-in tools

| Tool | Operations | Examples |
|:---|:---|:---|
| **Calculator** | percentage, add, subtract, multiply, divide, average, round | "What is 20% of 500?" |
| **Date/Time** | now, format, diff, add_days, parse | "How many days until March 1st?" |
| **JSON Transform** | filter, sort, select, aggregate | "Filter items where price > 100" |

### HTTP-backed tools (require config)

| Tool | Description | Examples |
|:---|:---|:---|
| **Weather** | Current conditions and forecasts | "What's the weather in London?" |
| **Location** | Geocoding and place search | "Find coordinates of the Eiffel Tower" |
| **Finance** | Stock quotes and currency conversion | "Convert 100 USD to EUR" |
| **Productivity** | Notifications and tasks | "Create a task for tomorrow" |

### Adapter configuration (pre-wired in `config/adapters/intent.yaml`)

```yaml
- name: "intent-agent-example"
  enabled: true
  type: "retriever"
  datasource: "http"
  adapter: "intent"
  implementation: "retrievers.implementations.intent.IntentAgentRetriever"

  # Embedding for template matching
  embedding_provider: "ollama"
  embedding_model: "nomic-embed-text"

  # Inference model for response synthesis
  inference_model_provider: "ollama"
  inference_model: "gemma3:270m"

  config:
    domain_config_path: "examples/intent-templates/agent-template/domain.yaml"
    template_library_path:
      - "examples/intent-templates/agent-template/tools.yaml"

    confidence_threshold: 0.6
    max_templates: 5

    agent:
      # Optional dedicated function-calling model
      function_model_provider: "ollama"
      function_model: "functiongemma"

      synthesize_response: true
```

### Create an API key

```bash
./bin/orbit.sh key create \
  --adapter intent-agent-example \
  --name "Agent Assistant" \
  --prompt-file ./examples/intent-templates/agent-template/agent-assistant-prompt.md \
  --prompt-name "Agent Assistant"
```

Or use the helper script:

```bash
./utils/scripts/generate-sample-api-keys.sh --adapter intent-agent-example
```

### Try it

**Calculator:** "What is 15% of 200?" · "Average of 10, 20, 30, 40" · "Multiply 125 by 8"

**Date/Time:** "What's today's date?" · "Days until December 25th?" · "Add 30 days to January 15, 2026"

**JSON Transform:** "Sort this data by price descending" · "Filter items where quantity > 10" · "Sum of all amounts"

**HTTP tools (when configured):** "Weather in San Francisco?" · "Apple stock price?" · "Convert 100 USD to EUR" · "Create a task to review the report"

### Multi-model setup (optional)

For better accuracy, split the work across specialized models:

```yaml
inference_model_provider: "ollama"
inference_model: "gemma3:270m"

embedding_provider: "ollama"
embedding_model: "nomic-embed-text"

config:
  agent:
    function_model_provider: "ollama"
    function_model: "functiongemma"
```

If no `function_model` is set, the inference model handles both synthesis and function calls.

### Response format

```json
{
  "content": "15% of 200 is **30**.",
  "metadata": {
    "tool_execution": {
      "tool_name": "calculator",
      "operation": "percentage",
      "parameters": {"value": 200, "percentage": 15},
      "result": {"result": 30},
      "status": "success"
    }
  }
}
```

See [Intent Agent Retriever](../adapters/intent-agent-retriever.md) for custom tool development.

---

[Tutorial home](../tutorial.md) | [Previous: Example 7: Multi-Source Composite](multi-source-composite.md) | [Next: Example 9: Skills and Image Generation](skills-image-generation.md)

---
