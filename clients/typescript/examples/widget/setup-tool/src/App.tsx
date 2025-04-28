import React, { useState, useEffect } from 'react';
import {
  MessageSquare,
  Code,
  Check,
  Plus,
  Trash2,
  Bot,
  HelpCircle,
  MessageCircle,
  MessagesSquare,
  Sparkles,
  Brain,
  Lightbulb,
  Headphones,
  type Icon as LucideIcon
} from 'lucide-react';

const themes = {
  modern: {
    primary: '#2563eb',
    secondary: '#3b82f6',
    background: '#ffffff',
    text: {
      primary: '#1e293b',
      secondary: '#64748b',
      inverse: '#ffffff'
    },
    input: {
      background: '#f1f5f9',
      border: '#e2e8f0'
    },
    message: {
      user: '#2563eb',
      assistant: '#f8fafc',
      userText: '#ffffff'
    },
    suggestedQuestions: {
      background: '#f0f9ff',
      hoverBackground: '#e0f2fe',
      text: '#2563eb'
    },
    iconColor: '#3b82f6'
  },
  corporate: {
    primary: '#0f172a',
    secondary: '#475569',
    background: '#ffffff',
    text: {
      primary: '#1e293b',
      secondary: '#64748b',
      inverse: '#ffffff'
    },
    input: {
      background: '#f8fafc',
      border: '#e2e8f0'
    },
    message: {
      user: '#0f172a',
      assistant: '#f8fafc',
      userText: '#ffffff'
    },
    suggestedQuestions: {
      background: '#f8fafc',
      hoverBackground: '#f1f5f9',
      text: '#0f172a'
    },
    iconColor: '#475569'
  },
  nature: {
    primary: '#15803d',
    secondary: '#22c55e',
    background: '#ffffff',
    text: {
      primary: '#1e293b',
      secondary: '#64748b',
      inverse: '#ffffff'
    },
    input: {
      background: '#f0fdf4',
      border: '#dcfce7'
    },
    message: {
      user: '#15803d',
      assistant: '#f0fdf4',
      userText: '#ffffff'
    },
    suggestedQuestions: {
      background: '#f0fdf4',
      hoverBackground: '#dcfce7',
      text: '#15803d'
    },
    iconColor: '#22c55e'
  },
  luxury: {
    primary: '#78350f',
    secondary: '#ca8a04',
    background: '#ffffff',
    text: {
      primary: '#1e293b',
      secondary: '#64748b',
      inverse: '#ffffff'
    },
    input: {
      background: '#fef3c7',
      border: '#fde68a'
    },
    message: {
      user: '#78350f',
      assistant: '#fffbeb',
      userText: '#ffffff'
    },
    suggestedQuestions: {
      background: '#fffbeb',
      hoverBackground: '#fef3c7',
      text: '#78350f'
    },
    iconColor: '#ca8a04'
  },
  tech: {
    primary: '#312e81',
    secondary: '#6366f1',
    background: '#ffffff',
    text: {
      primary: '#1e293b',
      secondary: '#64748b',
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
    iconColor: '#6366f1'
  },
  minimal: {
    primary: '#18181b',
    secondary: '#71717a',
    background: '#ffffff',
    text: {
      primary: '#18181b',
      secondary: '#71717a',
      inverse: '#ffffff'
    },
    input: {
      background: '#fafafa',
      border: '#e4e4e7'
    },
    message: {
      user: '#18181b',
      assistant: '#fafafa',
      userText: '#ffffff'
    },
    suggestedQuestions: {
      background: '#fafafa',
      hoverBackground: '#f4f4f5',
      text: '#18181b'
    },
    iconColor: '#71717a'
  },
  creative: {
    primary: '#be185d',
    secondary: '#ec4899',
    background: '#ffffff',
    text: {
      primary: '#1e293b',
      secondary: '#64748b',
      inverse: '#ffffff'
    },
    input: {
      background: '#fdf2f8',
      border: '#fce7f3'
    },
    message: {
      user: '#be185d',
      assistant: '#fdf2f8',
      userText: '#ffffff'
    },
    suggestedQuestions: {
      background: '#fdf2f8',
      hoverBackground: '#fce7f3',
      text: '#be185d'
    },
    iconColor: '#ec4899'
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
  }
};

const availableIcons = {
  'message-square': 'message-square',
  'bot': 'bot',
  'help-circle': 'help-circle',
  'message-circle': 'message-circle',
  'messages-square': 'messages-square',
  'sparkles': 'sparkles',
  'brain': 'brain',
  'lightbulb': 'lightbulb',
  'headphones': 'headphones'
} as const;

const iconComponents: Record<string, LucideIcon> = {
  'message-square': MessageSquare,
  'bot': Bot,
  'help-circle': HelpCircle,
  'message-circle': MessageCircle,
  'messages-square': MessagesSquare,
  'sparkles': Sparkles,
  'brain': Brain,
  'lightbulb': Lightbulb,
  'headphones': Headphones
};

interface WidgetConfig {
  theme: typeof themes.modern;
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
  const [copiedCode, setCopiedCode] = useState(false);
  const [currentConfig, setCurrentConfig] = useState<WidgetConfig>({
    theme: themes.modern,
    icon: "message-square",
    apiUrl: import.meta.env.VITE_API_ENDPOINT,
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
    const initWidget = () => {
      console.log('Initializing chatbot widget...');
      if (typeof window !== 'undefined' && window.initChatbotWidget) {
        try {
          window.initChatbotWidget({
            apiUrl: currentConfig.apiUrl,
            widgetConfig: {
              theme: currentConfig.theme,
              icon: currentConfig.icon,
              content: currentConfig.content
            }
          });
          console.log('Chatbot widget initialized successfully');
        } catch (error) {
          console.error('Failed to initialize chatbot widget:', error);
        }
      } else {
        console.error('Chatbot widget initialization function not found');
      }
    };

    const checkWidget = setInterval(() => {
      if (typeof window !== 'undefined' && window.initChatbotWidget) {
        clearInterval(checkWidget);
        initWidget();
      }
    }, 500);

    return () => clearInterval(checkWidget);
  }, []);

  useEffect(() => {
    if (typeof window !== 'undefined' && window.ChatbotWidget) {
      window.ChatbotWidget.updateWidgetConfig({
        theme: currentConfig.theme,
        icon: currentConfig.icon,
        content: currentConfig.content
      });
    }
  }, [currentConfig]);

  const handleCopyCode = () => {
    const codeElement = document.getElementById('implementation-code');
    if (codeElement) {
      navigator.clipboard.writeText(codeElement.textContent || '');
      setCopiedCode(true);
      setTimeout(() => setCopiedCode(false), 2000);
    }
  };

  const updateTheme = (themeName: keyof typeof themes) => {
    if (themes[themeName]) {
      const newTheme = themes[themeName];
      setCurrentConfig(prev => ({ ...prev, theme: newTheme }));
    }
  };

  const updateIcon = (iconName: string) => {
    setCurrentConfig(prev => ({ ...prev, icon: iconName }));
  };

  const updateContent = (newContent: Partial<WidgetConfig['content']>) => {
    setCurrentConfig(prev => {
      const updatedContent = {
        header: { ...prev.content?.header },
        welcome: { ...prev.content?.welcome },
        suggestedQuestions: [...(prev.content?.suggestedQuestions || [])]
      };

      if (newContent.header) {
        updatedContent.header = { ...updatedContent.header, ...newContent.header };
      }

      if (newContent.welcome) {
        updatedContent.welcome = { ...updatedContent.welcome, ...newContent.welcome };
      }

      if (newContent.suggestedQuestions) {
        updatedContent.suggestedQuestions = newContent.suggestedQuestions;
      }

      return {
        ...prev,
        content: updatedContent
      };
    });
  };

  const addSuggestedQuestion = () => {
    const newQuestion = {
      text: "New Question",
      query: "New Query"
    };
    
    updateContent({
      suggestedQuestions: [...(currentConfig.content?.suggestedQuestions || []), newQuestion]
    });
  };

  const removeSuggestedQuestion = (index: number) => {
    const updatedQuestions = currentConfig.content?.suggestedQuestions.filter((_, i) => i !== index);
    updateContent({
      suggestedQuestions: updatedQuestions
    });
  };

  const updateSuggestedQuestion = (index: number, field: 'text' | 'query', value: string) => {
    const updatedQuestions = [...(currentConfig.content?.suggestedQuestions || [])];
    updatedQuestions[index] = {
      ...updatedQuestions[index],
      [field]: value
    };
    
    updateContent({
      suggestedQuestions: updatedQuestions
    });
  };

  const getImplementationCode = () => {
    return `<!-- Add widget CSS -->
<link rel="stylesheet" href="https://unpkg.com/@schmitech/chatbot-widget@0.2.0/dist/chatbot-widget.css">

<!-- Widget dependencies -->
<script src="https://unpkg.com/react@18/umd/react.production.min.js" crossorigin></script>
<script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js" crossorigin></script>
<script src="https://unpkg.com/@schmitech/chatbot-widget@0.2.0/dist/chatbot-widget.umd.js" crossorigin></script>

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

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 p-6">
      <div className="max-w-[1200px] mx-auto">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-slate-900 mb-4">
            Widget Configurator
          </h1>
          <p className="text-lg text-slate-600">
            Customize your chatbot widget with our powerful configuration tool.
          </p>
        </div>

        <div className="grid gap-8">
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
            <div className="flex items-center space-x-4">
              <MessageSquare className="text-blue-500" size={24} />
              <div className="flex-1">
                <h2 className="text-xl font-semibold text-slate-900 mb-4">API Configuration</h2>
                <div className="text-sm text-slate-600 mb-4">
                  Your API endpoint is configured to: <code className="bg-slate-100 px-2 py-1 rounded">{currentConfig.apiUrl}</code>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
            <h2 className="text-xl font-semibold text-slate-900 mb-6">Widget Icon</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
              {Object.entries(availableIcons).map(([name]) => {
                const IconComponent = iconComponents[name];
                const isSelected = currentConfig.icon === name;
                return (
                  <button
                    key={name}
                    onClick={() => updateIcon(name)}
                    className={`
                      flex flex-col items-center justify-center p-4 rounded-lg border-2 transition-all
                      ${isSelected 
                        ? 'border-blue-500 bg-blue-50 text-blue-600' 
                        : 'border-slate-200 hover:border-blue-200 hover:bg-blue-50/50'}
                    `}
                  >
                    <IconComponent size={24} className={isSelected ? 'text-blue-500' : 'text-slate-600'} />
                    <span className="mt-2 text-sm font-medium capitalize">
                      {name.replace(/-/g, ' ')}
                    </span>
                    {isSelected && (
                      <Check size={16} className="absolute top-2 right-2 text-blue-500" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
            <h2 className="text-xl font-semibold text-slate-900 mb-6">Theme Selection</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {Object.entries(themes).map(([name, theme]) => (
                <div
                  key={name}
                  onClick={() => updateTheme(name as keyof typeof themes)}
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
                  <div className="p-3 bg-white border-t border-slate-200">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-slate-600">Select Theme</span>
                      <span className="text-blue-500 opacity-0 group-hover:opacity-100 transition-opacity">
                        Apply →
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
            <h2 className="text-xl font-semibold text-slate-900 mb-6">Content Configuration</h2>
            
            <div className="mb-8">
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Widget Title
              </label>
              <input
                type="text"
                value={currentConfig.content?.header.title}
                onChange={(e) => updateContent({ header: { title: e.target.value } })}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="Enter widget title"
              />
            </div>

            <div className="mb-8">
              <h3 className="text-lg font-medium text-slate-900 mb-4">Welcome Message</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    Welcome Title
                  </label>
                  <input
                    type="text"
                    value={currentConfig.content?.welcome.title}
                    onChange={(e) => updateContent({ welcome: { ...currentConfig.content!.welcome, title: e.target.value } })}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="Enter welcome title"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    Welcome Description
                  </label>
                  <textarea
                    value={currentConfig.content?.welcome.description}
                    onChange={(e) => updateContent({ welcome: { ...currentConfig.content!.welcome, description: e.target.value } })}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    rows={3}
                    placeholder="Enter welcome description"
                  />
                </div>
              </div>
            </div>

            <div>
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-medium text-slate-900">Suggested Questions</h3>
                <button
                  onClick={addSuggestedQuestion}
                  className="flex items-center space-x-2 px-4 py-2 text-blue-600 bg-blue-50 rounded-lg hover:bg-blue-100 transition-colors"
                >
                  <Plus size={16} />
                  <span>Add Question</span>
                </button>
              </div>
              <div className="space-y-4">
                {currentConfig.content?.suggestedQuestions.map((question, index) => (
                  <div key={index} className="p-4 border border-slate-200 rounded-lg">
                    <div className="flex justify-between items-start mb-4">
                      <span className="text-sm font-medium text-slate-600">Question {index + 1}</span>
                      <button
                        onClick={() => removeSuggestedQuestion(index)}
                        className="text-red-500 hover:text-red-600 transition-colors"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                    <div className="space-y-3">
                      <div>
                        <label className="block text-sm font-medium text-slate-700 mb-1">
                          Display Text
                        </label>
                        <input
                          type="text"
                          value={question.text}
                          onChange={(e) => updateSuggestedQuestion(index, 'text', e.target.value)}
                          className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                          placeholder="Question to display"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-slate-700 mb-1">
                          Query
                        </label>
                        <input
                          type="text"
                          value={question.query}
                          onChange={(e) => updateSuggestedQuestion(index, 'query', e.target.value)}
                          className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                          placeholder="Query to send"
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
              <h2 className="text-xl font-semibold text-slate-900">Implementation Code</h2>
              <button
                onClick={handleCopyCode}
                className="flex items-center space-x-2 px-4 py-2 bg-blue-50 text-blue-600 rounded-lg hover:bg-blue-100 transition-colors"
              >
                {copiedCode ? (
                  <>
                    <Check size={16} />
                    <span>Copied!</span>
                  </>
                ) : (
                  <>
                    <Code size={16} />
                    <span>Copy Code</span>
                  </>
                )}
              </button>
            </div>
            <div className="p-6 bg-slate-900">
              <pre className="overflow-x-auto">
                <code id="implementation-code" className="text-slate-300 text-sm whitespace-pre">
                  {getImplementationCode()}
                </code>
              </pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

declare global {
  interface Window {
    initChatbotWidget?: (config: any) => void;
    ChatbotWidget?: {
      updateWidgetConfig: (config: any) => void;
    };
  }
}

export default App;