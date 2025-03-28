import React, { useState, useEffect } from 'react';
import { Settings, Palette, MessageSquare, Layout, Sliders, Code, ChevronRight, Check } from 'lucide-react';

const themes = {
  default: {
    primary: '#2C3E50',
    secondary: '#f97316',
    background: '#ffffff',
    text: {
      primary: '#1a1a1a',
      secondary: '#666666',
      inverse: '#ffffff'
    },
    input: {
      background: '#f9fafb',
      border: '#e5e7eb'
    },
    message: {
      user: '#2C3E50',
      assistant: '#ffffff',
      userText: '#ffffff'
    },
    suggestedQuestions: {
      background: '#fff7ed',
      hoverBackground: '#ffedd5',
      text: '#2C3E50'
    },
    iconColor: '#f97316'
  },
  dark: {
    primary: '#111827',
    secondary: '#6366f1',
    background: '#1f2937',
    text: {
      primary: '#f3f4f6',
      secondary: '#d1d5db',
      inverse: '#ffffff'
    },
    input: {
      background: '#374151',
      border: '#4b5563'
    },
    message: {
      user: '#6366f1',
      assistant: '#1f2937',
      userText: '#ffffff'
    },
    suggestedQuestions: {
      background: '#1f2937',
      hoverBackground: '#374151',
      text: '#f3f4f6'
    },
    iconColor: '#6366f1'
  },
  light: {
    primary: '#e2e8f0',
    secondary: '#3b82f6',
    background: '#ffffff',
    text: {
      primary: '#1e293b',
      secondary: '#64748b',
      inverse: '#1e293b'
    },
    input: {
      background: '#f8fafc',
      border: '#cbd5e1'
    },
    message: {
      user: '#3b82f6',
      assistant: '#f1f5f9',
      userText: '#ffffff'
    },
    suggestedQuestions: {
      background: '#f0f9ff',
      hoverBackground: '#e0f2fe',
      text: '#1e293b'
    },
    iconColor: '#3b82f6'
  },
  nature: {
    primary: '#065f46',
    secondary: '#10b981',
    background: '#ffffff',
    text: {
      primary: '#1e293b',
      secondary: '#4b5563',
      inverse: '#ffffff'
    },
    input: {
      background: '#f0fdf4',
      border: '#d1fae5'
    },
    message: {
      user: '#065f46',
      assistant: '#ecfdf5',
      userText: '#ffffff'
    },
    suggestedQuestions: {
      background: '#ecfdf5',
      hoverBackground: '#d1fae5',
      text: '#065f46'
    },
    iconColor: '#10b981'
  },
  sunset: {
    primary: '#7c2d12',
    secondary: '#f59e0b',
    background: '#ffffff',
    text: {
      primary: '#1e293b',
      secondary: '#4b5563',
      inverse: '#ffffff'
    },
    input: {
      background: '#fff7ed',
      border: '#ffedd5'
    },
    message: {
      user: '#7c2d12',
      assistant: '#fff7ed',
      userText: '#ffffff'
    },
    suggestedQuestions: {
      background: '#fff7ed',
      hoverBackground: '#ffedd5',
      text: '#7c2d12'
    },
    iconColor: '#f59e0b'
  },
  ocean: {
    primary: '#0c4a6e',
    secondary: '#0ea5e9',
    background: '#ffffff',
    text: {
      primary: '#1e293b',
      secondary: '#4b5563',
      inverse: '#ffffff'
    },
    input: {
      background: '#f0f9ff',
      border: '#e0f2fe'
    },
    message: {
      user: '#0c4a6e',
      assistant: '#f0f9ff',
      userText: '#ffffff'
    },
    suggestedQuestions: {
      background: '#f0f9ff',
      hoverBackground: '#e0f2fe',
      text: '#0c4a6e'
    },
    iconColor: '#0ea5e9'
  },
  berry: {
    primary: '#701a75',
    secondary: '#ec4899',
    background: '#ffffff',
    text: {
      primary: '#1e293b',
      secondary: '#4b5563',
      inverse: '#ffffff'
    },
    input: {
      background: '#fdf2f8',
      border: '#fce7f3'
    },
    message: {
      user: '#701a75',
      assistant: '#fdf2f8',
      userText: '#ffffff'
    },
    suggestedQuestions: {
      background: '#fdf2f8',
      hoverBackground: '#fce7f3',
      text: '#701a75'
    },
    iconColor: '#ec4899'
  },
  royal: {
    primary: '#312e81',
    secondary: '#8b5cf6',
    background: '#ffffff',
    text: {
      primary: '#1e293b',
      secondary: '#4b5563',
      inverse: '#ffffff'
    },
    input: {
      background: '#eef2ff',
      border: '#e0e7ff'
    },
    message: {
      user: '#312e81',
      assistant: '#eef2ff',
      userText: '#ffffff'
    },
    suggestedQuestions: {
      background: '#eef2ff',
      hoverBackground: '#e0e7ff',
      text: '#312e81'
    },
    iconColor: '#8b5cf6'
  }
};

