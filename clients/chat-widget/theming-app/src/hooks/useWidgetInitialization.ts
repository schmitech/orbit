import { useState, useEffect, useRef } from 'react';
import type { WidgetConfig, CustomColors, TabType } from '../types/widget.types';
import { loadWidgetDependencies, loadPrism } from '../utils/dependencies';
import { initializeWidget, updateWidget, generateSessionId, resetWidgetInitialization } from '../utils/widgetUtils';
import { isDebugEnabled } from '../utils/widget-config';

interface UseWidgetInitializationProps {
  apiKey: string;
  apiEndpoint: string;
  widgetConfig: WidgetConfig;
  customColors: CustomColors;
  activeTab: TabType;
}

export const useWidgetInitialization = ({
  apiKey,
  apiEndpoint,
  widgetConfig,
  customColors,
  activeTab
}: UseWidgetInitializationProps) => {
  const [sessionId] = useState(generateSessionId());
  const [isLoading, setIsLoading] = useState(true);
  const [isInitialized, setIsInitialized] = useState(false);
  const widgetInitialized = useRef(false);
  const initializationAttempted = useRef(false);

  // Load dependencies and initialize widget
  useEffect(() => {
    // Prevent multiple initialization attempts
    if (initializationAttempted.current) return;
    initializationAttempted.current = true;

    const initializeDependencies = async () => {
      try {
        await Promise.all([
          loadWidgetDependencies(),
          loadPrism()
        ]);

        if (window.Prism) {
          window.Prism.highlightAll();
        }

        // Initialize widget after dependencies are loaded
        setTimeout(() => {
          handleInitializeWidget();
          setIsLoading(false);
        }, 500);
      } catch (error) {
        console.error('Failed to load dependencies:', error);
        setIsLoading(false);
      }
    };

    initializeDependencies();
  }, []);

  // Re-highlight code when tab changes to code
  useEffect(() => {
    if (activeTab === 'code' && window.Prism) {
      setTimeout(() => {
        window.Prism.highlightAll();
      }, 100);
    }
  }, [activeTab]);

  // Update widget when configuration changes
  useEffect(() => {
    if (widgetInitialized.current && window.ChatbotWidget) {
      handleUpdateWidget();
    }
  }, [customColors, widgetConfig.header, widgetConfig.welcome, widgetConfig.suggestedQuestions, widgetConfig.icon]);

  // Update API key when it changes
  useEffect(() => {
    if (widgetInitialized.current && window.ChatbotWidget?.setApiKey) {
      window.ChatbotWidget.setApiKey(apiKey);
    }
  }, [apiKey]);

  // Initialize widget
  const handleInitializeWidget = () => {
    // Double-check to prevent duplicate initialization
    if (widgetInitialized.current) {
      if (isDebugEnabled()) {
        console.log('🔄 Widget already initialized in hook - skipping');
      }
      return;
    }

    try {
      initializeWidget(apiKey, apiEndpoint, widgetConfig, customColors);
      widgetInitialized.current = true;
      setIsInitialized(true);
    } catch (error) {
      console.error('Failed to initialize widget:', error);
    }
  };

  // Update widget
  const handleUpdateWidget = () => {
    try {
      updateWidget(widgetConfig, customColors);
    } catch (error) {
      console.error('Failed to update widget:', error);
    }
  };

  // Reinitialize widget (useful for debugging or config changes)
  const reinitializeWidget = () => {
    widgetInitialized.current = false;
    initializationAttempted.current = false;
    setIsInitialized(false);
    resetWidgetInitialization(); // Reset the global state too
    setTimeout(() => {
      handleInitializeWidget();
    }, 100);
  };

  return {
    sessionId,
    isLoading,
    isInitialized,
    handleInitializeWidget,
    handleUpdateWidget,
    reinitializeWidget
  };
};