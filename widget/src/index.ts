import ChatWidget from './ChatWidget';
import { useChatStore } from './store/chatStore';
import './index.css';
import { streamChat, configureApi } from 'chatbot-api';

export { ChatWidget, useChatStore };

// This will be the global API URL that components can import
let apiUrl: string | null = null;

export function getApiUrl(): string {
  if (!apiUrl) {
    if (typeof window !== 'undefined' && window.CHATBOT_API_URL) {
      apiUrl = window.CHATBOT_API_URL;
    } else {
      throw new Error('API URL not set. Call setApiUrl or use injectChatWidget to configure the API URL.');
    }
  }
  return apiUrl;
}

export function setApiUrl(url: string): void {
  apiUrl = url;
  if (typeof window !== 'undefined') {
    window.CHATBOT_API_URL = url;
    // Configure the API
    configureApi(url);
  }
}

// Function to inject the widget into any website
export function injectChatWidget(config: { 
  apiUrl: string,
  containerSelector?: string 
}): void {
  // Ensure we're in a browser environment
  if (typeof window === 'undefined') return;

  // Set API URL and configure API
  setApiUrl(config.apiUrl);
  
  // We need to ensure this function is called only after React and ReactDOM are fully loaded
  function tryInitialize() {
    // Use a try-catch to handle any initialization errors
    try {
      if (!window.React || !window.ReactDOM) {
        console.log('React or ReactDOM not available yet, retrying in 100ms...');
        setTimeout(tryInitialize, 100);
        return;
      }
      
      // Get container
      const container = config.containerSelector
        ? document.querySelector(config.containerSelector)
        : document.createElement('div');
      
      if (!container) {
        console.error(`Container with selector "${config.containerSelector}" not found`);
        return;
      }
      
      // If no selector provided, append to body
      if (!config.containerSelector) {
        container.id = 'chatbot-widget-container';
        document.body.appendChild(container);
      }

      // Create root and render the widget with the window's React version
      const root = window.ReactDOM.createRoot(container as HTMLElement);
      root.render(window.React.createElement(ChatWidget));
      
      console.log('Widget initialized successfully!');
    } catch (err) {
      console.error('Error initializing chatbot widget:', err);
    }
  }

  // Start the initialization process with a short delay
  setTimeout(tryInitialize, 100);
}

// Make sure to set it on window for UMD builds
if (typeof window !== 'undefined') {
  window.initChatbotWidget = injectChatWidget;
  
  // Also expose the widget component directly
  window.ChatbotWidget = {
    ChatWidget,
    useChatStore,
    injectChatWidget,
    setApiUrl,
    getApiUrl
  };
  
  console.log('Chatbot widget loaded. initChatbotWidget function is available.');
}

export default ChatWidget; 