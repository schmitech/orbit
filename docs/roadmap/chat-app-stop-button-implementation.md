# Chat App Stop Button Implementation Plan

## Overview
Add a stop button to the chat app's message input component that allows users to cancel ongoing assistant responses. This will halt the streaming response both on the client side and (when server-side support is added) on the server side.

## Current State
- ✅ Chat app has streaming response functionality
- ✅ `MessageInput` component displays mic and send buttons
- ✅ `chatStore` manages streaming state via `isLoading` flag
- ✅ API client (`@schmitech/chatbot-api`) uses `AbortController` internally for timeout (60 seconds)
- ❌ No way to cancel streaming from the UI
- ❌ No `AbortController` reference stored in the store
- ❌ API client doesn't accept external `AbortSignal` parameter

## Implementation Requirements

### 1. UI Changes (Easy - ~15 minutes)

**File**: `clients/chat-app/src/components/MessageInput.tsx`

- Add a stop button that appears when `isLoading` is true
- Position it between the mic button and send button
- Use `Square` or `StopCircle` icon from `lucide-react`
- Button should call `stopStreaming()` from the chat store
- Style consistently with existing buttons (mic, send)

**Visual Layout**:
```
[Paperclip] [Textarea] [Mic] [Stop] [Send]
                    ↑
              (when isLoading)
```

### 2. Store Changes (Medium - ~30 minutes)

**File**: `clients/chat-app/src/stores/chatStore.ts`

**Add to store state**:
- `abortController: AbortController | null` - Reference to current stream's abort controller

**Add new method**:
- `stopStreaming(): void` - Aborts the current stream and cleans up state

**Modify `sendMessage` function**:
- Create `AbortController` before starting stream
- Store it in the store state
- Pass `abortController.signal` to the API client
- Check for abort in the streaming loop
- Handle `AbortError` gracefully
- Clean up abort controller after stream completes or is aborted

### 3. API Client Changes (Medium - ~20 minutes)

**File**: `clients/node-api/api.ts` (or wherever the API client is defined)

**Modify `streamChat` method signature**:
```typescript
// Current
public async *streamChat(
  message: string,
  stream: boolean = true,
  fileIds?: string[]
): AsyncGenerator<StreamResponse>

// Updated
public async *streamChat(
  message: string,
  stream: boolean = true,
  fileIds?: string[],
  options?: { signal?: AbortSignal }
): AsyncGenerator<StreamResponse>
```

**Update implementation**:
- Accept optional `options` parameter with `signal`
- Merge external `AbortSignal` with internal timeout controller
- Pass signal to fetch request
- Check for abort in the streaming loop
- Handle abort errors gracefully

**Also update legacy `streamChat` function**:
- Accept and pass through the `options` parameter

### 4. Type Definitions (Easy - ~5 minutes)

**File**: `clients/chat-app/src/api/loader.ts`

- Update `ApiClient` interface to include optional `signal` parameter in `streamChat` method
- Ensure TypeScript types are correct

## Detailed Implementation Steps

### Step 1: Update API Client Interface

**File**: `clients/chat-app/src/api/loader.ts`

```typescript
export interface ApiClient {
  // ... existing methods ...
  streamChat(
    message: string,
    stream?: boolean,
    fileIds?: string[],
    options?: { signal?: AbortSignal }
  ): AsyncGenerator<StreamResponse>;
}
```

### Step 2: Modify API Client Implementation

**File**: `clients/node-api/api.ts`

