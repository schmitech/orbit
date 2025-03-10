import React from 'react';
import { Settings, Mic, Trash2, Languages } from 'lucide-react';
import { useChatStore } from '../store';

export const Sidebar: React.FC = () => {
  const { 
    voiceEnabled, 
    setVoiceEnabled, 
    clearMessages, 
    messages,
    language,
    setLanguage,
    supportedLanguages
  } = useChatStore();

  return (
    <div className="w-64 border-r bg-gray-50 p-6">
      <div className="flex items-center gap-3 mb-8">
        <Settings size={24} />
        <h2 className="text-xl font-semibold">Settings</h2>
      </div>
      <div className="space-y-6">
        <div className="space-y-2">
          <div className="flex items-center gap-3 text-gray-600">
            <Languages size={20} className="shrink-0" />
            <span className="text-base font-medium text-gray-900">Mic Language</span>
          </div>
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="w-full p-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {supportedLanguages.map((lang) => (
              <option key={lang.value} value={lang.value}>
                {lang.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Mic size={20} className="text-gray-600 shrink-0" />
            <span className="text-base font-medium text-gray-900">Voice Responses</span>
          </div>
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={voiceEnabled}
              onChange={(e) => setVoiceEnabled(e.target.checked)}
              className="sr-only peer"
            />
            <div className="w-11 h-6 bg-gray-200 rounded-full peer 
              peer-focus:ring-4 peer-focus:ring-blue-100
              peer-checked:after:translate-x-full 
              peer-checked:after:border-white 
              peer-checked:bg-blue-500
              after:content-[''] 
              after:absolute 
              after:top-0.5 
              after:left-0.5 
              after:bg-white 
              after:rounded-full 
              after:h-5 
              after:w-5 
              after:shadow-sm
              after:transition-all"
            />
          </label>
        </div>
        
        <button
          onClick={clearMessages}
          disabled={messages.length === 0}
          className="flex items-center gap-3 w-full px-4 py-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-transparent"
        >
          <Trash2 size={20} />
          <span className="font-medium">Clear Chat</span>
        </button>
      </div>
    </div>
  );
};