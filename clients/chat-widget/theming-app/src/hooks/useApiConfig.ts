import { useState } from 'react';
import { generateImplementationCode, copyCodeToClipboard } from '../utils/codeGenerator';
import type { WidgetConfig, CustomColors } from '../types/widget.types';

export const useApiConfig = () => {
  const [apiKey, setApiKey] = useState('demo-api-key');

  // Generate implementation code
  const generateCode = (widgetConfig: WidgetConfig, customColors: CustomColors) => {
    return generateImplementationCode(apiKey, widgetConfig, customColors);
  };

  // Copy code to clipboard
  const copyToClipboard = async (widgetConfig: WidgetConfig, customColors: CustomColors) => {
    const code = generateCode(widgetConfig, customColors);
    const success = await copyCodeToClipboard(code);
    return success;
  };

  // Validate API key (basic validation)
  const isValidApiKey = (key: string) => {
    return key && key.length > 0 && key !== 'demo-api-key';
  };

  return {
    apiKey,
    setApiKey,
    generateCode,
    copyToClipboard,
    isValidApiKey
  };
};