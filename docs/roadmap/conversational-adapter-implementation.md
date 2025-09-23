# Conversational Adapter Implementation Plan

## Overview

This document outlines the implementation plan for creating a conversational adapter that acts as a passthrough with LLM inference and conversation memory. The adapter will work in `inference_only: true` mode with `chat_history: enabled: true`, serving as a conversational AI interface without any retrieval functionality.

## Requirements

- Act as a conversational AI interface with LLM inference and conversation memory
- Work in `inference_only: true` mode with `chat_history: enabled: true`
- Serve as a passthrough without any retrieval functionality
- Support inference provider override like other adapters
- Support model specification per adapter (e.g., different OpenAI models, Groq models, Ollama models)
- Integrate seamlessly with the existing pipeline architecture

## Architecture

### Design Principles

1. **Passthrough Design**: No retrieval, just passes user message to LLM
2. **Conversation Memory**: Full conversation history support
3. **Provider Override**: Can specify different LLM providers per adapter
4. **Model Specification**: Can specify different models per adapter (e.g., gpt-4, claude-3, llama3)
5. **Pipeline Integration**: Works with existing pipeline architecture
6. **Fault Tolerance**: Inherits all fault tolerance features
7. **Configuration**: YAML-based configuration like other adapters

### Integration Points

- Works with existing `PipelineChatService`
- Integrates with `ChatHistoryService` for conversation memory
- Uses `inference_only` pipeline (skips context retrieval step)
- Leverages same prompt mechanism as other adapters via `PromptService`
- Supports all existing LLM providers

## Implementation Plan

### 1. ConversationalAdapter Class

**File**: `server/adapters/passthrough/conversational/conversational_adapter.py`

- Extends `DocumentAdapter` interface
- Implements passthrough functionality (no actual document formatting)
- Leverages `PromptService` for system prompt management
- Handles conversation context preparation for LLM
- Manages conversation history integration

**Key Methods**:
- `format_document()`: Returns empty or minimal context
- `extract_direct_answer()`: Not applicable for passthrough
- `apply_domain_specific_filtering()`: No filtering needed

### 2. ConversationalImplementation Class

**File**: `server/implementations/passthrough/conversational/conversational_implementation.py`

- Extends `BaseRetriever` but skips actual retrieval
- Returns empty context to allow pure LLM inference
- Integrates with conversation history service
- Leverages `PromptService` for system prompt management (same as other adapters)
- Supports inference provider override
- Supports model specification per adapter

**Key Methods**:
- `get_relevant_context()`: Returns empty list (no retrieval)
- `initialize()`: Minimal initialization
- `retrieve()`: Not implemented (passthrough)

### 3. Adapter Registration

**Files**: 
- `server/adapters/registry.py` (new centralized registry)
- `server/adapters/domain_adapters.py` (new centralized adapters)

- Register in adapter registry system
- Add to `DocumentAdapterFactory`
- Ensure proper integration with dynamic adapter manager
- Support both retriever and passthrough adapter types

### 4. Configuration

**File**: `config/adapters.yaml`

Add chatbot adapter entry with:
- Support for inference provider override
- Support for model specification per adapter
- Support for system prompt configuration (via PromptService)
- Conversation history integration
- Appropriate fault tolerance settings
- No retrieval-specific configuration

### 5. File Structure

```
server/
├── adapters/
│   └── conversational/
│       ├── __init__.py
│       └── conversational_adapter.py
└── implementations/
    └── conversational/
        ├── __init__.py
        └── conversational_implementation.py
```

## Configuration Example

```yaml
- name: "conversational-passthrough"
  enabled: true
  type: "passthrough"  # New adapter type for non-retrieval adapters
  datasource: "none"  # No actual datasource needed
  adapter: "conversational"
  implementation: "adapters.passthrough.conversational.ConversationalAdapter"
  inference_provider: "groq"  # Override default
  model: "llama3-8b-8192"  # Specific model for this adapter
```

**Multiple Model Examples**:
```yaml
# OpenAI GPT-4
- name: "conversational-gpt4"
  enabled: true
  type: "passthrough"
  datasource: "none"
  adapter: "conversational"
  implementation: "adapters.passthrough.conversational.ConversationalAdapter"
  inference_provider: "openai"
  model: "gpt-4"
  config:
    # No retrieval-specific config needed for passthrough

# Anthropic Claude
- name: "conversational-claude"
  enabled: true
  type: "passthrough"
  datasource: "none"
  adapter: "conversational"
  implementation: "adapters.passthrough.conversational.ConversationalAdapter"
  inference_provider: "anthropic"
  model: "claude-3-sonnet-20240229"
  config:
    # No retrieval-specific config needed for passthrough

# Ollama Local Model
- name: "conversational-ollama"
  enabled: true
  type: "passthrough"
  datasource: "none"
  adapter: "conversational"
  implementation: "adapters.passthrough.conversational.ConversationalAdapter"
  inference_provider: "ollama"
  model: "llama3:8b"
  config:
    # No retrieval-specific config needed for passthrough
```

## Implementation Steps

1. **Create new folder structure** for passthrough adapters and implementations
2. **Create ConversationalAdapter class** that implements DocumentAdapter interface for passthrough functionality
3. **Create ConversationalImplementation class** that extends BaseRetriever but skips actual retrieval
4. **Update adapter registry system** to support both retriever and passthrough types
5. **Register the new conversational adapter** in the centralized adapter registry
6. **Add conversational adapter configuration** to adapters.yaml with new "passthrough" type
7. **Test the conversational adapter integration** with inference-only mode and conversation history

## Future Similar Adapters

This new structure will support future non-retrieval adapters such as:
- **Translation Adapter**: For language translation without retrieval
- **Summarization Adapter**: For document summarization without retrieval  
- **Code Generation Adapter**: For code generation without retrieval
- **Text Processing Adapter**: For text transformation without retrieval
- **Custom LLM Adapter**: For specialized LLM tasks without retrieval

## Benefits

- **Conversational AI Interface**: Provides a clean, conversational AI interface
- **Memory Support**: Full conversation history integration
- **Provider Flexibility**: Can use different LLM providers per adapter
- **Model Flexibility**: Can specify different models per adapter (GPT-4, Claude-3, Llama3, etc.)
- **Pipeline Integration**: Works seamlessly with existing architecture
- **No Complexity**: No retrieval logic, just pure LLM inference
- **Configuration**: Easy to configure and deploy

## Use Cases

- Conversational AI without RAG capabilities
- General-purpose conversational interfaces
- Testing and development environments
- Applications requiring pure LLM inference with conversation memory
- A/B testing different models for conversational AI
- Specialized conversational interfaces for different use cases (technical, casual, formal)

## Dependencies

- Existing `PipelineChatService`
- `ChatHistoryService` for conversation memory
- `PromptService` for system prompt management (same as other adapters)
- `BaseRetriever` for adapter structure (even though it's passthrough)
- `DocumentAdapter` interface
- Adapter registry system (updated to support passthrough types)
- Configuration system (with model specification support)
- LLM inference providers (OpenAI, Anthropic, Groq, Ollama, etc.)
- Model configuration system (for model-specific settings)
- Pipeline inference architecture (for inference-only mode)
