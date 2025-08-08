import React, { useState, useEffect } from 'react';
import type { WidgetConfig } from '../types/widget.types';
import { FormInput } from './FormInput';
import { FormTextarea } from './FormTextarea';
import { SuggestedQuestionsManager } from './SuggestedQuestionsManager';
import { getWidgetLimits, getLimitDescriptions } from '../utils/widget-limits';

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
  // Get widget limits
  const limits = getWidgetLimits();
  const limitDescriptions = getLimitDescriptions();

  // Local state for number inputs to allow free typing
  const [questionLengthInput, setQuestionLengthInput] = useState(String(widgetConfig.maxSuggestedQuestionLength));
  const [queryLengthInput, setQueryLengthInput] = useState(String(widgetConfig.maxSuggestedQuestionQueryLength));

  useEffect(() => {
    setQuestionLengthInput(String(widgetConfig.maxSuggestedQuestionLength));
  }, [widgetConfig.maxSuggestedQuestionLength]);

  useEffect(() => {
    setQueryLengthInput(String(widgetConfig.maxSuggestedQuestionQueryLength));
  }, [widgetConfig.maxSuggestedQuestionQueryLength]);

  // Handle question length change with validation
  const handleQuestionLengthChange = (value: string) => {
    setQuestionLengthInput(value);
  };

  const handleQuestionLengthBlur = () => {
    const raw = questionLengthInput;
    if (raw.trim() === '') {
      // Preserve previous value when empty/cleared
      setQuestionLengthInput(String(widgetConfig.maxSuggestedQuestionLength));
      return;
    }
    const value = parseInt(raw, 10);
    if (Number.isNaN(value)) {
      // Invalid input, revert to previous
      setQuestionLengthInput(String(widgetConfig.maxSuggestedQuestionLength));
      return;
    }
    const clampedValue = Math.max(
      limits.MIN_SUGGESTED_QUESTION_LENGTH,
      Math.min(value, limits.MAX_SUGGESTED_QUESTION_LENGTH_HARD)
    );
    onUpdateMaxQuestionLength(clampedValue);
    setQuestionLengthInput(String(clampedValue));
  };

  // Handle query length change with validation
  const handleQueryLengthChange = (value: string) => {
    setQueryLengthInput(value);
  };

  const handleQueryLengthBlur = () => {
    const raw = queryLengthInput;
    if (raw.trim() === '') {
      // Preserve previous value when empty/cleared
      setQueryLengthInput(String(widgetConfig.maxSuggestedQuestionQueryLength));
      return;
    }
    const value = parseInt(raw, 10);
    if (Number.isNaN(value)) {
      // Invalid input, revert to previous
      setQueryLengthInput(String(widgetConfig.maxSuggestedQuestionQueryLength));
      return;
    }
    
    // Store the user's intended value even if it needs clamping
    if (value >= limits.MIN_SUGGESTED_QUESTION_QUERY_LENGTH && value <= limits.MAX_SUGGESTED_QUESTION_QUERY_LENGTH_HARD) {
      // Valid value, use as-is
      onUpdateMaxQueryLength(value);
      setQueryLengthInput(String(value));
    } else {
      // Value is out of bounds, clamp it
      const clampedValue = Math.max(
        limits.MIN_SUGGESTED_QUESTION_QUERY_LENGTH,
        Math.min(value, limits.MAX_SUGGESTED_QUESTION_QUERY_LENGTH_HARD)
      );
      onUpdateMaxQueryLength(clampedValue);
      setQueryLengthInput(String(clampedValue));
    }
  };

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
            value={questionLengthInput}
            onChange={handleQuestionLengthChange}
            onBlur={handleQuestionLengthBlur}
            min={limits.MIN_SUGGESTED_QUESTION_LENGTH}
            max={limits.MAX_SUGGESTED_QUESTION_LENGTH_HARD}
            placeholder={`${limits.MIN_SUGGESTED_QUESTION_LENGTH}-${limits.MAX_SUGGESTED_QUESTION_LENGTH_HARD}`}
          />
          <p className="text-xs text-gray-500 mt-1">
            {limitDescriptions.questionLength.description} (Range: {limits.MIN_SUGGESTED_QUESTION_LENGTH}-{limits.MAX_SUGGESTED_QUESTION_LENGTH_HARD})
          </p>
          <FormInput
            label="Max Query Length"
            type="number"
            value={queryLengthInput}
            onChange={handleQueryLengthChange}
            onBlur={handleQueryLengthBlur}
            min={limits.MIN_SUGGESTED_QUESTION_QUERY_LENGTH}
            max={limits.MAX_SUGGESTED_QUESTION_QUERY_LENGTH_HARD}
            placeholder={`${limits.MIN_SUGGESTED_QUESTION_QUERY_LENGTH}-${limits.MAX_SUGGESTED_QUESTION_QUERY_LENGTH_HARD}`}
          />
          <p className="text-xs text-gray-500 mt-1">
            {limitDescriptions.queryLength.description} (Range: {limits.MIN_SUGGESTED_QUESTION_QUERY_LENGTH}-{limits.MAX_SUGGESTED_QUESTION_QUERY_LENGTH_HARD})
          </p>
        </div>
      </div>
    </div>
  );
};
