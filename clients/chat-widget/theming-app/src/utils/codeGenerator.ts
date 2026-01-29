import type { WidgetConfig, CustomColors } from '../types/widget.types';
import { generateThemeConfig } from './widgetUtils';
import { WIDGET_CONFIG } from './widget-config';

// Generate implementation code (without system prompt)
export const generateImplementationCode = (
  apiKey: string,
  apiEndpoint: string,
  widgetConfig: WidgetConfig,
  customColors: CustomColors
): string => {
  const { systemPrompt, ...widgetConfigWithoutPrompt } = widgetConfig;
  
  const config = {
    apiUrl: apiEndpoint,
    apiKey: apiKey,
    widgetConfig: {
      ...widgetConfigWithoutPrompt,
      theme: generateThemeConfig(customColors)
    }
  };

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Chatbot Widget</title>
  <link rel="stylesheet" href="https://unpkg.com/@schmitech/chatbot-widget@${WIDGET_CONFIG.npm.version}/dist/chatbot-widget.css">
</head>
<body>
  <div id="chatbot-widget"></div>
  <!-- Load Chatbot Widget Script -->
  <!-- Widget dependencies -->
  <script src="https://unpkg.com/react@19/umd/react.production.min.js" crossorigin></script>
  <script src="https://unpkg.com/react-dom@19/umd/react-dom.production.min.js" crossorigin></script>
  <script src="https://unpkg.com/@schmitech/chatbot-widget@${WIDGET_CONFIG.npm.version}/dist/chatbot-widget.umd.js" crossorigin></script>

  <!-- Initialize Widget -->
  <script>
    window.addEventListener('load', function() {
      // Ensure the container exists
      if (!document.getElementById('chatbot-widget')) {
        const container = document.createElement('div');
        container.id = 'chatbot-widget';
        document.body.appendChild(container);
      }
      
      window.initChatbotWidget(${JSON.stringify(config, null, 2)});
    });
  </script>
</body>
</html>`;
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