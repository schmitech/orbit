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
        className="inline-flex min-h-10 items-center gap-1.5 sm:gap-2 rounded-full border border-blue-200 bg-blue-600 px-3 py-1.5 sm:px-4 sm:py-2 text-xs sm:text-sm font-semibold text-white transition-colors hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:border-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600"
      >
        <LogIn className="h-4 w-4" />
        <span>Sign in</span>
      </button>
    );
  }

  const displayName = user.name || user.email || 'User';

  return (
    <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-[#bfc2cd]">
      <span className="max-w-[170px] truncate font-medium" title={displayName}>
        {displayName}
      </span>
      <button
        onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
        className="inline-flex min-h-10 items-center gap-1.5 rounded-full border border-slate-200 px-3 py-2 text-sm font-medium text-slate-600 transition-colors hover:border-red-200 hover:bg-red-50 hover:text-red-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400 dark:border-[#454755] dark:text-[#c4c8d4] dark:hover:border-red-900/40 dark:hover:bg-red-900/20 dark:hover:text-red-300"
        title="Log out"
      >
        <LogOut className="h-4 w-4" />
        <span>Log out</span>
      </button>
    </div>
  );
}
