import { Auth0Provider } from '@auth0/auth0-react';
import { getEnableAuth, getAuthDomain, getAuthClientId, getAuthAudience, getIsAuthConfigured, getAuthProvider } from '../utils/runtimeConfig';
import { EntraAuthProviderWrapper } from './EntraAuthProvider';

export function AuthProviderWrapper({ children }: { children: React.ReactNode }) {
  const enableAuth = getEnableAuth();

  if (!enableAuth || !getIsAuthConfigured()) {
    return <>{children}</>;
  }

  if (getAuthProvider() === 'entra') {
    return <EntraAuthProviderWrapper>{children}</EntraAuthProviderWrapper>;
  }

  const domain = getAuthDomain();
  const clientId = getAuthClientId();
  const audience = getAuthAudience();

  if (!domain || !clientId) {
    return <>{children}</>;
  }

  return (
    <Auth0Provider
      domain={domain}
      clientId={clientId}
      authorizationParams={{
        redirect_uri: window.location.origin,
        ...(audience ? { audience } : {}),
      }}
      cacheLocation="memory"
    >
      {children}
    </Auth0Provider>
  );
}
