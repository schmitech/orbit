import React, { useState } from 'react';
import { Copy, Check } from 'lucide-react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { github } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import prettier from 'prettier/standalone';
import parserBabel from 'prettier/parser-babel';
import parserHtml from 'prettier/parser-html';
import type { WidgetConfig, CustomColors } from '../types/widget.types';
import { Button } from './Button';

interface CodeTabProps {
  widgetConfig: WidgetConfig;
  customColors: CustomColors;
  copied: boolean;
  generateCode: (widgetConfig: WidgetConfig, customColors: CustomColors) => string;
  onCopyCode: () => void;
}

export const CodeTab: React.FC<CodeTabProps> = ({
  widgetConfig,
  customColors,
  generateCode,
  onCopyCode
}) => {
  const [activeSubTab, setActiveSubTab] = useState<'expanded' | 'minified'>('expanded');
  const [localCopied, setLocalCopied] = useState(false);

  const generateMinifiedCode = (widgetConfig: WidgetConfig, customColors: CustomColors): string => {
    const fullCode = generateCode(widgetConfig, customColors);
    // Basic minification: remove extra whitespace and line breaks
    return fullCode
      .replace(/\n\s*/g, ' ')
      .replace(/\s+/g, ' ')
      .replace(/>\s+</g, '><')
      .trim();
  };

  // Format code with Prettier for the expanded tab
  let formattedCode = '';
  if (activeSubTab === 'expanded') {
    const rawCode = generateCode(widgetConfig, customColors);
    let parser = 'babel';
    let plugin: any = parserBabel;
    if (/^\s*<\/?[a-zA-Z]/.test(rawCode)) {
      parser = 'html';
      plugin = parserHtml;
    }
    try {
      if (plugin) {
        const pretty = prettier.format(rawCode, {
          parser,
          plugins: [plugin],
          semi: true,
          singleQuote: true,
        });
        formattedCode = typeof pretty === 'string' ? pretty : rawCode;
      } else {
        formattedCode = rawCode;
      }
    } catch (e) {
      formattedCode = rawCode;
    }
  } else {
    formattedCode = generateMinifiedCode(widgetConfig, customColors);
  }
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
            // Add import instructions as a comment
            const importInstructions =
              '// To use this widget, include the following script in your HTML:\n' +
              "// <script src=\"https://unpkg.com/@schmitech/chatbot-widget@latest/dist/chatbot-widget.bundle.js\"></script>\n" +
              '// Then use the code below to initialize the widget:\n\n';
            const fileContent = importInstructions + formattedCode;
            const blob = new Blob([fileContent], { type: 'text/javascript' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'chatbot-widget-setup.js';
            document.body.appendChild(a);
            a.click();
            setTimeout(() => {
              document.body.removeChild(a);
              URL.revokeObjectURL(url);
            }, 100);
          }}
          className="ml-auto px-3 py-2 text-sm font-medium rounded-lg bg-green-100 text-green-800 border border-green-200 hover:bg-green-200 transition-colors"
        >
          Download JS
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
          language="javascript"
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
            <li>Replace <code className="bg-blue-100 px-1 rounded">your-api-key</code> with your actual API key</li>
            <li>Replace <code className="bg-blue-100 px-1 rounded">https://your-api-url.com</code> with your API endpoint</li>
            <li>The system prompt is configured separately via your API dashboard</li>
            <li>Session ID is automatically generated for each user session</li>
          </ul>
        </div>
      </div>
    </div>
  );
};