import type { CustomColors, Theme, WidgetConfig } from '../types/widget.types';

export const defaultCustomColors: CustomColors = {
  // Refined, modern default palette (name preserved)
  primary: '#2563eb',              // cobalt
  secondary: '#7c3aed',            // vivid violet accent
  background: '#ffffff',
  textPrimary: '#0f172a',          // slate-900
  textSecondary: '#475569',        // slate-600
  textInverse: '#ffffff',
  inputBackground: '#f8fafc',      // slate-50
  inputBorder: '#e5e7eb',          // gray-200
  userBubble: '#2563eb',
  assistantBubble: '#f8fafc',
  userText: '#ffffff',
  assistantText: '#0f172a',
  suggestedText: '#1d4ed8',
  chatButtonBg: '#2563eb',
  chatButtonHover: '#1d4ed8',
  iconColor: '#ffffff',
  iconBorderColor: '#2563eb',
  buttonBorderColor: 'transparent',
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
      text: 'What is the Theming App?',
      query: 'What is the ORBIT chat widget Theming App and what can I do with it?'
    },
    {
      text: 'How can I customize colors?',
      query: 'Explain how to customize theme colors (primary, secondary, text, bubbles, input, suggested chips, chat button, icon) in the Theming App.'
    },
    {
      text: 'Where do I set the API key?',
      query: 'Where do I enter the API key and API endpoint in the Theming App, and what happens when I click Update API Settings?'
    },
    {
      text: 'How do I export code?',
      query: 'How do I export the widget configuration from the Code tab as HTML or a JavaScript bundle, and which values must I replace before deploying?'
    },
    {
      text: 'Is it in beta and free?',
      query: 'Are the ORBIT widget and Theming App in beta, and are they free to use during the beta period?'
    }
  ],
  maxSuggestedQuestionLength: 120,
  maxSuggestedQuestionQueryLength: 200,
  icon: 'MessageSquare'
};

