import { useEffect } from 'react';
import { useMsal, useIsAuthenticated } from '@azure/msal-react';
import { setIsAuthenticated, setAuthenticatedUserId } from './authState';
import { setTokenGetter, clearTokenGetter } from './tokenStore';
import { getAuthScopes } from '../utils/runtimeConfig';

function EntraAuthGateInner({ children }: { children: React.ReactNode }) {
  const { instance, accounts } = useMsal();
  const isAuthenticated = useIsAuthenticated();

  useEffect(() => {
    setIsAuthenticated(isAuthenticated);
  }, [isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated || accounts.length === 0) {
      setAuthenticatedUserId(null);
      return;
    }
    const account = accounts[0];
    setAuthenticatedUserId(account.username || account.name || account.localAccountId || null);
  }, [isAuthenticated, accounts]);

  useEffect(() => {
    if (!isAuthenticated || accounts.length === 0) return;
    const account = accounts[0];
    const scopes = getAuthScopes();
    setTokenGetter(async () => {
      const result = await instance.acquireTokenSilent({ scopes, account });
      return result.accessToken;
    });
    return () => clearTokenGetter();
  }, [isAuthenticated, accounts, instance]);

  return <>{children}</>;
}

export function EntraAuthGate({ children }: { children: React.ReactNode }) {
  return <EntraAuthGateInner>{children}</EntraAuthGateInner>;
}
