import { Auth0Provider } from '@auth0/auth0-react';
import { getEnableAuth, getAuthDomain, getAuthClientId, getAuthAudience, getIsAuthConfigured } from '../utils/runtimeConfig';

export function AuthProviderWrapper({ children }: { children: React.ReactNode }) {
  const enableAuth = getEnableAuth();
  const domain = getAuthDomain();
  const clientId = getAuthClientId();
  const audience = getAuthAudience();

  if (!enableAuth || !getIsAuthConfigured() || !domain || !clientId) {
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
      cacheLocation="localstorage"
    >
      {children}
    </Auth0Provider>
  );
}
