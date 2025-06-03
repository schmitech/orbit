"use client";

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
  const handleApiUrlChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setChatOptions({ ...chatOptions, apiUrl: e.target.value });
  };

  const handleApiKeyChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setChatOptions({ ...chatOptions, apiKey: e.target.value });
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
        <Input
          type="password"
          id="api-key"
          className="w-full text-xs"
          value={chatOptions.apiKey || ""}
          onChange={handleApiKeyChange}
          placeholder="Enter your API key"
        />
      </div>

      <div className="text-xs text-gray-500 dark:text-gray-400">
        <p>Configure your ORBIT API endpoint and authentication key.</p>
        <p>These settings override environment variables.</p>
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
