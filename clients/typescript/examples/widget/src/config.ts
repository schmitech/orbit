export interface ThemeConfig {
  primary: string;      // Main brand color
  secondary: string;    // Secondary color
  background: string;   // Chat window background
  text: {
    primary: string;    // Main text color
    secondary: string;  // Secondary text color
    inverse: string;    // Text color on primary backgrounds
  };
  input: {
    background: string;
    border: string;
  };
  message: {
    user: string;       // User message background
    assistant: string;  // Assistant message background
    userText: string;   // User message text color
  };
  suggestedQuestions: {
    background: string; // Background for suggested questions
    hoverBackground: string; // Background for suggested questions on hover
    text: string;       // Text color for suggested questions
  };
  iconColor: string;    // Color for the icon in welcome message
}

// Default theme
export const defaultTheme: ThemeConfig = {
  primary: '#2C3E50',
  secondary: '#f97316', // orange-500
  background: '#ffffff',
  text: {
    primary: '#1a1a1a',
    secondary: '#666666',
    inverse: '#ffffff'
  },
  input: {
    background: '#f9fafb',
    border: '#e5e7eb'
  },
  message: {
    user: '#2C3E50',
    assistant: '#ffffff',
    userText: '#ffffff'
  },
  suggestedQuestions: {
    background: '#fff7ed',  // orange-50
    hoverBackground: '#ffedd5', // orange-100
    text: '#2C3E50'
  },
  iconColor: '#f97316'  // orange-500
};

// Possible icon options
export type IconType = 'heart' | 'message-square' | 'message-circle' | 'help-circle' | 'info' | 'bot' | 'sparkles';

// Update your existing config interface
export interface ChatConfig {
  header: {
    title: string;
  };
  welcome: {
    title: string;
    description: string;
  };
  suggestedQuestions: Array<{
    text: string;
    query: string;
  }>;
  theme: ThemeConfig;
  icon?: IconType; // Icon to display in the header and chat button
}