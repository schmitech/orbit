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

  const handleConfigureApi = async () => {
    if (apiUrl && apiKey) {
      try {
        await configureApiSettings(apiUrl, apiKey);
        setShowConfig(false);
        // Clear any existing error after successful configuration
        clearError();
      } catch (error) {
        console.error('Failed to configure API:', error);
        // Error will be handled by the store
      }
    }
  };

  return (
    <div className="flex-1 flex flex-col relative overflow-hidden">
      <div className="absolute inset-0 bg-white/85 dark:bg-slate-950/65 backdrop-blur-xl" />
      <div className="absolute inset-0 bg-[linear-gradient(140deg,_rgba(15,118,110,0.08),_transparent_45%,_rgba(79,70,229,0.08))] dark:bg-[linear-gradient(160deg,_rgba(15,118,110,0.18),_transparent_50%,_rgba(76,29,149,0.22))]" />
      <div className="absolute inset-y-0 left-0 w-px bg-white/60 dark:bg-slate-800/70" />
      <div className="absolute inset-y-0 left-0 w-10 bg-gradient-to-r from-slate-900/5 via-white/0 to-transparent dark:from-black/30" />
      <div className="relative z-10 flex flex-col h-full">

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
      <div className="px-10 py-6 border-b border-white/60 dark:border-slate-800/70 backdrop-blur-lg">
        <div className="flex items-center justify-between gap-6">
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-[0.28em] text-slate-500 dark:text-slate-400 font-semibold mb-2">
              Conversation
            </p>
            <h1 className="text-2xl font-semibold text-slate-900 dark:text-slate-100 truncate">
              {currentConversation?.title || 'New Chat'}
            </h1>
            {currentConversation && (
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                {currentConversation.messages.length} messages · Updated {' '}
                {currentConversation.updatedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </p>
            )}
          </div>
          <div className="flex-shrink-0 flex items-center gap-2">
            <button
              onClick={() => setShowConfig(true)}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200/80 dark:border-slate-700/60 px-4 py-2 text-sm font-medium text-slate-600 dark:text-slate-300 hover:border-slate-300 dark:hover:border-slate-500 hover:text-slate-900 dark:hover:text-white transition"
            >
              Configure API
            </button>
            <button
              onClick={onOpenSettings}
              className="p-2 rounded-xl bg-slate-900 text-slate-100 hover:bg-slate-800 dark:bg-slate-700 dark:hover:bg-slate-600 transition shadow-sm"
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
    </div>
  );
}
