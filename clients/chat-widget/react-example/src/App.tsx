import React from 'react';
import { useEffect, useRef } from 'react';

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
        theme?: any,
        icon?: string
      }
    }) => void;
    ChatbotWidget?: {
      updateWidgetConfig: (config: any) => void;
      setApiUrl: (apiUrl: string) => void;
      setApiKey: (apiKey: string) => void;
      getCurrentConfig?: () => any;
    };
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
    
    const config = {
      apiUrl: 'http://localhost:3000',
      apiKey: 'test-api-key',
      sessionId: getSessionId(),
      containerSelector: '#chatbot-container',
      widgetConfig: {
        header: {
          title: "Chat Widget Example"
        },
        welcome: {
          title: "Welcome to the Chat Widget",
          description: "This is a simple example of how to integrate the chat widget into your React application."
        },
        suggestedQuestions: [
          {
            text: "How do I get started?",
            query: "What are the first steps to use this widget?"
          },
          {
            text: "What features are available?",
            query: "Tell me about the available features"
          },
          {
            text: "How can I customize the widget?",
            query: "What customization options are available?"
          }
        ],
        maxSuggestedQuestionLength: 50,
        maxSuggestedQuestionQueryLength: 200,
        theme: {
          primary: '#2563eb',
          secondary: '#3b82f6',
          background: '#ffffff',
          text: {
            primary: '#1f2937',
            secondary: '#6b7280',
            inverse: '#ffffff'
          },
          input: {
            background: '#f9fafb',
            border: '#d1d5db'
          },
          message: {
            user: '#2563eb',
            assistant: '#f8fafc',
            userText: '#ffffff'
          },
          suggestedQuestions: {
            background: '#eff6ff',
            hoverBackground: '#dbeafe',
            text: '#1e40af'
          },
          chatButton: {
            background: '#ffffff',
            hoverBackground: '#f3f4f6'
          },
          iconColor: '#3b82f6'
        },
        icon: "message-square"
      }
    };
    
    window.initChatbotWidget(config);
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
          This is a simple example of how to integrate the chat widget into your React application.
          The widget is embedded below in container mode.
        </p>
      </div>

      <div className="test-section">
        <h3>Embedded Widget:</h3>
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