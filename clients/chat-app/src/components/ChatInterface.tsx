import { useState } from 'react';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { useChatStore } from '../stores/chatStore';
import { Eye, EyeOff, Settings } from 'lucide-react';
import { debugError } from '../utils/debug';

// Default API key from environment variable
const DEFAULT_API_KEY = import.meta.env.VITE_DEFAULT_KEY || 'default-key';
// Default API URL from environment variable
const DEFAULT_API_URL = import.meta.env.VITE_API_URL || 'http://localhost:3000';

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
    clearError
  } = useChatStore();

  // Configuration state for API settings
  const [showConfig, setShowConfig] = useState(false);
  // Always start with default values when opening the modal
  const [apiUrl, setApiUrl] = useState(DEFAULT_API_URL);
  const [apiKey, setApiKey] = useState(DEFAULT_API_KEY);
  const [showApiKey, setShowApiKey] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  const currentConversation = conversations.find(c => c.id === currentConversationId);

  // Disable Configure API button once conversation has started (has messages)
  // API key should remain immutable per conversation to prevent issues with conversation history
  const canConfigureApi = !currentConversation || currentConversation.messages.length === 0;

  // Clean up any orphaned streaming messages on mount (only once, not on every render)
  // Removed automatic cleanup to preserve streaming state when switching conversations
  // Streaming messages will be cleaned up when they complete naturally

  // Don't save API settings to localStorage when modal fields change
  // Only save when explicitly configured via configureApiSettings
  // This prevents default values from overwriting localStorage

  const handleSendMessage = (content: string, fileIds?: string[]) => {
    sendMessage(content, fileIds);
  };

  const handleConfigureApi = async () => {
    if (apiUrl && apiKey) {
      setIsValidating(true);
      setValidationError(null);
      
      try {
        await configureApiSettings(apiUrl, apiKey);
        // Clear any existing error after successful configuration
        clearError();
        // Reset to default values after successful configuration
        setApiUrl(DEFAULT_API_URL);
        setApiKey(DEFAULT_API_KEY);
        setValidationError(null);
        setShowApiKey(false);
        setShowConfig(false);
      } catch (error) {
        debugError('Failed to configure API:', error);
        // Set validation error for display in the modal
        const errorMessage = error instanceof Error ? error.message : 'Failed to configure API settings';
        setValidationError(errorMessage);
        // Also set error in the store for global error banner
        // (The store will handle this, but we can also show it in the modal)
        // Don't reset fields on error - let user see what they entered
      } finally {
        setIsValidating(false);
      }
    }
  };

  return (
    <div className="flex-1 flex flex-col">
      <div className="flex h-full w-full flex-col px-4 sm:px-6">
        <div className="mx-auto flex h-full w-full max-w-5xl flex-col">

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
                        // Reset to default values when canceling
                        setApiUrl(DEFAULT_API_URL);
                        setApiKey(DEFAULT_API_KEY);
                        setValidationError(null);
                        setShowApiKey(false);
                        setShowConfig(false);
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
          <div className="border-b border-gray-200 dark:border-[#4a4b54] pb-6 pt-6">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                {/* Adapter Info - show first when available */}
                {currentConversation?.adapterInfo && (
                  <div className="mb-4">
                    <div className="flex flex-wrap items-center gap-2 mb-3">
                      <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-md bg-gray-100 dark:bg-[#343541] border border-gray-200 dark:border-[#4a4b54]">
                        <span className="text-xs font-medium text-gray-600 dark:text-[#bfc2cd] uppercase tracking-wide">Agent</span>
                        <span className="text-sm font-semibold text-[#353740] dark:text-[#ececf1]">
                          {currentConversation.adapterInfo.client_name}
                        </span>
                      </div>
                      {currentConversation.adapterInfo.model && (
                        <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-md bg-gray-100 dark:bg-[#343541] border border-gray-200 dark:border-[#4a4b54]">
                          <span className="text-xs font-medium text-gray-600 dark:text-[#bfc2cd] uppercase tracking-wide">Model</span>
                          <span className="text-sm font-semibold text-[#353740] dark:text-[#ececf1]">
                            {currentConversation.adapterInfo.model}
                          </span>
                        </div>
                      )}
                    </div>
                    {/* Title and metadata */}
                    <h1 className="text-2xl font-semibold text-[#353740] dark:text-[#ececf1] mb-2">
                      {currentConversation?.title || 'New Chat'}
                    </h1>
                    {currentConversation && (
                      <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-[#bfc2cd]">
                        <span className="font-medium">{currentConversation.messages.length}</span>
                        <span className="text-gray-400 dark:text-[#6b6f7a]">•</span>
                        <span>Updated {currentConversation.updatedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  onClick={() => {
                    // Always reset to default values when opening the modal
                    // This ensures a clean slate for API key configuration
                    // The conversation's stored API key will remain unchanged until explicitly configured
                    setApiUrl(DEFAULT_API_URL);
                    setApiKey(DEFAULT_API_KEY);
                    setValidationError(null);
                    setShowApiKey(false);
                    setShowConfig(true);
                  }}
                  disabled={!canConfigureApi}
                  className="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-400 transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:border-gray-300 dark:border-[#4a4b54] dark:text-[#ececf1] dark:hover:bg-[#3c3f4a] dark:hover:border-[#6b6f7a] dark:disabled:hover:bg-transparent dark:disabled:hover:border-[#4a4b54]"
                  title={!canConfigureApi ? "API key cannot be changed once conversation has started. Create a new conversation to use a different API key." : "Configure API settings"}
                >
                  Configure API
                </button>
                <button
                  onClick={onOpenSettings}
                  className="rounded-md bg-[#343541] p-2 text-white hover:bg-[#282b32] transition-colors dark:bg-[#565869] dark:hover:bg-[#6b6f7a]"
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
            disabled={isLoading || !currentConversation || !currentConversation.apiKey}
            placeholder="Message ORBIT..."
          />
        </div>
      </div>
    </div>
  );
}
