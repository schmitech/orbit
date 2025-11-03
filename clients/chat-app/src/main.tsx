import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import './index.css';
import { getVersionInfo } from './utils/version';
import { debugLog } from './utils/debug';

// Log version information on startup
getVersionInfo().then(versionInfo => {
  debugLog('🚀 AI Chat Application started');
  debugLog(`📱 App Version: v${versionInfo.appVersion}`);
  debugLog(`📦 API Package: @schmitech/chatbot-api v${versionInfo.apiVersion}`);
  debugLog(`🔧 API Mode: ${versionInfo.isLocalApi ? 'Local' : 'NPM Package'}`);
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
