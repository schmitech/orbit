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

// Store the configured API URL and key
let configuredApiUrl: string | null = null;
let configuredApiKey: string | null = null;

// Configure the API with a custom URL and API key
export const configureApi = (apiUrl: string, apiKey: string): void => {
  if (!apiUrl || typeof apiUrl !== 'string') {
    throw new Error('API URL must be a valid string');
  }
  if (!apiKey || typeof apiKey !== 'string') {
    throw new Error('API key must be a valid string');
  }
  configuredApiUrl = apiUrl;
  configuredApiKey = apiKey;
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
      'X-Request-ID': requestId, // Add unique ID to track requests
      'X-API-Key': getApiKey()   // Add API key to headers
    }
  };
};

export async function* streamChat(
  message: string,
  stream: boolean = true
): AsyncGenerator<StreamResponse> {
  try {
    const API_URL = getApiUrl();
    
    const response = await fetch(`${API_URL}/chat`, getFetchOptions(API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': stream ? 'text/event-stream' : 'application/json'
      },
      body: JSON.stringify({ message, stream }),
    }));

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`API request failed: ${response.status} ${errorText}`);
      throw new Error(`Network response was not ok: ${response.status} ${errorText}`);
    }

    if (!stream) {
      // Handle non-streaming response
      const data = await response.json() as ChatResponse;
      yield {
        text: data.response,
        done: true
      };
      return;
    }
    
    const reader = response.body?.getReader();
    if (!reader) throw new Error('No reader available');

    const decoder = new TextDecoder();
    let buffer = '';
    let currentFullText = ''; // Track full response to detect duplicates

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
            // Properly extract the JSON part by trimming whitespace after 'data:'
            const jsonText = line.slice(6).trim();
            const data = JSON.parse(jsonText);
            
            if (data.text) {
              // Check if this is a duplicate or overlapping chunk
              const newText = extractNewText(data.text, currentFullText);
              
              // Only yield if we have new text
              if (newText) {
                currentFullText += newText;
                yield {
                  text: newText,
                  done: data.done || false
                };
              } else if (data.done) {
                // Always send done signal even if no new text
                yield {
                  text: '',
                  done: true
                };
              }
            } else {
              // Pass through as-is if no text property
              yield {
                text: data.text || '',
                done: data.done || false
              };
            }
          } catch (error) {
            console.warn('Error parsing JSON chunk:', line, 'Error:', error);
          }
        }
      }
    }

    if (buffer && buffer.startsWith('data: ')) {
      try {
        // Properly extract the JSON part by trimming whitespace after 'data:'
        const jsonText = buffer.slice(6).trim();
        const data = JSON.parse(jsonText);
        
        if (data.text) {
          // Check for duplicates in final chunk
          const newText = extractNewText(data.text, currentFullText);
          if (newText || data.done) {
            yield {
              text: newText || '',
              done: data.done || false
            };
          }
        } else {
          yield {
            text: data.text || '',
            done: data.done || false
          };
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
  // If we have no current text, all text is new
  if (!currentText) return incomingText;
  
  // Handle exact duplicates
  if (currentText.endsWith(incomingText)) return '';

  // If incoming text is larger, check if it's an expanded version
  if (incomingText.length > currentText.length) {
    // If incoming text contains all of current text at the beginning,
    // only return the new part
    if (incomingText.startsWith(currentText)) {
      return incomingText.slice(currentText.length);
    }
    
    // Sometimes the FastAPI server might send growing chunks like "Hel" -> "Hello" -> "Hello wo" -> "Hello world"
    // Find the longest common prefix
    let i = 0;
    const minLength = Math.min(currentText.length, incomingText.length);
    while (i < minLength && currentText[i] === incomingText[i]) {
      i++;
    }
    
    // If there's significant overlap, extract only the new part
    if (i > currentText.length / 2) {
      return incomingText.slice(i);
    }
  }
  
  // Default: return the full text (this handles non-overlapping chunks)
  return incomingText;
}