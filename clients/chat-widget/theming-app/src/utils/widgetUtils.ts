import type { CustomColors, ThemeConfig, WidgetConfig, WidgetInitConfig } from '../types/widget.types';
import { WIDGET_CONFIG, isDebugEnabled } from './widget-config';

export const MAX_PROMPT_LENGTH = window.REACT_APP_MAX_PROMPT_LENGTH || 1000;

// Track if widget has been initialized to prevent duplicates
let widgetInitialized = false;

// Generate theme configuration from custom colors
export const generateThemeConfig = (customColors: CustomColors): ThemeConfig => ({
  primary: customColors.primary,
  secondary: customColors.secondary,
  background: customColors.background,
  text: {
    primary: customColors.textPrimary,
    secondary: customColors.textSecondary,
    inverse: customColors.textInverse
  },
  input: {
    background: customColors.inputBackground,
    border: customColors.inputBorder
  },
  message: {
    user: customColors.userBubble,
    assistant: customColors.assistantBubble,
    userText: customColors.userText
  },
  suggestedQuestions: {
    background: customColors.suggestedBackground,
    hoverBackground: customColors.suggestedHoverBackground,
    text: customColors.suggestedText
  },
  chatButton: {
    background: customColors.chatButtonBg,
    hoverBackground: customColors.chatButtonHover,
    iconColor: customColors.iconColor,
    iconBorderColor: customColors.iconBorderColor,
    borderColor: customColors.buttonBorderColor,
    iconName: customColors.iconName
  }
});

// Initialize widget
export const initializeWidget = (
  apiKey: string,
  apiEndpoint: string,
  widgetConfig: WidgetConfig,
  customColors: CustomColors
): void => {
  if (!window.initChatbotWidget) {
    console.error('Widget dependencies not loaded');
    return;
  }

  // Check if already initialized to prevent duplicates
  if (widgetInitialized) {
    if (isDebugEnabled()) {
      const isLocal = WIDGET_CONFIG.source === 'local';
      const style = isLocal ? 'color: #10b981;' : 'color: #3b82f6;';
      console.log(`%c🔄 Widget already initialized with ${isLocal ? '🔧 LOCAL BUILD' : '📦 NPM PACKAGE'} - skipping duplicate initialization`, style);
    }
    return;
  }

  // Enhanced console logging for initialization (only if debug enabled)
  if (isDebugEnabled()) {
    const isLocal = WIDGET_CONFIG.source === 'local';
    const style = isLocal ? 'color: #10b981; font-weight: bold;' : 'color: #3b82f6; font-weight: bold;';
    const prefix = isLocal ? '🔧 LOCAL BUILD' : '📦 NPM PACKAGE';
    
    console.log(`%c━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`, style);
    console.log(`%c🚀 INITIALIZING WIDGET WITH ${prefix}`, style);
    console.log(`%c━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`, style);
    console.log(`%c📋 Widget Configuration:`, style);
    console.log(`%c   Header: "${widgetConfig.header.title}"`, style);
    console.log(`%c   Welcome: "${widgetConfig.welcome.title}"`, style);
    console.log(`%c   Suggested Questions: ${widgetConfig.suggestedQuestions.length} items`, style);
    console.log(`%c   Primary Color: ${customColors.primary}`, style);
    console.log(`%c   Secondary Color: ${customColors.secondary}`, style);
    
    if (isLocal) {
      console.log(`%c💡 Testing with local widget build`, style);
    } else {
      console.log(`%c💡 Using NPM package v${WIDGET_CONFIG.npm.version}`, style);
    }
    
    console.log(`%c━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`, style);
  }

  // Create a container div for the widget
  const containerId = 'chatbot-widget-container';
  let container = document.getElementById(containerId);
  
  if (!container) {
    container = document.createElement('div');
    container.id = containerId;
    container.style.position = 'fixed';
    container.style.bottom = '20px';
    container.style.right = '20px';
    container.style.zIndex = '9999';
    document.body.appendChild(container);
  }

  const { systemPrompt, ...widgetConfigWithoutPrompt } = widgetConfig;
  
  // Log the API key being used (masked for security)
  if (isDebugEnabled()) {
    const maskedKey = apiKey ? `${apiKey.substring(0, 4)}...${apiKey.substring(Math.max(0, apiKey.length - 4))}` : 'undefined';
    console.log(`%c🔑 Initializing with API Key: ${maskedKey}`, 'color: #f59e0b; font-weight: bold;');
    console.log(`%c🌐 Initializing with API Endpoint: ${apiEndpoint}`, 'color: #f59e0b; font-weight: bold;');
  }
  
  const config: WidgetInitConfig = {
    apiUrl: apiEndpoint,
    apiKey: apiKey,
    containerSelector: `#${containerId}`,
    widgetConfig: {
      ...widgetConfigWithoutPrompt,
      theme: generateThemeConfig(customColors)
    }
  };

  try {
    window.initChatbotWidget(config);
    widgetInitialized = true; // Mark as initialized
    
    if (isDebugEnabled()) {
      const isLocal = WIDGET_CONFIG.source === 'local';
      const style = isLocal ? 'color: #10b981; font-weight: bold;' : 'color: #3b82f6; font-weight: bold;';
      const prefix = isLocal ? '🔧 LOCAL BUILD' : '📦 NPM PACKAGE';
      console.log(`%c✅ Widget initialized successfully with ${prefix}!`, style);
      console.log(`%c🎯 Widget ready for testing in bottom-right corner`, style);
      
      // Wait a moment then ensure the widget has access to update methods
      setTimeout(() => {
        if (window.ChatbotWidget) {
          const hasUpdateConfig = typeof window.ChatbotWidget.updateWidgetConfig === 'function';
          const hasSetApiKey = typeof window.ChatbotWidget.setApiKey === 'function';
          const hasSetApiUrl = typeof window.ChatbotWidget.setApiUrl === 'function';
          
          console.log(`%c🔧 Widget capabilities:`, style, {
            updateConfig: hasUpdateConfig,
            setApiKey: hasSetApiKey,
            setApiUrl: hasSetApiUrl
          });
        }
      }, 100);
    }
  } catch (error) {
    // Always show initialization errors, even in production
    const isLocal = WIDGET_CONFIG.source === 'local';
    const prefix = isLocal ? '🔧 LOCAL BUILD' : '📦 NPM PACKAGE';
    const errorStyle = 'color: #ef4444; font-weight: bold;';
    console.error(`%c❌ Failed to initialize widget with ${prefix}:`, errorStyle, error);
  }
};

