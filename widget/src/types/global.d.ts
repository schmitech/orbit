interface Window {
  React: any;
  ReactDOM: any;
  initChatbotWidget: (config: { apiUrl: string; containerSelector?: string }) => void;
  CHATBOT_API_URL: string;
  ChatbotWidget: {
    ChatWidget: React.FC<any>;
    useChatStore: any;
    injectChatWidget: (config: { apiUrl: string; containerSelector?: string }) => void;
    setApiUrl: (url: string) => void;
    getApiUrl: () => string;
  };
} 