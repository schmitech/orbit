import React from 'react';
import { useEffect, useRef } from 'react';

/**
 * CHAT WIDGET CONFIGURATION EXAMPLE
 * 
 * This example demonstrates all available configuration options for the chat widget.
 * 
 * REQUIRED PARAMETERS:
 * - apiUrl: string          - Your chatbot API endpoint URL
 * - apiKey: string          - Your API authentication key  
 * - sessionId: string       - Unique identifier for the chat session
 * 
 * OPTIONAL PARAMETERS:
 * - containerSelector: string - CSS selector for custom container (defaults to floating widget)
 * 
 * WIDGET CONFIGURATION (all optional):
 * - header: { title: string }
 * - welcome: { title: string, description: string }
 * - suggestedQuestions: Array<{ text: string, query: string }>
 * - maxSuggestedQuestionLength: number (default: 50)
 * - maxSuggestedQuestionQueryLength: number (default: 200)
 * - theme: { comprehensive theme object - see below }
 * 
 * THEME PROPERTIES (all optional):
 * - primary: string (header/user message color)
 * - secondary: string (accent color)
 * - background: string (widget background)
 * - text: { primary: string, secondary: string, inverse: string }
 * - input: { background: string, border: string }
 * - message: { user: string, assistant: string, userText: string }
 * - suggestedQuestions: { background: string, hoverBackground: string, text: string }
 * - chatButton: { background: string, hoverBackground: string }
 */

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
  const storageKey = 'test_session_id';
  let sessionId = sessionStorage.getItem(storageKey);
  
  if (!sessionId) {
    sessionId = generateUUID();
    sessionStorage.setItem(storageKey, sessionId);
  }
  
  return sessionId;
}

declare global {
  interface Window {
    initChatbotWidget?: (config: {
      apiUrl: string,
      apiKey: string,
      sessionId?: string,
      containerSelector?: string,
      widgetConfig?: {
        header?: { title: string },
        welcome?: { title: string, description: string },
        suggestedQuestions?: Array<{ text: string, query: string }>,
        maxSuggestedQuestionLength?: number,
        maxSuggestedQuestionQueryLength?: number,
        theme?: any
      }
    }) => void;
    ChatbotWidget?: {
      updateWidgetConfig: (config: any) => void;
      setApiUrl: (apiUrl: string) => void;
      setApiKey: (apiKey: string) => void;
      getCurrentConfig?: () => any;
    };
    React?: any;
    ReactDOM?: any;
  }
}

