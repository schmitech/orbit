// For Node.js environments, we can use http.Agent for connection pooling
let httpAgent: any = null;
let httpsAgent: any = null;

// Define the StreamResponse interface
export interface StreamResponse {
  text: string;
  done: boolean;
}

export interface ChatResponse {
  response: string;
}

// MCP Protocol interfaces
interface MCPRequest {
  jsonrpc: "2.0";
  method: string;
  params: {
    name: string;
    arguments: {
      messages?: Array<{
        role: string;
        content: string;
      }>;
      stream?: boolean;
      tools?: Array<{
        name: string;
        parameters: Record<string, any>;
      }>;
    };
  };
  id: string;
}

interface MCPResponse {
  jsonrpc: "2.0";
  id: string;
  result?: {
    type?: "start" | "chunk" | "complete";
    chunk?: {
      content: string;
    };
    output?: {
      messages: Array<{
        role: string;
        content: string;
      }>;
    };
  };
  error?: {
    code: number;
    message: string;
  };
}

// Store the configured API URL, key, and session ID
let configuredApiUrl: string | null = null;
let configuredApiKey: string | null = null;
let configuredSessionId: string | null = null;

// Configure the API with a custom URL, API key (optional), and session ID (optional)
export const configureApi = (apiUrl: string, apiKey: string | null = null, sessionId: string | null = null): void => {
  if (!apiUrl || typeof apiUrl !== 'string') {
    throw new Error('API URL must be a valid string');
  }
  if (apiKey !== null && typeof apiKey !== 'string') {
    throw new Error('API key must be a valid string or null');
  }
  if (sessionId !== null && typeof sessionId !== 'string') {
    throw new Error('Session ID must be a valid string or null');
  }
  configuredApiUrl = apiUrl;
  configuredApiKey = apiKey;
  configuredSessionId = sessionId;
}

// Get the configured API URL or throw an error if not configured
const getApiUrl = (): string => {
  if (!configuredApiUrl) {
    throw new Error('API URL not configured. Please call configureApi() with your server URL before using any API functions.');
  }
  return configuredApiUrl;
};

// Get the configured API key or return null if not configured
const getApiKey = (): string | null => {
  return configuredApiKey;
};

// Get the configured session ID or return null if not configured
const getSessionId = (): string | null => {
  return configuredSessionId;
};

// Helper to get fetch options with connection pooling if available
const getFetchOptions = (apiUrl: string, options: RequestInit = {}): RequestInit | any => {
  const isHttps = apiUrl.startsWith('https:');
  
  // Only use agents in Node.js environment
  if (typeof window === 'undefined') {
    if (isHttps && httpsAgent) {
      return { ...options, agent: httpsAgent } as any;
    } else if (httpAgent) {
      return { ...options, agent: httpAgent } as any;
    }
  }
  
  // Browser environment
  const requestId = Date.now().toString(36) + Math.random().toString(36).substring(2);
  
  // Use keep-alive header in browser environments
  const headers: Record<string, string> = {
    'Connection': 'keep-alive',
    'X-Request-ID': requestId
  };
  
  // Add API key to headers only if it exists
  const apiKey = getApiKey();
  if (apiKey) {
    headers['X-API-Key'] = apiKey;
  }
  
  // Add session ID to headers only if it exists
  const sessionId = getSessionId();
  if (sessionId) {
    headers['X-Session-ID'] = sessionId;
  }
  
  return {
    ...options,
    headers: {
      ...options.headers,
      ...headers
    }
  };
};

// Create MCP request
const createMCPRequest = (message: string, stream: boolean = true): MCPRequest => {
  return {
    jsonrpc: "2.0",
    method: "tools/call",
    params: {
      name: "chat",
      arguments: {
        messages: [
          { role: "user", content: message }
        ],
        stream
      }
    },
    id: Date.now().toString(36) + Math.random().toString(36).substring(2)
  };
};

// Create MCP tools request
const createMCPToolsRequest = (tools: Array<{ name: string; parameters: Record<string, any> }>): MCPRequest => {
  return {
    jsonrpc: "2.0",
    method: "tools/call",
    params: {
      name: "tools",
      arguments: {
        tools
      }
    },
    id: Date.now().toString(36) + Math.random().toString(36).substring(2)
  };
};

