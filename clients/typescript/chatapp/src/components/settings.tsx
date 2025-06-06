"use client";

import { useState } from "react";
import { EyeOpenIcon, EyeClosedIcon } from "@radix-ui/react-icons";
import SettingsThemeToggle from "./settings-theme-toggle";
import { Input } from "./ui/input";

interface SettingsProps {
  chatOptions: {
    apiUrl?: string;
    apiKey?: string;
  };
  setChatOptions: React.Dispatch<React.SetStateAction<{
    apiUrl?: string;
    apiKey?: string;
  }>>;
}

const APIConfiguration = ({
  chatOptions,
  setChatOptions,
}: SettingsProps) => {
  const [showApiKey, setShowApiKey] = useState(false);

  const handleApiUrlChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setChatOptions({ ...chatOptions, apiUrl: e.target.value });
  };

  const handleApiKeyChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setChatOptions({ ...chatOptions, apiKey: e.target.value });
  };

  const toggleApiKeyVisibility = () => {
    setShowApiKey(!showApiKey);
  };

  const refreshFromEnvironment = () => {
    const envApiUrl = process.env.NEXT_PUBLIC_API_URL;
    const envApiKey = process.env.NEXT_PUBLIC_API_KEY;
    
    if (envApiUrl || envApiKey) {
      setChatOptions({
        apiUrl: envApiUrl || "http://localhost:3000",
        apiKey: envApiKey || "",
      });
      console.log('Refreshed from environment variables');
    } else {
      console.log('No environment variables found');
    }
  };

  return (
    <div className="space-y-4 border-b border-gray-200 dark:border-gray-700 pb-4 mb-4">
      <h3 className="text-sm font-medium text-gray-900 dark:text-white">API Configuration</h3>
      
      <div>
        <label
          htmlFor="api-url"
          className="block text-xs font-medium text-gray-900 dark:text-white mb-1"
        >
          API URL
        </label>
        <Input
          type="text"
          id="api-url"
          className="w-full text-xs"
          value={chatOptions.apiUrl || ""}
          onChange={handleApiUrlChange}
          placeholder="http://localhost:3000"
        />
      </div>

      <div>
        <label
          htmlFor="api-key"
          className="block text-xs font-medium text-gray-900 dark:text-white mb-1"
        >
          API Key
        </label>
        <div className="relative">
          <Input
            type={showApiKey ? "text" : "password"}
            id="api-key"
            className="w-full text-xs pr-8"
            value={chatOptions.apiKey || ""}
            onChange={handleApiKeyChange}
            placeholder="Enter your API key"
          />
          {chatOptions.apiKey && (
            <button
              type="button"
              onClick={toggleApiKeyVisibility}
              className="absolute right-2 top-1/2 transform -translate-y-1/2 p-1 hover:bg-accent rounded transition-colors"
              title={showApiKey ? 'Hide API key' : 'Show API key'}
            >
              {showApiKey ? (
                <EyeClosedIcon className="w-3 h-3 text-gray-500 dark:text-gray-400" />
              ) : (
                <EyeOpenIcon className="w-3 h-3 text-gray-500 dark:text-gray-400" />
              )}
            </button>
          )}
        </div>
      </div>

      <div className="space-y-2">
        <button
          type="button"
          onClick={refreshFromEnvironment}
          className="text-xs bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 px-2 py-1 rounded hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-colors"
        >
          Refresh from Environment
        </button>
        <div className="text-xs text-gray-500 dark:text-gray-400">
          <p>Configure your ORBIT API endpoint and authentication key.</p>
          <p>These settings override environment variables.</p>
        </div>
      </div>
    </div>
  );
};

export default function Settings({
  chatOptions,
  setChatOptions,
}: SettingsProps) {
  return (
    <>
      <APIConfiguration chatOptions={chatOptions} setChatOptions={setChatOptions} />
      <SettingsThemeToggle />
    </>
  );
}
