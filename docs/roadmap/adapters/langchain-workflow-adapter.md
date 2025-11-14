# Workflow Adapter Implementation Plan

The proposed workflow adapter is an orchestration layer that lets us chain existing adapters declaratively. Each workflow entry in `adapters.yaml` lists ordered steps, where every step points at an existing adapter (intent, file, conversational, etc.), wraps it as a LangChain tool, and defines explicit input/output mappings. At runtime the workflow adapter executes those steps sequentially via a `WorkflowExecutor`, passes mapped data from one step to the next, and returns a final payload that matches the retriever contract so the broader inference pipeline can consume it unchanged.

## Overview

Create a new workflow adapter type that enables sequential execution of existing adapters (intent, conversational, file, etc.) using LangChain tools with explicit data mapping between steps. Workflows are defined declaratively in `adapters.yaml`.

## Architecture

The workflow adapter will:

1. Wrap existing adapters as LangChain tools
2. Execute workflow steps sequentially based on YAML configuration
3. Map data between steps using explicit field mappings
4. Integrate with the existing pipeline architecture

## Implementation Steps

### 1. Create Workflow Adapter Base Classes

**File: `server/adapters/workflow/base.py`**

- Create `WorkflowAdapter` base class extending `DocumentAdapter`
- Define workflow execution engine that processes YAML-defined steps sequentially
- Implement data mapping and context passing between steps

**File: `server/adapters/workflow/workflow_executor.py`**

- Create `WorkflowExecutor` class that:
  - Loads workflow definitions from adapter config
  - Executes steps sequentially
  - Handles data mapping between steps
  - Manages workflow context and state

### 2. Create LangChain Tool Wrappers

**File: `server/adapters/workflow/tools/adapter_tool.py`**

- Create `AdapterTool` class extending LangChain's `BaseTool`
- Wrap existing adapters (intent, conversational, file, etc.) as callable tools
- Each tool:
  - Takes query and optional parameters
  - Invokes the adapter's `get_relevant_context` method
  - Returns formatted results for next step

**File: `server/adapters/workflow/tools/__init__.py`**

- Export tool classes and factory functions

### 3. Create Workflow Implementation

**File: `server/implementations/workflow/workflow_implementation.py`**

- Create `WorkflowImplementation` extending `BaseRetriever`
- Integrates with `DynamicAdapterManager` to access other adapters
- Executes workflow steps using `WorkflowExecutor`
- Formats workflow results for pipeline consumption

### 4. Define YAML Schema and Configuration

**File: `config/adapters.yaml` (example entry)**

```yaml
- name: "intent-then-chat-workflow"
  enabled: true
  type: "workflow"
  datasource: "none"
  adapter: "workflow"
  implementation: "implementations.workflow.workflow_implementation.WorkflowImplementation"
  inference_provider: "ollama_cloud"
  model: "kimi-k2-thinking:cloud"
  
  config:
    workflow:
      steps:
    - name: "intent_query"
          adapter: "intent-sql-postgres"
          tool_name: "query_database"
          input_mapping:
            query: "{user_message}"
          output_mapping:
            db_results: "{results}"
            
    - name: "conversational_response"
          adapter: "simple-chat"
          tool_name: "generate_response"
          input_mapping:
            query: "{user_message}"
            context: "{db_results}"
          output_mapping:
            final_response: "{response}"
```

### 5. Register Workflow Adapter

**File: `server/adapters/__init__.py`**

- Register workflow adapter with `DocumentAdapterFactory`
- Add workflow adapter type to adapter registry

**File: `server/adapters/factory.py`**

- Add workflow adapter factory function

### 6. Integration Points

**File: `server/services/dynamic_adapter_manager.py`**

- Ensure workflow adapters can access other adapters via `get_adapter()`
- Support adapter references in workflow steps

**File: `server/inference/pipeline/steps/context_retrieval.py`**

- Ensure workflow adapters are handled in context retrieval step
- Workflow adapters should return results compatible with existing pipeline

### 7. Error Handling and Validation

- Validate workflow YAML structure on adapter initialization
- Handle adapter failures gracefully (skip step, use fallback, etc.)
- Provide clear error messages for missing adapters or invalid mappings
- Log workflow execution trace for debugging

### 8. Testing

**File: `server/tests/test_workflow_adapter.py`**

- Test sequential step execution
- Test data mapping between steps
- Test adapter tool wrapping
- Test error handling
- Test integration with existing adapters

## Key Design Decisions

1. **LangChain Tools**: Use LangChain's `BaseTool` interface to wrap adapters, enabling future agent-based workflows while supporting sequential execution now.

2. **Data Mapping**: Use explicit field mappings (e.g., `{user_message}` → `query`) to make data flow clear and debuggable.

3. **Adapter Access**: Workflow executor uses `DynamicAdapterManager` to get adapter instances, ensuring proper initialization and caching.

4. **Pipeline Integration**: Workflow adapters return results in the same format as other retrievers, ensuring seamless pipeline integration.

5. **YAML Configuration**: Workflows defined in `adapters.yaml` for consistency with existing adapter configuration patterns.

## Files to Create/Modify

**New Files:**

- `server/adapters/workflow/base.py`
- `server/adapters/workflow/workflow_executor.py`
- `server/adapters/workflow/tools/adapter_tool.py`
- `server/adapters/workflow/tools/__init__.py`
- `server/implementations/workflow/workflow_implementation.py`
- `server/tests/test_workflow_adapter.py`

**Modified Files:**

- `config/adapters.yaml` (add example workflow adapter)
- `server/adapters/__init__.py` (register workflow adapter)
- `server/adapters/factory.py` (add workflow factory)

## Dependencies

- LangChain (already in `install/dependencies.toml`)
- Existing adapter infrastructure
- `DynamicAdapterManager` for adapter access

## Assessment

### Value Proposition

- Centralizes multi-adapter sequences in configuration so product teams can reuse existing intent/chat/file adapters without bespoke glue code, aligning with the current YAML-driven registry.
- Wrapping adapters as LangChain tools future-proofs the design for agentic workflows while still delivering a deterministic executor today.
- Explicit input/output mappings make data flow debuggable and give the workflow executor a clear contract when pulling adapters from `DynamicAdapterManager`.

### Risks and Gaps

- The plan introduces numerous new modules and registry changes; validate that there is sufficient demand for multi-step workflows before committing to the full surface area.
- The YAML example is currently malformed and there is no concrete schema enforcement story—define a schema (pydantic or JSON Schema) early to avoid fragile runtime validation.
- Not every adapter cleanly exposes `get_relevant_context`; clarify how generators or side-effecting adapters should be wrapped so the tool abstraction does not leak.
- Execution is strictly sequential with no branching, retries, or parallel steps; if conditional flows are on the roadmap, note the eventual path to support them.
- Error handling guidance is high level; specify concrete strategies (retry counts, short-circuit semantics, partial outputs) to keep the workflow adapter reliable.

### Recommendation

If teams already chain adapters manually, this adapter should provide real value sooner rather than later. If workflows are still speculative, consider piloting a thinner “fetch + respond” orchestrator first to validate demand, then expand into the broader LangChain-based architecture.
