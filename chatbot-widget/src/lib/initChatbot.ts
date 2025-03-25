import { ChatbotConfig } from '../types/chatbot';
import { useChatStore } from '../store/chatStore';

export const initChatbot = (config: ChatbotConfig) => {
  const { setConfig, messages } = useChatStore.getState();
  
  // Only set config if there are no messages yet
  if (messages.length === 0) {
    setConfig(config);
  }
};