```typescript
public async *streamChat(
  message: string,
  stream: boolean = true,
  fileIds?: string[],
  options?: { signal?: AbortSignal }
): AsyncGenerator<StreamResponse> {
  try {
    // Create timeout controller
    const timeoutController = new AbortController();
    const timeoutId = setTimeout(() => timeoutController.abort(), 60000);

    // Merge signals if external signal provided
    let signal: AbortSignal;
    if (options?.signal) {
      // If both signals exist, abort when either is aborted
      const mergedController = new AbortController();
      const abort = () => mergedController.abort();
      options.signal.addEventListener('abort', abort);
      timeoutController.signal.addEventListener('abort', abort);
      signal = mergedController.signal;
    } else {
      signal = timeoutController.signal;
    }

    const response = await fetch(`${this.apiUrl}/v1/chat`, {
      ...this.getFetchOptions({
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': stream ? 'text/event-stream' : 'application/json'
        },
        body: JSON.stringify(this.createChatRequest(message, stream, fileIds)),
      }),
      signal
    });

    clearTimeout(timeoutId);

    // ... rest of implementation ...
    
    // Check for abort in streaming loop
    try {
      while (true) {
        if (signal.aborted) {
          reader.cancel();
          break;
        }
        
        const { done, value } = await reader.read();
        if (done) break;
        
        // ... process chunk ...
      }
    } catch (error) {
      if (error.name === 'AbortError') {
        // Clean abort, just break
        break;
      }
      throw error;
    }
  } catch (error) {
    if (error.name === 'AbortError') {
      // User cancelled, return gracefully
      return;
    }
    throw error;
  }
}
```

### Step 3: Update Chat Store

**File**: `clients/chat-app/src/stores/chatStore.ts`

**Add to store interface**:
```typescript
interface ExtendedChatState extends ChatState {
  // ... existing fields ...
  abortController: AbortController | null;
}
```

**Add to store state**:
```typescript
export const useChatStore = create<ExtendedChatState>((set, get) => ({
  // ... existing state ...
  abortController: null,
  
  // ... existing methods ...
  
  stopStreaming: () => {
    const controller = get().abortController;
    if (controller) {
      controller.abort();
      set({ abortController: null });
      
      // Mark current message as no longer streaming
      const state = get();
      const currentConversation = state.conversations.find(
        conv => conv.id === state.currentConversationId
      );
      
      if (currentConversation) {
        const lastMessage = currentConversation.messages[currentConversation.messages.length - 1];
        if (lastMessage && lastMessage.role === 'assistant' && lastMessage.isStreaming) {
          set(state => ({
            conversations: state.conversations.map(conv =>
              conv.id === state.currentConversationId
                ? {
                    ...conv,
                    messages: conv.messages.map(msg =>
                      msg.id === lastMessage.id
                        ? { ...msg, isStreaming: false }
                        : msg
                    ),
                    updatedAt: new Date()
                  }
                : conv
            ),
            isLoading: false,
            abortController: null
          }));
        }
      }
    }
  },
  
  // Modify sendMessage function
  sendMessage: async (content: string, fileIds?: string[]) => {
    // ... existing validation ...
    
    // Create abort controller for this stream
    const abortController = new AbortController();
    set({ abortController });
    
    try {
      // ... existing message creation ...
      
      const api = await getApi();
      debugLog(`[chatStore] Starting streamChat with fileIds:`, fileIds);
      
      try {
        for await (const response of api.streamChat(content, true, fileIds, {
          signal: abortController.signal
        })) {
          // Check if aborted
          if (abortController.signal.aborted) {
            debugLog(`[chatStore] Stream aborted by user`);
            break;
          }
          
          debugLog(`[chatStore] Received stream chunk:`, { text: response.text?.substring(0, 50), done: response.done });
          if (response.text) {
            get().appendToLastMessage(response.text, streamingConversationId);
            receivedAnyText = true;
            await new Promise(resolve => setTimeout(resolve, 30));
          }
          
          if (response.done) {
            debugLog(`[chatStore] Stream completed, receivedAnyText:`, receivedAnyText);
            break;
          }
        }
      } catch (error) {
        if (error.name === 'AbortError') {
          debugLog(`[chatStore] Stream aborted:`, error);
          // User cancelled, don't show error
          return;
        }
        throw error;
      }
      
      // ... rest of error handling ...
    } catch (error) {
      if (error.name === 'AbortError') {
        // User cancelled, don't show error
        return;
      }
      logError('Chat API error:', error);
      get().appendToLastMessage('Sorry, there was an error processing your request.', streamingConversationId);
    } finally {
      // Clean up abort controller
      set({ abortController: null, isLoading: false });
      
      // Mark message as no longer streaming
      // ... existing cleanup code ...
    }
  }
}));
```

