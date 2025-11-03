# Multimodal Conversational Adapter Implementation Plan

## Overview

Create a new hybrid adapter (`conversational-multimodal`) that combines:

- **Conversational passthrough**: Maintains conversation history like `conversational-passthrough`
- **File retrieval**: Queries file chunks from vector store like `file-document-qa`
- **Session-based file tracking**: Associates files with conversations/sessions using Redis

## Architecture

### Adapter Components

1. **New Implementation**: `server/implementations/passthrough/multimodal/multimodal_implementation.py`

- Extends `BaseRetriever` (similar to `ConversationalImplementation`)
- Integrates `FileVectorRetriever` for file chunk retrieval
- Uses Redis to track files per session
- Returns empty context when no files, file chunks when files are present

2. **New Adapter**: `server/adapters/passthrough/adapter.py` (extend existing)

- Add `MultimodalAdapter` class that handles conversation + file context formatting

3. **Configuration**: `config/adapters.yaml`

- Add new `conversational-multimodal` adapter entry
- Configure with same providers as `conversational-passthrough`
- Include file adapter config settings

### File Tracking Strategy

**Redis-based Session File Tracking**:

- Store file associations: `conversation_files:{session_id}` → `List[str]` (file_ids)
- When message includes `file_ids`, add/update files in session
- When retrieving context, fetch all files for session and query their chunks
- TTL: Match session TTL (default 1 hour from Redis config)

### Integration Points

1. **Pipeline Integration**: File chunks retrieved in `ContextRetrievalStep`

- Adapter's `get_relevant_context()` returns file chunks when files present
- Empty list when no files (pure conversation mode)

2. **Chat Service**: Already supports `file_ids` parameter

- Pass `file_ids` to adapter via `ProcessingContext`
- Adapter uses `file_ids` to query chunks from vector store

3. **File Routes**: Already exist (`file_routes.py`)

- Frontend uploads files → gets `file_id`
- Frontend sends `file_ids` with chat message → backend queries chunks

## Implementation Tasks

### 1. Create Multimodal Implementation

**File**: `server/implementations/passthrough/multimodal/multimodal_implementation.py`

- Extend `BaseRetriever`
- Initialize `FileVectorRetriever` instance
- Initialize `RedisService` for file tracking
- Implement `get_relevant_context()`:
- Accept `file_ids` from `kwargs`
- Update Redis: add file_ids to session's file list
- For each file_id: query vector store for relevant chunks
- Combine chunks from all files
- Return formatted results

### 2. Extend Passthrough Adapter

**File**: `server/adapters/passthrough/adapter.py`

- Add `MultimodalAdapter` class (similar to `ConversationalAdapter`)
- Format file chunks alongside conversation context
- Handle metadata from file chunks

### 3. Register Adapter Components

**File**: `server/adapters/__init__.py`

- Register multimodal adapter factory
- Add to `ADAPTER_REGISTRY` as type `passthrough`, name `multimodal`

### 4. Add Adapter Configuration

**File**: `config/adapters.yaml`

- Add `conversational-multimodal` entry after `conversational-passthrough`
- Configure with same providers (inference, embedding, vision)
- Include file adapter config: `collection_prefix`, vector store settings

### 5. Update Processing Context

**Files**:

- `server/inference/pipeline/steps/context_retrieval.py`
- `server/inference/pipeline.py`

- Ensure `file_ids` from request propagate to `ProcessingContext`
- Pass `file_ids` to adapter's `get_relevant_context()` via `kwargs`

### 6. File Tracking Service (Optional Helper)

**File**: `server/services/conversation_file_service.py` (new)

- Service to manage session-file associations in Redis
- Methods:
- `add_files_to_session(session_id, file_ids)`
- `get_session_files(session_id) -> List[str]`
- `remove_files_from_session(session_id, file_ids)`

## Design Decisions

### File Retrieval

- **Strategy**: Retrieve chunks from ALL files in session when message includes any `file_ids`
- **Rationale**: Ensures full context available, let LLM determine relevance
- **Alternative**: Can add semantic filtering later if needed

### Storage

- **Primary**: Redis for session-file mapping (fast, ephemeral)
- **Metadata**: FileMetadataStore (SQLite/MongoDB) for file info
- **Chunks**: Vector store (ChromaDB) for semantic search

### Context Format

- File chunks formatted with metadata: `file_id`, `chunk_index`, `filename`
- Included in context alongside conversation history
- LLM receives: conversation history + relevant file chunks

## Testing Considerations

- Test with no files (should behave like conversational-passthrough)
- Test with single file (retrieve chunks)
- Test with multiple files (combine chunks)
- Test session file persistence in Redis
- Test file chunk retrieval from vector store

## Files to Create/Modify

**New Files**:

- `server/implementations/passthrough/multimodal/__init__.py`
- `server/implementations/passthrough/multimodal/multimodal_implementation.py`
- `server/services/conversation_file_service.py` (optional helper)

**Modified Files**:

- `server/adapters/passthrough/adapter.py` (add MultimodalAdapter)
- `server/adapters/__init__.py` (register multimodal adapter)
- `config/adapters.yaml` (add conversational-multimodal entry)
- `server/inference/pipeline/steps/context_retrieval.py` (ensure file_ids passed)
- `server/inference/pipeline.py` (ensure ProcessingContext includes file_ids)