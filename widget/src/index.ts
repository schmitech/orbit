import React from 'react';
import ReactDOM from 'react-dom/client';
import { ChatWidget, ChatWidgetProps } from './ChatWidget';
import { useChatStore } from './store/chatStore';
import './index.css';
import { streamChat, configureApi } from '@schmitech/chatbot-api';
import { getChatConfig, ChatConfig, defaultConfig } from './config/index';

export { ChatWidget, useChatStore, getChatConfig };
export type { ChatWidgetProps, ChatConfig };

// Also export as default for backward compatibility
export default ChatWidget;

// This will be the global API URL that components can import
let apiUrl: string | null = null;
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

export function setApiUrl(url: string): void {
  apiUrl = url;
  if (typeof window !== 'undefined') {
    window.CHATBOT_API_URL = url;
    // Configure the API
    configureApi(url);
  }
}

// Function to update widget configuration at runtime
export function updateWidgetConfig(config: Partial<ChatConfig>): void {
  if (typeof window === 'undefined') return;
  
  currentConfig = {
    ...defaultConfig,  // Start with default config
    ...currentConfig,  // Keep existing config
    ...config,         // Apply new config
    // Ensure required properties are present
    header: {
      ...defaultConfig.header,  // Keep default header
      ...currentConfig?.header, // Keep existing header
      ...config.header         // Apply new header
    },
    welcome: {
      ...defaultConfig.welcome,  // Keep default welcome
      ...currentConfig?.welcome, // Keep existing welcome
      ...config.welcome         // Apply new welcome
    },
    suggestedQuestions: config.suggestedQuestions || currentConfig?.suggestedQuestions || defaultConfig.suggestedQuestions,
    theme: {
      ...defaultConfig.theme,  // Keep default theme
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
  containerSelector?: string,
  widgetConfig?: Partial<ChatConfig>
}): void {
  // Ensure we're in a browser environment
  if (typeof window === 'undefined') return;

  // Set API URL and configure API
  setApiUrl(config.apiUrl);
  
  // Store initial config if provided
  if (config.widgetConfig) {
    currentConfig = {
      ...defaultConfig,  // Start with default config
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
    getApiUrl,
    updateWidgetConfig
  };
  
  console.log('Chatbot widget loaded. initChatbotWidget function is available.');
} 