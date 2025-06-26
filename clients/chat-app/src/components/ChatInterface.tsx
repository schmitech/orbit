import React, { useState, useEffect } from 'react';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { useChatStore } from '../stores/chatStore';
import { Eye, EyeOff } from 'lucide-react';

export function ChatInterface() {
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
    <div className="flex-1 flex flex-col bg-white dark:bg-gray-900">
      {/* API Configuration Modal */}
      {showConfig && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 p-6 rounded-lg max-w-md w-full mx-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
              Configure API Settings
            </h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  API URL
                </label>
                <input
                  type="text"
                  value={apiUrl}
                  onChange={(e) => setApiUrl(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white"
                  placeholder="https://api.example.com"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  API Key
                </label>
                <div className="relative">
                  <input
                    type={showApiKey ? "text" : "password"}
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white pr-10"
                    placeholder="your-api-key"
                  />
                  <button
                    type="button"
                    onClick={() => setShowApiKey(!showApiKey)}
                    className="absolute right-2 top-1/2 transform -translate-y-1/2 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                  >
                    {showApiKey ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
              </div>
              <div className="flex justify-end space-x-2">
                <button
                  onClick={() => setShowConfig(false)}
                  className="px-4 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200"
                >
                  Cancel
                </button>
                <button
                  onClick={handleConfigureApi}
                  disabled={!apiUrl || !apiKey}
                  className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 disabled:opacity-50"
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
        <div className="bg-red-50 dark:bg-red-900/20 border-l-4 border-red-400 p-4">
          <div className="flex justify-between items-center">
            <div className="flex">
              <div className="ml-3">
                <p className="text-sm text-red-700 dark:text-red-400">
                  {error}
                </p>
              </div>
            </div>
            <button
              onClick={clearError}
              className="text-red-400 hover:text-red-600 dark:hover:text-red-300"
            >
              ×
            </button>
          </div>
        </div>
      )}

      {/* Chat Header */}
      <div className="h-20 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 flex items-center">
        <div className="w-full flex justify-between items-center">
          <div className="flex-1">
            {currentConversation && (
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                {currentConversation.messages.length} messages • Last updated {
                  currentConversation.updatedAt.toLocaleDateString()
                }
              </p>
            )}
          </div>
          <div className="flex-shrink-0 ml-4 pr-4">
            <button
              onClick={() => setShowConfig(true)}
              className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
            >
              Configure API
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