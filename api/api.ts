// For Node.js environments, we can use http.Agent for connection pooling
let httpAgent: any = null;
let httpsAgent: any = null;

// Track connections for debugging
let connectionCounter = 0;
let connectionReuseCounter = 0;

// Define the StreamResponse interface
export interface StreamResponse {
  text?: string;
  content?: string; // Adding alternative property name
  done?: boolean;
  type?: string;    // Type of response (e.g., 'text', 'audio')
}

// Initialize the HTTP agents for connection pooling
const initConnectionPool = async () => {
  // Only run in Node.js environment
  if (typeof window === 'undefined') {
    try {
      // Use dynamic imports for Node.js modules in ESM context
      let http, https;
      
      try {
        http = await import('node:http');
        https = await import('node:https');
      } catch (e) {
        console.warn('[Connection Pool] Failed to import Node.js modules:', e);
        return;
      }
      
      // Create agents with keepAlive enabled and add tracking
      httpAgent = new http.Agent({ 
        keepAlive: true,
        keepAliveMsecs: 30000, // 30 seconds
        maxSockets: 5          // Limit parallel connections
      });
      
      // Add tracking for connection reuse
      const originalCreateConnection = httpAgent.createConnection;
      httpAgent.createConnection = function(options: any, callback: any) {
        connectionCounter++;
        
        
        const socket = originalCreateConnection.call(this, options, callback);
        
        socket.on('reuse', () => {
          connectionReuseCounter++;
        });
        
        return socket;
      };
      
      httpsAgent = new https.Agent({ 
        keepAlive: true,
        keepAliveMsecs: 30000,
        maxSockets: 5
      });
      
    } catch (error) {
      console.warn('[Connection Pool] Failed to initialize HTTP agents:', error);
    }
  }
};

// Try to initialize connection pool (as an async function)
(async () => {
  try {
    await initConnectionPool();
  } catch (error) {
    console.warn('Failed to initialize connection pool:', error);
  }
})();

// Store the configured API URL
let configuredApiUrl: string | null = null;

// Configure the API with a custom URL
export const configureApi = (apiUrl: string): void => {
  if (!apiUrl || typeof apiUrl !== 'string') {
    throw new Error('API URL must be a valid string');
  }
  configuredApiUrl = apiUrl;
}

// Get the configured API URL or throw an error if not configured
const getApiUrl = (): string => {
  if (!configuredApiUrl) {
    throw new Error('API URL not configured. Please call configureApi() with your server URL before using any API functions.');
  }
  return configuredApiUrl;
};

// Helper to get fetch options with connection pooling if available
const getFetchOptions = (apiUrl: string, options: RequestInit = {}): RequestInit | any => {
  const isHttps = apiUrl.startsWith('https:');
  
  // Only use agents in Node.js environment
  if (typeof window === 'undefined') {
    if (isHttps && httpsAgent) {
      // Using 'any' type to bypass TypeScript limitations with Node.js http.Agent
      return { ...options, agent: httpsAgent } as any;
    } else if (httpAgent) {
      return { ...options, agent: httpAgent } as any;
    }
  }
  
  // Browser environment
  const requestId = Date.now().toString(36) + Math.random().toString(36).substring(2);
  
  // Use keep-alive header in browser environments
  return {
    ...options,
    headers: {
      ...options.headers,
      'Connection': 'keep-alive',
      'X-Request-ID': requestId // Add unique ID to track requests
    }
  };
};

export async function* streamChat(
  message: string,
  voiceEnabled: boolean
): AsyncGenerator<StreamResponse> {
  try {
    // Get the API URL at the time of the request (allows for dynamic configuration)
    const API_URL = getApiUrl();
    
    // Skip the OPTIONS preflight check that was causing CORS issues
    const response = await fetch(`${API_URL}/chat`, getFetchOptions(API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message, voiceEnabled }),
    }));

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`API request failed: ${response.status} ${errorText}`);
      throw new Error(`Network response was not ok: ${response.status} ${errorText}`);
    }
    
    const reader = response.body?.getReader();
    if (!reader) throw new Error('No reader available');

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }

      const chunk = decoder.decode(value, { stream: true });
      buffer += chunk;
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.trim()) {
          try {
            const data = JSON.parse(line);
            
            // Normalize the response to use 'text' property
            if (data.content && !data.text) {
              data.text = data.content;
            }
            
            yield data;
          } catch (error: any) {
            // Silent error handling for JSON parse errors
            console.warn('Error parsing JSON chunk:', line);
          }
        }
      }
    }

    if (buffer) {
      try {
        const data = JSON.parse(buffer);
        
        // Normalize the response to use 'text' property
        if (data.content && !data.text) {
          data.text = data.content;
        }
        
        yield data;
      } catch (error: any) {
        // Silent error handling for JSON parse errors
        console.warn('Error parsing final JSON buffer:', buffer);
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