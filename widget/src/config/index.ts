// Define configuration types
export interface ChatConfig {
  welcome: {
    title: string;
    description: string;
  };
  suggestedQuestions: {
    text: string;
    query: string;
  }[];
  header: {
    title: string;
  };
}

// Import the configuration
import defaultConfig from './chatConfig.json';

// Get the configuration
export const getChatConfig = (): ChatConfig => {
  return defaultConfig as ChatConfig;
}; 