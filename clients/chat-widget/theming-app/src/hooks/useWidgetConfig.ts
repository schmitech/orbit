import { useState } from 'react';
import type { WidgetConfig } from '../types/widget.types';
import { defaultWidgetConfig } from '../constants/themes';

export const useWidgetConfig = () => {
  const [widgetConfig, setWidgetConfig] = useState<WidgetConfig>(defaultWidgetConfig);

  // Update suggested question
  const updateSuggestedQuestion = (index: number, field: 'text' | 'query', value: string) => {
    const questions = [...widgetConfig.suggestedQuestions];
    questions[index] = { ...questions[index], [field]: value };
    setWidgetConfig({ ...widgetConfig, suggestedQuestions: questions });
  };

  // Add suggested question
  const addSuggestedQuestion = () => {
    if (widgetConfig.suggestedQuestions.length < 5) {
      setWidgetConfig({
        ...widgetConfig,
        suggestedQuestions: [
          ...widgetConfig.suggestedQuestions,
          { text: "New question", query: "New query" }
        ]
      });
    }
  };

  // Remove suggested question
  const removeSuggestedQuestion = (index: number) => {
    const questions = widgetConfig.suggestedQuestions.filter((_: any, i: number) => i !== index);
    setWidgetConfig({ ...widgetConfig, suggestedQuestions: questions });
  };

  // Update header title
  const updateHeaderTitle = (title: string) => {
    setWidgetConfig({
      ...widgetConfig,
      header: { ...widgetConfig.header, title }
    });
  };

  // Update welcome message
  const updateWelcomeTitle = (title: string) => {
    setWidgetConfig({
      ...widgetConfig,
      welcome: { ...widgetConfig.welcome, title }
    });
  };

  const updateWelcomeDescription = (description: string) => {
    setWidgetConfig({
      ...widgetConfig,
      welcome: { ...widgetConfig.welcome, description }
    });
  };

  // Update system prompt
  const updateSystemPrompt = (systemPrompt: string) => {
    setWidgetConfig({
      ...widgetConfig,
      systemPrompt
    });
  };

  // Update icon
  const updateIcon = (icon: string) => {
    setWidgetConfig({
      ...widgetConfig,
      icon
    });
  };

  // Update character limits
  const updateMaxSuggestedQuestionLength = (maxLength: number) => {
    setWidgetConfig({
      ...widgetConfig,
      maxSuggestedQuestionLength: maxLength
    });
  };

  const updateMaxSuggestedQuestionQueryLength = (maxLength: number) => {
    setWidgetConfig({
      ...widgetConfig,
      maxSuggestedQuestionQueryLength: maxLength
    });
  };

  return {
    widgetConfig,
    setWidgetConfig,
    updateSuggestedQuestion,
    addSuggestedQuestion,
    removeSuggestedQuestion,
    updateHeaderTitle,
    updateWelcomeTitle,
    updateWelcomeDescription,
    updateSystemPrompt,
    updateIcon,
    updateMaxSuggestedQuestionLength,
    updateMaxSuggestedQuestionQueryLength
  };
};