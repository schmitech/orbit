interface Window {
  React: any;
  ReactDOM: any;
  initChatbotWidget: (config: { 
    apiUrl: string; 
    containerSelector?: string;
    widgetConfig?: Partial<ChatConfig>;
  }) => void;
  CHATBOT_API_URL: string;
  ChatbotWidget: {
    ChatWidget: React.FC<any>;
    useChatStore: any;
    injectChatWidget: (config: { 
      apiUrl: string; 
      containerSelector?: string;
      widgetConfig?: Partial<ChatConfig>;
    }) => void;
    setApiUrl: (url: string) => void;
    getApiUrl: () => string;
    updateWidgetConfig: (config: Partial<ChatConfig>) => void;
  };
} 