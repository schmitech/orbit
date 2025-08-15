import type { CustomColors, Theme, WidgetConfig } from '../types/widget.types';

export const defaultCustomColors: CustomColors = {
  primary: '#4f46e5',
  secondary: '#7c3aed',
  background: '#ffffff',
  textPrimary: '#111827',
  textSecondary: '#6b7280',
  textInverse: '#ffffff',
  inputBackground: '#f9fafb',
  inputBorder: '#e5e7eb',
  userBubble: '#4f46e5',
  assistantBubble: '#f8fafc',
  userText: '#ffffff',
  suggestedBackground: '#fff7ed',
  suggestedHoverBackground: '#ffedd5',
  suggestedText: '#4338ca',
  chatButtonBg: '#ffffff',
  chatButtonHover: '#f8fafc',
  iconColor: '#7c3aed',
  iconBorderColor: '#e5e7eb',
  buttonBorderColor: '#e5e7eb',
  iconName: 'MessageSquare'
};

export const defaultWidgetConfig: WidgetConfig = {
  header: {
    title: 'Chat Assistant'
  },
  welcome: {
    title: 'Hello! 👋',
    description: 'How can I help you today?'
  },
  suggestedQuestions: [
    {
      text: 'What can you help me with?',
      query: 'What can you help me with today?'
    },
    {
      text: 'How do I get started?',
      query: 'How do I get started with this service?'
    }
  ],
  maxSuggestedQuestionLength: 120,
  maxSuggestedQuestionQueryLength: 200,
  icon: 'MessageSquare'
};

