import { useAuth0 } from '@auth0/auth0-react';
import { LogIn, LogOut } from 'lucide-react';
import { getEnableAuth, getEnableHeader } from '../utils/runtimeConfig';
import { useIsAuthenticated } from '../hooks/useIsAuthenticated';

export function AuthStatus() {
  if (!getEnableAuth() || !getEnableHeader()) return null;
  return <AuthStatusInner />;
}

function AuthStatusInner() {
  const { user, logout, loginWithRedirect } = useAuth0();
  const isAuthenticated = useIsAuthenticated();

  if (!isAuthenticated || !user) {
    return (
      <button
        onClick={() => loginWithRedirect()}
        className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-blue-400/70 bg-blue-600 px-3 py-2 text-xs font-semibold text-white shadow-sm active:scale-[0.97] transition-all duration-150 hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:border-blue-500 dark:bg-blue-500 dark:hover:bg-blue-600"
      >
        <LogIn className="h-4 w-4" />
        <span>Sign in</span>
      </button>
    );
  }

  const displayName = user.name || user.email || 'User';

  return (
    <div className="flex min-w-0 items-center gap-2 text-sm text-gray-600 dark:text-[#bfc2cd]">
      <span className="hidden max-w-[170px] truncate font-medium md:block" title={displayName}>
        {displayName}
      </span>
      <button
        onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
        className="inline-flex min-h-10 items-center justify-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 shadow-sm transition-colors hover:border-red-200 hover:bg-red-50 hover:text-red-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400 dark:border-[#454755] dark:text-[#c4c8d4] dark:hover:border-red-900/40 dark:hover:bg-red-900/20 dark:hover:text-red-300 md:rounded-full md:text-sm md:font-medium"
        title="Log out"
        aria-label="Log out"
      >
        <LogOut className="h-4 w-4" />
        <span className="hidden md:inline">Log out</span>
      </button>
    </div>
  );
}
