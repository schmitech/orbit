import React, { useState, useEffect } from 'react';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { useChatStore } from '../stores/chatStore';
import { Eye, EyeOff, Settings } from 'lucide-react';
import { debugError } from '../utils/debug';

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
  const [isValidating, setIsValidating] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

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

  const handleSendMessage = (content: string, fileIds?: string[]) => {
    sendMessage(content, fileIds);
  };

  const handleConfigureApi = async () => {
    if (apiUrl && apiKey) {
      setIsValidating(true);
      setValidationError(null);
      
      try {
        await configureApiSettings(apiUrl, apiKey);
        setShowConfig(false);
        // Clear any existing error after successful configuration
        clearError();
      } catch (error) {
        debugError('Failed to configure API:', error);
        // Set validation error for display in the modal
        const errorMessage = error instanceof Error ? error.message : 'Failed to configure API settings';
        setValidationError(errorMessage);
        // Also set error in the store for global error banner
        // (The store will handle this, but we can also show it in the modal)
      } finally {
        setIsValidating(false);
      }
    }
  };

  return (
    <div className="flex-1 flex flex-col">
      <div className="flex h-full w-full flex-col px-4 sm:px-6">
        <div className="mx-auto flex h-full w-full max-w-3xl flex-col">

          {/* API Configuration Modal */}
          {showConfig && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
              <div className="w-full max-w-md rounded-lg border border-gray-200 bg-white p-6 shadow-lg dark:border-[#444654] dark:bg-[#202123]">
                <h2 className="text-lg font-medium text-[#353740] dark:text-[#ececf1] mb-4">
                  Configure API Settings
                </h2>
                <div className="space-y-5">
                  <div>
                    <label className="block text-sm font-medium text-[#353740] dark:text-[#d1d5db] mb-2">
                      API URL
                    </label>
                    <input
                      type="text"
                      value={apiUrl}
                      onChange={(e) => setApiUrl(e.target.value)}
                      className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-[#353740] focus:border-gray-400 focus:outline-none dark:border-[#4a4b54] dark:bg-[#343541] dark:text-[#ececf1]"
                      placeholder="https://api.example.com"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-[#353740] dark:text-[#d1d5db] mb-2">
                      API Key
                    </label>
                    <div className="relative">
                      <input
                        type={showApiKey ? 'text' : 'password'}
                        value={apiKey}
                        onChange={(e) => {
                          setApiKey(e.target.value);
                          setValidationError(null); // Clear validation error when user types
                        }}
                        className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 pr-10 text-sm text-[#353740] focus:border-gray-400 focus:outline-none dark:border-[#4a4b54] dark:bg-[#343541] dark:text-[#ececf1]"
                        placeholder="your-api-key"
                        disabled={isValidating}
                      />
                      <button
                        type="button"
                        onClick={() => setShowApiKey(!showApiKey)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-gray-500 hover:text-gray-700 dark:text-[#d1d5db] dark:hover:text-white"
                        aria-label={showApiKey ? 'Hide API key' : 'Show API key'}
                        disabled={isValidating}
                      >
                        {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>
                  {validationError && (
                    <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-600/40 dark:bg-red-900/30 dark:text-red-200">
                      {validationError}
                    </div>
                  )}
                  <div className="flex justify-end gap-3 pt-2">
                    <button
                      onClick={() => {
                        setShowConfig(false);
                        setValidationError(null);
                      }}
                      className="rounded-md border border-transparent px-4 py-2 text-sm text-gray-600 hover:border-gray-300 hover:text-gray-900 dark:text-[#d1d5db] dark:hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                      disabled={isValidating}
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleConfigureApi}
                      disabled={!apiUrl || !apiKey || isValidating}
                      className="rounded-md bg-[#343541] px-4 py-2 text-sm font-medium text-white hover:bg-[#282b32] disabled:cursor-not-allowed disabled:opacity-50 dark:bg-[#565869] dark:hover:bg-[#6b6f7a]"
                    >
                      {isValidating ? 'Validating...' : 'Configure'}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Error Banner */}
          {error && (
            <div className="mt-6 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-600/40 dark:bg-red-900/30 dark:text-red-200">
              <div className="flex items-start justify-between">
                <p>{error}</p>
                <button
                  onClick={clearError}
                  className="ml-4 rounded p-1 text-red-500 hover:bg-red-100 hover:text-red-700 dark:text-red-200 dark:hover:bg-red-800/40"
                  aria-label="Dismiss error"
                >
                  ×
                </button>
              </div>
            </div>
          )}

          {/* Chat Header */}
          <div className="border-b border-gray-200 py-5 dark:border-[#4a4b54]">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h1 className="text-lg font-medium text-[#353740] dark:text-[#ececf1]">
                  {currentConversation?.title || 'New Chat'}
                </h1>
                {currentConversation && (
                  <p className="mt-1 text-xs text-gray-500 dark:text-[#bfc2cd]">
                    {currentConversation.messages.length} messages · Updated{' '}
                    {currentConversation.updatedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  onClick={() => setShowConfig(true)}
                  className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 dark:border-[#4a4b54] dark:text-[#ececf1] dark:hover:bg-[#3c3f4a]"
                >
                  Configure API
                </button>
                <button
                  onClick={onOpenSettings}
                  className="rounded-md bg-[#343541] p-2 text-white hover:bg-[#282b32] dark:bg-[#565869] dark:hover:bg-[#6b6f7a]"
                  title="Settings"
                >
                  <Settings className="h-4 w-4" />
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
            placeholder="Message ORBIT..."
          />
        </div>
      </div>
    </div>
  );
}
