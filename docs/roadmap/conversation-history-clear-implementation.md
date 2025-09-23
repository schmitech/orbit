# Conversation History Clear Implementation Plan

## Overview
This document outlines the implementation plan for adding conversation history clearing functionality to the ORBIT system. The feature will allow users to clear conversation history using API key authentication and session ID through admin routes and client libraries.

## Goals
- Add a new admin route to clear conversation history by session ID
- Implement client-side methods in both Python and Node.js clients
- Ensure proper authentication and authorization
- Maintain data integrity and audit logging
- Follow existing patterns and conventions

## Implementation Phases

### Phase 1: Backend Service Enhancement
**Files to modify:**
- `server/services/chat_history_service.py`
- `server/routes/admin_routes.py`
- `server/models/schema.py`

#### 1.1 Enhance Chat History Service
**File:** `server/services/chat_history_service.py`

Add new method to the `ChatHistoryService` class:

```python
async def clear_conversation_history(
    self,
    session_id: str,
    api_key: str,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Clear conversation history for a specific session with mandatory API key validation.
    
    Args:
        session_id: Session identifier to clear (required)
        api_key: API key for validation and authorization (required)
        user_id: Optional user ID for additional validation
        
    Returns:
        Dictionary containing operation result and statistics
    """
    if not self.enabled:
        return {
            "success": False,
            "error": "Chat history service is disabled",
            "deleted_count": 0
        }
    
    # Validate required parameters
    if not session_id:
        return {
            "success": False,
            "error": "Session ID is required",
            "deleted_count": 0
        }
    
    if not api_key:
        return {
            "success": False,
            "error": "API key is required",
            "deleted_count": 0
        }
    
    try:
        # Validate API key - this is mandatory for security and data access
        if hasattr(self, 'api_key_service'):
            is_valid, adapter_name, prompt_id = await self.api_key_service.validate_api_key(api_key)
            if not is_valid:
                return {
                    "success": False,
                    "error": "Invalid API key",
                    "deleted_count": 0
                }
        else:
            return {
                "success": False,
                "error": "API key service not available",
                "deleted_count": 0
            }
        
        # Get count before deletion for statistics
        collection = self.mongodb_service.get_collection(self.collection_name)
        count_before = await collection.count_documents({"session_id": session_id})
        
        # Delete all messages for the session
        result = await collection.delete_many({"session_id": session_id})
        
        # Clear from tracking
        self._active_sessions.pop(session_id, None)
        self._session_message_counts.pop(session_id, None)
        
        # Log the operation
        if self.verbose:
            logger.info(f"Cleared conversation history for session {session_id}: {result.deleted_count} messages deleted")
        
        return {
            "success": True,
            "session_id": session_id,
            "deleted_count": result.deleted_count,
            "api_key_validated": True,
            "adapter_name": adapter_name,
            "timestamp": datetime.now(UTC).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error clearing conversation history for session {session_id}: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "deleted_count": 0
        }
```

#### 1.2 Add Admin Route
**File:** `server/routes/admin_routes.py`

Add new route after the existing chat history route:

```python
@admin_router.delete("/chat-history/{session_id}")
async def clear_chat_history(
    session_id: str,
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID")
):
    """
    Clear chat history for a specific session.
    
    This endpoint allows clearing conversation history using:
    - Admin authentication (Bearer token)
    - Valid API key with appropriate permissions (REQUIRED)
    - Session ID validation
    
    Security considerations:
    - Requires admin authentication or valid API key (API key is mandatory)
    - Session ID must be provided in URL path
    - API key is required for MongoDB record access
    - Operation is logged for audit purposes
    
    Args:
        session_id: Session identifier to clear (required)
        request: The incoming request
        x_api_key: API key from header (required)
        x_session_id: Optional session ID from header (for validation)
        
    Returns:
        Operation result with statistics
        
    Raises:
        HTTPException: If operation fails or service is unavailable
    """
    # Check if inference_only is enabled (this feature is only available in inference-only mode)
    inference_only = is_true_value(request.app.state.config.get('general', {}).get('inference_only', False))
    if not inference_only:
        raise HTTPException(
            status_code=503, 
            detail="Chat history management is only available in inference-only mode"
        )
    
    # Check if chat history service is available
    chat_history_service = getattr(request.app.state, 'chat_history_service', None)
    if not chat_history_service:
        raise HTTPException(status_code=503, detail="Chat history service is not available")
    
    # Validate session ID if provided in header
    if x_session_id and x_session_id != session_id:
        raise HTTPException(
            status_code=400, 
            detail="Session ID in header does not match URL parameter"
        )
    
    # Validate that API key is provided (should be enforced by FastAPI but double-check)
    if not x_api_key:
        raise HTTPException(
            status_code=400,
            detail="API key is required for clearing conversation history"
        )
    
    # Perform the clear operation
    result = await chat_history_service.clear_conversation_history(
        session_id=session_id,
        api_key=x_api_key
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to clear conversation history: {result.get('error', 'Unknown error')}"
        )
    
    # Log the operation
    logger.info(f"Cleared conversation history for session {session_id}: {result['deleted_count']} messages")
    
    return {
        "status": "success",
        "message": f"Cleared {result['deleted_count']} messages from session {session_id}",
        "session_id": session_id,
        "deleted_count": result["deleted_count"],
        "timestamp": result["timestamp"]
    }
```

