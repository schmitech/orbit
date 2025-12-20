import type { CustomColors, Theme, WidgetConfig } from '../types/widget.types';

export const defaultCustomColors: CustomColors = {
  // Refined, modern default palette (name preserved)
  primary: '#2563eb',              // cobalt
  secondary: '#7c3aed',            // vivid violet accent
  questionsBackground: '#ffffff',
  textPrimary: '#111827',          // darker for title
  textSecondary: '#6b7280',        // lighter gray for description
  textInverse: '#ffffff',
  inputBackground: '#ffffff',      // slate-50
  inputBorder: '#e5e7eb',          // gray-200
  userBubble: '#2563eb',
  assistantBubble: '#f8fafc',
  userText: '#ffffff',
  assistantText: '#374151',
  suggestedText: '#2563eb',        // blue for suggested questions
  highlightedBackground: '#fef3c7', // light yellow for highlighted state
  chatButtonBg: '#2563eb',
  chatButtonHover: '#1d4ed8',
  iconColor: '#ffffff',
  iconBorderColor: '#2563eb',
  buttonBorderColor: '#2563eb',
  iconName: 'MessageSquare'
};

export const defaultWidgetConfig: WidgetConfig = {
  header: {
    title: 'My Custom AI Assistant'
  },
  welcome: {
    title: '👋 How may I help you today?',
    description: 'I\'m your AI assistant, ready to help with any questions you might have.'
  },
  suggestedQuestions: [
    {
      text: '👋 Introduce yourself',
      query: 'Hello! Please introduce yourself and tell me what you can help with.'
    },
    {
      text: '💡 Explain quantum computing',
      query: 'Explain quantum computing in simple terms.'
    },
    {
      text: '🍳 Give me a recipe',
      query: 'What is a quick and easy pasta recipe?'
    },
    {
      text: '🧠 Tell me a fun fact',
      query: 'Tell me a surprising fun fact I probably don\'t know.'
    },
    {
      text: '📝 Write a haiku',
      query: 'Write a haiku about technology.'
    }
  ],
  maxSuggestedQuestionLength: 120,
  maxSuggestedQuestionQueryLength: 200,
  icon: 'MessageSquare'
};

