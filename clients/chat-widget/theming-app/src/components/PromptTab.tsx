import React from 'react';
import type { WidgetConfig } from '../types/widget.types';
import { PROMPT_EXAMPLES } from '../constants/themes';
import { MAX_PROMPT_LENGTH } from '../utils/widgetUtils';
import { FormTextarea } from './FormTextarea';
import { Button } from './Button';

interface PromptTabProps {
  widgetConfig: WidgetConfig;
  onUpdateSystemPrompt: (prompt: string) => void;
}

export const PromptTab: React.FC<PromptTabProps> = ({
  widgetConfig,
  onUpdateSystemPrompt
}) => {
  const handlePromptChange = (value: string) => {
    if (value.length <= MAX_PROMPT_LENGTH) {
      onUpdateSystemPrompt(value);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <FormTextarea
          label="System Prompt"
          value={widgetConfig.systemPrompt || ''}
          onChange={handlePromptChange}
          placeholder="You are a helpful, friendly assistant that answers questions about our products and services..."
          rows={12}
          maxLength={MAX_PROMPT_LENGTH}
          showCharacterCount={true}
          textareaClassName="font-mono text-sm"
        />
        <p className="text-xs text-gray-500 mt-1">
          Define how your AI assistant should behave and respond to users
        </p>
        
        <div className="mt-4 space-y-3">
          <h4 className="text-sm font-medium text-gray-900">Prompt Examples</h4>
          <div className="space-y-2">
            {Object.entries(PROMPT_EXAMPLES).map(([key, example]) => (
              <Button
                key={key}
                onClick={() => onUpdateSystemPrompt(example.prompt)}
                variant="outline"
                className="w-full text-left justify-start p-3 h-auto"
              >
                <div className="text-left w-full">
                  <div className="font-medium text-gray-900 text-left">{example.title}</div>
                  <p className="text-xs text-gray-500 mt-1 text-left">{example.description}</p>
                </div>
              </Button>
            ))}
          </div>
        </div>
        
        <div className="mt-4 p-4 bg-amber-50 border border-amber-200 rounded-lg">
          <h4 className="text-sm font-medium text-amber-900 mb-2">Best Practices</h4>
          <ul className="text-xs text-amber-700 space-y-1 list-disc list-inside">
            <li>Be specific about your company, products, or services</li>
            <li>Define the tone and personality (professional, casual, friendly)</li>
            <li>Set boundaries on what the assistant should and shouldn't discuss</li>
            <li>Include instructions for handling edge cases or difficult questions</li>
            <li>Mention any specific knowledge or context the assistant should have</li>
          </ul>
        </div>
        
        <div className="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <p className="text-xs text-blue-700">
            <strong>Note:</strong> The system prompt is tied to your API key and managed separately from the widget configuration. 
            Changes here will be applied to your chatbot when you save the project.
          </p>
        </div>
      </div>
    </div>
  );
};