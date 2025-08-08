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
  modern: {
    name: 'Modern',
    colors: {
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
      iconName: 'Sparkles'
    }
  },
  minimal: {
    name: 'Minimal',
    colors: {
      primary: '#374151',
      secondary: '#6b7280',
      background: '#ffffff',
      textPrimary: '#111827',
      textSecondary: '#6b7280',
      textInverse: '#ffffff',
      inputBackground: '#f9fafb',
      inputBorder: '#d1d5db',
      userBubble: '#374151',
      assistantBubble: '#f9fafb',
      userText: '#ffffff',
      suggestedBackground: '#f3f4f6',
      suggestedHoverBackground: '#e5e7eb',
      suggestedText: '#374151',
      chatButtonBg: '#ffffff',
      chatButtonHover: '#f9fafb',
      iconColor: '#6b7280',
      iconBorderColor: '#e5e7eb',
      buttonBorderColor: '#e5e7eb',
      iconName: 'MessageCircle'
    }
  },
  corporate: {
    name: 'Corporate',
    colors: {
      primary: '#1e40af',
      secondary: '#3b82f6',
      background: '#ffffff',
      textPrimary: '#1e293b',
      textSecondary: '#64748b',
      textInverse: '#ffffff',
      inputBackground: '#f8fafc',
      inputBorder: '#e2e8f0',
      userBubble: '#1e40af',
      assistantBubble: '#f1f5f9',
      userText: '#ffffff',
      suggestedBackground: '#eff6ff',
      suggestedHoverBackground: '#dbeafe',
      suggestedText: '#1d4ed8',
      chatButtonBg: '#ffffff',
      chatButtonHover: '#f8fafc',
      iconColor: '#3b82f6',
      iconBorderColor: '#e5e7eb',
      buttonBorderColor: '#e5e7eb',
      iconName: 'MessageSquareText'
    }
  },
  dark: {
    name: 'Dark',
    colors: {
      primary: '#0f172a',
      secondary: '#06b6d4',
      background: '#1e293b',
      textPrimary: '#f1f5f9',
      textSecondary: '#cbd5e1',
      textInverse: '#ffffff',
      inputBackground: '#334155',
      inputBorder: '#475569',
      userBubble: '#06b6d4',
      assistantBubble: '#0f172a',
      userText: '#ffffff',
      suggestedBackground: '#164e63',
      suggestedHoverBackground: '#0e7490',
      suggestedText: '#67e8f9',
      chatButtonBg: '#334155',
      chatButtonHover: '#475569',
      iconColor: '#06b6d4',
      iconBorderColor: '#475569',
      buttonBorderColor: '#475569',
      iconName: 'Bot'
    }
  },
  emerald: {
    name: 'Emerald',
    colors: {
      primary: '#065f46',
      secondary: '#10b981',
      background: '#ffffff',
      textPrimary: '#1f2937',
      textSecondary: '#6b7280',
      textInverse: '#ffffff',
      inputBackground: '#f0fdf4',
      inputBorder: '#d1fae5',
      userBubble: '#065f46',
      assistantBubble: '#ecfdf5',
      userText: '#ffffff',
      suggestedBackground: '#ecfdf5',
      suggestedHoverBackground: '#d1fae5',
      suggestedText: '#047857',
      chatButtonBg: '#ffffff',
      chatButtonHover: '#f0fdf4',
      iconColor: '#10b981',
      iconBorderColor: '#e5e7eb',
      buttonBorderColor: '#e5e7eb',
      iconName: 'Leaf'
    }
  },
  sunset: {
    name: 'Sunset',
    colors: {
      primary: '#dc2626',
      secondary: '#f59e0b',
      background: '#ffffff',
      textPrimary: '#1f2937',
      textSecondary: '#6b7280',
      textInverse: '#ffffff',
      inputBackground: '#fffbeb',
      inputBorder: '#fed7aa',
      userBubble: '#dc2626',
      assistantBubble: '#fff7ed',
      userText: '#ffffff',
      suggestedBackground: '#fff7ed',
      suggestedHoverBackground: '#ffedd5',
      suggestedText: '#c2410c',
      chatButtonBg: '#ffffff',
      chatButtonHover: '#fffbeb',
      iconColor: '#f59e0b',
      iconBorderColor: '#e5e7eb',
      buttonBorderColor: '#e5e7eb',
      iconName: 'Sun'
    }
  },
  lavender: {
    name: 'Lavender',
    colors: {
      primary: '#7c3aed',
      secondary: '#a855f7',
      background: '#ffffff',
      textPrimary: '#1f2937',
      textSecondary: '#6b7280',
      textInverse: '#ffffff',
      inputBackground: '#faf5ff',
      inputBorder: '#e9d5ff',
      userBubble: '#7c3aed',
      assistantBubble: '#f5f3ff',
      userText: '#ffffff',
      suggestedBackground: '#f5f3ff',
      suggestedHoverBackground: '#ede9fe',
      suggestedText: '#6d28d9',
      chatButtonBg: '#ffffff',
      chatButtonHover: '#faf5ff',
      iconColor: '#a855f7',
      iconBorderColor: '#e5e7eb',
      buttonBorderColor: '#e5e7eb',
      iconName: 'Sparkles'
    }
  },
  monochrome: {
    name: 'Monochrome',
    colors: {
      primary: '#1f2937',
      secondary: '#6b7280',
      background: '#ffffff',
      textPrimary: '#111827',
      textSecondary: '#6b7280',
      textInverse: '#ffffff',
      inputBackground: '#f9fafb',
      inputBorder: '#d1d5db',
      userBubble: '#1f2937',
      assistantBubble: '#f3f4f6',
      userText: '#ffffff',
      suggestedBackground: '#f3f4f6',
      suggestedHoverBackground: '#e5e7eb',
      suggestedText: '#374151',
      chatButtonBg: '#ffffff',
      chatButtonHover: '#f9fafb',
      iconColor: '#6b7280',
      iconBorderColor: '#e5e7eb',
      buttonBorderColor: '#e5e7eb',
      iconName: 'MessageCircleMore'
    }
  },
  rose: {
    name: 'Rose',
    colors: {
      primary: '#be185d',
      secondary: '#ec4899',
      background: '#ffffff',
      textPrimary: '#1f2937',
      textSecondary: '#6b7280',
      textInverse: '#ffffff',
      inputBackground: '#fdf2f8',
      inputBorder: '#f9a8d4',
      userBubble: '#be185d',
      assistantBubble: '#fdf2f8',
      userText: '#ffffff',
      suggestedBackground: '#fdf2f8',
      suggestedHoverBackground: '#fce7f3',
      suggestedText: '#be185d',
      chatButtonBg: '#ffffff',
      chatButtonHover: '#fdf2f8',
      iconColor: '#ec4899',
      iconBorderColor: '#e5e7eb',
      buttonBorderColor: '#e5e7eb',
      iconName: 'Sparkles'
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