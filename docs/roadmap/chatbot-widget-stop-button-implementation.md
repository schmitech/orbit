# Server-Side Stop Streaming Implementation Plan

## Overview
The current stop button implementation only stops client-side streaming reception. The server continues generating responses in the background, wasting computational resources. This document outlines the necessary server-side changes to properly handle streaming cancellation.

## Current State
- ✅ Client-side stop button UI implemented
- ✅ Client-side AbortController created for each request
- ✅ Typing animation stops when button clicked
- ⚠️ Typing effect creates illusion (animates already-received content)
- ⚠️ Stop button shows all received content, not truly stopping at current position
- ❌ Server continues processing after client disconnects
- ❌ API doesn't accept abort signals

### Current Behavior Explanation
The typing effect currently works by:
1. Server sends chunks → Immediately appended to message content
2. TypingEffect component animates the display of already-received content
3. Stop button reveals all received content (not stopping at typed position)

This means the "typing" is an illusion - the content is already received and stored. The stop button doesn't stop at the current typing position but rather shows everything received so far from the server.

## Implementation Requirements

### 1. Update `@schmitech/chatbot-api` Package

#### Modify the `streamChat` function signature:
```typescript
// Before
export function streamChat(
  message: string
): AsyncGenerator<StreamResponse>;

// After
export function streamChat(
  message: string,
  options?: {
    signal?: AbortSignal;
  }
): AsyncGenerator<StreamResponse>;
```

#### Update the implementation:
```typescript
export async function* streamChat(
  message: string,
  options?: { signal?: AbortSignal }
): AsyncGenerator<StreamResponse> {
  const response = await fetch(`${apiUrl}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${apiKey}`,
      'X-Session-Id': sessionId
    },
    body: JSON.stringify({ message }),
    signal: options?.signal, // Pass abort signal to fetch
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  try {
    while (true) {
      // Check if aborted
      if (options?.signal?.aborted) {
        reader.cancel();
        break;
      }

      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      // Parse and yield chunks...
      yield parseChunk(chunk);
    }
  } finally {
    reader.releaseLock();
  }
}
```

### 2. Update Client-Side Store

Modify `/src/store/chatStore.ts` to pass the abort signal:

```typescript
// In sendMessage function
try {
  // Use the streamChat function with abort signal
  for await (const chunk of streamChat(safeContent, { 
    signal: abortController.signal 
  })) {
    if (abortController.signal.aborted) {
      break;
    }
    if (chunk.text) {
      get().appendToLastMessage(chunk.text);
      receivedAnyText = true;
    }
  }
} catch (error) {
  if (error.name === 'AbortError') {
    console.log('Stream aborted by user');
  } else if (!abortController.signal.aborted) {
    console.error('Chat API error:', error);
    get().appendToLastMessage('Sorry, there was an error processing your request.');
  }
}
```

### 3. Server-Side Implementation

#### Option A: Handle Abort in Streaming Endpoint

```javascript
// Express/Node.js example
const activeGenerations = new Map();

app.post('/api/chat/stream', async (req, res) => {
  const { message } = req.body;
  const sessionId = req.headers['x-session-id'];
  
  // Create abort controller for this generation
  const abortController = new AbortController();
  activeGenerations.set(sessionId, abortController);

  // Set up SSE headers
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Access-Control-Allow-Origin': '*',
  });

  // Handle client disconnect
  req.on('close', () => {
    console.log(`Client disconnected for session: ${sessionId}`);
    abortController.abort();
    activeGenerations.delete(sessionId);
  });

  try {
    // Pass abort signal to your AI service (OpenAI, Anthropic, etc.)
    const stream = await aiService.createChatCompletion({
      messages: [{ role: 'user', content: message }],
      stream: true,
      // Most AI SDKs support abort signals
      signal: abortController.signal,
    });

    for await (const chunk of stream) {
      if (abortController.signal.aborted) {
        console.log(`Generation aborted for session: ${sessionId}`);
        break;
      }

      const data = {
        text: chunk.choices[0]?.delta?.content || '',
        done: chunk.choices[0]?.finish_reason === 'stop'
      };

      res.write(`data: ${JSON.stringify(data)}\n\n`);
    }
  } catch (error) {
    if (error.name === 'AbortError') {
      console.log(`Generation cancelled for session: ${sessionId}`);
    } else {
      console.error('Stream error:', error);
      res.write(`data: ${JSON.stringify({ error: 'Stream error' })}\n\n`);
    }
  } finally {
    activeGenerations.delete(sessionId);
    res.end();
  }
});
```

