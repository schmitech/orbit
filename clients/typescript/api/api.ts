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

// Configure the API with a custom URL, API key, and optional session ID
export const configureApi = (apiUrl: string, apiKey: string, sessionId?: string): void => {
  if (!apiUrl || typeof apiUrl !== 'string') {
    throw new Error('API URL must be a valid string');
  }
  if (!apiKey || typeof apiKey !== 'string') {
    throw new Error('API key must be a valid string');
  }
  if (sessionId !== undefined && typeof sessionId !== 'string') {
    throw new Error('Session ID must be a valid string');
  }
  configuredApiUrl = apiUrl;
  configuredApiKey = apiKey;
  configuredSessionId = sessionId || null;
}

// Get the configured API URL or throw an error if not configured
const getApiUrl = (): string => {
  if (!configuredApiUrl) {
    throw new Error('API URL not configured. Please call configureApi() with your server URL before using any API functions.');
  }
  return configuredApiUrl;
};

// Get the configured API key or throw an error if not configured
const getApiKey = (): string => {
  if (!configuredApiKey) {
    throw new Error('API key not configured. Please call configureApi() with your API key before using any API functions.');
  }
  return configuredApiKey;
};

// Get the configured session ID
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
    'X-Request-ID': requestId,
    'X-API-Key': getApiKey()
  };

  // Add session ID to headers if configured
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
    
    const response = await fetch(`${API_URL}/v1/chat`, getFetchOptions(API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': stream ? 'text/event-stream' : 'application/json'
      },
      body: JSON.stringify(createMCPRequest(message, stream)),
    }));

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`API request failed: ${response.status} ${errorText}`);
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

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      buffer += chunk;
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.trim() && line.startsWith('data: ')) {
          try {
            const jsonText = line.slice(6).trim();
            if (jsonText === '[DONE]') {
              yield { text: '', done: true };
              break;
            }

            const data = JSON.parse(jsonText) as MCPResponse;
            
            if (data.result) {
              let content = '';
              
              // Handle different response types
              if (data.result.type === 'start') {
                continue;
              } else if (data.result.type === 'chunk' && data.result.chunk) {
                content = data.result.chunk.content;
              } else if (data.result.type === 'complete' && data.result.output?.messages?.[0]) {
                content = data.result.output.messages[0].content;
              }

              if (content) {
                const newText = extractNewText(content, currentFullText);
                if (newText) {
                  currentFullText += newText;
                  yield {
                    text: newText,
                    done: data.result.type === 'complete'
                  };
                } else if (data.result.type === 'complete') {
                  yield { text: '', done: true };
                }
              }
            }
          } catch (error) {
            console.warn('Error parsing JSON chunk:', line, 'Error:', error);
          }
        }
      }
    }

    // Handle any remaining buffer
    if (buffer && buffer.startsWith('data: ')) {
      try {
        const jsonText = buffer.slice(6).trim();
        if (jsonText !== '[DONE]') {
          const data = JSON.parse(jsonText) as MCPResponse;
          if (data.result?.chunk?.content) {
            const newText = extractNewText(data.result.chunk.content, currentFullText);
            if (newText) {
              yield {
                text: newText,
                done: data.result.type === 'complete'
              };
            }
          }
        }
      } catch (error) {
        console.warn('Error parsing final JSON buffer:', buffer, 'Error:', error);
      }
    }
  } catch (error: any) {
    console.error('Chat API error:', error.message);
    yield { 
      text: `Error connecting to chat server: ${error.message}`, 
      done: true 
    };
  }
}

// Helper function to extract only new text from incoming chunks
function extractNewText(incomingText: string, currentText: string): string {
  if (!currentText) return incomingText;
  if (currentText.endsWith(incomingText)) return '';
  
  if (incomingText.length > currentText.length) {
    if (incomingText.startsWith(currentText)) {
      return incomingText.slice(currentText.length);
    }
    
    let i = 0;
    const minLength = Math.min(currentText.length, incomingText.length);
    while (i < minLength && currentText[i] === incomingText[i]) {
      i++;
    }
    
    if (i > currentText.length / 2) {
      return incomingText.slice(i);
    }
  }
  
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