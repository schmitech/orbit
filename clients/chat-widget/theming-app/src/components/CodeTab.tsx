import React, { useState } from 'react';
import { Copy, Check } from 'lucide-react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { github } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import type { WidgetConfig, CustomColors } from '../types/widget.types';
import { generateThemeConfig } from '../utils/widgetUtils';

interface CodeTabProps {
  widgetConfig: WidgetConfig;
  customColors: CustomColors;
  copied: boolean;
  generateCode: (widgetConfig: WidgetConfig, customColors: CustomColors) => string;
  onCopyCode: () => void;
  apiKey: string;
  apiEndpoint: string;
}

export const CodeTab: React.FC<CodeTabProps> = ({
  widgetConfig,
  customColors,
  generateCode,
  onCopyCode,
  apiKey,
  apiEndpoint
}) => {
  const [activeSubTab, setActiveSubTab] = useState<'expanded' | 'minified'>('expanded');
  const [localCopied, setLocalCopied] = useState(false);

  const generateMinifiedCode = (widgetConfig: WidgetConfig, customColors: CustomColors): string => {
    // Simple and safe minification approach
    // Generate a minified version directly with compact JSON
    
    const { systemPrompt, ...widgetConfigWithoutPrompt } = widgetConfig;
    const minifiedConfig = {
      apiUrl: apiEndpoint,
      apiKey: apiKey,
      widgetConfig: {
        ...widgetConfigWithoutPrompt,
        theme: generateThemeConfig(customColors)
      }
    };
    
    // Generate a new minified HTML with compact JSON
    const minifiedHTML = `<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Chatbot Widget</title><link rel="stylesheet" href="https://unpkg.com/@schmitech/chatbot-widget@0.4.12/dist/chatbot-widget.css"></head><body><div id="chatbot-widget"></div><script src="https://unpkg.com/react@18/umd/react.production.min.js" crossorigin></script><script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js" crossorigin></script><script src="https://unpkg.com/@schmitech/chatbot-widget@0.4.12/dist/chatbot-widget.umd.js" crossorigin></script><script>window.addEventListener('load',function(){if(!document.getElementById('chatbot-widget')){const container=document.createElement('div');container.id='chatbot-widget';document.body.appendChild(container);}window.initChatbotWidget(${JSON.stringify(minifiedConfig)});});</script></body></html>`;
    
    return minifiedHTML;
  };

  // Get the formatted code based on active tab
  let formattedCode = '';
  if (activeSubTab === 'expanded') {
    // For expanded view, just use the generated code as-is
    // (it's already nicely formatted from the generator)
    formattedCode = generateCode(widgetConfig, customColors);
  } else {
    formattedCode = generateMinifiedCode(widgetConfig, customColors);
  }
  
  // Ensure formattedCode is always a string
  if (typeof formattedCode !== 'string') {
    formattedCode = '';
  }

  const handleCopyCode = async () => {
    try {
      await navigator.clipboard.writeText(formattedCode);
      setLocalCopied(true);
      setTimeout(() => setLocalCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy code:', err);
      // Fallback to the original method if clipboard API fails
      onCopyCode();
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-gray-900">Implementation Code</h3>
      </div>

      {/* Sub-tabs and Download Button */}
      <div className="flex items-center mb-4">
        <div className="flex space-x-1">
          <button
            onClick={() => setActiveSubTab('expanded')}
            className={`px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
              activeSubTab === 'expanded'
                ? 'bg-blue-100 text-blue-700 border border-blue-200'
                : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
            }`}
          >
            Expanded
          </button>
          <button
            onClick={() => setActiveSubTab('minified')}
            className={`px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
              activeSubTab === 'minified'
                ? 'bg-blue-100 text-blue-700 border border-blue-200'
                : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
            }`}
          >
            Minified
          </button>
        </div>
        <button
          onClick={() => {
            const blob = new Blob([formattedCode], { type: 'text/html' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'chatbot-widget.html';
            document.body.appendChild(a);
            a.click();
            setTimeout(() => {
              document.body.removeChild(a);
              URL.revokeObjectURL(url);
            }, 100);
          }}
          className="ml-auto px-3 py-2 text-sm font-medium rounded-lg bg-green-100 text-green-800 border border-green-200 hover:bg-green-200 transition-colors"
        >
          Download HTML
        </button>
      </div>
      
      <div className="relative rounded-lg overflow-hidden">
        {/* Copy icon overlay */}
        <button
          onClick={handleCopyCode}
          className="absolute top-2 right-2 z-10 p-1 bg-white/80 hover:bg-white rounded shadow transition-colors"
          title={localCopied ? 'Copied!' : 'Copy code'}
          style={{ lineHeight: 0 }}
        >
          {localCopied ? <Check className="w-5 h-5 text-green-600" /> : <Copy className="w-5 h-5 text-gray-600" />}
        </button>
        <SyntaxHighlighter
          key={activeSubTab}
          language="html"
          style={github}
          customStyle={{
            fontSize: '13px',
            lineHeight: '1.4',
            fontFamily: 'Mona Sans, Roboto Mono, ui-monospace, SFMono-Regular, SF Mono, Consolas, Liberation Mono, Menlo, monospace',
            margin: 0,
            borderRadius: '0.5rem',
            padding: '1rem'
          }}
          showLineNumbers={false}
          wrapLines={true}
        >
          {formattedCode}
        </SyntaxHighlighter>
      </div>

      <div className="mt-4 space-y-3">
        {/* Version-specific notes */}
        <div className="p-3 bg-gray-50 border border-gray-200 rounded-lg">
          <h4 className="text-sm font-medium text-gray-900 mb-2">
            {activeSubTab === 'expanded' ? 'Expanded Version' : 'Minified Version'}
          </h4>
          <p className="text-xs text-gray-600">
            {activeSubTab === 'expanded' 
              ? 'Human-readable format with proper indentation and spacing. Best for development and debugging.'
              : 'Compressed format with minimal whitespace. Optimized for production use to reduce file size.'
            }
          </p>
        </div>

        {/* Implementation notes */}
        <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <h4 className="text-sm font-medium text-blue-900 mb-2">Implementation Notes</h4>
          <ul className="text-xs text-blue-700 space-y-1 list-disc list-inside">
            <li>Replace <code className="bg-blue-100 px-1 rounded">demo-api-key</code> with your actual API key</li>
            <li>Replace <code className="bg-blue-100 px-1 rounded">http://localhost:3000</code> with your production API endpoint</li>
            <li>This generates a complete HTML file that you can save and open directly in a browser</li>
            <li>The system prompt is configured separately via your API dashboard</li>
            <li>Session ID is automatically generated for each user session</li>
            <li>For production, use HTTPS endpoints and ensure CORS is properly configured</li>
          </ul>
        </div>
      </div>
    </div>
  );
};