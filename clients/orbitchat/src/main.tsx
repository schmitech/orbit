import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import './index.css';
import { getVersionInfo } from './utils/version.ts';
import { debugLog } from './utils/debug.ts';
import { getApplicationFavicon, getApplicationName, getStartupScripts } from './utils/runtimeConfig.ts';
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

const startupScripts = getStartupScripts();
for (const scriptConfig of startupScripts) {
  const src = scriptConfig.src?.trim() || '';
  const content = scriptConfig.content?.trim() || '';
  const scriptId = scriptConfig.id?.trim() || '';
  if (!src && !content) continue;

  if (scriptId && document.querySelector(`script[data-orbitchat-startup-script-id="${scriptId}"]`)) {
    continue;
  }

  const alreadyInjected = Array.from(document.querySelectorAll<HTMLScriptElement>('script[data-orbitchat-startup-script]'))
    .some((scriptEl) => {
      const sameSrc = src && scriptEl.dataset.orbitchatStartupScriptSrc === src;
      const sameContent = content && (scriptEl.textContent || '').trim() === content;
      return Boolean(sameSrc || sameContent);
    });
  if (alreadyInjected) continue;

  const script = document.createElement('script');
  if (src) script.src = src;
  if (content) script.text = content;
  script.async = scriptConfig.async ?? true;
  if (scriptConfig.defer !== undefined) script.defer = scriptConfig.defer;
  if (scriptConfig.type?.trim()) script.type = scriptConfig.type.trim();
  if (scriptConfig.integrity?.trim()) script.integrity = scriptConfig.integrity.trim();
  if (scriptConfig.crossOrigin) script.crossOrigin = scriptConfig.crossOrigin;
  if (scriptConfig.referrerPolicy?.trim()) script.referrerPolicy = scriptConfig.referrerPolicy.trim();
  script.dataset.orbitchatStartupScript = 'true';
  if (scriptId) script.dataset.orbitchatStartupScriptId = scriptId;
  if (src) script.dataset.orbitchatStartupScriptSrc = src;
  document.head.appendChild(script);
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
