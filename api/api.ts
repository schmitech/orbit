// Load environment variables
import { config } from 'dotenv';

// Define the StreamResponse interface
export interface StreamResponse {
  text?: string;
  content?: string; // Adding alternative property name
  done?: boolean;
  type?: string;    // Type of response (e.g., 'text', 'audio')
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
  // Node.js environment
  if (typeof process !== 'undefined' && process.env && process.env.VITE_API_URL) {
    return process.env.VITE_API_URL;
  }
  
  // Browser environment with Vite
  if (import.meta && import.meta.env && import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }
  
  // Default fallback
  return 'http://localhost:3000';
};

const API_URL = getApiUrl();

export async function* streamChat(
  message: string,
  voiceEnabled: boolean
): AsyncGenerator<StreamResponse> {
  try {
    const response = await fetch(`${API_URL}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message, voiceEnabled }),
    });

    if (!response.ok) {
      const errorText = await response.text();
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
            // Silent error handling
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
        // Silent error handling
      }
    }
  } catch (error: any) {
    yield { text: `Error: ${error.message}`, done: true };
  }
}