import React, { useState } from 'react';
import { Copy, Check } from 'lucide-react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { github } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import type { WidgetConfig, CustomColors } from '../types/widget.types';
import { generateThemeConfig } from '../utils/widgetUtils';
import { WIDGET_CONFIG } from '../utils/widget-config';

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
    // Generate a JavaScript bundle that can be imported
    
    const { systemPrompt, ...widgetConfigWithoutPrompt } = widgetConfig;
    const minifiedConfig = {
      apiUrl: apiEndpoint,
      apiKey: apiKey,
      widgetConfig: {
        ...widgetConfigWithoutPrompt,
        theme: generateThemeConfig(customColors)
      }
    };
    
    // Generate a self-contained JavaScript bundle
    const jsBundle = `(function(){
  // Load dependencies
  function loadScript(src, onload) {
    var script = document.createElement('script');
    script.src = src;
    script.crossOrigin = 'anonymous';
    if (onload) script.onload = onload;
    document.head.appendChild(script);
  }
  
  function loadStyle(href) {
    var link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    document.head.appendChild(link);
  }
  
  // Initialize the widget
  function initWidget() {
    // Ensure container exists
    if (!document.getElementById('chatbot-widget')) {
      var container = document.createElement('div');
      container.id = 'chatbot-widget';
      document.body.appendChild(container);
    }
    
    // Initialize with config
    window.initChatbotWidget(${JSON.stringify(minifiedConfig)});
  }
  
  // Load resources in sequence
  window.addEventListener('DOMContentLoaded', function() {
    // Load CSS
    loadStyle('https://unpkg.com/@schmitech/chatbot-widget@${WIDGET_CONFIG.npm.version}/dist/chatbot-widget.css');
    
    // Load React
    loadScript('https://unpkg.com/react@19/umd/react.production.min.js', function() {
      // Load ReactDOM
      loadScript('https://unpkg.com/react-dom@19/umd/react-dom.production.min.js', function() {
        // Load Widget
        loadScript('https://unpkg.com/@schmitech/chatbot-widget@${WIDGET_CONFIG.npm.version}/dist/chatbot-widget.umd.js', function() {
          // Initialize widget after all dependencies are loaded
          initWidget();
        });
      });
    });
  });
})();`;
    
    return jsBundle;
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
        <h3 className="text-sm font-medium text-gray-900">
          {activeSubTab === 'expanded' 
            ? 'Example of using the widget in your website:' 
            : 'Importable JavaScript bundle:'}
        </h3>
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
            HTML
          </button>
          <button
            onClick={() => setActiveSubTab('minified')}
            className={`px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
              activeSubTab === 'minified'
                ? 'bg-blue-100 text-blue-700 border border-blue-200'
                : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
            }`}
          >
            JavaScript
          </button>
        </div>
        <button
          onClick={() => {
            const isJS = activeSubTab === 'minified';
            const blob = new Blob([formattedCode], { type: isJS ? 'text/javascript' : 'text/html' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = isJS ? 'chatbot-widget.js' : 'chatbot-widget.html';
            document.body.appendChild(a);
            a.click();
            setTimeout(() => {
              document.body.removeChild(a);
              URL.revokeObjectURL(url);
            }, 100);
          }}
          className="ml-auto px-3 py-2 text-sm font-medium rounded-lg bg-green-100 text-green-800 border border-green-200 hover:bg-green-200 transition-colors"
        >
          Download {activeSubTab === 'minified' ? 'JS' : 'HTML'}
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
          language={activeSubTab === 'minified' ? 'javascript' : 'html'}
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
            {activeSubTab === 'expanded' ? 'HTML Version' : 'JavaScript Bundle'}
          </h4>
          <p className="text-xs text-gray-600">
            {activeSubTab === 'expanded' 
              ? 'Complete HTML file with proper indentation and spacing. Best for development and debugging.'
              : 'Self-contained JavaScript bundle that can be imported with a single <script> tag. Handles all dependencies automatically.'
            }
          </p>
        </div>

        {/* Implementation notes */}
        <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <h4 className="text-sm font-medium text-blue-900 mb-2">Implementation Notes</h4>
          <ul className="text-xs text-blue-700 space-y-1 list-disc list-inside">
            <li>Replace <code className="bg-blue-100 px-1 rounded">default-key</code> with your actual API key</li>
            <li>Replace <code className="bg-blue-100 px-1 rounded">http://localhost:3000</code> with your production API endpoint</li>
            <li>{activeSubTab === 'expanded' 
              ? 'This generates a complete HTML file that you can save and open directly in a browser' 
              : 'Add this script to your website with: <script src="chatbot-widget.js"></script>'}</li>
            <li>The system prompt is configured separately via your API dashboard</li>
            <li>Session ID is automatically generated for each user session</li>
            <li>For production, use HTTPS endpoints and ensure CORS is properly configured</li>
          </ul>
        </div>
      </div>
    </div>
  );
};