export const themes: Record<string, Theme> = {
  // Light Themes
  aurora: {
    name: 'Aurora',
    colors: {
      primary: '#8b5cf6',
      secondary: '#a78bfa',
      background: '#fdfcff',
      textPrimary: '#2e1065',
      textSecondary: '#6b21a8',
      textInverse: '#ffffff',
      inputBackground: '#f5f3ff',
      inputBorder: '#c4b5fd',
      userBubble: '#8b5cf6',
      assistantBubble: '#f5f3ff',
      userText: '#ffffff',
      suggestedBackground: '#ede9fe',
      suggestedHoverBackground: '#ddd6fe',
      suggestedText: '#6b21a8',
      chatButtonBg: '#ffffff',
      chatButtonHover: '#faf5ff',
      iconColor: '#a78bfa',
      iconBorderColor: '#c4b5fd',
      buttonBorderColor: '#c4b5fd',
      iconName: 'Sparkles'
    }
  },
  ocean: {
    name: 'Ocean',
    colors: {
      primary: '#0369a1',
      secondary: '#0ea5e9',
      background: '#f0f9ff',
      textPrimary: '#0c4a6e',
      textSecondary: '#0284c7',
      textInverse: '#ffffff',
      inputBackground: '#e0f2fe',
      inputBorder: '#7dd3fc',
      userBubble: '#0ea5e9',
      assistantBubble: '#e0f2fe',
      userText: '#ffffff',
      suggestedBackground: '#dbeafe',
      suggestedHoverBackground: '#bae6fd',
      suggestedText: '#0369a1',
      chatButtonBg: '#ffffff',
      chatButtonHover: '#f0f9ff',
      iconColor: '#0ea5e9',
      iconBorderColor: '#bae6fd',
      buttonBorderColor: '#bae6fd',
      iconName: 'Bot'
    }
  },
  sage: {
    name: 'Sage',
    colors: {
      primary: '#426651',
      secondary: '#87a08e',
      background: '#fafdf6',
      textPrimary: '#2d4a37',
      textSecondary: '#5a7c65',
      textInverse: '#ffffff',
      inputBackground: '#f0f4ec',
      inputBorder: '#c5d4c8',
      userBubble: '#87a08e',
      assistantBubble: '#f0f4ec',
      userText: '#ffffff',
      suggestedBackground: '#e8f0e4',
      suggestedHoverBackground: '#dce8d6',
      suggestedText: '#426651',
      chatButtonBg: '#ffffff',
      chatButtonHover: '#fafdf6',
      iconColor: '#87a08e',
      iconBorderColor: '#c5d4c8',
      buttonBorderColor: '#c5d4c8',
      iconName: 'Leaf'
    }
  },
  // Semi-Dark Themes
  twilight: {
    name: 'Twilight',
    colors: {
      primary: '#4c1d95',
      secondary: '#7c3aed',
      background: '#1e1b4b',
      textPrimary: '#e9d5ff',
      textSecondary: '#c4b5fd',
      textInverse: '#ffffff',
      inputBackground: '#312e81',
      inputBorder: '#4c1d95',
      userBubble: '#7c3aed',
      assistantBubble: '#312e81',
      userText: '#ffffff',
      suggestedBackground: '#312e81',
      suggestedHoverBackground: '#4c1d95',
      suggestedText: '#c4b5fd',
      chatButtonBg: '#312e81',
      chatButtonHover: '#4c1d95',
      iconColor: '#a78bfa',
      iconBorderColor: '#4c1d95',
      buttonBorderColor: '#4c1d95',
      iconName: 'Sparkles'
    }
  },
  lavender: {
    name: 'Lavender',
    colors: {
      primary: '#6b40b5',
      secondary: '#8b5fd3',
      background: '#faf8fc',
      textPrimary: '#4a3d5c',
      textSecondary: '#6b5d7a',
      textInverse: '#ffffff',
      inputBackground: '#f3eff7',
      inputBorder: '#d4c9e0',
      userBubble: '#440a8f',
      assistantBubble: '#f3eff7',
      userText: '#ffffff',
      suggestedBackground: '#ede7f3',
      suggestedHoverBackground: '#e0d8e9',
      suggestedText: '#6b5d7a',
      chatButtonBg: '#ffffff',
      chatButtonHover: '#faf8fc',
      iconColor: '#6b40b5',
      iconBorderColor: '#d4c9e0',
      buttonBorderColor: '#d4c9e0',
      iconName: 'Sparkles'
    }
  },
  midnight: {
    name: 'Midnight',
    colors: {
      primary: '#1e3a8a',
      secondary: '#3b82f6',
      background: '#0f172a',
      textPrimary: '#e0e7ff',
      textSecondary: '#a5b4fc',
      textInverse: '#ffffff',
      inputBackground: '#1e293b',
      inputBorder: '#334155',
      userBubble: '#3b82f6',
      assistantBubble: '#1e293b',
      userText: '#ffffff',
      suggestedBackground: '#1e293b',
      suggestedHoverBackground: '#334155',
      suggestedText: '#93bbfc',
      chatButtonBg: '#1e293b',
      chatButtonHover: '#334155',
      iconColor: '#60a5fa',
      iconBorderColor: '#334155',
      buttonBorderColor: '#334155',
      iconName: 'MessageCircleMore'
    }
  },
  // Dark Themes
  obsidian: {
    name: 'Obsidian',
    colors: {
      primary: '#2f3037',
      secondary: '#5a5d6e',
      background: '#202124',
      textPrimary: '#e8eaed',
      textSecondary: '#9aa0a6',
      textInverse: '#ffffff',
      inputBackground: '#292b2f',
      inputBorder: '#5f6368',
      userBubble: '#5a5d6e',
      assistantBubble: '#2f3037',
      userText: '#e8eaed',
      suggestedBackground: '#2f3037',
      suggestedHoverBackground: '#5a5d6e',
      suggestedText: '#9aa0a6',
      chatButtonBg: '#292b2f',
      chatButtonHover: '#5f6368',
      iconColor: '#80868b',
      iconBorderColor: '#5f6368',
      buttonBorderColor: '#5f6368',
      iconName: 'Brain'
    }
  },
  carbon: {
    name: 'Carbon',
    colors: {
      primary: '#171717',
      secondary: '#262626',
      background: '#0a0a0a',
      textPrimary: '#f5f5f5',
      textSecondary: '#a3a3a3',
      textInverse: '#ffffff',
      inputBackground: '#171717',
      inputBorder: '#262626',
      userBubble: '#262626',
      assistantBubble: '#171717',
      userText: '#f5f5f5',
      suggestedBackground: '#171717',
      suggestedHoverBackground: '#262626',
      suggestedText: '#a3a3a3',
      chatButtonBg: '#171717',
      chatButtonHover: '#262626',
      iconColor: '#737373',
      iconBorderColor: '#262626',
      buttonBorderColor: '#262626',
      iconName: 'Cpu'
    }
  },
  // Colorful Themes
  sapphire: {
    name: 'Sapphire',
    colors: {
      primary: '#1e3a5f',
      secondary: '#2c5282',
      background: '#f7fafc',
      textPrimary: '#102a43',
      textSecondary: '#486581',
      textInverse: '#ffffff',
      inputBackground: '#e6f2ff',
      inputBorder: '#90cdf4',
      userBubble: '#2c5282',
      assistantBubble: '#e6f2ff',
      userText: '#ffffff',
      suggestedBackground: '#dbeafe',
      suggestedHoverBackground: '#bfdbfe',
      suggestedText: '#1e3a5f',
      chatButtonBg: '#ffffff',
      chatButtonHover: '#f7fafc',
      iconColor: '#2563eb',
      iconBorderColor: '#90cdf4',
      buttonBorderColor: '#90cdf4',
      iconName: 'Zap'
    }
  }
};

export const PROMPT_EXAMPLES = {
  general: {
    title: "General Assistant",
    description: "A friendly, professional assistant for general inquiries",
    prompt: "You are a helpful and friendly AI assistant. You provide accurate, concise, and professional responses to user questions. Always maintain a polite and supportive tone."
  },
  support: {
    title: "Customer Support",
    description: "Focused on helping customers with issues and questions",
    prompt: "You are a customer support specialist. Help users with product questions, troubleshooting, and account issues. Be empathetic and solution-focused. If you cannot resolve an issue, guide them to contact human support."
  },
  sales: {
    title: "Sales Assistant",
    description: "Help convert visitors into customers",
    prompt: "You are a sales assistant helping potential customers. Answer questions about products, pricing, and features. Highlight benefits and value propositions. Be persuasive but not pushy. Guide interested users toward making a purchase decision."
  },
  technical: {
    title: "Technical Support",
    description: "For technical documentation and developer support",
    prompt: "You are a technical support expert. Help users with technical issues, API documentation, and implementation questions. Provide clear, step-by-step instructions. Include code examples when relevant. Be patient with users of all technical levels."
  }
};