#### 1.3 Add Schema Models
**File:** `server/models/schema.py`

Add new response model:

```python
class ChatHistoryClearResponse(BaseModel):
    """Response model for chat history clear operation"""
    status: str
    message: str
    session_id: str
    deleted_count: int
    timestamp: str
```

### Phase 2: Python Client Implementation
**Files to modify:**
- `clients/python/schmitech_orbit_client/chat_client.py`
- `clients/python/schmitech_orbit_client/__init__.py`

#### 2.1 Add Clear History Method
**File:** `clients/python/schmitech_orbit_client/chat_client.py`

Add new method to the `OrbitChatClient` class:

```python
async def clear_conversation_history(self, session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Clear conversation history for a session.
    
    Args:
        session_id: Optional session ID to clear. If None, uses current session.
        
    Returns:
        Dictionary containing operation result
        
    Raises:
        Exception: If the operation fails
    """
    # Use provided session_id or current session
    target_session_id = session_id or self.session_id
    
    if not target_session_id:
        raise ValueError("No session ID provided and no current session available")
    
    if not self.api_key:
        raise ValueError("API key is required for clearing conversation history")
    
    # Prepare headers
    headers = {
        'Content-Type': 'application/json',
        'X-Session-ID': target_session_id
    }
    
    if self.api_key:
        headers['X-API-Key'] = self.api_key
    
    try:
        # Make DELETE request to admin endpoint
        response = requests.delete(
            f"{self.api_url}/admin/chat-history/{target_session_id}",
            headers=headers,
            timeout=self.timeout
        )
        
        if response.status_code == 200:
            result = response.json()
            if self.verbose:
                console.print(f"[green]✓[/green] Cleared {result['deleted_count']} messages from session {target_session_id}")
            return result
        else:
            error_detail = response.json().get('detail', 'Unknown error') if response.headers.get('content-type', '').startswith('application/json') else response.text
            raise Exception(f"Failed to clear conversation history: {error_detail}")
            
    except requests.exceptions.RequestException as e:
        raise Exception(f"Network error while clearing conversation history: {str(e)}")
```

#### 2.2 Add Slash Command
**File:** `clients/python/schmitech_orbit_client/chat_client.py`

Add to the `SlashCommandCompleter` commands list:
```python
"/clear-server-history": "Clear conversation history from server"
```

Add command handler in the `handle_slash_command` method:
```python
elif command == "/clear-server-history":
    if not self.session_id:
        console.print("[red]No active session to clear[/red]")
        return
    
    try:
        result = await self.clear_conversation_history()
        console.print(f"[green]✓[/green] {result['message']}")
    except Exception as e:
        console.print(f"[red]Error clearing server history: {str(e)}[/red]")
```

#### 2.3 Update Package Exports
**File:** `clients/python/schmitech_orbit_client/__init__.py`

Ensure the new method is available:
```python
from .chat_client import OrbitChatClient, clear_conversation_history

__all__ = ['OrbitChatClient', 'clear_conversation_history']
```

### Phase 3: Node.js Client Implementation
**Files to modify:**
- `clients/node-api/api.ts`

