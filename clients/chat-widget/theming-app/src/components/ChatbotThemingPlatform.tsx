import { useWidgetConfig } from '../hooks/useWidgetConfig';
import { useThemeCustomization } from '../hooks/useThemeCustomization';
import { useUIState } from '../hooks/useUIState';
import { useWidgetInitialization } from '../hooks/useWidgetInitialization';
import { useApiConfig } from '../hooks/useApiConfig';
import { useGitHubStats } from '../hooks/useGitHubStats';
import { WIDGET_CONFIG, isDebugEnabled } from '../utils/widget-config';
import { useEffect, useState } from 'react';

import { 
  TabNavigation, 
  FormInput,
  ThemeTab,
  ContentTab,
  PromptTab,
  CodeTab
} from './index';

const ChatbotThemingPlatform = () => {
  
  const isServiceUnavailable = import.meta.env.VITE_UNAVAILABLE_MSG === 'true';
  const isEndpointFieldEnabled = import.meta.env.VITE_ENDPOINT_FIELD_ENABLED === 'true';
  const isApiConfigEnabled = import.meta.env.VITE_API_CONFIG_ENABLED !== 'false';
  
  const { 
    widgetConfig, 
    updateSuggestedQuestion,
    addSuggestedQuestion,
    removeSuggestedQuestion,
    updateHeaderTitle,
    updateWelcomeTitle,
    updateWelcomeDescription,
    updateSystemPrompt,
    updateMaxSuggestedQuestionLength,
    updateMaxSuggestedQuestionQueryLength
  } = useWidgetConfig();

  const { 
    selectedTheme, 
    customColors, 
    applyTheme, 
    updateColor 
  } = useThemeCustomization();

  const { 
    activeTab, 
    setActiveTab, 
    copied, 
    expandedSections, 
    toggleSection,
    handleCopySuccess 
  } = useUIState();

  // Handle case where prompt tab is disabled but user is on it
  useEffect(() => {
    if (!WIDGET_CONFIG.promptEnabled && activeTab === 'prompt') {
      setActiveTab('theme');
    }
  }, [WIDGET_CONFIG.promptEnabled, activeTab, setActiveTab]);

  const { 
    apiKey, 
    setApiKey, 
    apiEndpoint,
    setApiEndpoint,
    generateCode, 
    copyToClipboard 
  } = useApiConfig();

  // GitHub stats hook
  const githubStats = useGitHubStats(WIDGET_CONFIG.github.owner, WIDGET_CONFIG.github.repo);

  // State for API update message
  const [apiUpdateMessage, setApiUpdateMessage] = useState('');
  const [tempApiKey, setTempApiKey] = useState(apiKey);
  const [tempApiEndpoint, setTempApiEndpoint] = useState(apiEndpoint);

  // Keep temp values in sync with actual values when they change externally
  useEffect(() => {
    setTempApiKey(apiKey);
  }, [apiKey]);

  useEffect(() => {
    setTempApiEndpoint(apiEndpoint);
  }, [apiEndpoint]);

  // Widget initialization hook
  const { reinitializeWidget, tryUpdateWidget } = useWidgetInitialization({
    apiKey,
    apiEndpoint,
    widgetConfig,
    customColors,
    activeTab
  });

  // Helper function to safely update widget API settings
  const updateWidgetApiSettings = (newApiKey: string, newEndpoint: string): boolean => {
    try {
      if (!window.ChatbotWidget) {
        console.warn('Widget not available for API update');
        return false;
      }

      let success = true;

      // Update API key if method is available
      if (typeof window.ChatbotWidget.setApiKey === 'function') {
        window.ChatbotWidget.setApiKey(newApiKey);
        if (isDebugEnabled()) {
          console.log('✅ API key updated successfully');
        }
      } else {
        console.warn('Widget does not support setApiKey method');
        success = false;
      }

      // Update API URL if method is available
      if (typeof window.ChatbotWidget.setApiUrl === 'function') {
        window.ChatbotWidget.setApiUrl(newEndpoint);
        if (isDebugEnabled()) {
          console.log('✅ API endpoint updated successfully');
        }
      } else {
        console.warn('Widget does not support setApiUrl method');
        success = false;
      }

      return success;
    } catch (error) {
      console.error('Error updating widget API settings:', error);
      return false;
    }
  };

  // Copy to clipboard handler
  const handleCopyCode = async () => {
    const success = await copyToClipboard(widgetConfig, customColors);
    if (success) {
      handleCopySuccess();
    }
  };

  // Handle API configuration update
  const getRuntimeApiEndpoint = () => {
    if (typeof window !== 'undefined' && window.CHATBOT_API_URL) {
      return window.CHATBOT_API_URL;
    }
    return apiEndpoint;
  };

  const handleApiUpdate = () => {
    if (isDebugEnabled()) {
      console.log('🔄 Updating API configuration:', { 
        apiKey: tempApiKey.substring(0, 4) + '...', 
        apiEndpoint: isEndpointFieldEnabled ? tempApiEndpoint : 'endpoint field disabled'
      });
    }
    
    // Validate inputs
    if (!tempApiKey || tempApiKey.trim() === '') {
      setApiUpdateMessage('❌ API key cannot be empty');
      setTimeout(() => setApiUpdateMessage(''), 3000);
      return;
    }

    // Check if API key or endpoint actually changed
    const hasApiKeyChanged = tempApiKey !== apiKey;
    const hasEndpointChanged = isEndpointFieldEnabled && (tempApiEndpoint !== apiEndpoint);
    
    if (!hasApiKeyChanged && !hasEndpointChanged) {
      setApiUpdateMessage('No changes detected in API configuration');
      setTimeout(() => setApiUpdateMessage(''), 3000);
      return;
    }

    // Determine the effective endpoint to use
    const effectiveEndpoint = isEndpointFieldEnabled ? tempApiEndpoint : getRuntimeApiEndpoint();
    
    // Update the React state first
    setApiKey(tempApiKey);
    if (isEndpointFieldEnabled) {
      setApiEndpoint(tempApiEndpoint);
    } else {
      const runtimeEndpoint = getRuntimeApiEndpoint();
      setApiEndpoint(runtimeEndpoint);
      setTempApiEndpoint(runtimeEndpoint);
    }

    // Try to update the widget using the helper function
    const updateSuccess = updateWidgetApiSettings(tempApiKey, effectiveEndpoint);

    if (updateSuccess) {
      // Successfully updated via live methods
      if (isDebugEnabled()) {
        console.log('✅ Widget API settings updated successfully');
      }
      
      // Trigger a config update to ensure everything is synced
      setTimeout(() => {
        tryUpdateWidget();
      }, 100);
      
      setApiUpdateMessage('✅ API configuration updated successfully!');
    } else {
      // Live update failed or not supported, reinitialize the widget
      if (isDebugEnabled()) {
        console.log('🔄 Live update not available, reinitializing widget');
      }
      
      reinitializeWidget(tempApiKey, effectiveEndpoint);
      setApiUpdateMessage('✅ API configuration updated (widget reinitialized)');
    }
    
    // Clear message after 3 seconds
    setTimeout(() => setApiUpdateMessage(''), 3000);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Service Unavailable Message */}
      {isServiceUnavailable && (
        <div className="w-full bg-red-600 text-white py-4 px-4 text-center">
          <div className="max-w-7xl mx-auto">
            <p className="text-lg font-medium">
              ⚠️ The service is temporarily unavailable. We're working to restore access as soon as possible.
            </p>
          </div>
        </div>
      )}
      
      <div className="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-8">
          {/* Left Column - Customization Panel */}
          <div className="lg:col-span-3 space-y-6">
            {/* Header always visible; API key/endpoint fields and Update button hidden when VITE_API_CONFIG_ENABLED=false */}
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <div className="flex items-center justify-between flex-wrap gap-2 mb-4">
                <h2 className="text-lg font-semibold text-gray-900">ORBIT Chatbot Widget Builder</h2>
                <div className="flex items-center gap-2">
                  {WIDGET_CONFIG.source === 'local' ? (
                    <div className="px-3 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
                      🔧 Local Build
                    </div>
                  ) : (
                    <a 
                      href="https://www.npmjs.com/package/@schmitech/chatbot-widget"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-3 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800 hover:bg-blue-200 transition-colors"
                    >
                      📦 NPM Package v{WIDGET_CONFIG.npm.version}
                    </a>
                  )}
                </div>
              </div>
              {isApiConfigEnabled && (
                <div className="space-y-4">
                  <FormInput
                    label="API Key"
                    value={tempApiKey}
                    onChange={setTempApiKey}
                    placeholder="your-api-key"
                    type="password"
                    showPasswordToggle={true}
                    className="font-mono text-sm"
                    maxLength={50}
                  />
                  {isEndpointFieldEnabled && (
                    <FormInput
                      label="API Endpoint"
                      value={tempApiEndpoint}
                      onChange={setTempApiEndpoint}
                      placeholder="https://your-api-endpoint.com"
                      className="font-mono text-sm"
                      maxLength={50}
                    />
                  )}
                  <div className="flex items-center justify-between flex-wrap gap-2">
                    <div className="flex items-start gap-2">
                      {WIDGET_CONFIG.source === 'local' && (
                        <div className="text-xs text-green-600 bg-green-50 px-2 py-1 rounded">
                          Testing with local build - make sure the widget is built in ../dist/
                        </div>
                      )}
                    </div>
                    <button
                      onClick={handleApiUpdate}
                      className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors"
                    >
                      Update API Settings
                    </button>
                  </div>
                  {apiUpdateMessage && (
                    <div className="text-sm text-green-600 bg-green-50 px-3 py-2 rounded-lg border border-green-200">
                      ✓ {apiUpdateMessage}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Tabs */}
            <div className="bg-white rounded-lg shadow-sm border border-gray-200">
              <TabNavigation 
                activeTab={activeTab}
                onTabChange={setActiveTab}
              />

              <div className="p-6">
                {/* Theme Tab */}
                {activeTab === 'theme' && (
                  <ThemeTab
                    selectedTheme={selectedTheme}
                    customColors={customColors}
                    expandedSections={expandedSections}
                    onApplyTheme={applyTheme}
                    onUpdateColor={updateColor}
                    onToggleSection={toggleSection}
                  />
                )}

                {/* Content Tab */}
                {activeTab === 'content' && (
                  <ContentTab
                    widgetConfig={widgetConfig}
                    onUpdateHeaderTitle={updateHeaderTitle}
                    onUpdateWelcomeTitle={updateWelcomeTitle}
                    onUpdateWelcomeDescription={updateWelcomeDescription}
                    onUpdateSuggestedQuestion={updateSuggestedQuestion}
                    onAddSuggestedQuestion={addSuggestedQuestion}
                    onRemoveSuggestedQuestion={removeSuggestedQuestion}
                    onUpdateMaxQuestionLength={updateMaxSuggestedQuestionLength}
                    onUpdateMaxQueryLength={updateMaxSuggestedQuestionQueryLength}
                  />
                )}

                {/* Prompt Tab */}
                {activeTab === 'prompt' && WIDGET_CONFIG.promptEnabled && (
                  <PromptTab
                    widgetConfig={widgetConfig}
                    onUpdateSystemPrompt={updateSystemPrompt}
                  />
                )}

                              {/* Code Tab */}
              {activeTab === 'code' && (
                <CodeTab
                  widgetConfig={widgetConfig}
                  customColors={customColors}
                  copied={copied}
                  generateCode={generateCode}
                  onCopyCode={handleCopyCode}
                  apiKey={apiKey}
                  apiEndpoint={apiEndpoint}
                />
              )}
              </div>
            </div>
          </div>

          {/* Right Column - Instructions Panel */}
          <div className="lg:col-span-2">
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8">
              <div className="text-center mb-8">
                <div className="w-20 h-20 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-5">
                  <svg className="w-10 h-10 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                </div>
                <h3 className="text-2xl font-bold text-gray-900 mb-3">Live Preview</h3>
                <p className="text-base text-gray-600 leading-relaxed">See your customizations in real-time</p>
              </div>

              <div className="space-y-5">
                <div className="bg-gray-50 rounded-xl p-5">
                  <div className="flex items-start gap-4">
                    <div className="flex-shrink-0 w-8 h-8 bg-blue-600 text-white rounded-full flex items-center justify-center text-sm font-bold">1</div>
                    <div>
                      <p className="text-base font-semibold text-gray-900 mb-2">Customize Your Theme</p>
                      <p className="text-sm text-gray-600 leading-relaxed">Use the controls on the left to personalize colors, content, and behavior. Try different themes or adjust individual settings.</p>
                    </div>
                  </div>
                </div>

                <div className="bg-gray-50 rounded-xl p-5">
                  <div className="flex items-start gap-4">
                    <div className="flex-shrink-0 w-8 h-8 bg-blue-600 text-white rounded-full flex items-center justify-center text-sm font-bold">2</div>
                    <div>
                      <p className="text-base font-semibold text-gray-900 mb-2">Find the Widget</p>
                      <p className="text-sm text-gray-600 leading-relaxed">Look for the chat button in the bottom-right corner of your screen. It will appear as a colorful floating button.</p>
                    </div>
                  </div>
                </div>

                <div className="bg-gray-50 rounded-xl p-5">
                  <div className="flex items-start gap-4">
                    <div className="flex-shrink-0 w-8 h-8 bg-blue-600 text-white rounded-full flex items-center justify-center text-sm font-bold">3</div>
                    <div>
                      <p className="text-base font-semibold text-gray-900 mb-2">Click to Expand</p>
                      <p className="text-sm text-gray-600 leading-relaxed">Click the widget button to open the chat interface and see your theme changes applied in real-time!</p>
                    </div>
                  </div>
                </div>

                <div className="bg-gray-50 rounded-xl p-5">
                  <div className="flex items-start gap-4">
                    <div className="flex-shrink-0 w-8 h-8 bg-blue-600 text-white rounded-full flex items-center justify-center text-sm font-bold">4</div>
                    <div>
                      <p className="text-base font-semibold text-gray-900 mb-2">Test & Iterate</p>
                      <p className="text-sm text-gray-600 leading-relaxed">Make adjustments and see changes instantly in the live widget. Test different scenarios and interactions.</p>
                    </div>
                  </div>
                </div>
              </div>

               {/* ORBIT Project Information */}
               <div className="mt-8 pt-6 border-t border-gray-200">
                 <div className="text-center">
                   <div className="flex items-center justify-center gap-2 mb-3">
                     <svg className="w-5 h-5 text-gray-600" fill="currentColor" viewBox="0 0 24 24">
                       <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
                     </svg>
                     <span className="text-sm font-medium text-gray-900">Powered by ORBIT</span>
                   </div>
                   
                   {githubStats.isLoading ? (
                     <div className="flex items-center justify-center gap-2 text-xs text-gray-500 mb-3">
                       <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gray-400"></div>
                       <span>Loading stats...</span>
                     </div>
                   ) : githubStats.error ? (
                     <div className="flex items-center justify-center gap-2 text-xs text-red-500 mb-3">
                       <span>⚠️ Failed to load stats: {githubStats.error}</span>
                     </div>
                   ) : (
                     <div className="flex items-center justify-center gap-4 text-xs text-gray-500 mb-3">
                       <div className="flex items-center gap-1">
                         <svg className="w-4 h-4 text-yellow-500" fill="currentColor" viewBox="0 0 24 24">
                           <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/>
                         </svg>
                         <span>{githubStats.stars.toLocaleString()} stars</span>
                       </div>
                       <div className="flex items-center gap-1">
                         <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                           <path d="M22 5.72l-4.6-3.86-1.29 1.53 4.6 3.86L22 5.72zM7.88 3.39L6.6 1.86 2 5.71l1.29 1.53 4.59-3.85zM12.5 8H11v6l4.75 2.85.75-1.23-4-2.37V8zM12 4c-4.97 0-9 4.03-9 9s4.02 9 9 9c4.97 0 9-4.03 9-9s-4.03-9-9-9zm0 16c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z"/>
                         </svg>
                         <span>{githubStats.forks.toLocaleString()} forks</span>
                       </div>
                     </div>
                   )}
                   
                   <a 
                     href={`https://github.com/${WIDGET_CONFIG.github.owner}/${WIDGET_CONFIG.github.repo}`}
                     target="_blank" 
                     rel="noopener noreferrer"
                     className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 transition-colors"
                   >
                     <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                       <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
                     </svg>
                     View on GitHub
                   </a>
                 </div>
               </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatbotThemingPlatform;