function App() {
  const widgetInitialized = React.useRef(false);

  const initializeWidget = () => {
    if (!window.initChatbotWidget) {
      console.error('initChatbotWidget not available');
      return;
    }

    console.log('Initializing widget...');
    
    // This example demonstrates all available configuration options
    // Remove or modify any options based on your needs
    
    const config = {
      // Required parameters
      apiUrl: 'http://localhost:3000',
      apiKey: 'test-api-key',
      sessionId: getSessionId(),
      
      // Optional: Custom container selector (remove this to use default floating widget)
      containerSelector: '#chatbot-container',
      
      // Widget configuration
      widgetConfig: {
        // Header configuration
        header: {
          title: "AI Retail Assistant"
        },
        
        // Welcome message configuration
        welcome: {
          title: "Need Help Running Your Store?",
          description: "Your always-on assistant for retail store operations, support, and service delivery."
        },
        
        // Suggested questions configuration
        suggestedQuestions: [
          {
            text: "How do I set up a new store location?",
            query: "What is the process for launching a new retail store?"
          },
          {
            text: "What's the process for onboarding new employees?",
            query: "How do I onboard new retail staff effectively?"
          },
          {
            text: "How can I track inventory in real time?",
            query: "What tools are available for real-time inventory tracking?"
          },
          {
            text: "What are the best practices for handling customer complaints?",
            query: "How should customer complaints be managed in-store?"
          }
        ],
        
        // Optional: Customize length limits for suggested questions
        maxSuggestedQuestionLength: 60,      // Display length limit (default: 50)
        maxSuggestedQuestionQueryLength: 200, // Query length limit (default: 200)
        
        // Theme configuration (all properties are optional)
        theme: {
          // Main colors
          primary: '#2563eb',     // Header and user message color
          secondary: '#3b82f6',   // Secondary/accent color
          background: '#ffffff',  // Widget background color
          
          // Text colors
          text: {
            primary: '#1f2937',   // Main text color
            secondary: '#6b7280', // Secondary text color (required)
            inverse: '#ffffff'    // Text color on colored backgrounds
          },
          
          // Input field styling
          input: {
            background: '#f9fafb', // Input field background
            border: '#d1d5db'     // Input field border color
          },
          
          // Message bubble styling
          message: {
            user: '#2563eb',      // User message bubble color
            assistant: '#f8fafc', // Assistant message bubble color
            userText: '#ffffff'   // User message text color
          },
          
          // Suggested questions styling
          suggestedQuestions: {
            background: '#eff6ff',    // Background color
            hoverBackground: '#dbeafe', // Hover background color
            text: '#1e40af'          // Text color
          },
          
          // Chat button styling
          chatButton: {
            background: '#ffffff',     // Button background
            hoverBackground: '#f3f4f6', // Button hover background
            iconColor: '#3b82f6',      // Icon color (matches secondary theme color)
            iconBorderColor: '#e5e7eb', // Icon border color
            borderColor: '#e5e7eb',     // Button border color
            iconName: 'MessageSquare'   // Icon name (see available icons in README)
          }
        }
      }
    };
    
    window.initChatbotWidget(config);
    
    // ALTERNATIVE: Floating widget configuration (without container)
    // Uncomment the code below and comment out the config above to use floating mode
    /*
    const floatingConfig = {
      // Required parameters
      apiUrl: 'http://localhost:3000',
      apiKey: 'test-api-key', 
      sessionId: getSessionId(),
      
      // Note: No containerSelector = floating widget in bottom-right corner
      
      // Widget configuration
      widgetConfig: {
        header: { title: "AI Assistant" },
        welcome: { 
          title: "Hello! How can I help?",
          description: "I'm here to assist you with any questions." 
        },
        suggestedQuestions: [
          { text: "What can you help me with?", query: "What can you help me with?" },
          { text: "Get started", query: "How do I get started?" }
        ],
        theme: {
          primary: '#10b981', // Emerald theme
          secondary: '#059669'
        }
      }
    };
    
    window.initChatbotWidget(floatingConfig);
    */
  };

  useEffect(() => {
    if (!widgetInitialized.current) {
      const checkWidgetLoaded = () => {
        if (typeof window.initChatbotWidget !== 'undefined') {
          if (typeof window.React === 'undefined' || typeof window.ReactDOM === 'undefined') {
            console.error('React or ReactDOM not loaded!');
            console.log('Waiting for React to load...');
            setTimeout(checkWidgetLoaded, 100);
            return;
          }
          
          console.log('ChatbotWidget loaded successfully! Starting initialization...');
          initializeWidget();
          widgetInitialized.current = true;
        } else {
          console.log('Waiting for ChatbotWidget to load...');
          setTimeout(checkWidgetLoaded, 100);
        }
      };
      
      const timer = setTimeout(checkWidgetLoaded, 100);
      return () => clearTimeout(timer);
    }
  }, []);

  return (
    <div className="container" style={{
      maxWidth: '900px',
      margin: '0 auto',
      padding: '20px',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
    }}>
      <h1>Chat Widget React Example</h1>
      
      <div className="test-section">
        <p>
          This is a comprehensive example showing how to integrate the chat widget into your React application.
          The widget is embedded below in container mode, demonstrating all available configuration options including:
        </p>
        <ul style={{ marginLeft: '20px', marginTop: '10px' }}>
          <li><strong>Custom theming</strong> with all color options</li>
          <li><strong>Suggested questions</strong> with length limits</li>
          <li><strong>Header and welcome message</strong> customization</li>
          <li><strong>Session management</strong> with UUID generation</li>
          <li><strong>Container mode</strong> vs floating widget options</li>
        </ul>
        <p style={{ marginTop: '15px', fontSize: '14px', color: '#666' }}>
          💡 <strong>Tip:</strong> Check the source code to see alternative configurations, including floating widget mode.
        </p>
      </div>

      <div className="test-section">
        <h3>Embedded Widget (Container Mode):</h3>
        <div 
          id="chatbot-container" 
          style={{
            border: '2px dashed #ddd',
            minHeight: '400px',
            padding: '20px',
            borderRadius: '8px',
            background: '#fafafa'
          }}
        >
          <p>Widget will appear here</p>
        </div>
      </div>
    </div>
  );
}

export default App; 