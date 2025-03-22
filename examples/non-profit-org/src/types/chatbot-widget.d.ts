declare module 'chatbot-widget' {
  import { FC } from 'react';
  
  export interface ChatWidgetProps {}
  
  export const ChatWidget: FC<ChatWidgetProps>;
  export const useChatStore: any;
}

interface Window {
  ChatbotWidget: {
    setApiUrl: (url: string) => void;
    getApiUrl: () => string;
    injectChatWidget: (config: { apiUrl: string; containerSelector?: string }) => void;
  }
} 