interface WidgetConfig {
  theme: typeof themes.default;
  icon?: string;
  apiUrl?: string;
  content?: {
    header: {
      title: string;
    };
    welcome: {
      title: string;
      description: string;
    };
    suggestedQuestions: Array<{
      text: string;
      query: string;
    }>;
  };
}

function App() {
  const [activeTab, setActiveTab] = useState('themes');
  const [copiedCode, setCopiedCode] = useState(false);
  const [currentConfig, setCurrentConfig] = useState<WidgetConfig>({
    theme: themes.default,
    icon: 'message-square',
    apiUrl: 'http://localhost:3000',
    content: {
      header: {
        title: "Chat Assistant"
      },
      welcome: {
        title: "Welcome!",
        description: "How can I help you today?"
      },
      suggestedQuestions: [
        {
          text: "What can you do?",
          query: "What are your capabilities?"
        },
        {
          text: "Help me get started",
          query: "How do I begin?"
        }
      ]
    }
  });

  useEffect(() => {
    // Initialize widget when component mounts
    const initWidget = () => {
      if (window.initChatbotWidget) {
        window.initChatbotWidget({
          apiUrl: currentConfig.apiUrl,
          widgetConfig: {
            theme: currentConfig.theme,
            icon: currentConfig.icon,
            content: currentConfig.content
          }
        });
      }
    };

    // Check for widget availability
    const checkWidget = setInterval(() => {
      if (window.initChatbotWidget) {
        clearInterval(checkWidget);
        initWidget();
      }
    }, 100);

    return () => clearInterval(checkWidget);
  }, [currentConfig]);

  const handleCopyCode = () => {
    const codeElement = document.getElementById('implementation-code');
    if (codeElement) {
      navigator.clipboard.writeText(codeElement.textContent || '');
      setCopiedCode(true);
      setTimeout(() => setCopiedCode(false), 2000);
    }
  };

  const updateApiUrl = () => {
    const apiUrl = document.getElementById('api-url')?.value;
    if (apiUrl && window.ChatbotWidget) {
      window.ChatbotWidget.setApiUrl(apiUrl);
      setCurrentConfig(prev => ({ ...prev, apiUrl }));
    } else {
      alert('Please enter a valid API URL');
    }
  };

  const updateTheme = (themeName: keyof typeof themes) => {
    if (window.ChatbotWidget && themes[themeName]) {
      const newTheme = themes[themeName];
      window.ChatbotWidget.updateWidgetConfig({
        theme: newTheme
      });
      setCurrentConfig(prev => ({ ...prev, theme: newTheme }));
    }
  };

  const updateContent = (content: Partial<WidgetConfig['content']>) => {
    if (window.ChatbotWidget) {
      const newContent = { ...currentConfig.content, ...content };
      window.ChatbotWidget.updateWidgetConfig({ content: newContent });
      setCurrentConfig(prev => ({ ...prev, content: newContent }));
    }
  };

  const getImplementationCode = () => {
    return `<!-- Include the chatbot widget -->
<script src="https://unpkg.com/@schmitech/chatbot-widget@0.1.0/dist/chatbot-widget.bundle.js"></script>

<script>
  window.addEventListener('load', function() {
    window.initChatbotWidget({
      apiUrl: '${currentConfig.apiUrl}',
      widgetConfig: {
        theme: ${JSON.stringify(currentConfig.theme, null, 2)},
        icon: '${currentConfig.icon}',
        content: ${JSON.stringify(currentConfig.content, null, 2)}
      }
    });
  });
</script>`;
  };

  const renderTabContent = () => {
    switch (activeTab) {
      case 'themes':
        return (
          <div className="space-y-8">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {Object.entries(themes).map(([name, theme]) => (
                <ThemeCard
                  key={name}
                  name={name}
                  theme={theme}
                  onClick={() => updateTheme(name as keyof typeof themes)}
                />
              ))}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              <ColorSection
                title="Main Colors"
                colors={[
                  { id: 'primary-color', label: 'Primary' },
                  { id: 'secondary-color', label: 'Accent' },
                  { id: 'background-color', label: 'Background' },
                  { id: 'text-primary-color', label: 'Text' }
                ]}
              />
              <ColorSection
                title="Message Bubbles"
                colors={[
                  { id: 'user-bubble-color', label: 'User' },
                  { id: 'assistant-bubble-color', label: 'Assistant' }
                ]}
              />
              <ColorSection
                title="Suggested Questions"
                colors={[
                  { id: 'suggested-bg-color', label: 'Background' },
                  { id: 'suggested-hover-color', label: 'Hover' },
                  { id: 'suggested-text-color', label: 'Text' }
                ]}
              />
              <ColorSection
                title="Icon"
                colors={[
                  { id: 'icon-color', label: 'Color' }
                ]}
              />
            </div>
          </div>
        );

      case 'customization':
        return (
          <div className="space-y-8">
            <div className="bg-white p-6 rounded-lg shadow-sm border border-slate-200">
              <h3 className="text-lg font-semibold text-slate-900 mb-4">Widget Position</h3>
              <div className="grid grid-cols-2 gap-4">
                <button
                  onClick={() => window.ChatbotWidget?.updateWidgetConfig({ position: 'bottom-right' })}
                  className="p-4 border rounded-lg hover:bg-slate-50 transition-colors"
                >
                  Bottom Right
                </button>
                <button
                  onClick={() => window.ChatbotWidget?.updateWidgetConfig({ position: 'bottom-left' })}
                  className="p-4 border rounded-lg hover:bg-slate-50 transition-colors"
                >
                  Bottom Left
                </button>
              </div>
            </div>

            <div className="bg-white p-6 rounded-lg shadow-sm border border-slate-200">
              <h3 className="text-lg font-semibold text-slate-900 mb-4">Widget Size</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Width (px)
                  </label>
                  <input
                    type="number"
                    min="300"
                    max="600"
                    defaultValue="380"
                    className="w-full rounded-md border-slate-300"
                    onChange={(e) => window.ChatbotWidget?.updateWidgetConfig({ size: { width: parseInt(e.target.value) } })}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Height (px)
                  </label>
                  <input
                    type="number"
                    min="400"
                    max="800"
                    defaultValue="600"
                    className="w-full rounded-md border-slate-300"
                    onChange={(e) => window.ChatbotWidget?.updateWidgetConfig({ size: { height: parseInt(e.target.value) } })}
                  />
                </div>
              </div>
            </div>
          </div>
        );

      case 'content':
        return (
          <div className="space-y-8">
            <div className="bg-white p-6 rounded-lg shadow-sm border border-slate-200">
              <h3 className="text-lg font-semibold text-slate-900 mb-4">Header Configuration</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Widget Title
                  </label>
                  <input
                    type="text"
                    defaultValue={currentConfig.content?.header.title}
                    className="w-full rounded-md border-slate-300"
                    onChange={(e) => updateContent({ header: { title: e.target.value } })}
                  />
                </div>
              </div>
            </div>

            <div className="bg-white p-6 rounded-lg shadow-sm border border-slate-200">
              <h3 className="text-lg font-semibold text-slate-900 mb-4">Welcome Message</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Welcome Title
                  </label>
                  <input
                    type="text"
                    defaultValue={currentConfig.content?.welcome.title}
                    className="w-full rounded-md border-slate-300"
                    onChange={(e) => updateContent({ welcome: { ...currentConfig.content!.welcome, title: e.target.value } })}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Welcome Description
                  </label>
                  <textarea
                    defaultValue={currentConfig.content?.welcome.description}
                    className="w-full rounded-md border-slate-300"
                    rows={3}
                    onChange={(e) => updateContent({ welcome: { ...currentConfig.content!.welcome, description: e.target.value } })}
                  />
                </div>
              </div>
            </div>

            <div className="bg-white p-6 rounded-lg shadow-sm border border-slate-200">
              <h3 className="text-lg font-semibold text-slate-900 mb-4">Suggested Questions</h3>
              <div className="space-y-4">
                {currentConfig.content?.suggestedQuestions.map((question, index) => (
                  <div key={index} className="flex gap-4">
                    <div className="flex-1">
                      <input
                        type="text"
                        defaultValue={question.text}
                        placeholder="Question text"
                        className="w-full rounded-md border-slate-300 mb-2"
                        onChange={(e) => {
                          const newQuestions = [...currentConfig.content!.suggestedQuestions];
                          newQuestions[index] = { ...question, text: e.target.value };
                          updateContent({ suggestedQuestions: newQuestions });
                        }}
                      />
                      <input
                        type="text"
                        defaultValue={question.query}
                        placeholder="Query to send"
                        className="w-full rounded-md border-slate-300"
                        onChange={(e) => {
                          const newQuestions = [...currentConfig.content!.suggestedQuestions];
                          newQuestions[index] = { ...question, query: e.target.value };
                          updateContent({ suggestedQuestions: newQuestions });
                        }}
                      />
                    </div>
                    <button
                      onClick={() => {
                        const newQuestions = currentConfig.content!.suggestedQuestions.filter((_, i) => i !== index);
                        updateContent({ suggestedQuestions: newQuestions });
                      }}
                      className="px-3 py-2 text-red-600 hover:bg-red-50 rounded"
                    >
                      Remove
                    </button>
                  </div>
                ))}
                <button
                  onClick={() => {
                    const newQuestions = [
                      ...currentConfig.content!.suggestedQuestions,
                      { text: 'New Question', query: 'New Query' }
                    ];
                    updateContent({ suggestedQuestions: newQuestions });
                  }}
                  className="w-full py-2 border-2 border-dashed border-slate-300 rounded-lg text-slate-600 hover:border-slate-400 hover:text-slate-700 transition-colors"
                >
                  Add Question
                </button>
              </div>
            </div>
          </div>
        );

      case 'settings':
        return (
          <div className="space-y-8">
            <div className="bg-white p-6 rounded-lg shadow-sm border border-slate-200">
              <h3 className="text-lg font-semibold text-slate-900 mb-4">General Settings</h3>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="font-medium text-slate-900">Auto Open</h4>
                    <p className="text-sm text-slate-600">Automatically open the widget on page load</p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      className="sr-only peer"
                      onChange={(e) => window.ChatbotWidget?.updateWidgetConfig({ autoOpen: e.target.checked })}
                    />
                    <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                  </label>
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="font-medium text-slate-900">Sound Effects</h4>
                    <p className="text-sm text-slate-600">Play sound on new messages</p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      className="sr-only peer"
                      onChange={(e) => window.ChatbotWidget?.updateWidgetConfig({ sound: e.target.checked })}
                    />
                    <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                  </label>
                </div>
              </div>
            </div>

            <div className="bg-white p-6 rounded-lg shadow-sm border border-slate-200">
              <h3 className="text-lg font-semibold text-slate-900 mb-4">Advanced Settings</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Rate Limit (messages per minute)
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="60"
                    defaultValue="10"
                    className="w-full rounded-md border-slate-300"
                    onChange={(e) => window.ChatbotWidget?.updateWidgetConfig({ rateLimit: parseInt(e.target.value) })}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Message History Limit
                  </label>
                  <input
                    type="number"
                    min="10"
                    max="100"
                    defaultValue="50"
                    className="w-full rounded-md border-slate-300"
                    onChange={(e) => window.ChatbotWidget?.updateWidgetConfig({ messageHistoryLimit: parseInt(e.target.value) })}
                  />
                </div>
              </div>
            </div>
          </div>
        );

      case 'code':
        return (
          <div className="bg-slate-900 rounded-lg overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 bg-slate-800">
              <span className="text-slate-400 text-sm">Implementation Code</span>
              <button
                onClick={handleCopyCode}
                className="flex items-center space-x-2 px-3 py-1 bg-slate-700 rounded text-slate-300 hover:bg-slate-600 transition-colors"
              >
                {copiedCode ? (
                  <>
                    <Check size={14} />
                    <span>Copied!</span>
                  </>
                ) : (
                  <>
                    <Code size={14} />
                    <span>Copy Code</span>
                  </>
                )}
              </button>
            </div>
            <pre className="p-4 overflow-x-auto">
              <code id="implementation-code" className="text-slate-300 text-sm">
                {getImplementationCode()}
              </code>
            </pre>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100">
      <div className="max-w-[1400px] mx-auto p-6">
        {/* Header */}
        <div className="text-center mb-12 pt-8">
          <h1 className="text-4xl font-bold text-slate-900 mb-4">
            Widget Configurator
          </h1>
          <p className="text-lg text-slate-600 max-w-2xl mx-auto">
            Customize your chatbot widget with our powerful configuration tool. Preview changes in real-time and generate implementation code instantly.
          </p>
        </div>

        {/* Main Content */}
        <div className="bg-white rounded-2xl shadow-xl overflow-hidden">
          {/* Navigation */}
          <nav className="border-b border-slate-200">
            <div className="flex space-x-1 p-2">
              <TabButton
                active={activeTab === 'themes'}
                onClick={() => setActiveTab('themes')}
                icon={<Palette size={18} />}
                text="Themes"
              />
              <TabButton
                active={activeTab === 'customization'}
                onClick={() => setActiveTab('customization')}
                icon={<Sliders size={18} />}
                text="Customization"
              />
              <TabButton
                active={activeTab === 'content'}
                onClick={() => setActiveTab('content')}
                icon={<Layout size={18} />}
                text="Content"
              />
              <TabButton
                active={activeTab === 'settings'}
                onClick={() => setActiveTab('settings')}
                icon={<Settings size={18} />}
                text="Settings"
              />
              <TabButton
                active={activeTab === 'code'}
                onClick={() => setActiveTab('code')}
                icon={<Code size={18} />}
                text="Implementation"
              />
            </div>
          </nav>

          {/* Content Area */}
          <div className="p-6">
            {/* API URL Input */}
            <div className="mb-8">
              <div className="flex items-center space-x-4 p-4 bg-blue-50 rounded-lg border border-blue-100">
                <MessageSquare className="text-blue-500" size={24} />
                <div className="flex-1">
                  <label htmlFor="api-url" className="block text-sm font-medium text-blue-900 mb-1">
                    API Endpoint
                  </label>
                  <div className="flex space-x-2">
                    <input
                      type="text"
                      id="api-url"
                      className="flex-1 rounded-md border-slate-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                      placeholder="http://localhost:3000"
                      defaultValue={currentConfig.apiUrl}
                    />
                    <button
                      onClick={updateApiUrl}
                      className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                    >
                      Update
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Tab Content */}
            {renderTabContent()}
          </div>
        </div>
      </div>
    </div>
  );
}

interface TabButtonProps {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  text: string;
}

function TabButton({ active, onClick, icon, text }: TabButtonProps) {
  return (
    <button
      onClick={onClick}
      className={`
        flex items-center space-x-2 px-4 py-2 rounded-md transition-colors
        ${active 
          ? 'bg-slate-100 text-slate-900' 
          : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'}
      `}
    >
      {icon}
      <span>{text}</span>
    </button>
  );
}

interface ThemeCardProps {
  name: string;
  theme: typeof themes.default;
  onClick: () => void;
}

function ThemeCard({ name, theme, onClick }: ThemeCardProps) {
  return (
    <div
      onClick={onClick}
      className="group cursor-pointer rounded-lg overflow-hidden border border-slate-200 hover:border-blue-500 transition-all hover:shadow-lg"
    >
      <div 
        className="h-24 p-4"
        style={{ backgroundColor: theme.primary }}
      >
        <div className="flex justify-between items-start">
          <div className="text-white">
            <h3 className="font-medium capitalize">{name}</h3>
            <p className="text-sm opacity-80">Theme</p>
          </div>
          <div
            className="w-8 h-8 rounded-full"
            style={{ backgroundColor: theme.secondary }}
          />
        </div>
      </div>
      <div 
        className="p-3 bg-white border-t border-slate-200 group-hover:border-blue-500 transition-colors"
      >
        <div className="flex items-center justify-between">
          <span className="text-sm text-slate-600">Select Theme</span>
          <ChevronRight size={16} className="text-slate-400 group-hover:text-blue-500 transition-colors" />
        </div>
      </div>
    </div>
  );
}

interface ColorSectionProps {
  title: string;
  colors: Array<{
    id: string;
    label: string;
  }>;
}

function ColorSection({ title, colors }: ColorSectionProps) {
  return (
    <div className="p-4 bg-slate-50 rounded-lg">
      <h3 className="font-medium text-slate-900 mb-4">{title}</h3>
      <div className="space-y-3">
        {colors.map(color => (
          <div key={color.id} className="flex items-center space-x-3">
            <input
              type="color"
              id={color.id}
              className="w-8 h-8 rounded cursor-pointer"
            />
            <label htmlFor={color.id} className="text-sm text-slate-700">
              {color.label}
            </label>
          </div>
        ))}
      </div>
    </div>
  );
}

declare global {
  interface Window {
    initChatbotWidget?: (config: any) => void;
    ChatbotWidget?: {
      setApiUrl: (url: string) => void;
      updateWidgetConfig: (config: any) => void;
    };
  }
}

export default App;