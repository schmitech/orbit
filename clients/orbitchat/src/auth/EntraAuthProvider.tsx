import { useState, useEffect } from 'react';
import { PublicClientApplication } from '@azure/msal-browser';
import { MsalProvider } from '@azure/msal-react';
import { getAuthClientId, getAuthTenantId } from '../utils/runtimeConfig';

const msalInstance = new PublicClientApplication({
  auth: {
    clientId: getAuthClientId(),
    authority: `https://login.microsoftonline.com/${getAuthTenantId()}`,
    redirectUri: typeof window !== 'undefined' ? window.location.origin : '/',
  },
  cache: {
    cacheLocation: 'sessionStorage',
  },
});

export function EntraAuthProviderWrapper({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    msalInstance
      .initialize()
      .then(() => msalInstance.handleRedirectPromise())
      .catch((err: unknown) => {
        console.error('[EntraAuth] Redirect processing failed:', err);
      })
      .finally(() => setReady(true));
  }, []);

  // Block rendering until both initialize() and handleRedirectPromise() have
  // settled. This clears any stale interaction.status lock left in sessionStorage
  // before children (including login/logout controls) are mounted.
  if (!ready) return null;

  return <MsalProvider instance={msalInstance}>{children}</MsalProvider>;
}