export async function* streamChat(
  message: string,
  stream: boolean = true
): AsyncGenerator<StreamResponse> {
  try {
    const API_URL = getApiUrl();
    
    // Add timeout to the fetch request
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 60000); // 60 second timeout

    const response = await fetch(`${API_URL}/v1/chat`, {
      ...getFetchOptions(API_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': stream ? 'text/event-stream' : 'application/json'
        },
        body: JSON.stringify(createMCPRequest(message, stream)),
      }),
      signal: controller.signal
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Network response was not ok: ${response.status} ${errorText}`);
    }

    if (!stream) {
      // Handle non-streaming response
      const data = await response.json() as MCPResponse;
      if (data.error) {
        throw new Error(`MCP Error: ${data.error.message}`);
      }
      if (data.result?.output?.messages?.[0]?.content) {
        yield {
          text: data.result.output.messages[0].content,
          done: true
        };
      }
      return;
    }
    
    const reader = response.body?.getReader();
    if (!reader) throw new Error('No reader available');

    const decoder = new TextDecoder();
    let buffer = '';
    let currentFullText = '';
    let hasReceivedContent = false;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }

        const chunk = decoder.decode(value, { stream: true });
        buffer += chunk;
        
        // Process complete lines immediately as they arrive
        let lineStartIndex = 0;
        let newlineIndex;
        
        while ((newlineIndex = buffer.indexOf('\n', lineStartIndex)) !== -1) {
          const line = buffer.slice(lineStartIndex, newlineIndex).trim();
          lineStartIndex = newlineIndex + 1;
          
          if (line && line.startsWith('data: ')) {
            try {
              const jsonText = line.slice(6).trim();
              
              // Check for [DONE] message (legacy format)
              if (jsonText === '[DONE]') {
                yield { text: '', done: true };
                return;
              }

              // Skip empty data lines
              if (!jsonText) {
                continue;
              }

              const data = JSON.parse(jsonText) as MCPResponse;
              
              // Handle errors
              if (data.error) {
                throw new Error(`MCP Error: ${data.error.message}`);
              }
              
              let content = '';
              let isDone = false;
              
              // Handle MCP protocol format
              if (data.result) {
                if (data.result.type === 'start') {
                  continue;
                } else if (data.result.type === 'chunk' && data.result.chunk) {
                  content = data.result.chunk.content;
                } else if (data.result.type === 'complete' && data.result.output?.messages?.[0]) {
                  content = data.result.output.messages[0].content;
                  isDone = true;
                }
              }
              
              // Handle direct server response format (from LLM clients)
              // This is what the server actually sends: { "response": "...", "done": false/true }
              if (!content && 'response' in data && typeof data.response === 'string') {
                content = data.response;
              }
              
              // Check for done signal in the data
              if ('done' in data && data.done === true) {
                isDone = true;
              }

              if (content) {
                const newText = extractNewText(content, currentFullText);
                if (newText) {
                  currentFullText += newText;
                  hasReceivedContent = true;
                  yield {
                    text: newText,
                    done: isDone
                  };
                }
              }
              
              // If we received a done signal, exit
              if (isDone) {
                if (!hasReceivedContent) {
                  // Yield empty response to indicate completion
                  yield { text: '', done: true };
                }
                return;
              }
            } catch (parseError) {
              // Don't throw, just continue processing
              console.warn('Error parsing JSON chunk:', parseError);
            }
          }
        }
        
        // Keep remaining incomplete line in buffer
        buffer = buffer.slice(lineStartIndex);
        
        // Prevent buffer from growing too large
        if (buffer.length > 1000000) { // 1MB limit
          console.warn('Buffer too large, truncating...');
          buffer = buffer.slice(-500000); // Keep last 500KB
        }
      }
      
      // If we exit the while loop naturally, ensure we send a done signal
      if (hasReceivedContent) {
        yield { text: '', done: true };
      }
      
    } finally {
      reader.releaseLock();
    }

    // Handle any remaining buffer (fallback)
    if (buffer && buffer.startsWith('data: ')) {
      try {
        const jsonText = buffer.slice(6).trim();
        if (jsonText && jsonText !== '[DONE]') {
          const data = JSON.parse(jsonText) as MCPResponse;
          if (data.result?.chunk?.content) {
            const newText = extractNewText(data.result.chunk.content, currentFullText);
            if (newText) {
              yield {
                text: newText,
                done: true
              };
            }
          }
        }
      } catch (error) {
        console.warn('Error parsing final JSON buffer:', error);
      }
    }
    
  } catch (error: any) {
    if (error.name === 'AbortError') {
      yield { 
        text: 'Connection timed out. Please check if the server is running.', 
        done: true 
      };
    } else if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
      yield { 
        text: 'Could not connect to the server. Please check if the server is running.', 
        done: true 
      };
    } else {
      yield { 
        text: `Error: ${error.message}`, 
        done: true 
      };
    }
  }
}

// Helper function to extract only new text from incoming chunks
function extractNewText(incomingText: string, currentText: string): string {
  // Simplified version - just check if we have new content at the end
  if (!currentText) return incomingText;
  
  // If incoming text is longer and starts with current text, return the new part
  if (incomingText.length > currentText.length && incomingText.startsWith(currentText)) {
    return incomingText.slice(currentText.length);
  }
  
  // Otherwise return the full incoming text (fallback)
  return incomingText;
}

// New function to send tools request
export async function sendToolsRequest(tools: Array<{ name: string; parameters: Record<string, any> }>): Promise<MCPResponse> {
  const API_URL = getApiUrl();
  
  const response = await fetch(`${API_URL}/v1/chat`, getFetchOptions(API_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(createMCPToolsRequest(tools)),
  }));

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Network response was not ok: ${response.status} ${errorText}`);
  }

  const data = await response.json() as MCPResponse;
  if (data.error) {
    throw new Error(`MCP Error: ${data.error.message}`);
  }

  return data;
}