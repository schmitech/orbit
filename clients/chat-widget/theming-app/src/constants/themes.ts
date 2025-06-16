import type { CustomColors, Theme, WidgetConfig } from '../types/widget.types';

export const defaultCustomColors: CustomColors = {
  primary: '#4f46e5',
  secondary: '#7c3aed',
  background: '#ffffff',
  textPrimary: '#111827',
  textInverse: '#ffffff',
  inputBackground: '#f9fafb',
  inputBorder: '#e5e7eb',
  userBubble: '#4f46e5',
  assistantBubble: '#f8fafc',
  userText: '#ffffff',
  suggestedText: '#4338ca',
  chatButtonBg: '#ffffff',
  chatButtonHover: '#f8fafc',
  iconColor: '#7c3aed'
};

export const defaultWidgetConfig: WidgetConfig = {
  header: {
    title: 'ORBIT Chat'
  },
  welcome: {
    title: 'Welcome! 👋',
    description: 'How can I help you today?'
  },
  suggestedQuestions: [
    {
      text: "Help me code something",
      query: "Can you help me write a simple function to calculate a tip?"
    },
    {
      text: "Explain a concept",
      query: "What is machine learning and how does it work?"
    },
    {
      text: "Write something creative",
      query: "Write a short story about a robot learning to paint"
    },
    {
      text: "Solve a problem",
      query: "I need to organize my daily schedule better. Any tips?"
    },
    {
      text: "Analyze something",
      query: "What are the pros and cons of remote work?"
    },
    {
      text: "Learn a language",
      query: "Teach me 5 basic Spanish phrases for travel"
    },
    {
      text: "Get advice",
      query: "How can I improve my productivity while working from home?"
    },
    {
      text: "Do some math",
      query: "If I save $50 per month, how much will I have in 2 years?"
    }
  ],
  maxSuggestedQuestionLength: 100,
  maxSuggestedQuestionQueryLength: 200,
  icon: 'message-square'
};

export const themes: Record<string, Theme> = {
  modern: {
    name: 'Modern',
    colors: {
      primary: '#4f46e5',
      secondary: '#7c3aed',
      background: '#ffffff',
      textPrimary: '#111827',
      textInverse: '#ffffff',
      inputBackground: '#f9fafb',
      inputBorder: '#e5e7eb',
      userBubble: '#4f46e5',
      assistantBubble: '#f8fafc',
      userText: '#ffffff',
      suggestedText: '#4338ca',
      chatButtonBg: '#ffffff',
      chatButtonHover: '#f8fafc',
      iconColor: '#7c3aed'
    }
  },
  minimal: {
    name: 'Minimal',
    colors: {
      primary: '#374151',
      secondary: '#6b7280',
      background: '#ffffff',
      textPrimary: '#111827',
      textInverse: '#ffffff',
      inputBackground: '#f9fafb',
      inputBorder: '#d1d5db',
      userBubble: '#374151',
      assistantBubble: '#f9fafb',
      userText: '#ffffff',
      suggestedText: '#374151',
      chatButtonBg: '#ffffff',
      chatButtonHover: '#f9fafb'
    }
  },
  corporate: {
    name: 'Corporate',
    colors: {
      primary: '#1e40af',
      secondary: '#3b82f6',
      background: '#ffffff',
      textPrimary: '#1e293b',
      textInverse: '#ffffff',
      inputBackground: '#f8fafc',
      inputBorder: '#e2e8f0',
      userBubble: '#1e40af',
      assistantBubble: '#f1f5f9',
      userText: '#ffffff',
      suggestedText: '#1d4ed8',
      chatButtonBg: '#ffffff',
      chatButtonHover: '#f8fafc'
    }
  },
  dark: {
    name: 'Dark',
    colors: {
      primary: '#0f172a',
      secondary: '#06b6d4',
      background: '#1e293b',
      textPrimary: '#f1f5f9',
      textInverse: '#ffffff',
      inputBackground: '#334155',
      inputBorder: '#475569',
      userBubble: '#06b6d4',
      assistantBubble: '#0f172a',
      userText: '#ffffff',
      suggestedText: '#67e8f9',
      chatButtonBg: '#334155',
      chatButtonHover: '#475569'
    }
  },
  emerald: {
    name: 'Emerald',
    colors: {
      primary: '#065f46',
      secondary: '#10b981',
      background: '#ffffff',
      textPrimary: '#1f2937',
      textInverse: '#ffffff',
      inputBackground: '#f0fdf4',
      inputBorder: '#d1fae5',
      userBubble: '#065f46',
      assistantBubble: '#ecfdf5',
      userText: '#ffffff',
      suggestedText: '#047857',
      chatButtonBg: '#ffffff',
      chatButtonHover: '#f0fdf4'
    }
  },
  sunset: {
    name: 'Sunset',
    colors: {
      primary: '#dc2626',
      secondary: '#f59e0b',
      background: '#ffffff',
      textPrimary: '#1f2937',
      textInverse: '#ffffff',
      inputBackground: '#fffbeb',
      inputBorder: '#fed7aa',
      userBubble: '#dc2626',
      assistantBubble: '#fff7ed',
      userText: '#ffffff',
      suggestedText: '#c2410c',
      chatButtonBg: '#ffffff',
      chatButtonHover: '#fffbeb'
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