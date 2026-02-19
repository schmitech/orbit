# Capability-Based Architecture

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     Context Retrieval Pipeline                  │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
                    ┌──────────────────────────┐
                    │  ContextRetrievalStep    │
                    │                          │
                    │  should_execute()?       │
                    │  process()               │
                    └──────────────┬───────────┘
                                   │
                                   │ Query
                                   ▼
                    ┌──────────────────────────┐
                    │  AdapterCapabilities     │
                    │  Registry                │
                    │                          │
                    │  get(adapter_name)       │
                    └──────────────┬───────────┘
                                   │
                                   │ Returns
                                   ▼
                    ┌──────────────────────────┐
                    │  AdapterCapabilities     │
                    │                          │
                    │  • retrieval_behavior    │
                    │  • formatting_style      │
                    │  • supports_file_ids     │
                    │  • skip_when_no_files    │
                    │  • context_format        │
                    │  • context_max_tokens    │
                    │  • numeric_precision     │
                    │  • ...                   │
                    └──────────────┬───────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
                    ▼                             ▼
         ┌──────────────────┐        ┌──────────────────┐
         │ should_retrieve()│        │ build_retriever_ │
         │                  │        │ kwargs()         │
         │ Returns bool     │        │                  │
         │ based on context │        │ Returns dict     │
         └──────────────────┘        └──────────────────┘
```

## Before vs After

### Before: Hardcoded Checks

```
┌─────────────────────────────────────────────────────────────────┐
│                     ContextRetrievalStep                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  should_execute():                                              │
│    if adapter == 'multimodal':                                 │
│      return True                                                │
│    if adapter_type == 'passthrough':                           │
│      return False                                               │
│    # ... more hardcoded checks                                 │
│                                                                  │
│  process():                                                     │
│    if adapter == 'file-document-qa' or is_multimodal:          │
│      kwargs['file_ids'] = context.file_ids                     │
│    if 'file' in adapter_name.lower():                          │
│      use_clean_formatting = True                               │
│    # ... more hardcoded checks                                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

Problems:
  ❌ Hardcoded adapter names
  ❌ String matching
  ❌ Not extensible
  ❌ Difficult to test
```

### After: Capability-Based

```
┌─────────────────────────────────────────────────────────────────┐
│                     ContextRetrievalStep                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  should_execute():                                              │
│    capabilities = self._get_capabilities(adapter_name)          │
│    return capabilities.should_retrieve(context)                 │
│                                                                  │
│  process():                                                     │
│    capabilities = self._get_capabilities(adapter_name)          │
│    kwargs = capabilities.build_retriever_kwargs(context)        │
│    style = capabilities.formatting_style                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                                   │
                                   │ Delegates to
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AdapterCapabilities                           │
├─────────────────────────────────────────────────────────────────┤
│  • retrieval_behavior: "conditional"                            │
│  • formatting_style: "clean"                                    │
│  • supports_file_ids: true                                      │
│  • skip_when_no_files: true                                     │
│                                                                  │
│  should_retrieve(context):                                      │
│    if behavior == CONDITIONAL and skip_when_no_files:           │
│      return bool(context.file_ids)                              │
│                                                                  │
│  build_retriever_kwargs(context):                               │
│    kwargs = {}                                                  │
│    if supports_file_ids and context.file_ids:                   │
│      kwargs['file_ids'] = context.file_ids                      │
│    return kwargs                                                │
└─────────────────────────────────────────────────────────────────┘

Benefits:
  ✅ No hardcoded checks
  ✅ Configuration-driven
  ✅ Easily extensible
  ✅ Testable
```

## Data Flow

### Request Processing Flow

```
1. API Request
   │
   ├─ adapter_name: "simple-chat-with-files"
   ├─ message: "What's in the document?"
   ├─ file_ids: ["file123"]
   └─ api_key: "key_abc"

   ▼

2. Pipeline: ContextRetrievalStep.should_execute()
   │
   ├─ Get capabilities for "simple-chat-with-files"
   │  └─ Registry lookup or inference
   │
   ├─ Check: capabilities.should_retrieve(context)
   │  └─ behavior == CONDITIONAL + file_ids present = True
   │
   └─ Return: True (proceed with retrieval)

   ▼

3. Pipeline: ContextRetrievalStep.process()
   │
   ├─ Get capabilities for "simple-chat-with-files"
   │
   ├─ Build retriever kwargs
   │  └─ capabilities.build_retriever_kwargs(context)
   │     └─ {'file_ids': ['file123'], 'api_key': 'key_abc'}
   │
   ├─ Call retriever.get_relevant_context()
   │  └─ Returns: [doc1, doc2, doc3]
   │
   └─ Format context
      └─ capabilities.formatting_style == CLEAN
         └─ Use _format_clean() (no citations)

   ▼

4. Response
   └─ Formatted context without citations
```

## Capability Types

### RetrievalBehavior

```
┌───────────────┬─────────────────────────────────────────────┐
│ NONE          │ No retrieval (pure passthrough)            │
│               │ Example: simple-chat                        │
├───────────────┼─────────────────────────────────────────────┤
│ ALWAYS        │ Always retrieve context                     │
│               │ Example: qa-sql, file-document-qa           │
├───────────────┼─────────────────────────────────────────────┤
│ CONDITIONAL   │ Retrieve based on conditions                │
│               │ Example: multimodal (if file_ids present)   │
└───────────────┴─────────────────────────────────────────────┘
```

### FormattingStyle

```
┌───────────────┬─────────────────────────────────────────────┐
│ STANDARD      │ Citations with source and confidence        │
│               │ "[1] Doc (confidence: 0.85)"               │
│               │ Example: qa-sql, intent-postgres           │
├───────────────┼─────────────────────────────────────────────┤
│ CLEAN         │ No citations or metadata                    │
│               │ "## Content from files:\n\nContent..."    │
│               │ Example: file-document-qa, multimodal      │
├───────────────┼─────────────────────────────────────────────┤
│ CUSTOM        │ Custom formatting function                  │
│               │ Advanced use cases                          │
└───────────────┴─────────────────────────────────────────────┘
```

## Capability Inference Rules

```
adapter_config.type == "passthrough"
    │
    ├─ adapter_config.adapter == "multimodal"
    │  └─ RetrievalBehavior.CONDITIONAL
    │     FormattingStyle.CLEAN
    │     supports_file_ids: true
    │
    └─ Other passthrough
       └─ RetrievalBehavior.NONE
          FormattingStyle.STANDARD

