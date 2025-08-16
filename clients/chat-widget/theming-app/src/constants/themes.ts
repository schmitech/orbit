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
  suggestedBackground: '#eef2ff',  // indigo-50
  suggestedHoverBackground: '#e0e7ff',
  suggestedText: '#1d4ed8',
  chatButtonBg: '#ffffff',
  chatButtonHover: '#f8fafc',
  iconColor: '#2563eb',
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
    { text: 'What can you help me with?', query: 'What can you help me with today?' },
    { text: 'How do I get started?',      query: 'How do I get started with this service?' }
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
      suggestedBackground: '#eaf2ff',
      suggestedHoverBackground: '#dbeafe',
      suggestedText: '#1e3a8a',
      chatButtonBg: '#ffffff',
      chatButtonHover: '#f8fafc',
      iconColor: '#1d4ed8',
      iconBorderColor: '#93c5fd',
      buttonBorderColor: '#93c5fd',
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
      suggestedBackground: '#dbeafe',
      suggestedHoverBackground: '#bae6fd',
      suggestedText: '#0369a1',
      chatButtonBg: '#ffffff',
      chatButtonHover: '#f0f9ff',
      iconColor: '#0ea5e9',
      iconBorderColor: '#bae6fd',
      buttonBorderColor: '#bae6fd',
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
      suggestedBackground: '#e8f5ea',
      suggestedHoverBackground: '#bbf7d0',
      suggestedText: '#14532d',
      chatButtonBg: '#ffffff',
      chatButtonHover: '#f9fdf9',
      iconColor: '#166534',
      iconBorderColor: '#86efac',
      buttonBorderColor: '#86efac',
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
      suggestedBackground: '#2a265a',
      suggestedHoverBackground: '#4c1d95',
      suggestedText: '#d8b4fe',
      chatButtonBg: '#2a265a',
      chatButtonHover: '#4c1d95',
      iconColor: '#a78bfa',
      iconBorderColor: '#4c1d95',
      buttonBorderColor: '#4c1d95',
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
      suggestedBackground: '#ede7f3',
      suggestedHoverBackground: '#e0d8e9',
      suggestedText: '#6b5d7a',
      chatButtonBg: '#ffffff',
      chatButtonHover: '#fbfaff',
      iconColor: '#6b40b5',
      iconBorderColor: '#d4c9e0',
      buttonBorderColor: '#d4c9e0',
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
      suggestedBackground: '#1e293b',
      suggestedHoverBackground: '#334155',
      suggestedText: '#93c5fd',
      chatButtonBg: '#1e293b',
      chatButtonHover: '#334155',
      iconColor: '#60a5fa',
      iconBorderColor: '#334155',
      buttonBorderColor: '#334155',
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
      suggestedBackground: '#1f2937',
      suggestedHoverBackground: '#4b5563',
      suggestedText: '#d1d5db',
      chatButtonBg: '#1f2937',
      chatButtonHover: '#374151',
      iconColor: '#9ca3af',
      iconBorderColor: '#374151',
      buttonBorderColor: '#374151',
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
      suggestedBackground: '#141414',
      suggestedHoverBackground: '#262626',
      suggestedText: '#a3a3a3',
      chatButtonBg: '#141414',
      chatButtonHover: '#262626',
      iconColor: '#737373',
      iconBorderColor: '#262626',
      buttonBorderColor: '#262626',
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
      suggestedBackground: '#dbeafe',
      suggestedHoverBackground: '#bfdbfe',
      suggestedText: '#1e3a5f',
      chatButtonBg: '#ffffff',
      chatButtonHover: '#f8fafc',
      iconColor: '#2563eb',
      iconBorderColor: '#90cdf4',
      buttonBorderColor: '#90cdf4',
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