#### Option B: Separate Stop Endpoint (Additional)

If you want explicit stop control beyond connection close:

```javascript
app.post('/api/chat/stop', async (req, res) => {
  const sessionId = req.headers['x-session-id'];
  
  const controller = activeGenerations.get(sessionId);
  if (controller) {
    controller.abort();
    activeGenerations.delete(sessionId);
    res.json({ success: true, message: 'Generation stopped' });
  } else {
    res.status(404).json({ 
      success: false, 
      message: 'No active generation found for session' 
    });
  }
});
```

### 4. AI Service Integration Examples

#### OpenAI SDK
```javascript
import OpenAI from 'openai';

const openai = new OpenAI();

async function generateWithAbort(message, signal) {
  const stream = await openai.chat.completions.create({
    model: 'gpt-4',
    messages: [{ role: 'user', content: message }],
    stream: true,
  }, {
    signal, // Pass abort signal to OpenAI SDK
  });

  return stream;
}
```

#### Anthropic SDK
```javascript
import Anthropic from '@anthropic-ai/sdk';

const anthropic = new Anthropic();

async function generateWithAbort(message, signal) {
  const stream = await anthropic.messages.create({
    model: 'claude-3-opus-20240229',
    messages: [{ role: 'user', content: message }],
    stream: true,
  }, {
    signal, // Pass abort signal to Anthropic SDK
  });

  return stream;
}
```

## Testing Checklist

- [ ] Verify abort signal is passed from client to API
- [ ] Confirm server stops processing when client disconnects
- [ ] Test that AI service calls are properly cancelled
- [ ] Ensure no memory leaks from uncleaned abort controllers
- [ ] Verify error handling for aborted requests
- [ ] Test multiple concurrent sessions don't interfere
- [ ] Confirm resources are cleaned up after abort

## Performance Considerations

1. **Memory Management**: Clean up abort controllers after use
2. **Connection Handling**: Properly detect client disconnections
3. **Resource Cleanup**: Ensure AI API calls are cancelled to save costs
4. **Session Management**: Use Map or Redis for production scale

## Security Considerations

1. **Session Validation**: Verify session ownership before allowing stop
2. **Rate Limiting**: Prevent abuse of stop endpoint
3. **Authentication**: Ensure stop requests are authenticated
4. **CORS**: Configure appropriate CORS headers

## Deployment Steps

1. Update and test `@schmitech/chatbot-api` package locally
2. Publish new version of the package
3. Update server endpoint to handle abort signals
4. Deploy server changes
5. Update client to use new API version
6. Test end-to-end in staging environment
7. Deploy to production with monitoring

## Monitoring

Add logging/metrics for:
- Number of streams started vs completed
- Number of user-initiated stops
- Average stream duration before stop
- Resource savings from cancelled generations

## Alternative Implementation: True Position-Based Stop

If you want the stop button to truly stop at the current typed position (not show all received content), you would need to:

1. **Buffer incoming chunks** separately from displayed content
2. **Only append to message** what has been "typed" so far
3. **On stop**, discard any buffered but not-yet-typed content

This approach has trade-offs:
- **Pro**: More intuitive user experience (stops exactly where typing appears)
- **Con**: May lose content that was already received from server
- **Con**: More complex state management
- **Con**: Potential sync issues between buffer and display

## Fallback Plan

If server-side implementation is delayed:
1. Current client-side stop still works (stops display)
2. Server resources will be wasted but functionality intact
3. Can be deployed incrementally
4. Consider adding visual indicator: "[Response stopped]" when stop is pressed

## References

- [MDN: AbortController](https://developer.mozilla.org/en-US/docs/Web/API/AbortController)
- [Fetch API: Using AbortSignal](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch#aborting_a_fetch)
- [Node.js Streams: Destroying Streams](https://nodejs.org/api/stream.html#stream_readable_destroy_error)
- [OpenAI Streaming API](https://platform.openai.com/docs/api-reference/streaming)
- [Anthropic Streaming](https://docs.anthropic.com/claude/reference/messages-streaming)