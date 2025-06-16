import type { WidgetConfig, CustomColors } from '../types/widget.types';
import { generateThemeConfig } from './widgetUtils';

// Generate implementation code (without system prompt)
export const generateImplementationCode = (
  apiKey: string,
  widgetConfig: WidgetConfig,
  customColors: CustomColors
): string => {
  const { systemPrompt, ...widgetConfigWithoutPrompt } = widgetConfig;
  
  const config = {
    apiUrl: 'http://localhost:3000',
    apiKey: apiKey,
    widgetConfig: {
      ...widgetConfigWithoutPrompt,
      theme: generateThemeConfig(customColors)
    }
  };

  return `<!-- Chatbot Widget Implementation -->
<script src="https://unpkg.com/@schmitech/chatbot-widget@latest/dist/chatbot-widget.bundle.js"></script>

<script>
  window.addEventListener('load', function() {
    window.initChatbotWidget(${JSON.stringify(config, null, 2)});
  });
</script>`;
};

// Copy code to clipboard
export const copyCodeToClipboard = async (code: string): Promise<boolean> => {
  try {
    await navigator.clipboard.writeText(code);
    return true;
  } catch (err) {
    console.error('Failed to copy code:', err);
    return false;
  }
};