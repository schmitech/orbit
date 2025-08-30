// For Node.js environments, we can use http.Agent for connection pooling
let httpAgent: any = null;
let httpsAgent: any = null;

// Initialize agents for connection pooling in Node.js environments
if (typeof window === 'undefined') {
  // Lazy load to avoid including 'http' in browser bundles
  Promise.all([
    import('http').catch(() => null),
    import('https').catch(() => null)
  ]).then(([http, https]) => {
    if (http?.default?.Agent) {
      httpAgent = new http.default.Agent({ keepAlive: true });
    } else if (http?.Agent) {
      httpAgent = new http.Agent({ keepAlive: true });
    }
    
    if (https?.default?.Agent) {
      httpsAgent = new https.default.Agent({ keepAlive: true });
    } else if (https?.Agent) {
      httpsAgent = new https.Agent({ keepAlive: true });
    }
  }).catch(err => {
    // Silently fail - connection pooling is optional
    console.warn('Failed to initialize HTTP agents:', err.message);
  });
}

// Define the StreamResponse interface
export interface StreamResponse {
  text: string;
  done: boolean;
}

// The server now returns this directly for non-streaming chat
export interface ChatResponse {
  response: string;
  sources?: any[];
}

// The request body for the /v1/chat endpoint
interface ChatRequest {
  messages: Array<{ role: string; content: string; }>;
  stream: boolean;
}

export class ApiClient {
  private readonly apiUrl: string;
  private readonly apiKey: string | null;
  private sessionId: string | null; // Session ID can be mutable

  constructor(config: { apiUrl: string; apiKey?: string | null; sessionId?: string | null }) {
    if (!config.apiUrl || typeof config.apiUrl !== 'string') {
      throw new Error('API URL must be a valid string');
    }
    if (config.apiKey !== undefined && config.apiKey !== null && typeof config.apiKey !== 'string') {
      throw new Error('API key must be a valid string or null');
    }
    if (config.sessionId !== undefined && config.sessionId !== null && typeof config.sessionId !== 'string') {
      throw new Error('Session ID must be a valid string or null');
    }
    
    this.apiUrl = config.apiUrl;
    this.apiKey = config.apiKey ?? null;
    this.sessionId = config.sessionId ?? null;
  }

  public setSessionId(sessionId: string | null): void {
    if (sessionId !== null && typeof sessionId !== 'string') {
      throw new Error('Session ID must be a valid string or null');
    }
    this.sessionId = sessionId;
  }

  public getSessionId(): string | null {
    return this.sessionId;
  }

  // Helper to get fetch options with connection pooling if available
  private getFetchOptions(options: RequestInit = {}): RequestInit {
    const baseOptions: RequestInit = {};
    
    // Environment-specific options
    if (typeof window === 'undefined') {
      // Node.js: Use connection pooling agent
      const isHttps = this.apiUrl.startsWith('https:');
      const agent = isHttps ? httpsAgent : httpAgent;
      if (agent) {
        (baseOptions as any).agent = agent;
      }
    } else {
      // Browser: Use keep-alive header
      baseOptions.headers = { 'Connection': 'keep-alive' };
    }

    // Common headers
    const headers: Record<string, string> = {
      'X-Request-ID': Date.now().toString(36) + Math.random().toString(36).substring(2),
    };

    // Merge base options headers (for browser keep-alive)
    if (baseOptions.headers) {
      Object.assign(headers, baseOptions.headers);
    }

    // Merge original request headers
    if (options.headers) {
      Object.assign(headers, options.headers);
    }

    if (this.apiKey) {
      headers['X-API-Key'] = this.apiKey;
    }

    if (this.sessionId) {
      headers['X-Session-ID'] = this.sessionId;
    }

    return {
      ...options,
      ...baseOptions,
      headers,
    };
  }

  // Create Chat request
  private createChatRequest(message: string, stream: boolean = true): ChatRequest {
    return {
      messages: [
        { role: "user", content: message }
      ],
      stream
    };
  }

  public async *streamChat(
    message: string,
    stream: boolean = true
  ): AsyncGenerator<StreamResponse> {
    try {
      // Add timeout to the fetch request
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 60000); // 60 second timeout

      const response = await fetch(`${this.apiUrl}/v1/chat`, {
        ...this.getFetchOptions({
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Accept': stream ? 'text/event-stream' : 'application/json'
          },
          body: JSON.stringify(this.createChatRequest(message, stream)),
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
        const data = await response.json() as ChatResponse;
        if (data.response) {
          yield {
            text: data.response,
            done: true
          };
        }
        return;
      }
      
      const reader = response.body?.getReader();
      if (!reader) throw new Error('No reader available');

      const decoder = new TextDecoder();
      let buffer = '';
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
              const jsonText = line.slice(6).trim();
              
              if (!jsonText || jsonText === '[DONE]') {
                yield { text: '', done: true };
                return;
              }

              try {
                const data = JSON.parse(jsonText);
                
                if (data.error) {
                  throw new Error(`Server Error: ${data.error.message}`);
                }
                
                if (data.response) {
                  hasReceivedContent = true;
                  yield { text: data.response, done: data.done || false };
                }

                if (data.done) {
                    yield { text: '', done: true };
                    return;
                }
                
              } catch (parseError) {
                console.warn('Error parsing JSON chunk:', parseError, 'Chunk:', jsonText);
              }
            } else if (line) {
                // Handle raw text chunks that are not in SSE format
                hasReceivedContent = true;
                yield { text: line, done: false };
            }
          }
          
          buffer = buffer.slice(lineStartIndex);
          
          if (buffer.length > 1000000) { // 1MB limit
            console.warn('Buffer too large, truncating...');
            buffer = buffer.slice(-500000); // Keep last 500KB
          }
        }
        
        if (hasReceivedContent) {
          yield { text: '', done: true };
        }
        
      } finally {
        reader.releaseLock();
      }
      
    } catch (error: any) {
      if (error.name === 'AbortError') {
        throw new Error('Connection timed out. Please check if the server is running.');
      } else if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
        throw new Error('Could not connect to the server. Please check if the server is running.');
      } else {
        throw error;
      }
    }
  }
}

// Legacy compatibility functions - these create a default client instance
// These are kept for backward compatibility but should be deprecated in favor of the class-based approach

let defaultClient: ApiClient | null = null;

// Configure the API with a custom URL, API key (optional), and session ID (optional)
export const configureApi = (apiUrl: string, apiKey: string | null = null, sessionId: string | null = null): void => {
  defaultClient = new ApiClient({ apiUrl, apiKey, sessionId });
}

// Legacy streamChat function that uses the default client
export async function* streamChat(
  message: string,
  stream: boolean = true
): AsyncGenerator<StreamResponse> {
  if (!defaultClient) {
    throw new Error('API not configured. Please call configureApi() with your server URL before using any API functions.');
  }
  
  yield* defaultClient.streamChat(message, stream);
}
