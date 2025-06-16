import { useWidgetConfig } from '../hooks/useWidgetConfig';
import { useThemeCustomization } from '../hooks/useThemeCustomization';
import { useUIState } from '../hooks/useUIState';
import { useWidgetInitialization } from '../hooks/useWidgetInitialization';
import { useApiConfig } from '../hooks/useApiConfig';
import { WIDGET_CONFIG } from '../utils/widget-config';

// Import UI components
import { 
  TabNavigation, 
  FormInput,
  ThemeTab,
  ContentTab,
  PromptTab,
  CodeTab
} from './index';

const ChatbotThemingPlatform = () => {
  // Custom hooks for state management
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

  const { 
    apiKey, 
    setApiKey, 
    generateCode, 
    copyToClipboard 
  } = useApiConfig();

  // Widget initialization hook
  useWidgetInitialization({
    apiKey,
    widgetConfig,
    customColors,
    activeTab
  });

  // Copy to clipboard handler
  const handleCopyCode = async () => {
    const success = await copyToClipboard(widgetConfig, customColors);
    if (success) {
      handleCopySuccess();
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-3 gap-8">
          {/* Left Column - Customization Panel */}
          <div className="col-span-2 space-y-6">
            {/* API Configuration */}
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-gray-900">Chatbot Widget Theme Builder</h2>
                <div className={`px-3 py-1 rounded-full text-xs font-medium ${
                  WIDGET_CONFIG.source === 'local' 
                    ? 'bg-green-100 text-green-800' 
                    : 'bg-blue-100 text-blue-800'
                }`}>
                  {WIDGET_CONFIG.source === 'local' ? '🔧 Local Build' : '📦 NPM Package'}
                </div>
              </div>
              <div className="space-y-4">
                <FormInput
                  label="API Key"
                  value={apiKey}
                  onChange={setApiKey}
                  placeholder="your-api-key"
                  className="font-mono text-sm"
                />
                <div className="flex items-start gap-2">
                  <p className="text-xs text-gray-500">Replace this with your actual API key when implementing</p>
                  {WIDGET_CONFIG.source === 'local' && (
                    <div className="text-xs text-green-600 bg-green-50 px-2 py-1 rounded">
                      Testing with local build - make sure the widget is built in ../dist/
                    </div>
                  )}
                </div>
              </div>
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
                {activeTab === 'prompt' && (
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
                />
              )}
              </div>
            </div>
          </div>

          {/* Right Column - Instructions Panel */}
          <div className="col-span-1">
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sticky top-8">
              <div className="text-center mb-6">
                <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
                  <svg className="w-8 h-8 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                </div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">Live Preview</h3>
                <p className="text-sm text-gray-600">See your customizations in real-time</p>
              </div>

              <div className="space-y-4">
                <div className="bg-gray-50 rounded-lg p-4">
                  <div className="flex items-start gap-3">
                    <div className="flex-shrink-0 w-6 h-6 bg-blue-600 text-white rounded-full flex items-center justify-center text-xs font-bold">1</div>
                    <div>
                      <p className="text-sm font-medium text-gray-900">Customize Your Theme</p>
                      <p className="text-xs text-gray-600 mt-1">Use the controls on the left to personalize colors, content, and behavior</p>
                    </div>
                  </div>
                </div>

                <div className="bg-gray-50 rounded-lg p-4">
                  <div className="flex items-start gap-3">
                    <div className="flex-shrink-0 w-6 h-6 bg-blue-600 text-white rounded-full flex items-center justify-center text-xs font-bold">2</div>
                    <div>
                      <p className="text-sm font-medium text-gray-900">Find the Widget</p>
                      <p className="text-xs text-gray-600 mt-1">Look for the chat button in the bottom-right corner of your screen</p>
                    </div>
                  </div>
                </div>

                <div className="bg-gray-50 rounded-lg p-4">
                  <div className="flex items-start gap-3">
                    <div className="flex-shrink-0 w-6 h-6 bg-blue-600 text-white rounded-full flex items-center justify-center text-xs font-bold">3</div>
                    <div>
                      <p className="text-sm font-medium text-gray-900">Click to Expand</p>
                      <p className="text-xs text-gray-600 mt-1">Click the widget button to open and see your theme changes applied!</p>
                    </div>
                  </div>
                </div>

                <div className="bg-gray-50 rounded-lg p-4">
                  <div className="flex items-start gap-3">
                    <div className="flex-shrink-0 w-6 h-6 bg-blue-600 text-white rounded-full flex items-center justify-center text-xs font-bold">4</div>
                    <div>
                      <p className="text-sm font-medium text-gray-900">Test & Iterate</p>
                      <p className="text-xs text-gray-600 mt-1">Make adjustments and see changes instantly in the live widget</p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="mt-6 pt-6 border-t border-gray-200">
                <div className="text-center">
                  <div className="inline-flex items-center gap-2 text-sm text-gray-600 mb-2">
                  </div>
                  <p className="text-xs text-gray-500">Changes are applied instantly - no need to save or refresh!</p>
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