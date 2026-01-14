import { useState } from 'react';
import { generateImplementationCode, copyCodeToClipboard } from '../utils/codeGenerator';
import type { WidgetConfig, CustomColors } from '../types/widget.types';
import { WIDGET_CONFIG } from '../utils/widget-config';

export const useApiConfig = () => {
  const resolveInitialApiKey = (): string => {
    if (typeof window !== 'undefined' && window.CHATBOT_API_KEY) {
      return window.CHATBOT_API_KEY;
    }
    return 'default-key';
  };

  const resolveInitialApiEndpoint = (): string => {
    if (typeof window !== 'undefined' && window.CHATBOT_API_URL) {
      return window.CHATBOT_API_URL;
    }
    return WIDGET_CONFIG.defaultApiEndpoint;
  };

  const [apiKey, setApiKey] = useState(resolveInitialApiKey);
  const [apiEndpoint, setApiEndpoint] = useState(resolveInitialApiEndpoint);

  // Generate implementation code
  const generateCode = (widgetConfig: WidgetConfig, customColors: CustomColors) => {
    return generateImplementationCode(apiKey, apiEndpoint, widgetConfig, customColors);
  };

  // Copy code to clipboard
  const copyToClipboard = async (widgetConfig: WidgetConfig, customColors: CustomColors) => {
    const code = generateCode(widgetConfig, customColors);
    const success = await copyCodeToClipboard(code);
    return success;
  };

  // Validate API key (basic validation)
  const isValidApiKey = (key: string) => {
    return key && key.length > 0 && key !== 'default-key';
  };

  // Validate API endpoint (basic validation)
  const isValidApiEndpoint = (endpoint: string) => {
    return endpoint && endpoint.length > 0 && endpoint !== WIDGET_CONFIG.defaultApiEndpoint;
  };

  return {
    apiKey,
    setApiKey,
    apiEndpoint,
    setApiEndpoint,
    generateCode,
    copyToClipboard,
    isValidApiKey,
    isValidApiEndpoint
  };
};
