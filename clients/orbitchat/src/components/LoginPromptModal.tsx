import { useEffect } from 'react';
import { useAuth0 } from '@auth0/auth0-react';
import { useLoginPromptStore } from '../stores/loginPromptStore';
import { getEnableAuth, getIsAuthConfigured } from '../utils/runtimeConfig';
import { useIsAuthenticated } from '../hooks/useIsAuthenticated';
import { LogIn, X } from 'lucide-react';

export function LoginPromptModal() {
  const enableAuth = getEnableAuth();
  const isAuthConfigured = getIsAuthConfigured();
  const isAuthenticated = useIsAuthenticated();
  const { showLoginPrompt, promptMessage, closeLoginPrompt } = useLoginPromptStore();

  useEffect(() => {
    if (showLoginPrompt && (!enableAuth || !isAuthConfigured || isAuthenticated)) {
      closeLoginPrompt();
    }
  }, [showLoginPrompt, enableAuth, isAuthConfigured, isAuthenticated, closeLoginPrompt]);

  if (!enableAuth || !isAuthConfigured || isAuthenticated || !showLoginPrompt) return null;

  return <LoginPromptModalInner message={promptMessage} onClose={closeLoginPrompt} />;
}

function LoginPromptModalInner({ message, onClose }: { message: string; onClose: () => void }) {
  const { loginWithRedirect } = useAuth0();

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      {/* Modal */}
      <div className="relative z-10 mx-4 w-full max-w-md rounded-2xl border border-gray-200 bg-white p-6 shadow-2xl dark:border-[#4a4b54] dark:bg-[#2d2f39]">
        <button
          onClick={onClose}
          className="absolute right-3 top-3 rounded-full p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-[#3c3f4a] dark:hover:text-[#ececf1]"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="mb-4 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-900/40">
            <LogIn className="h-5 w-5 text-blue-600 dark:text-blue-300" />
          </div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-[#ececf1]">
            Sign in for more
          </h2>
        </div>

        <p className="mb-6 text-sm leading-relaxed text-gray-600 dark:text-[#bfc2cd]">
          {message}
        </p>

        <div className="flex gap-3">
          <button
            onClick={() => loginWithRedirect()}
            className="flex-1 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:bg-blue-500 dark:hover:bg-blue-600"
          >
            Sign in
          </button>
          <button
            onClick={onClose}
            className="flex-1 rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-400 dark:border-[#4a4b54] dark:bg-[#2d2f39] dark:text-[#bfc2cd] dark:hover:bg-[#3c3f4a]"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
