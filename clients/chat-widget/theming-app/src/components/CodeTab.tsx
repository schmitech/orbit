import React, { useState } from 'react';
import { Copy, Check } from 'lucide-react';
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

  const currentCode = activeSubTab === 'expanded' 
    ? generateCode(widgetConfig, customColors)
    : generateMinifiedCode(widgetConfig, customColors);

  const handleCopyCode = async () => {
    try {
      await navigator.clipboard.writeText(currentCode);
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
        <Button
          onClick={handleCopyCode}
          icon={localCopied ? Check : Copy}
          size="sm"
        >
          {localCopied ? 'Copied!' : 'Copy Code'}
        </Button>
      </div>

      {/* Sub-tabs */}
      <div className="flex space-x-1 mb-4">
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
      
      <div className="relative rounded-lg overflow-hidden">
        <pre className="bg-gray-900 text-gray-100 p-4 overflow-x-auto">
          <code className="language-html text-sm">
            {currentCode}
          </code>
        </pre>
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