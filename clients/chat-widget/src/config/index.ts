export interface ChatConfig {
  header: {
    title: string;
  };
  theme: {
    primary: string;
    secondary: string;
    background: string;
    text: {
      primary: string;
      secondary: string;
      inverse: string;
    };
    input: {
      background: string;
      border: string;
    };
    message: {
      user: string;
      userText: string;
      assistant: string;
      assistantText?: string;
    };
    suggestedQuestions: {
      questionsBackground: string;
      text: string;
      highlightedBackground: string;
    };
    chatButton: {
      background: string;
      hoverBackground?: string;
      borderColor?: string;
      iconColor?: string;
      iconBorderColor?: string;
      iconName?: string;
    };
  };
  welcome: {
    title: string;
    description: string;
  };
  suggestedQuestions: Array<{
    text: string;
    query: string;
  }>;
}

export const defaultTheme = {
  primary: '#EC994B',
  secondary: '#1E3A8A',
  background: '#FFFFFF',
  text: {
    primary: '#1F2937',
    secondary: '#6B7280',
    inverse: '#FFFFFF'
  },
  input: {
    background: '#FFFFFF',
    border: '#D1D5DB'
  },
  message: {
    user: '#1E3A8A',
    userText: '#FFFFFF',
    assistant: '#FFFFFF'
  },
  suggestedQuestions: {
    questionsBackground: '#F3F4F6',
    text: '#1F2937',
    highlightedBackground: '#FEF3C7'
  },
  chatButton: {
    background: '#ffffff',
    hoverBackground: '#f8fafc',
    borderColor: '#e5e7eb',
    iconColor: '#f97316',
    iconBorderColor: '#111111',
    iconName: 'MessageSquare'
  }
};

export const getChatConfig = (): ChatConfig => ({
  header: {
    title: "AI Assistant"
  },
  theme: defaultTheme,
  welcome: {
    title: "Hello! How can I help you today?",
    description: "I'm your AI assistant, ready to help with any questions you might have."
  },
  suggestedQuestions: [
    { text: "What can you help me with?", query: "What can you help me with?" },
    { text: "Tell me about your features", query: "Tell me about your features" },
    { text: "How do I get started?", query: "How do I get started?" }
  ]
});