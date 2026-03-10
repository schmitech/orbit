import { useEffect } from 'react';
import { useAuth0 } from '@auth0/auth0-react';
import { getIsAuthConfigured } from '../utils/runtimeConfig';
import { setTokenGetter, clearTokenGetter } from '../auth/tokenStore';
import { setAuthenticatedUserId, setIsAuthenticated } from '../auth/authState';

function AuthGateInner({ children }: { children: React.ReactNode }) {
  const { isLoading, isAuthenticated, getAccessTokenSilently, user } = useAuth0();

  // Sync auth state to module-scoped store (drives AppConfig Proxy + React hook)
  useEffect(() => {
    setIsAuthenticated(isAuthenticated);
  }, [isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated) {
      setAuthenticatedUserId(null);
      return;
    }

    const resolvedUserId =
      user?.sub ||
      user?.email ||
      user?.nickname ||
      user?.name ||
      null;

    setAuthenticatedUserId(resolvedUserId);
  }, [isAuthenticated, user]);

  useEffect(() => {
    if (isAuthenticated) {
      setTokenGetter(() => getAccessTokenSilently());
    }
    return () => clearTokenGetter();
  }, [isAuthenticated, getAccessTokenSilently]);

  // Only show spinner during initial Auth0 SDK load
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-white dark:bg-[#212121]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 dark:border-gray-100" />
      </div>
    );
  }

  // Always render children — guests see the app with lower limits
  return <>{children}</>;
}

function AuthGateBypass({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    setIsAuthenticated(false);
    setAuthenticatedUserId(null);
    clearTokenGetter();
  }, []);

  return <>{children}</>;
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  if (!getIsAuthConfigured()) {
    return <AuthGateBypass>{children}</AuthGateBypass>;
  }
  return <AuthGateInner>{children}</AuthGateInner>;
}