// Update widget configuration
export const updateWidget = (
  widgetConfig: WidgetConfig,
  customColors: CustomColors
): void => {
  if (!window.ChatbotWidget) {
    if (isDebugEnabled()) {
      console.warn('⚠️ Widget not available for update');
    }
    return;
  }

  if (!window.ChatbotWidget.updateWidgetConfig) {
    if (isDebugEnabled()) {
      console.warn('⚠️ Widget does not support updateWidgetConfig method');
    }
    return;
  }

  const { systemPrompt, ...widgetConfigWithoutPrompt } = widgetConfig;
  
  try {
    // Update theme and configuration
    window.ChatbotWidget.updateWidgetConfig({
      ...widgetConfigWithoutPrompt,
      theme: generateThemeConfig(customColors)
    });
    
    // Optional: Log updates only if debug enabled
    if (isDebugEnabled()) {
      const isLocal = WIDGET_CONFIG.source === 'local';
      const style = isLocal ? 'color: #10b981;' : 'color: #3b82f6;';
      console.log(`%c🔄 Widget updated (${isLocal ? 'LOCAL' : 'NPM'})`, style);
      console.log(`%c   Updated config:`, style, {
        header: widgetConfigWithoutPrompt.header.title,
        welcome: widgetConfigWithoutPrompt.welcome.title,
        questionsCount: widgetConfigWithoutPrompt.suggestedQuestions.length,
        maxQuestionLength: widgetConfigWithoutPrompt.maxSuggestedQuestionLength,
        maxQueryLength: widgetConfigWithoutPrompt.maxSuggestedQuestionQueryLength
      });
    }
  } catch (error) {
    console.error('Failed to update widget:', error);
  }
};

// Reset initialization state (useful for development)
export const resetWidgetInitialization = (): void => {
  widgetInitialized = false;
  
  // Also clear any existing widget container to ensure a clean slate
  const container = document.getElementById('chatbot-widget-container');
  if (container) {
    container.remove();
  }
  
  if (isDebugEnabled()) {
    console.log('🔄 Widget initialization state reset and container cleared');
  }
};

// Generate session ID
export const generateSessionId = (): string => {
  return `session-${Math.random().toString(36).substr(2, 9)}-${Date.now()}`;
};