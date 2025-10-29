# File Upload and Conversation Integration Plan

## Overview

Enable ChatGPT-like file uploads and conversations with files by integrating:

- Frontend file upload UI components
- Backend file routes registration
- File adapter activation and chat integration
- API client file methods
- Context-aware chat with file references

## Architecture Flow

### Upload Flow

1. User uploads file → Frontend sends to `/api/files/upload`
2. Backend processes file → Extraction, chunking, vector indexing
3. File metadata stored → SQLite metadata store
4. Response includes `file_id` → Frontend stores in conversation context

### Conversation Flow

1. User sends message with file context → Frontend includes `file_id` references
2. Chat endpoint receives message → Extracts `file_id` from context or message
3. Adapter manager routes to file adapter → Uses `file-document-qa` adapter
4. File retriever queries vector store → Semantic search over file chunks
5. Results formatted → Included in LLM context
6. Streaming response → Frontend displays with file context indicators

## Implementation Tasks

### 1. Backend Integration

#### 1.1 Register File Routes (`server/main.py` or route configurator)

- Import `create_file_router()` from `file_routes.py`
- Register router with main FastAPI app
- Ensure `FileProcessingService` is initialized in app state

**Files**: `server/main.py`, `server/routes/routes_configurator.py`

#### 1.2 Complete File Query Endpoint (`server/routes/file_routes.py`)

- Replace TODO in `/api/files/{file_id}/query` endpoint
- Initialize `FileVectorRetriever` with adapter config
- Perform semantic search over file chunks
- Return formatted query results

**File**: `server/routes/file_routes.py` (lines 338-344)

#### 1.3 Integrate File Context in Chat Endpoint (`server/routes/routes_configurator.py`)

- Modify chat request model to accept optional `file_ids: List[str]`
- Extract file IDs from request or message context
- Pass file context to adapter execution
- File adapter should handle `file_id` filtering in retrieval

**File**: `server/routes/routes_configurator.py`

#### 1.4 Enhance File Adapter for Chat Context (`server/retrievers/implementations/file/file_retriever.py`)

- Modify `get_relevant_context()` to accept `file_ids: List[str]`
- Filter collections by provided file IDs
- Ensure proper API key and file ownership validation

**File**: `server/retrievers/implementations/file/file_retriever.py`

#### 1.5 Activate File Adapter (`config/adapters.yaml`)

- Enable `file-document-qa` adapter (change `enabled: false` to `true`)
- Verify configuration matches file processing service settings
- Ensure vision provider is configured for image support

**File**: `config/adapters.yaml` (line 478)

### 2. Frontend Integration

#### 2.1 Add File Upload Types (`clients/chat-app/src/types/index.ts`)

- Add `FileAttachment` interface with `file_id`, `filename`, `mime_type`, `file_size`
- Extend `Message` interface with optional `attachments: FileAttachment[]`
- Extend `Conversation` with `attachedFiles: FileAttachment[]`

**File**: `clients/chat-app/src/types/index.ts`

#### 2.2 Create File Upload Service (`clients/chat-app/src/services/fileService.ts`)

- Implement `uploadFile(file: File, apiUrl: string, apiKey: string)` function
- Handle FormData creation and multipart upload
- Return file metadata including `file_id`
- Add error handling and progress tracking hooks

**New File**: `clients/chat-app/src/services/fileService.ts`

#### 2.3 Enhance API Client (`clients/node-api/api.ts`)

- Add `uploadFile(file: File)` method to `ApiClient` class
- Add `queryFile(fileId: string, query: string)` method
- Add `listFiles()` method
- Add `deleteFile(fileId: string)` method
- Export file-related functions

**File**: `clients/node-api/api.ts`

#### 2.4 Implement File Upload Component (`clients/chat-app/src/components/FileUpload.tsx`)

- Create file picker component with drag-and-drop
- Show upload progress indicator
- Display uploaded files with preview/metadata
- Support multiple file uploads
- Handle file type validation (client-side check)

**New File**: `clients/chat-app/src/components/FileUpload.tsx`

#### 2.5 Update MessageInput Component (`clients/chat-app/src/components/MessageInput.tsx`)

- Enable attachment button (remove `disabled` prop)
- Integrate file upload UI
- Pass selected files to send handler
- Show attached files in input area

**File**: `clients/chat-app/src/components/MessageInput.tsx` (line 89)

#### 2.6 Update Chat Store (`clients/chat-app/src/stores/chatStore.ts`)

- Add `attachedFiles` state to conversations
- Implement `uploadFile()` action
- Modify `sendMessage()` to include file IDs in request
- Track file uploads per conversation

**File**: `clients/chat-app/src/stores/chatStore.ts`

#### 2.7 Update Chat Context/Store (`clients/chat-app/src/contexts/ChatContext.tsx` or store)

- Modify chat API call to include file context
- Add `file_ids` array to chat request payload
- Handle file attachment display in messages
- Store file metadata with messages

**Files**: `clients/chat-app/src/contexts/ChatContext.tsx`, `clients/chat-app/src/stores/chatStore.ts`

#### 2.8 Display File Attachments (`clients/chat-app/src/components/Message.tsx`)

- Show attached files in message bubbles
- Display file icons/metadata
- Show file previews for images
- Add file download/remove actions

**File**: `clients/chat-app/src/components/Message.tsx`

### 3. Multimodal Support

#### 3.1 Vision Service Integration (Already exists)

- Verify vision service is registered in AI services factory
- Ensure vision provider config is accessible to file processing
- File processing service already calls vision service for images

**File**: `server/services/file_processing/file_processing_service.py` (lines 205-251)

#### 3.2 Image Preview in Frontend (`clients/chat-app/src/components/FilePreview.tsx`)

- Create image preview component
- Handle image file display
- Show OCR results or image descriptions
- Support multiple image formats

**New File**: `clients/chat-app/src/components/FilePreview.tsx`

### 4. Testing

#### 4.1 Update API Tests (`clients/node-api/test/api.test.ts`)

- Add tests for `uploadFile()` function
- Add tests for `queryFile()` function
- Test error handling scenarios
- Test file type validation

**File**: `clients/node-api/test/api.test.ts`

#### 4.2 Frontend Integration Tests

- Test file upload flow
- Test chat with file attachments
- Test file display in messages
- Test error states (upload failure, invalid types)

## Configuration Updates

### Enable File Adapter

- Set `enabled: true` in `config/adapters.yaml` for `file-document-qa`
- Verify chunking strategy matches requirements
- Ensure vision provider is configured

### Environment Variables

- No new env vars needed (uses existing API URL/key config)

## Key Integration Points

1. **File Routes → Main App**: Register router in FastAPI app
2. **File Processing → Chat**: File adapter receives file context from chat endpoint
3. **API Client → Frontend**: Add file upload methods to API client
4. **Frontend → Backend**: Send file IDs with chat messages
5. **File Metadata → Vector Store**: Chunks indexed with file metadata
6. **Vision Service → File Processing**: Images processed via vision service

## File Chunking Strategy

Already implemented in `server/services/file_processing/chunking/`:

- `FixedSizeChunker`: Fixed-size chunks with overlap
- `SemanticChunker`: Sentence-aware semantic chunking
- Configurable via adapter config (`chunking_strategy`, `chunk_size`, `chunk_overlap`)

## MIME Type Handlers

File processing service routes to processors based on MIME type:

- Documents: PDF, DOCX via Docling
- Images: PNG, JPEG via Vision Service
- Data: CSV via DuckDB path (if enabled)
- Text: TXT, MD via text processors

All processors registered in `FileProcessorRegistry`.