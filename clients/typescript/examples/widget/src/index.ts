import React from 'react';
import ReactDOM from 'react-dom/client';
import { ChatWidget, ChatWidgetProps } from './ChatWidget';
import { useChatStore } from './store/chatStore';
import './index.css';
import { configureApi } from '@schmitech/chatbot-api';
import { getChatConfig, ChatConfig } from './config/index';

export { ChatWidget, useChatStore, getChatConfig };
export type { ChatWidgetProps, ChatConfig };

// Also export as default for backward compatibility
export default ChatWidget;

// This will be the global API URL that components can import
let apiUrl: string | null = null;
let apiKey: string | null = null;
let sessionId: string | null = null;
let currentConfig: ChatConfig | null = null;

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

export function getApiKey(): string {
  if (!apiKey) {
    if (typeof window !== 'undefined' && window.CHATBOT_API_KEY) {
      apiKey = window.CHATBOT_API_KEY;
    } else {
      throw new Error('API key not set. Call setApiKey or use injectChatWidget to configure the API key.');
    }
  }
  return apiKey;
}

export function setApiUrl(url: string): void {
  apiUrl = url;
  if (typeof window !== 'undefined') {
    window.CHATBOT_API_URL = url;
    // Configure the API with both URL and key
    if (apiKey && sessionId) {
      configureApi(url, apiKey, sessionId);
    }
  }
}

export function setApiKey(key: string): void {
  apiKey = key;
  if (typeof window !== 'undefined') {
    window.CHATBOT_API_KEY = key;
    // Configure the API with both URL and key
    if (apiUrl && sessionId) {
      configureApi(apiUrl, key, sessionId);
    }
  }
}

// Function to update widget configuration at runtime
export function updateWidgetConfig(config: Partial<ChatConfig>): void {
  if (typeof window === 'undefined') return;
  
  currentConfig = {
    ...getChatConfig(),  // Start with default config
    ...currentConfig,  // Keep existing config
    ...config,         // Apply new config
    // Ensure required properties are present
    header: {
      ...getChatConfig().header,  // Keep default header
      ...currentConfig?.header, // Keep existing header
      ...config.header         // Apply new header
    },
    welcome: {
      ...getChatConfig().welcome,  // Keep default welcome
      ...currentConfig?.welcome, // Keep existing welcome
      ...config.welcome         // Apply new welcome
    },
    suggestedQuestions: config.suggestedQuestions || currentConfig?.suggestedQuestions || getChatConfig().suggestedQuestions,
    theme: {
      ...getChatConfig().theme,  // Keep default theme
      ...currentConfig?.theme, // Keep existing theme
      ...config.theme         // Apply new theme
    }
  };
  
  // Dispatch a custom event to notify the widget of the config change
  window.dispatchEvent(new CustomEvent('chatbot-config-update', { 
    detail: currentConfig 
  }));
}

// Function to inject the widget into any website
export function injectChatWidget(config: { 
  apiUrl: string,
  apiKey: string,
  sessionId: string,
  containerSelector?: string,
  widgetConfig?: Partial<ChatConfig>
}): void {
  // Ensure we're in a browser environment
  if (typeof window === 'undefined') return;

  apiUrl = config.apiUrl;
  apiKey = config.apiKey;
  sessionId = config.sessionId;
  
  // Configure API with all required parameters
  configureApi(config.apiUrl, config.apiKey, config.sessionId);
  
  // Store initial config if provided
  if (config.widgetConfig) {
    currentConfig = {
      ...getChatConfig(),  // Start with default config
      ...config.widgetConfig  // Override with provided config
    };
  }
  
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

      // Create root and render the widget with the window's React version and pass the config
      const root = window.ReactDOM.createRoot(container as HTMLElement);
      root.render(window.React.createElement(ChatWidget, currentConfig));
      
      console.log('Chatbot widget initialized successfully!');
    } catch (err) {
      console.error('Error initializing chatbot widget:', err);
    }
  }

  // Start the initialization process with a short delay
  setTimeout(tryInitialize, 100);
}

// Make sure to set it on window for UMD builds
if (typeof window !== 'undefined') {
  // Explicitly make these available globally
  window.initChatbotWidget = injectChatWidget;
  
  // Also expose the widget component directly
  window.ChatbotWidget = {
    ChatWidget,
    useChatStore,
    injectChatWidget,
    setApiUrl,
    getApiUrl,
    setApiKey,
    getApiKey,
    updateWidgetConfig,
    configureApi
  };
  
  console.log('Chatbot widget loaded.');
} 