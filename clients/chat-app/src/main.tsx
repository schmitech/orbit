import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import './index.css';
import { getVersionInfo } from './utils/version';

// Log version information on startup
getVersionInfo().then(versionInfo => {
  const debugMode = (import.meta.env as any).VITE_CONSOLE_DEBUG === 'true';
  if (debugMode) {
    console.log('🚀 AI Chat Application started');
    console.log(`📱 App Version: v${versionInfo.appVersion}`);
    console.log(`📦 API Package: @schmitech/chatbot-api v${versionInfo.apiVersion}`);
    console.log(`🔧 API Mode: ${versionInfo.isLocalApi ? 'Local' : 'NPM Package'}`);
  }
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
