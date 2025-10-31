# Chatbot API Integration

This chat application integrates with the `@schmitech/chatbot-api` package for real-time streaming chat responses and file upload capabilities.

## Configuration

The application supports multiple ways to configure the API:

### 1. Environment Variables (Vite)
Create a `.env.local` file in the root directory:

```bash
VITE_API_URL=https://your-api-endpoint.com
VITE_API_KEY=your-api-key-here
VITE_USE_LOCAL_API=true          # Set to 'true' to use local API build
VITE_LOCAL_API_PATH=/api.mjs      # Path to local API (defaults to /api.mjs from public directory)
VITE_CONSOLE_DEBUG=false          # Enable debug logging
```

### 2. Window Variables
Set global variables in your HTML or before the app loads:

```javascript
window.CHATBOT_API_URL = 'https://your-api-endpoint.com';
window.CHATBOT_API_KEY = 'your-api-key-here';
```

### 3. Runtime Configuration
Use the "Configure API" button in the chat interface to set the API URL and key at runtime.

## Local Development Setup

### Using Local API Build

For local development, you can use the local API build instead of the npm package:

**Option 1: Use the convenience script** (recommended):
```bash
npm run dev:with-api
```
This script automatically:
1. Builds the API from `../node-api`
2. Copies the built files to `public/api.mjs`
3. Starts the dev server with local API enabled

**Option 2: Manual setup**:
```bash
# Build and copy API files
npm run build:api

# Start dev server with local API
npm run dev:local
```

**Option 3: Build API separately**:
```bash
# From node-api directory
cd ../node-api
npm run build:chat-app

# Then start chat-app
cd ../chat-app
npm run dev:local
```

The local API files will be copied to `src/api/local/` directory. When `VITE_USE_LOCAL_API=true` is set, the app will load `./local/api.mjs` from the src directory instead of the npm package.

## Features

- **Streaming Responses**: Real-time streaming of AI responses
- **File Upload**: Upload and attach files (PDF, DOCX, TXT, CSV, JSON, HTML, images, audio) to conversations
- **File Context**: Query uploaded files and include them in chat context
- **Session Management**: Automatic session ID generation and persistence
- **Error Handling**: Comprehensive error handling with user-friendly messages
- **Conversation Persistence**: Chat history is saved to localStorage
- **API Configuration**: Flexible API configuration options

## Usage

### Basic Chat

1. Configure your API settings using one of the methods above
2. Start a conversation by typing a message
3. The AI will respond with streaming text
4. Use the regenerate button (↻) to regenerate responses
5. Use the copy button to copy AI responses to clipboard

### File Upload

1. Click the paperclip icon (📎) in the message input
2. Upload files using drag-and-drop or file picker
3. Supported formats: PDF, DOCX, TXT, CSV, JSON, HTML, Markdown, images (PNG, JPEG, TIFF), audio (WAV, MP3)
4. Files are automatically processed and indexed
5. Attach files to messages - they will be included in the chat context
6. Files are chunked and stored in the vector store for semantic search

**File Upload Flow**:
- Upload files using the file upload UI
- Files are processed on the server (extraction, chunking, embedding)
- File IDs are automatically included with your messages
- The AI can query and reference uploaded files in responses

## File Upload Details

### Supported File Types

| Type | Formats | Processing |
|------|---------|------------|
| Documents | PDF, DOCX, PPTX, XLSX | Text extraction, chunking, vector indexing |
| Text | TXT, MD, HTML | Direct chunking and indexing |
| Data | CSV, Parquet | DuckDB integration or vector store |
| Images | PNG, JPEG, TIFF | OCR via vision service |
| Audio | WAV, MP3 | ASR (Automatic Speech Recognition) |

### File Size Limits

- Maximum file size: 50MB
- Maximum files per conversation: 5 (configurable)

### File Processing

Files are processed through the following pipeline:
1. **Upload**: File uploaded via `/api/files/upload`
2. **Validation**: File type and size validation
3. **Storage**: File saved to filesystem (or S3 in production)
4. **Extraction**: Text and metadata extracted using format-specific processors
5. **Chunking**: Content chunked using configured strategy (fixed or semantic)
6. **Indexing**: Chunks indexed in vector store for semantic search
7. **Metadata**: Processing status tracked in SQLite

## Available Scripts

- `npm run dev` - Start dev server (uses npm package)
- `npm run dev:local` - Start dev server with local API enabled
- `npm run dev:with-api` - Build API and start dev server with local API
- `npm run build` - Build for production (uses npm package)
- `npm run build:local` - Build for production with local API
- `npm run build:api` - Build API and copy to public directory
- `npm run preview` - Preview production build
- `npm run preview:local` - Preview production build with local API

## Integration Details

The integration uses:
- **Zustand** for state management (replacing React Context)
- **@schmitech/chatbot-api** for streaming chat functionality and file operations
- **localStorage** for persistent session and conversation storage
- **TypeScript** for type safety throughout the integration
- **File Upload Service** for handling file uploads with progress tracking
- **Vector Store** for semantic search over uploaded file content

## Troubleshooting

### Local API Not Loading

If you see a 404 error for `api.mjs`:

1. **Ensure API is built**:
   ```bash
   cd ../node-api
   npm run build
   ```

2. **Copy files to src/api/local directory**:
   ```bash
   mkdir -p ../chat-app/src/api/local
   cp dist/api.mjs ../chat-app/src/api/local/api.mjs
   cp dist/api.d.ts ../chat-app/src/api/local/api.d.ts
   ```

3. **Restart dev server with local API enabled**:
   ```bash
   npm run dev:local
   ```

4. **Check environment variable**:
   - Ensure `VITE_USE_LOCAL_API=true` is set (or use `npm run dev:local`)
   - The default path `./local/api.mjs` should work if files are in `src/api/local/`

### File Upload Issues

- **File size exceeded**: Check file size (max 50MB)
- **Unsupported format**: Verify file type is in supported list
- **Upload fails**: Check server logs and API key configuration
- **Processing fails**: Ensure file processing service is initialized on server

### Debug Mode

Enable debug logging by setting:
```bash
VITE_CONSOLE_DEBUG=true
```

This will show detailed API loading and file upload information in the console.
