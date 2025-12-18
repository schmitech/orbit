// Function to generate a UUID v4
function generateUUID(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

// Storage key for session ID
const SESSION_STORAGE_KEY = 'orbit_session_id';

// Get or create a persistent session ID
export function getOrCreateSessionId(): string {
  // First check if server provided a session ID
  if (typeof window !== 'undefined' && window.CHATBOT_SESSION_ID) {
    return window.CHATBOT_SESSION_ID;
  }
  
  // If no server session ID, check sessionStorage
  let sessionId = sessionStorage.getItem(SESSION_STORAGE_KEY);
  
  if (!sessionId) {
    sessionId = generateUUID();
    sessionStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  }
  
  // Store in window object for global access
  if (typeof window !== 'undefined') {
    window.CHATBOT_SESSION_ID = sessionId;
  }
  
  return sessionId;
}

// Set a new session ID
export function setSessionId(sessionId: string): void {
  if (typeof window === 'undefined') return;
  
  // Store in sessionStorage
  sessionStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  
  // Store in window object
  window.CHATBOT_SESSION_ID = sessionId;
} 