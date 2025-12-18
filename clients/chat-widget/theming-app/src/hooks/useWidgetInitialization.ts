import { useState, useEffect, useRef, useCallback } from 'react';
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
  const [reinitCount, setReinitCount] = useState(0); // Track reinitializations to force re-renders
  const widgetInitialized = useRef(false);
  const initializationAttempted = useRef(false);
  
  // Keep refs to current values so we can access them in event handlers
  const currentWidgetConfig = useRef(widgetConfig);
  const currentCustomColors = useRef(customColors);
  
  // Update refs whenever values change
  useEffect(() => {
    currentWidgetConfig.current = widgetConfig;
  }, [widgetConfig]);
  
  useEffect(() => {
    currentCustomColors.current = customColors;
  }, [customColors]);

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

  // Core update function that directly calls updateWidget
  const performWidgetUpdate = useCallback(() => {
    try {
      if (isDebugEnabled()) {
        console.log('🔄 Performing widget update with current values');
      }
      updateWidget(currentWidgetConfig.current, currentCustomColors.current);
      return true;
    } catch (error) {
      console.error('Failed to update widget:', error);
      return false;
    }
  }, []);

  // Force update function that can be called anytime
  const forceWidgetUpdate = useCallback(() => {
    if (widgetInitialized.current && window.ChatbotWidget) {
      if (isDebugEnabled()) {
        console.log('🔄 Force updating widget with current config');
      }
      performWidgetUpdate();
    }
  }, [performWidgetUpdate]);

  // Create a stable update function that checks widget availability and updates
  const tryUpdateWidget = useCallback(() => {
    if (widgetInitialized.current && window.ChatbotWidget && typeof window.ChatbotWidget.updateWidgetConfig === 'function') {
      if (isDebugEnabled()) {
        console.log('📝 Trying to update widget...');
      }
      return performWidgetUpdate();
    } else if (widgetInitialized.current && isDebugEnabled()) {
      console.warn('⚠️ Widget not available for update or missing updateWidgetConfig method');
    }
    return false;
  }, [performWidgetUpdate]);

  // Re-apply configuration after reinitialization
  useEffect(() => {
    if (reinitCount > 0) {
      if (isDebugEnabled()) {
        console.log('🔄 Reapplying configuration after reinitialization...');
      }
      // Force an update to ensure the widget has the latest configuration
      setTimeout(() => {
        forceWidgetUpdate();
      }, 150);
    }
  }, [reinitCount, forceWidgetUpdate]);

  // Update widget when configuration changes - use a more reliable approach
  useEffect(() => {
    // Small delay to ensure any state updates are complete
    const timeoutId = setTimeout(() => {
      tryUpdateWidget();
    }, 10);
    
    return () => clearTimeout(timeoutId);
  }, [customColors, widgetConfig, tryUpdateWidget]);

  // Note: API key and endpoint updates are now handled explicitly through
  // the handleApiUpdate function in ChatbotThemingPlatform to avoid conflicts
  // with manual updates. These effects are commented out but kept for reference.
  
  // // Update API key when it changes
  // useEffect(() => {
  //   if (widgetInitialized.current && window.ChatbotWidget?.setApiKey) {
  //     if (isDebugEnabled()) {
  //       console.log(`🔑 Updating widget API key to: ${apiKey}`);
  //     }
  //     window.ChatbotWidget.setApiKey(apiKey);
  //   } else if (widgetInitialized.current) {
  //     console.warn('⚠️ Widget does not support setApiKey method - may need to reinitialize');
  //   }
  // }, [apiKey]);

  // // Update API endpoint when it changes
  // useEffect(() => {
  //   if (widgetInitialized.current && window.ChatbotWidget?.setApiUrl) {
  //     if (isDebugEnabled()) {
  //       console.log(`🌐 Updating widget API endpoint to: ${apiEndpoint}`);
  //     }
  //     window.ChatbotWidget.setApiUrl(apiEndpoint);
  //   } else if (widgetInitialized.current) {
  //     console.warn('⚠️ Widget does not support setApiUrl method - may need to reinitialize');
  //   }
  // }, [apiEndpoint]);

  // Initialize widget
  const handleInitializeWidget = (forceApiKey?: string, forceApiEndpoint?: string) => {
    // Double-check to prevent duplicate initialization
    if (widgetInitialized.current) {
      if (isDebugEnabled()) {
        console.log('🔄 Widget already initialized in hook - skipping');
      }
      return;
    }

    try {
      // Use forced values if provided (for reinitialize), otherwise use current values
      const keyToUse = forceApiKey || apiKey;
      const endpointToUse = forceApiEndpoint || apiEndpoint;
      
      if (isDebugEnabled()) {
        console.log('🚀 Initializing widget with:', { 
          apiKey: keyToUse.substring(0, 4) + '...',
          apiEndpoint: endpointToUse 
        });
      }
      
      initializeWidget(keyToUse, endpointToUse, widgetConfig, customColors);
      widgetInitialized.current = true;
      setIsInitialized(true);
      
      // Ensure the widget is properly available for updates
      if (window.ChatbotWidget) {
        if (isDebugEnabled()) {
          console.log('✅ Widget reference is available for updates');
        }
      }
    } catch (error) {
      console.error('Failed to initialize widget:', error);
    }
  };

  // Update widget - using refs to always get current values
  const handleUpdateWidget = useCallback(() => {
    performWidgetUpdate();
  }, [performWidgetUpdate]);

  // Reinitialize widget (useful for debugging or config changes)
  const reinitializeWidget = (newApiKey?: string, newApiEndpoint?: string) => {
    if (isDebugEnabled()) {
      console.log('🔄 Reinitializing widget with:', {
        apiKey: (newApiKey || apiKey).substring(0, 4) + '...',
        apiEndpoint: newApiEndpoint || apiEndpoint
      });
    }
    
    // First, try to destroy the existing widget if it exists
    if (window.ChatbotWidget && 'destroy' in window.ChatbotWidget && typeof (window.ChatbotWidget as any).destroy === 'function') {
      try {
        (window.ChatbotWidget as any).destroy();
        if (isDebugEnabled()) {
          console.log('✅ Existing widget destroyed');
        }
      } catch (error) {
        console.warn('⚠️ Failed to destroy existing widget:', error);
      }
    }
    
    // Remove the widget container if it exists
    const container = document.getElementById('chatbot-widget-container');
    if (container) {
      container.remove();
      if (isDebugEnabled()) {
        console.log('✅ Widget container removed');
      }
    }
    
    // Reset state
    widgetInitialized.current = false;
    initializationAttempted.current = false;
    setIsInitialized(false);
    resetWidgetInitialization(); // Reset the global state too
    
    // Clear any existing widget references
    if (window.ChatbotWidget) {
      delete (window as any).ChatbotWidget;
    }
    
    // Reinitialize after a short delay to ensure cleanup is complete
    setTimeout(() => {
      if (isDebugEnabled()) {
        console.log('🚀 Starting fresh widget initialization...');
      }
      handleInitializeWidget(newApiKey || apiKey, newApiEndpoint || apiEndpoint);
      
      // Add another short delay to ensure widget is fully ready for updates
      setTimeout(() => {
        if (window.ChatbotWidget && isDebugEnabled()) {
          console.log('✅ Widget reinitialization complete, ready for updates');
        }
        // Increment reinit counter to force re-render and reconnect update mechanisms
        setReinitCount(prev => prev + 1);
      }, 100);
    }, 200);
  };

  return {
    sessionId,
    isLoading,
    isInitialized,
    handleInitializeWidget,
    handleUpdateWidget,
    reinitializeWidget,
    forceWidgetUpdate,
    tryUpdateWidget
  };
};