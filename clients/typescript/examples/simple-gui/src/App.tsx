import { useRef, useEffect } from 'react';
import { ChatMessage } from './components/ChatMessage';
import { ChatInput } from './components/ChatInput';
import { Sidebar } from './components/Sidebar';
import { useChatStore } from './store';
import { streamChat, configureApi } from '../../../api/api';

// Function to generate a UUID v4
function generateUUID(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

// Function to get or create session ID
function getSessionId(): string {
  const storageKey = 'orbit_session_id';
  let sessionId = sessionStorage.getItem(storageKey);
  
  if (!sessionId) {
    sessionId = generateUUID();
    sessionStorage.setItem(storageKey, sessionId);
  }
  
  return sessionId;
}

// Configure the API with the endpoint and API key from environment variables
const apiEndpoint = import.meta.env.VITE_API_ENDPOINT;
const apiKey = import.meta.env.VITE_API_KEY;

if (!apiEndpoint) {
  throw new Error('VITE_API_ENDPOINT is not configured in .env file');
}

if (!apiKey) {
  throw new Error('VITE_API_KEY is not configured in .env file');
}

// Initialize the API client with the configured endpoint, API key, and generated session ID
configureApi(apiEndpoint, apiKey, getSessionId());
console.log('API configured with endpoint:', apiEndpoint);

function App() {
  const { messages, isLoading, sendMessage } = useChatStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSendMessage = async (content: string) => {
    sendMessage(content);
  };

  return (
    <div className="flex h-screen bg-white">
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <header className="border-b p-6">
          <h1 className="text-3xl font-bold">{import.meta.env.VITE_PAGE_TITLE}</h1>
        </header>
        <div className="flex-1 overflow-y-auto">
          {messages.map((message, index) => (
            <ChatMessage key={index} message={message} />
          ))}
          <div ref={messagesEndRef} />
        </div>
        <ChatInput onSendMessage={handleSendMessage} disabled={isLoading} />
      </div>
    </div>
  );
}

export default App;