export const themes: Record<string, Theme> = {
  // Light Themes
  // Replaced "Aurora" palette with a dark-blue forward look; keeping key but renaming display
  aurora: {
    name: 'Nebula',
    colors: {
      primary: '#1d4ed8',                 // cobalt
      secondary: '#60a5fa',               // bright sky-blue accent
      background: '#f8fafc',              // soft gray-blue
      textPrimary: '#0f172a',             // near-black navy
      textSecondary: '#1e3a8a',
      textInverse: '#ffffff',
      inputBackground: '#e0f2fe',
      inputBorder: '#93c5fd',
      userBubble: '#1d4ed8',
      assistantBubble: '#e0f2fe',
      userText: '#ffffff',
      assistantText: '#0f172a',
      suggestedText: '#1e3a8a',
      chatButtonBg: '#1d4ed8',
      chatButtonHover: '#1e3a8a',
      iconColor: '#ffffff',
      iconBorderColor: '#1d4ed8',
      buttonBorderColor: 'transparent',
      iconName: 'MessageSquare'
    }
  },

  ocean: {
    name: 'Ocean',
    colors: {
      primary: '#0284c7',
      secondary: '#38bdf8',
      background: '#f0f9ff',
      textPrimary: '#0c4a6e',
      textSecondary: '#0369a1',
      textInverse: '#ffffff',
      inputBackground: '#e0f2fe',
      inputBorder: '#7dd3fc',
      userBubble: '#0284c7',
      assistantBubble: '#e0f2fe',
      userText: '#ffffff',
      assistantText: '#0c4a6e',
      suggestedText: '#0369a1',
      chatButtonBg: '#0284c7',
      chatButtonHover: '#0369a1',
      iconColor: '#ffffff',
      iconBorderColor: '#0284c7',
      buttonBorderColor: 'transparent',
      iconName: 'MessageSquare'
    }
  },

  // Replaced "Sage" with deeper greens; keeping key but renaming display
  sage: {
    name: 'Evergreen',
    colors: {
      primary: '#14532d',                 // deep forest green
      secondary: '#4ade80',               // modern green accent
      background: '#f0fdf4',              // light green-tinted
      textPrimary: '#052e16',
      textSecondary: '#166534',
      textInverse: '#ffffff',
      inputBackground: '#dcfce7',
      inputBorder: '#86efac',
      userBubble: '#166534',
      assistantBubble: '#dcfce7',
      userText: '#ffffff',
      assistantText: '#052e16',
      suggestedText: '#14532d',
      chatButtonBg: '#166534',
      chatButtonHover: '#14532d',
      iconColor: '#ffffff',
      iconBorderColor: '#166534',
      buttonBorderColor: 'transparent',
      iconName: 'MessageSquare'
    }
  },

  // Semi-Dark Themes
  twilight: {
    name: 'Twilight',
    colors: {
      primary: '#6d28d9',
      secondary: '#8b5cf6',
      background: '#1f1b3a',
      textPrimary: '#e9d5ff',
      textSecondary: '#c4b5fd',
      textInverse: '#ffffff',
      inputBackground: '#2a265a',
      inputBorder: '#4c1d95',
      userBubble: '#8b5cf6',
      assistantBubble: '#2a265a',
      userText: '#ffffff',
      assistantText: '#e9d5ff',
      suggestedText: '#d8b4fe',
      chatButtonBg: '#6d28d9',
      chatButtonHover: '#5b21b6',
      iconColor: '#ffffff',
      iconBorderColor: '#6d28d9',
      buttonBorderColor: 'transparent',
      iconName: 'MessageSquare'
    }
  },

  lavender: {
    name: 'Lavender',
    colors: {
      primary: '#7e22ce',
      secondary: '#8b5fd3',
      background: '#fbfaff',
      textPrimary: '#4a3d5c',
      textSecondary: '#6b5d7a',
      textInverse: '#ffffff',
      inputBackground: '#f3eff7',
      inputBorder: '#d4c9e0',
      userBubble: '#7e22ce',
      assistantBubble: '#f3eff7',
      userText: '#ffffff',
      assistantText: '#4a3d5c',
      suggestedText: '#6b5d7a',
      chatButtonBg: '#7e22ce',
      chatButtonHover: '#6b21a8',
      iconColor: '#ffffff',
      iconBorderColor: '#7e22ce',
      buttonBorderColor: 'transparent',
      iconName: 'MessageSquare'
    }
  },

  midnight: {
    name: 'Midnight',
    colors: {
      primary: '#1d4ed8',
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
      assistantText: '#e0e7ff',
      suggestedText: '#93c5fd',
      chatButtonBg: '#1d4ed8',
      chatButtonHover: '#1e40af',
      iconColor: '#ffffff',
      iconBorderColor: '#1d4ed8',
      buttonBorderColor: 'transparent',
      iconName: 'MessageSquare'
    }
  },

  // Dark Themes
  // Replaced "Obsidian" with a slate-gray dark; keeping key but renaming display
  obsidian: {
    name: 'Granite',
    colors: {
      primary: '#374151',                 // slate-700
      secondary: '#6b7280',               // slate-500
      background: '#111827',              // slate-900
      textPrimary: '#f3f4f6',
      textSecondary: '#9ca3af',
      textInverse: '#ffffff',
      inputBackground: '#1f2937',
      inputBorder: '#374151',
      userBubble: '#374151',
      assistantBubble: '#1f2937',
      userText: '#f3f4f6',
      assistantText: '#f3f4f6',
      suggestedText: '#d1d5db',
      chatButtonBg: '#374151',
      chatButtonHover: '#4b5563',
      iconColor: '#ffffff',
      iconBorderColor: '#374151',
      buttonBorderColor: 'transparent',
      iconName: 'MessageSquare'
    }
  },

  carbon: {
    name: 'Carbon',
    colors: {
      primary: '#111111',
      secondary: '#2d2d2d',
      background: '#0a0a0a',
      textPrimary: '#e5e5e5',
      textSecondary: '#a3a3a3',
      textInverse: '#ffffff',
      inputBackground: '#141414',
      inputBorder: '#262626',
      userBubble: '#2d2d2d',
      assistantBubble: '#111111',
      userText: '#f5f5f5',
      assistantText: '#e5e5e5',
      suggestedText: '#a3a3a3',
      chatButtonBg: '#111111',
      chatButtonHover: '#1f1f1f',
      iconColor: '#ffffff',
      iconBorderColor: '#111111',
      buttonBorderColor: 'transparent',
      iconName: 'MessageSquare'
    }
  },

  // Colorful Themes
  sapphire: {
    name: 'Sapphire',
    colors: {
      primary: '#2563eb',
      secondary: '#3b82f6',
      background: '#f8fafc',
      textPrimary: '#102a43',
      textSecondary: '#1e3a5f',
      textInverse: '#ffffff',
      inputBackground: '#e6f2ff',
      inputBorder: '#90cdf4',
      userBubble: '#3b82f6',
      assistantBubble: '#e6f2ff',
      userText: '#ffffff',
      assistantText: '#102a43',
      suggestedText: '#1e3a5f',
      chatButtonBg: '#2563eb',
      chatButtonHover: '#1d4ed8',
      iconColor: '#ffffff',
      iconBorderColor: '#2563eb',
      buttonBorderColor: 'transparent',
      iconName: 'MessageSquare'
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
