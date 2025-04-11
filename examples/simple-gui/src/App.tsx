import { useRef, useEffect } from 'react';
import { ChatMessage } from './components/ChatMessage';
import { ChatInput } from './components/ChatInput';
import { Sidebar } from './components/Sidebar';
import { useChatStore } from './store';
import { streamChat, configureApi } from './api';

// Configure the API with the endpoint and API key from environment variables
const apiEndpoint = import.meta.env.VITE_API_ENDPOINT;
const apiKey = import.meta.env.VITE_API_KEY;

if (!apiEndpoint) {
  throw new Error('VITE_API_ENDPOINT is not configured in .env file');
}

if (!apiKey) {
  throw new Error('VITE_API_KEY is not configured in .env file');
}

// Initialize the API client with the configured endpoint and API key
configureApi(apiEndpoint, apiKey);
console.log('API configured with endpoint:', apiEndpoint);

function App() {
  const { messages, isLoading, addMessage, setIsLoading, appendToLastMessage } = useChatStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSendMessage = async (content: string) => {
    addMessage({ role: 'user', content });
    setIsLoading(true);
    addMessage({ role: 'assistant', content: '' });
  
    try {
      for await (const chunk of streamChat(content)) {
        if (chunk.text) {
          appendToLastMessage(chunk.text);
        }
        
        if (chunk.done) {
          console.log('Response complete');
        }
      }
    } catch (error) {
      console.error('Error in chat:', error);
      appendToLastMessage('Sorry, there was an error processing your request.');
    } finally {
      setIsLoading(false);
    }
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