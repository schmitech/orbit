import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import './index.css';
import { getVersionInfo } from './utils/version.ts';
import { debugLog } from './utils/debug.ts';
import { getApplicationFavicon, getApplicationName } from './utils/runtimeConfig.ts';
import { AuthProviderWrapper } from './auth/AuthProvider.tsx';

// Set document title from runtime config
document.title = getApplicationName();
const faviconHref = getApplicationFavicon();
const faviconEl = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
if (faviconEl) {
  faviconEl.href = faviconHref;
} else {
  const link = document.createElement('link');
  link.rel = 'icon';
  link.href = faviconHref;
  document.head.appendChild(link);
}

// Log version information on startup
const versionInfo = getVersionInfo();
debugLog('🚀 AI Chat Application started');
debugLog(`📱 App Version: v${versionInfo.appVersion}`);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProviderWrapper>
      <App />
    </AuthProviderWrapper>
  </StrictMode>
);
