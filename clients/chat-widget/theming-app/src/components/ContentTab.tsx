import React from 'react';
import type { WidgetConfig } from '../types/widget.types';
import { FormInput } from './FormInput';
import { FormTextarea } from './FormTextarea';
import { SuggestedQuestionsManager } from './SuggestedQuestionsManager';

interface ContentTabProps {
  widgetConfig: WidgetConfig;
  onUpdateHeaderTitle: (title: string) => void;
  onUpdateWelcomeTitle: (title: string) => void;
  onUpdateWelcomeDescription: (description: string) => void;
  onUpdateSuggestedQuestion: (index: number, field: 'text' | 'query', value: string) => void;
  onAddSuggestedQuestion: () => void;
  onRemoveSuggestedQuestion: (index: number) => void;
  onUpdateMaxQuestionLength: (maxLength: number) => void;
  onUpdateMaxQueryLength: (maxLength: number) => void;
}

export const ContentTab: React.FC<ContentTabProps> = ({
  widgetConfig,
  onUpdateHeaderTitle,
  onUpdateWelcomeTitle,
  onUpdateWelcomeDescription,
  onUpdateSuggestedQuestion,
  onAddSuggestedQuestion,
  onRemoveSuggestedQuestion,
  onUpdateMaxQuestionLength,
  onUpdateMaxQueryLength
}) => {
  return (
    <div className="space-y-6">
      {/* Header Configuration */}
      <FormInput
        label="Widget Header"
        value={widgetConfig.header.title}
        onChange={onUpdateHeaderTitle}
        placeholder="Widget title"
        maxLength={50}
        showCharacterCount={true}
      />

      {/* Welcome Message */}
      <div>
        <h3 className="text-sm font-medium text-gray-900 mb-3">Welcome Message</h3>
        <div className="space-y-3">
          <FormInput
            label="Welcome Title"
            value={widgetConfig.welcome.title}
            onChange={onUpdateWelcomeTitle}
            placeholder="Welcome title"
            maxLength={25}
            showCharacterCount={true}
          />
          <FormTextarea
            label="Welcome Description"
            value={widgetConfig.welcome.description}
            onChange={onUpdateWelcomeDescription}
            placeholder="Welcome description"
            rows={3}
            maxLength={200}
            showCharacterCount={true}
          />
        </div>
      </div>

      {/* Suggested Questions */}
      <SuggestedQuestionsManager
        questions={widgetConfig.suggestedQuestions}
        maxQuestionLength={widgetConfig.maxSuggestedQuestionLength}
        maxQueryLength={widgetConfig.maxSuggestedQuestionQueryLength}
        onUpdateQuestion={onUpdateSuggestedQuestion}
        onAddQuestion={onAddSuggestedQuestion}
        onRemoveQuestion={onRemoveSuggestedQuestion}
      />

      {/* Length Limits */}
      <div>
        <h3 className="text-sm font-medium text-gray-900 mb-3">Character Limits</h3>
        <div className="space-y-3">
          <FormInput
            label="Max Question Display Length"
            type="number"
            value={widgetConfig.maxSuggestedQuestionLength}
            onChange={(value) => {
              if (value === '') {
                onUpdateMaxQuestionLength(50);
              } else {
                const num = parseInt(value);
                if (!isNaN(num)) {
                  if (num < 10) {
                    onUpdateMaxQuestionLength(10);
                  } else if (num > 200) {
                    onUpdateMaxQuestionLength(200);
                  } else {
                    onUpdateMaxQuestionLength(num);
                  }
                }
              }
            }}
            min={10}
            max={200}
            maxLength={3}
          />
          <FormInput
            label="Max Query Length"
            type="number"
            value={widgetConfig.maxSuggestedQuestionQueryLength}
            onChange={(value) => {
              if (value === '') {
                onUpdateMaxQueryLength(200);
              } else {
                const num = parseInt(value);
                if (!isNaN(num)) {
                  if (num < 50) {
                    onUpdateMaxQueryLength(50);
                  } else if (num > 1000) {
                    onUpdateMaxQueryLength(1000);
                  } else {
                    onUpdateMaxQueryLength(num);
                  }
                }
              }
            }}
            min={50}
            max={1000}
            maxLength={4}
          />
        </div>
      </div>
    </div>
  );
};