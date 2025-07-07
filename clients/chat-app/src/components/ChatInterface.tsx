import React, { useState, useEffect } from 'react';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { useChatStore } from '../stores/chatStore';
import { Eye, EyeOff, Settings } from 'lucide-react';

interface ChatInterfaceProps {
  onOpenSettings: () => void;
}

export function ChatInterface({ onOpenSettings }: ChatInterfaceProps) {
  const { 
    conversations, 
    currentConversationId, 
    sendMessage, 
    regenerateResponse, 
    isLoading,
    configureApiSettings,
    error,
    clearError,
    cleanupStreamingMessages
  } = useChatStore();

  // Configuration state for API settings
  const [showConfig, setShowConfig] = useState(false);
  const [apiUrl, setApiUrl] = useState(() => localStorage.getItem('chat-api-url') || 'http://localhost:3000');
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('chat-api-key') || 'orbit-123456789');
  const [showApiKey, setShowApiKey] = useState(false);

  const currentConversation = conversations.find(c => c.id === currentConversationId);

  // Clean up any orphaned streaming messages on mount
  useEffect(() => {
    cleanupStreamingMessages();
  }, [cleanupStreamingMessages]);

  // Save API settings to localStorage when they change
  useEffect(() => {
    localStorage.setItem('chat-api-url', apiUrl);
    localStorage.setItem('chat-api-key', apiKey);
  }, [apiUrl, apiKey]);

  const handleSendMessage = (content: string) => {
    sendMessage(content);
  };

  const handleConfigureApi = () => {
    if (apiUrl && apiKey) {
      configureApiSettings(apiUrl, apiKey);
      setShowConfig(false);
      // Clear any existing error after successful configuration
      clearError();
    }
  };

  return (
    <div className="flex-1 flex flex-col bg-gradient-to-br from-white/90 via-slate-50/85 to-blue-50/90 dark:from-slate-900/90 dark:via-slate-800/85 dark:to-slate-900/90 relative overflow-hidden backdrop-blur-md">
      {/* Enhanced gradient overlay for seamless blending */}
      <div className="absolute inset-0 bg-gradient-to-br from-blue-50/20 via-transparent to-indigo-50/30 dark:from-blue-900/10 dark:via-transparent dark:to-indigo-900/15 pointer-events-none"></div>
      
      {/* Subtle left border to complement sidebar */}
      <div className="absolute left-0 top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-slate-200/30 to-transparent dark:via-slate-700/30"></div>
      
      {/* Soft shadow transition from sidebar */}
      <div className="absolute left-0 top-0 bottom-0 w-8 bg-gradient-to-r from-black/[0.02] to-transparent dark:from-black/[0.05] pointer-events-none"></div>
      
      {/* API Configuration Modal */}
      {showConfig && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-white dark:bg-slate-800 p-8 rounded-2xl max-w-md w-full mx-4 shadow-2xl">
            <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100 mb-6">
              Configure API Settings
            </h2>
            <div className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                  API URL
                </label>
                <input
                  type="text"
                  value={apiUrl}
                  onChange={(e) => setApiUrl(e.target.value)}
                  className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 dark:focus:ring-blue-400/30 text-slate-900 dark:text-slate-100 transition-all duration-200"
                  placeholder="https://api.example.com"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                  API Key
                </label>
                <div className="relative">
                  <input
                    type={showApiKey ? "text" : "password"}
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 dark:focus:ring-blue-400/30 text-slate-900 dark:text-slate-100 pr-12 transition-all duration-200"
                    placeholder="your-api-key"
                  />
                  <button
                    type="button"
                    onClick={() => setShowApiKey(!showApiKey)}
                    className="absolute right-3 top-1/2 transform -translate-y-1/2 text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 transition-colors"
                  >
                    {showApiKey ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
              </div>
              <div className="flex justify-end space-x-3 pt-4">
                <button
                  onClick={() => setShowConfig(false)}
                  className="px-6 py-3 text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 font-medium transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleConfigureApi}
                  disabled={!apiUrl || !apiKey}
                  className="px-6 py-3 bg-gradient-to-r from-blue-600 to-blue-700 text-white rounded-xl hover:from-blue-700 hover:to-blue-800 disabled:opacity-50 disabled:cursor-not-allowed font-medium transition-all duration-200 shadow-lg hover:shadow-xl"
                >
                  Configure
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Error Banner */}
      {error && (
        <div className="bg-gradient-to-r from-red-50 to-rose-50 dark:from-red-900/20 dark:to-rose-900/20 p-4 m-4 rounded-2xl shadow-sm relative z-10">
          <div className="flex justify-between items-center">
            <div className="flex items-center">
              <div className="w-2 h-2 bg-red-500 rounded-full mr-3"></div>
              <p className="text-sm text-red-700 dark:text-red-400 font-medium">
                {error}
              </p>
            </div>
            <button
              onClick={clearError}
              className="text-red-400 hover:text-red-600 dark:hover:text-red-300 p-1 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/20 transition-colors"
            >
              <span className="text-lg">×</span>
            </button>
          </div>
        </div>
      )}

      {/* Chat Header */}
      <div className="px-8 py-6 relative z-10">
        <div className="w-full flex justify-between items-center">
          <div className="flex-1">
            {currentConversation && (
              <div className="flex items-center space-x-4">
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse shadow-sm"></div>
                <p className="text-sm text-slate-600 dark:text-slate-400 font-medium">
                  {currentConversation.messages.length} messages • Last updated {
                    currentConversation.updatedAt.toLocaleDateString()
                  }
                </p>
              </div>
            )}
          </div>
          <div className="flex-shrink-0 flex items-center gap-3">
            <button
              onClick={() => setShowConfig(true)}
              className="px-4 py-2 text-sm text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-white/20 dark:hover:bg-slate-800/30 rounded-lg transition-all duration-200 font-medium backdrop-blur-sm"
            >
              Configure API
            </button>
            <button
              onClick={onOpenSettings}
              className="p-2 text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-white/20 dark:hover:bg-slate-800/30 rounded-lg transition-all duration-200 backdrop-blur-sm"
              title="Settings"
            >
              <Settings className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>

      {/* Messages */}
      <MessageList
        messages={currentConversation?.messages || []}
        onRegenerate={regenerateResponse}
        isLoading={isLoading}
      />

      {/* Input */}
      <MessageInput
        onSend={handleSendMessage}
        disabled={isLoading}
        placeholder="Ask me anything..."
      />
    </div>
  );
}