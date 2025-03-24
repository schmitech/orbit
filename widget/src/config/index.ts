// Define configuration types
import { ThemeConfig, defaultTheme, IconType } from '../config';

export { defaultTheme };

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
  theme: ThemeConfig;
  icon?: IconType; // Icon to display in the header and chat button
}

// Default configuration
export const defaultConfig: ChatConfig = {
  welcome: {
    title: "Welcome to Our Help Center!",
    description: "I'm here to help you with any questions you might have."
  },
  suggestedQuestions: [
    {
      text: "How can I help you today?",
      query: "What services do you offer?"
    },
    {
      text: "Contact information",
      query: "What are your contact details?"
    }
  ],
  header: {
    title: "Help Center"
  },
  theme: defaultTheme,
  icon: "message-square" // Default icon
};

// Get the configuration
export const getChatConfig = (): ChatConfig => {
  return defaultConfig;
}; 