#### 3.1 Add Clear History Method
**File:** `clients/node-api/api.ts`

Add new method to the `ApiClient` class:

```typescript
public async clearConversationHistory(sessionId?: string): Promise<{
  status: string;
  message: string;
  session_id: string;
  deleted_count: number;
  timestamp: string;
}> {
  /**
   * Clear conversation history for a session.
   * 
   * @param sessionId - Optional session ID to clear. If not provided, uses current session.
   * @returns Promise resolving to operation result
   * @throws Error if the operation fails
   */
  const targetSessionId = sessionId || this.sessionId;
  
  if (!targetSessionId) {
    throw new Error('No session ID provided and no current session available');
  }
  
  if (!this.apiKey) {
    throw new Error('API key is required for clearing conversation history');
  }
  
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Session-ID': targetSessionId
  };
  
  if (this.apiKey) {
    headers['X-API-Key'] = this.apiKey;
  }
  
  try {
    const response = await fetch(`${this.apiUrl}/admin/chat-history/${targetSessionId}`, {
      ...this.getFetchOptions({
        method: 'DELETE',
        headers
      })
    });
    
    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Failed to clear conversation history: ${response.status} ${errorText}`);
    }
    
    const result = await response.json();
    return result;
    
  } catch (error: any) {
    if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
      throw new Error('Could not connect to the server. Please check if the server is running.');
    } else {
      throw error;
    }
  }
}
```

#### 3.2 Add Legacy Function
**File:** `clients/node-api/api.ts`

Add legacy function for backward compatibility:

```typescript
// Legacy clearConversationHistory function that uses the default client
export async function clearConversationHistory(sessionId?: string): Promise<{
  status: string;
  message: string;
  session_id: string;
  deleted_count: number;
  timestamp: string;
}> {
  if (!defaultClient) {
    throw new Error('API not configured. Please call configureApi() with your server URL before using any API functions.');
  }
  
  return await defaultClient.clearConversationHistory(sessionId);
}
```

### Phase 4: Testing and Validation
**Files to create:**
- `server/tests/test_chat_history_clear.py`
- `clients/python/test_clear_history.py`
- `clients/node-api/test/test_clear_history.ts`

#### 4.1 Backend Tests
**File:** `server/tests/test_chat_history_clear.py`

```python
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from server.services.chat_history_service import ChatHistoryService
from server.routes.admin_routes import clear_chat_history

class TestChatHistoryClear:
    """Test cases for chat history clearing functionality"""
    
    @pytest.fixture
    async def mock_chat_history_service(self):
        """Create a mock chat history service"""
        service = AsyncMock(spec=ChatHistoryService)
        service.clear_conversation_history = AsyncMock(return_value={
            "success": True,
            "session_id": "test-session-123",
            "deleted_count": 5,
            "timestamp": "2024-01-01T00:00:00Z"
        })
        return service
    
    @pytest.mark.asyncio
    async def test_clear_conversation_history_success(self, mock_chat_history_service):
        """Test successful conversation history clearing"""
        result = await mock_chat_history_service.clear_conversation_history(
            session_id="test-session-123",
            api_key="test-api-key"
        )
        
        assert result["success"] is True
        assert result["deleted_count"] == 5
        assert result["session_id"] == "test-session-123"
    
    @pytest.mark.asyncio
    async def test_clear_conversation_history_invalid_api_key(self, mock_chat_history_service):
        """Test conversation history clearing with invalid API key"""
        mock_chat_history_service.clear_conversation_history.return_value = {
            "success": False,
            "error": "Invalid API key",
            "deleted_count": 0
        }
        
        result = await mock_chat_history_service.clear_conversation_history(
            session_id="test-session-123",
            api_key="invalid-key"
        )
        
        assert result["success"] is False
        assert "Invalid API key" in result["error"]
```

#### 4.2 Python Client Tests
**File:** `clients/python/test_clear_history.py`

```python
import pytest
import asyncio
from unittest.mock import patch, MagicMock
from schmitech_orbit_client import OrbitChatClient

