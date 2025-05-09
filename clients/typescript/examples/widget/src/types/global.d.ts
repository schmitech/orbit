interface Window {
  React: any;
  ReactDOM: any;
  initChatbotWidget: (config: { 
    apiUrl: string; 
    apiKey: string;
    sessionId: string;
    containerSelector?: string;
    widgetConfig?: Partial<ChatConfig>;
  }) => void;
  CHATBOT_API_URL: string;
  CHATBOT_API_KEY: string;
  ChatbotWidget: {
    ChatWidget: React.FC<any>;
    useChatStore: any;
    injectChatWidget: (config: { 
      apiUrl: string; 
      apiKey: string;
      sessionId: string;
      containerSelector?: string;
      widgetConfig?: Partial<ChatConfig>;
    }) => void;
    setApiUrl: (url: string) => void;
    getApiUrl: () => string;
    setApiKey: (key: string) => void;
    getApiKey: () => string;
    updateWidgetConfig: (config: Partial<ChatConfig>) => void;
    configureApi: (apiUrl: string, apiKey: string, sessionId: string) => void;
    _latestConfig?: ChatConfig;
  };
} 