export const themes: Record<string, Theme> = {
  nebula: {
    name: 'Nebula',
    colors: {
      primary: '#1d4ed8',                 // cobalt
      secondary: '#3b82f6',               // blue-500 - better contrast for send button
      questionsBackground: '#ffffff',              // soft gray-blue
      textPrimary: '#111827',             // dark for title
      textSecondary: '#475569',            // slate-600 - darker gray for better contrast
      textInverse: '#ffffff',
      inputBackground: '#ffffff',
      inputBorder: '#93c5fd',
      userBubble: '#1d4ed8',
      assistantBubble: '#e0f2fe',
      userText: '#ffffff',
      assistantText: '#334155',
      suggestedText: '#1d4ed8',            // blue for questions
      highlightedBackground: '#dbeafe', // light blue for highlighted state
      chatButtonBg: '#1d4ed8',
      chatButtonHover: '#1e3a8a',
      iconColor: '#ffffff',
      iconBorderColor: '#1d4ed8',
      buttonBorderColor: '#1d4ed8',
      iconName: 'MessageSquare'
    }
  },

  ocean: {
    name: 'Ocean',
    colors: {
      primary: '#0284c7',
      secondary: '#0ea5e9',               // sky-500 - better contrast for send button
      questionsBackground: '#ffffff',
      textPrimary: '#0f172a',
      textSecondary: '#475569',            // slate-600 - darker for better contrast
      textInverse: '#ffffff',
      inputBackground: '#ffffff',
      inputBorder: '#7dd3fc',
      userBubble: '#0284c7',
      assistantBubble: '#e0f2fe',
      userText: '#ffffff',
      assistantText: '#374151',
      suggestedText: '#0284c7',            // ocean blue for questions
      highlightedBackground: '#e0f2fe', // light cyan for highlighted state
      chatButtonBg: '#0284c7',
      chatButtonHover: '#0369a1',
      iconColor: '#ffffff',
      iconBorderColor: '#0284c7',
      buttonBorderColor: '#0284c7',
      iconName: 'MessageSquare'
    }
  },

  // Replaced "Sage" with deeper greens; keeping key but renaming display
  sage: {
    name: 'Evergreen',
    colors: {
      primary: '#14532d',                 // deep forest green
      secondary: '#16a34a',               // green-600 - better contrast for send button
      questionsBackground: '#f0fdf4',              // light green-tinted
      textPrimary: '#111827',             // dark for title
      textSecondary: '#4b5563',            // gray-600 - darker for better contrast
      textInverse: '#ffffff',
      inputBackground: '#ffffff',
      inputBorder: '#86efac',
      userBubble: '#166534',
      assistantBubble: '#dcfce7',
      userText: '#ffffff',
      assistantText: '#374151',
      suggestedText: '#166534',            // green for questions
      highlightedBackground: '#dcfce7', // light green for highlighted state
      chatButtonBg: '#166534',
      chatButtonHover: '#14532d',
      iconColor: '#ffffff',
      iconBorderColor: '#166534',
      buttonBorderColor: '#166534',
      iconName: 'MessageSquare'
    }
  },

  // Semi-Dark Themes
  twilight: {
    name: 'Twilight',
    colors: {
      primary: '#0d9488',
      secondary: '#2dd4bf',
      questionsBackground: '#0b1f24',
      textPrimary: '#ccfbf1',
      textSecondary: '#99f6e4',
      textInverse: '#ffffff',
      inputBackground: '#11343c',
      inputBorder: '#155e75',
      userBubble: '#0d9488',
      assistantBubble: '#11343c',
      userText: '#ffffff',
      assistantText: '#ccfbf1',
      suggestedText: '#14b8a6',
      highlightedBackground: '#1e4e4b', // lighter teal for highlighted state
      chatButtonBg: '#0d9488',
      chatButtonHover: '#155e75',
      iconColor: '#ffffff',
      iconBorderColor: '#0d9488',
      buttonBorderColor: '#0d9488',
      iconName: 'MessageSquare'
    }
  },
  lavender: {
    name: 'Lavender',
    colors: {
      primary: '#a21caf',
      secondary: '#e879f9',
      questionsBackground: '#fff7fb',
      textPrimary: '#4a044e',
      textSecondary: '#86198f',
      textInverse: '#ffffff',
      inputBackground: '#ffffff',
      inputBorder: '#f5d0fe',
      userBubble: '#a21caf',
      assistantBubble: '#fce7f3',
      userText: '#ffffff',
      assistantText: '#374151',
      suggestedText: '#a21caf',
      highlightedBackground: '#fae8ff', // light lavender for highlighted state
      chatButtonBg: '#a21caf',
      chatButtonHover: '#86198f',
      iconColor: '#ffffff',
      iconBorderColor: '#a21caf',
      buttonBorderColor: '#a21caf',
      iconName: 'MessageSquare'
    }
  },

  midnight: {
    name: 'Midnight',
    colors: {
      primary: '#1e40af',
      secondary: '#6366f1',
      questionsBackground: '#0f172a',
      textPrimary: '#e0e7ff',
      textSecondary: '#a5b4fc',
      textInverse: '#ffffff',
      inputBackground: '#111827',
      inputBorder: '#1f2937',
      userBubble: '#6366f1',
      assistantBubble: '#111827',
      userText: '#ffffff',
      assistantText: '#e0e7ff',
      suggestedText: '#c7d2fe',
      highlightedBackground: '#ddcf3c', // lighter indigo for highlighted state
      chatButtonBg: '#1e40af',
      chatButtonHover: '#1e3a8a',
      iconColor: '#ffffff',
      iconBorderColor: '#1e40af',
      buttonBorderColor: '#1e40af',
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
      questionsBackground: '#111827',              // slate-900
      textPrimary: '#f3f4f6',
      textSecondary: '#9ca3af',            // slate-400 - lighter for better contrast
      textInverse: '#ffffff',
      inputBackground: '#1f2937',
      inputBorder: '#374151',
      userBubble: '#374151',
      assistantBubble: '#1f2937',
      userText: '#f3f4f6',
      assistantText: '#f3f4f6',
      suggestedText: '#d1d5db',
      highlightedBackground: '#ddcf3c', // lighter gray for highlighted state
      chatButtonBg: '#374151',
      chatButtonHover: '#4b5563',
      iconColor: '#ffffff',
      iconBorderColor: '#374151',
      buttonBorderColor: '#374151',
      iconName: 'MessageSquare'
    }
  },

  carbon: {
    name: 'Carbon',
    colors: {
      primary: '#111111',
      secondary: '#525252',               // neutral-600 - better contrast for send button
      questionsBackground: '#0a0a0a',
      textPrimary: '#e5e5e5',
      textSecondary: '#737373',            // neutral-500 - darker for better contrast
      textInverse: '#ffffff',
      inputBackground: '#141414',
      inputBorder: '#262626',
      userBubble: '#2d2d2d',
      assistantBubble: '#111111',
      userText: '#f5f5f5',
      assistantText: '#e5e5e5',
      suggestedText: '#a3a3a3',
      highlightedBackground: '#ddcf3c', // lighter charcoal for highlighted state
      chatButtonBg: '#111111',
      chatButtonHover: '#1f1f1f',
      iconColor: '#ffffff',
      iconBorderColor: '#111111',
      buttonBorderColor: '#111111',
      iconName: 'MessageSquare'
    }
  },

  // Colorful Themes
  sapphire: {
    name: 'Sapphire',
    colors: {
      primary: '#06b6d4',
      secondary: '#0891b2',
      questionsBackground: '#f0fdfa',
      textPrimary: '#0f766e',
      textSecondary: '#155e75',
      textInverse: '#ffffff',
      inputBackground: '#ffffff',
      inputBorder: '#a5f3fc',
      userBubble: '#06b6d4',
      assistantBubble: '#ecfeff',
      userText: '#ffffff',
      assistantText: '#0e7490',
      suggestedText: '#06b6d4',
      highlightedBackground: '#cffafe', // light cyan for highlighted state
      chatButtonBg: '#06b6d4',
      chatButtonHover: '#0891b2',
      iconColor: '#ffffff',
      iconBorderColor: '#06b6d4',
      buttonBorderColor: '#06b6d4',
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