class TestClearHistory:
    """Test cases for Python client clear history functionality"""
    
    @pytest.fixture
    def client(self):
        """Create a test client instance"""
        return OrbitChatClient(
            api_url="http://localhost:8000",
            api_key="test-key",
            session_id="test-session"
        )
    
    @pytest.mark.asyncio
    async def test_clear_conversation_history_success(self, client):
        """Test successful conversation history clearing"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "message": "Cleared 5 messages from session test-session",
            "session_id": "test-session",
            "deleted_count": 5,
            "timestamp": "2024-01-01T00:00:00Z"
        }
        
        with patch('requests.delete', return_value=mock_response):
            result = await client.clear_conversation_history()
            
            assert result["status"] == "success"
            assert result["deleted_count"] == 5
            assert result["session_id"] == "test-session"
    
  @pytest.mark.asyncio
  async def test_clear_conversation_history_no_session(self, client):
      """Test clearing history without session ID"""
      client.session_id = None
      
      with pytest.raises(ValueError, match="No session ID provided"):
          await client.clear_conversation_history()
  
  @pytest.mark.asyncio
  async def test_clear_conversation_history_no_api_key(self, client):
      """Test clearing history without API key"""
      client.api_key = None
      
      with pytest.raises(ValueError, match="API key is required"):
          await client.clear_conversation_history()
```

#### 4.3 Node.js Client Tests
**File:** `clients/node-api/test/test_clear_history.ts`

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ApiClient } from '../api';

describe('Clear History', () => {
  let client: ApiClient;
  
  beforeEach(() => {
    client = new ApiClient({
      apiUrl: 'http://localhost:8000',
      apiKey: 'test-key',
      sessionId: 'test-session'
    });
  });
  
  it('should clear conversation history successfully', async () => {
    const mockResponse = {
      status: 'success',
      message: 'Cleared 5 messages from session test-session',
      session_id: 'test-session',
      deleted_count: 5,
      timestamp: '2024-01-01T00:00:00Z'
    };
    
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResponse)
    });
    
    const result = await client.clearConversationHistory();
    
    expect(result.status).toBe('success');
    expect(result.deleted_count).toBe(5);
    expect(result.session_id).toBe('test-session');
  });
  
  it('should throw error when no session ID available', async () => {
    const clientWithoutSession = new ApiClient({
      apiUrl: 'http://localhost:8000',
      apiKey: 'test-key',
      sessionId: null
    });
    
    await expect(clientWithoutSession.clearConversationHistory()).rejects.toThrow(
      'No session ID provided and no current session available'
    );
  });
  
  it('should throw error when no API key available', async () => {
    const clientWithoutApiKey = new ApiClient({
      apiUrl: 'http://localhost:8000',
      apiKey: null,
      sessionId: 'test-session'
    });
    
    await expect(clientWithoutApiKey.clearConversationHistory()).rejects.toThrow(
      'API key is required for clearing conversation history'
    );
  });
});
```

### Phase 5: Documentation and Examples
**Files to create:**
- `docs/chat-history-management.md`
- `examples/clear-history/`

#### 5.1 Documentation
**File:** `docs/chat-history-management.md`

```markdown
# Chat History Management

## Overview
The ORBIT system provides comprehensive chat history management capabilities, including the ability to clear conversation history for specific sessions.

## Features
- Clear conversation history by session ID
- API key authentication support
- Admin-level access control
- Audit logging and statistics
- Client library integration

## API Endpoints

### Clear Chat History
```
DELETE /admin/chat-history/{session_id}
```

**Headers:**
- `X-API-Key`: **REQUIRED** API key for authentication and MongoDB access
- `X-Session-ID`: Optional session ID for validation

**Response:**
```json
{
  "status": "success",
  "message": "Cleared 5 messages from session abc123",
  "session_id": "abc123",
  "deleted_count": 5,
  "timestamp": "2024-01-01T00:00:00Z"
}
```

## Client Usage

### Python Client
```python
from schmitech_orbit_client import OrbitChatClient

client = OrbitChatClient(
    api_url="http://localhost:8000",
    api_key="your-api-key",
    session_id="your-session-id"
)

# Clear current session history
result = await client.clear_conversation_history()
print(f"Cleared {result['deleted_count']} messages")

# Clear specific session history
result = await client.clear_conversation_history("other-session-id")
```

### Node.js Client
```typescript
import { ApiClient } from '@schmitech/orbit-client';

const client = new ApiClient({
  apiUrl: 'http://localhost:8000',
  apiKey: 'your-api-key',
  sessionId: 'your-session-id'
});

// Clear current session history
const result = await client.clearConversationHistory();
console.log(`Cleared ${result.deleted_count} messages`);

// Clear specific session history
const result2 = await client.clearConversationHistory('other-session-id');
```

## Security Considerations
- **API key is MANDATORY** for MongoDB record access and authentication
- Session ID validation prevents unauthorized access
- All operations are logged for audit purposes
- Only available in inference-only mode
- API key must be valid and active
```

#### 5.2 Example Scripts
**File:** `examples/clear-history/python_example.py`

```python
#!/usr/bin/env python3
"""
Example script demonstrating conversation history clearing
"""
import asyncio
from schmitech_orbit_client import OrbitChatClient

async def main():
    # Initialize client
    client = OrbitChatClient(
        api_url="http://localhost:8000",
        api_key="your-api-key",
        session_id="example-session"
    )
    
    # Clear conversation history
    try:
        result = await client.clear_conversation_history()
        print(f"✓ Successfully cleared {result['deleted_count']} messages")
        print(f"Session: {result['session_id']}")
        print(f"Timestamp: {result['timestamp']}")
    except Exception as e:
        print(f"✗ Error clearing history: {e}")

if __name__ == "__main__":
    asyncio.run(main())
```

**File:** `examples/clear-history/node_example.js`

```javascript
const { ApiClient } = require('@schmitech/orbit-client');

async function main() {
  // Initialize client
  const client = new ApiClient({
    apiUrl: 'http://localhost:8000',
    apiKey: 'your-api-key',
    sessionId: 'example-session'
  });
  
  // Clear conversation history
  try {
    const result = await client.clearConversationHistory();
    console.log(`✓ Successfully cleared ${result.deleted_count} messages`);
    console.log(`Session: ${result.session_id}`);
    console.log(`Timestamp: ${result.timestamp}`);
  } catch (error) {
    console.error(`✗ Error clearing history: ${error.message}`);
  }
}

main();
```

## Implementation Checklist

### Backend
- [ ] Add `clear_conversation_history` method to `ChatHistoryService`
- [ ] Add `DELETE /admin/chat-history/{session_id}` route
- [ ] Add `ChatHistoryClearResponse` schema model
- [ ] Add comprehensive error handling and logging
- [ ] Add API key validation integration
- [ ] Write unit tests for service method
- [ ] Write integration tests for admin route

### Python Client
- [ ] Add `clear_conversation_history` method to `OrbitChatClient`
- [ ] Add `/clear-server-history` slash command
- [ ] Update package exports
- [ ] Write unit tests
- [ ] Update documentation

### Node.js Client
- [ ] Add `clearConversationHistory` method to `ApiClient`
- [ ] Add legacy function for backward compatibility
- [ ] Write unit tests
- [ ] Update TypeScript definitions

### Testing
- [ ] Backend service tests
- [ ] Admin route integration tests
- [ ] Python client tests
- [ ] Node.js client tests
- [ ] End-to-end integration tests

### Documentation
- [ ] API documentation
- [ ] Client usage examples
- [ ] Security considerations
- [ ] Example scripts

## Security Considerations

1. **API Key Required**: All clear operations require a valid API key (MANDATORY)
2. **Session Validation**: Session ID must be provided and validated
3. **MongoDB Access**: API key is essential for finding and accessing conversation records
4. **Audit Logging**: All operations are logged with timestamps and user information
5. **Rate Limiting**: Consider implementing rate limiting for clear operations
6. **Data Retention**: Ensure compliance with data retention policies
7. **Access Control**: Only authorized users with valid API keys can clear conversation history

## Performance Considerations

1. **Batch Operations**: For large conversation histories, consider batch deletion
2. **Indexing**: Ensure proper MongoDB indexes on session_id for fast lookups
3. **Memory Management**: Clear tracking data after deletion
4. **Async Operations**: All operations are asynchronous to prevent blocking

## Future Enhancements

1. **Bulk Clear**: Clear multiple sessions at once
2. **Selective Clear**: Clear specific message types or date ranges
3. **Soft Delete**: Option for soft delete with recovery
4. **Export Before Clear**: Export conversation before clearing
5. **Scheduled Cleanup**: Automatic cleanup based on retention policies
