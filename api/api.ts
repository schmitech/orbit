// Load environment variables
import { config } from 'dotenv';

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
const initConnectionPool = () => {
  // Only run in Node.js environment
  if (typeof window === 'undefined') {
    try {
      const http = Function('return require')()('http');
      const https = Function('return require')()('https');
      
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
        console.log(`[Connection Pool] Creating connection #${connectionCounter}`);
        
        const socket = originalCreateConnection.call(this, options, callback);
        
        socket.on('reuse', () => {
          connectionReuseCounter++;
          console.log(`[Connection Pool] Reusing connection - total reuses: ${connectionReuseCounter}`);
        });
        
        return socket;
      };
      
      httpsAgent = new https.Agent({ 
        keepAlive: true,
        keepAliveMsecs: 30000,
        maxSockets: 5
      });
      
      console.log('[Connection Pool] HTTP connection pool initialized with keepAlive enabled');
    } catch (error) {
      console.warn('[Connection Pool] Failed to initialize HTTP agents:', error);
    }
  } else {
    console.log('[Connection Pool] Running in browser environment, using native connection pooling');
  }
};

// Try to initialize connection pool
try {
  initConnectionPool();
} catch (error) {
  console.warn('Failed to initialize connection pool:', error);
}

// Initialize environment
const initEnvironment = () => {
  // Only run Node.js specific code in a Node.js environment
  if (typeof window === 'undefined') {
    try {
      // Use a more compatible approach for importing Node.js modules
      // This avoids issues with ESM vs CommonJS
      let url, path, fs;
      
      // Use a function to safely evaluate requires without breaking browser builds
      const safeRequire = (moduleName: string) => {
        try {
          // Using Function constructor to avoid static analysis issues
          // This is a workaround that prevents bundlers from trying to process these requires
          return Function('return require')()(moduleName);
        } catch (e) {
          return null;
        }
      };
      
      url = safeRequire('url');
      path = safeRequire('path');
      fs = safeRequire('fs');
      
      if (url && path && fs) {
        const fileURLToPath = url.fileURLToPath;
        const { dirname, resolve } = path;
        const { existsSync } = fs;
        
        // Get the directory of the current module
        const __filename = fileURLToPath(import.meta.url);
        const __dirname = dirname(__filename);
        
        // Path to .env file in the same directory as this file
        const envPath = resolve(__dirname, '.env');
        
        if (existsSync(envPath)) {
          config({ path: envPath });
          console.log(`Loaded environment variables from ${envPath}`);
        }
      }
    } catch (error) {
      // Silently fail if we're in a browser environment or imports fail
      console.warn('Environment loading skipped: running in browser or missing modules');
    }
  } else {
    // Browser environment - no need to load .env file
    console.log('Running in browser environment');
  }
};

// Try to initialize the environment
try {
  initEnvironment();
} catch (error) {
  console.warn('Failed to initialize environment:', error);
}

// Use environment variables with fallback to Vite's env system for browser compatibility
const getApiUrl = () => {
  // Try to get URL from Node.js environment variables (set from .env file)
  if (typeof process !== 'undefined' && process.env && process.env.VITE_API_URL) {
    console.log('Using API URL from Node.js environment:', process.env.VITE_API_URL);
    return process.env.VITE_API_URL;
  }
  
  // Try to get URL from Vite's environment system
  if (import.meta && import.meta.env && import.meta.env.VITE_API_URL) {
    console.log('Using API URL from Vite environment:', import.meta.env.VITE_API_URL);
    return import.meta.env.VITE_API_URL;
  }
  
  // Read directly from .env file if possible
  try {
    if (typeof process !== 'undefined' && process.env) {
      // Try to read from any other environment variables that might contain the URL
      for (const key in process.env) {
        if (key.includes('API_URL') && process.env[key]) {
          console.log(`Found API URL in environment variable ${key}:`, process.env[key]);
          return process.env[key];
        }
      }
    }
  } catch (e) {
    console.warn('Error checking environment variables:', e);
  }
  
  // Use the value from .env file
  const envFileUrl = 'http://172.208.108.47:3000';
  console.log('Falling back to API URL from .env file:', envFileUrl);
  return envFileUrl;
};

const API_URL = getApiUrl();
console.log('Final API URL being used:', API_URL);

// Helper to get fetch options with connection pooling if available
const getFetchOptions = (options: RequestInit = {}): RequestInit | any => {
  const isHttps = API_URL.startsWith('https:');
  
  // Only use agents in Node.js environment
  if (typeof window === 'undefined') {
    if (isHttps && httpsAgent) {
      console.log('[Connection Pool] Using HTTPS agent with keepAlive');
      // Using 'any' type to bypass TypeScript limitations with Node.js http.Agent
      return { ...options, agent: httpsAgent } as any;
    } else if (httpAgent) {
      console.log('[Connection Pool] Using HTTP agent with keepAlive');
      return { ...options, agent: httpAgent } as any;
    }
  }
  
  // Browser environment
  const requestId = Date.now().toString(36) + Math.random().toString(36).substr(2);
  console.log(`[Connection Pool] Browser request ${requestId} using keep-alive header`);
  
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
    const startTime = Date.now();
    console.log(`[${startTime}] Attempting to connect to ${API_URL}/chat with message:`, message.substring(0, 30) + '...');
    
    // Skip the OPTIONS preflight check that was causing CORS issues
    const response = await fetch(`${API_URL}/chat`, getFetchOptions({
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message, voiceEnabled }),
    }));

    const responseTime = Date.now() - startTime;
    console.log(`[Connection Pool] Response received in ${responseTime}ms`);

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