### Step 4: Add Stop Button to MessageInput

**File**: `clients/chat-app/src/components/MessageInput.tsx`

**Add import**:
```typescript
import { Send, Mic, MicOff, Paperclip, X, Loader2, Square } from 'lucide-react';
```

**Add to component**:
```typescript
const { createConversation, currentConversationId, removeFileFromConversation, conversations, isLoading, stopStreaming } = useChatStore();
```

**Add stop button in the button group** (between mic and send):
```typescript
{voiceSupported && (
  <button
    type="button"
    onClick={handleVoiceToggle}
    // ... existing props ...
  >
    {/* ... existing content ... */}
  </button>
)}

{isLoading && (
  <button
    type="button"
    onClick={() => stopStreaming()}
    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors bg-red-50 text-red-600 hover:bg-red-100 dark:bg-red-900/40 dark:text-red-300 dark:hover:bg-red-900/60"
    title="Stop generating"
  >
    <Square className="h-4 w-4" fill="currentColor" />
  </button>
)}

<button
  type="submit"
  // ... existing props ...
>
  {/* ... existing content ... */}
</button>
```

## Testing Checklist

- [ ] Stop button appears when `isLoading` is true
- [ ] Stop button disappears when stream completes or is stopped
- [ ] Clicking stop button cancels the fetch request
- [ ] Stream loop breaks cleanly when aborted
- [ ] Message is marked as no longer streaming after stop
- [ ] No error messages shown when user cancels
- [ ] AbortController is cleaned up after stream completes
- [ ] AbortController is cleaned up after stream is stopped
- [ ] Multiple rapid stop clicks don't cause issues
- [ ] Starting a new message after stopping works correctly
- [ ] Stop button works with file attachments
- [ ] Stop button works with voice input

## Edge Cases to Handle

1. **Rapid stop/start**: Ensure abort controller is properly cleaned up before starting a new stream
2. **Stream completes while stopping**: Handle race condition where stream completes just as user clicks stop
3. **Network errors during abort**: Ensure abort errors are distinguished from network errors
4. **Multiple conversations**: Ensure abort controller is scoped to the correct conversation

## Performance Considerations

1. **Memory Management**: Clean up abort controllers after use to prevent memory leaks
2. **Signal Merging**: Efficiently merge timeout and user abort signals
3. **Event Listeners**: Remove event listeners when abort controller is cleaned up

## Security Considerations

1. **No authentication needed**: Stop button is a client-side operation, no additional auth required
2. **Session validation**: Ensure stop only affects the current user's session (handled by existing session management)

## Estimated Complexity

- **UI Changes**: ~15 minutes
- **Store Logic**: ~30 minutes
- **API Client Changes**: ~20 minutes
- **Type Definitions**: ~5 minutes
- **Testing**: ~15 minutes
- **Total**: ~1-1.5 hours

## Future Enhancements

1. **Server-side cancellation**: Once server supports abort signals, ensure they're properly passed through
2. **Visual feedback**: Add animation or loading state to stop button
3. **Keyboard shortcut**: Add Ctrl+C or Esc to stop streaming
4. **Partial response indicator**: Show "[Response stopped]" when user cancels mid-stream

## Related Documentation

- See [chatbot-widget-stop-button-implementation.md](./chatbot-widget-stop-button-implementation.md) for server-side implementation plan
- [MDN: AbortController](https://developer.mozilla.org/en-US/docs/Web/API/AbortController)
- [Fetch API: Using AbortSignal](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch#aborting_a_fetch)