adapter_config.adapter == "file"
OR "file" in adapter_config.name.lower()
    │
    └─ RetrievalBehavior.ALWAYS
       FormattingStyle.CLEAN
       supports_file_ids: true

Default (retriever adapters)
    │
    └─ RetrievalBehavior.ALWAYS
       FormattingStyle.STANDARD
```

## Extension Points

### Adding a New Adapter Type

```yaml
# adapters.yaml
- name: "my-custom-adapter"
  type: "retriever"
  adapter: "custom"

  # Just declare capabilities!
  capabilities:
    retrieval_behavior: "conditional"
    formatting_style: "clean"
    supports_file_ids: true
    supports_custom_param: true
    custom_parameters:
      - "custom_param1"
      - "custom_param2"
```

**No code changes needed in `context_retrieval.py`!**

### Context Efficiency Options

Control how context is formatted and sized via capabilities:

```yaml
# adapters.yaml
- name: "intent-sql-analytics"
  type: "retriever"
  adapter: "intent"

  capabilities:
    retrieval_behavior: "always"
    formatting_style: "standard"
    context_format: "markdown_table"  # markdown_table, toon, csv, or null (pipe-separated)
    context_max_tokens: 8000          # Drop low-confidence docs to fit budget
    numeric_precision:
      decimal_places: 2              # Round unformatted floats
```

**How it works:**
- `context_format` is read by intent retrievers (SQL, HTTP, GraphQL) and passed to `TableRenderer`
- `context_max_tokens` is applied after formatting in `ContextRetrievalStep._format_context()`
- `numeric_precision` is applied by `ResponseFormatter._format_single_result()` for floats without a `display_format`

### Custom Behavior Hooks (Advanced)

```python
from adapters.capabilities import AdapterCapabilities

# Define custom logic
def custom_should_execute(context):
    """Custom retrieval decision logic"""
    return context.user_id in premium_users

def custom_formatter(docs, truncation_info):
    """Custom formatting logic"""
    return "\n---\n".join([d['content'] for d in docs])

# Register capabilities
capabilities = AdapterCapabilities(
    retrieval_behavior=RetrievalBehavior.CONDITIONAL,
    formatting_style=FormattingStyle.CUSTOM,
    custom_should_execute=custom_should_execute,
    custom_format_context=custom_formatter
)
```

## Testing Strategy

### Unit Tests

```python
def test_multimodal_capabilities():
    """Test multimodal adapter capabilities"""
    capabilities = AdapterCapabilities.for_passthrough(
        supports_file_retrieval=True
    )

    # Test retrieval behavior
    context_with_files = Mock(file_ids=['f1', 'f2'])
    assert capabilities.should_retrieve(context_with_files) is True

    context_without_files = Mock(file_ids=[])
    assert capabilities.should_retrieve(context_without_files) is False

    # Test kwargs building
    kwargs = capabilities.build_retriever_kwargs(context_with_files)
    assert 'file_ids' in kwargs
    assert kwargs['file_ids'] == ['f1', 'f2']
```

### Integration Tests

```python
async def test_context_retrieval_with_multimodal():
    """Test context retrieval with multimodal adapter"""
    context = ProcessingContext(
        adapter_name="simple-chat-with-files",
        message="What's in the file?",
        file_ids=["file123"]
    )

    step = ContextRetrievalStep(container)

    # Should execute (has file_ids)
    assert step.should_execute(context) is True

    # Process and check formatting
    result = await step.process(context)
    assert "## Content extracted from uploaded file(s):" in result.formatted_context
    assert "[1]" not in result.formatted_context  # No citations
```

## Performance Considerations

### Capability Caching

Capabilities are loaded once at startup and cached:

```python
def _initialize_capabilities(self) -> None:
    """Load capabilities once at startup"""
    adapter_configs = adapter_manager._adapter_configs

    for adapter_name, adapter_config in adapter_configs.items():
        capabilities = self._infer_capabilities(adapter_config)
        self._capability_registry.register(adapter_name, capabilities)

    # Capabilities cached in registry - no repeated parsing
```

### Lookup Performance

```
Registry lookup: O(1) - Simple dictionary lookup
Capability inference: O(1) - Only runs once per adapter at startup
Decision making: O(1) - Boolean checks on capability flags
```

## Summary

The capability-based architecture provides:

1. **Clean Separation of Concerns**
   - Pipeline step focuses on orchestration
   - Capabilities encapsulate adapter behavior
   - No mixing of adapter-specific logic

2. **Configuration-Driven Design**
   - Behavior defined in YAML
   - No code changes for new adapters
   - Easy to understand and modify

3. **Type Safety**
   - Enum-based behaviors
   - No string matching
   - Compile-time checks

4. **Extensibility**
   - Add adapters via configuration
   - Custom behavior hooks available
   - No pipeline modifications needed

5. **Maintainability**
   - Self-documenting capabilities
   - Easy to test
   - Clear decision logic

**Result:** A flexible, maintainable, and extensible context retrieval system! 🎉
