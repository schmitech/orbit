import { useEffect, useState } from 'react';
import { ThemeProvider } from './contexts/ThemeContext';
import { SettingsProvider } from './contexts/SettingsContext';
import { ChatInterface } from './components/ChatInterface';
import { Sidebar } from './components/Sidebar';
import { Settings } from './components/Settings';
import { PanelLeftOpen, X } from 'lucide-react';
import { getOutOfServiceMessage } from './utils/runtimeConfig';
import { OutOfServicePage } from './components/OutOfServicePage';
import { AuthGate } from './components/AuthGate';
import { LoginPromptModal } from './components/LoginPromptModal';
import { AppHeader } from './components/AppHeader';
import { AgentHomeNavProvider } from './contexts/AgentHomeNavProvider';
import { useChatStore } from './stores/chatStore';

function App() {
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [isDesktopSidebarCollapsed, setIsDesktopSidebarCollapsed] = useState(
    () => localStorage.getItem('desktop-sidebar-collapsed') === 'true'
  );
  const conversations = useChatStore(state => state.conversations);
  const outOfServiceMessage = getOutOfServiceMessage();

  useEffect(() => {
    localStorage.setItem('desktop-sidebar-collapsed', String(isDesktopSidebarCollapsed));
  }, [isDesktopSidebarCollapsed]);

  if (outOfServiceMessage) {
    return (
      <ThemeProvider>
        <OutOfServicePage message={outOfServiceMessage} />
      </ThemeProvider>
    );
  }

  const showSidebar = conversations.some(
    c => (c.messages.length > 0 || (c.attachedFiles?.length ?? 0) > 0) && !c.adapterLoadError
  );

  return (
    <ThemeProvider>
      <SettingsProvider>
        <AuthGate>
          <AgentHomeNavProvider>
            <div className="h-dvh flex flex-col bg-white dark:bg-black text-slate-900 dark:text-slate-100">
              <div className="flex-1 flex flex-col md:flex-row md:pl-4 min-h-0">
                {showSidebar && (
                  <div className={`hidden md:h-full ${isDesktopSidebarCollapsed ? 'md:hidden' : 'md:flex'}`}>
                    <Sidebar
                      onToggleDesktopSidebar={() => setIsDesktopSidebarCollapsed(true)}
                    />
                  </div>
                )}
                <div className="flex-1 flex flex-col w-full min-h-0">
                  <AppHeader hasCollapsedSidebarButton={showSidebar && isDesktopSidebarCollapsed} />
                  {showSidebar && isDesktopSidebarCollapsed && (
                    <div className="pointer-events-none absolute left-4 top-5 z-40 hidden md:block">
                      <button
                        type="button"
                        onClick={() => setIsDesktopSidebarCollapsed(false)}
                        className="pointer-events-auto inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-slate-200/80 bg-white text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:border-[#333645] dark:bg-[#161616] dark:text-[#d1d5db] dark:hover:border-[#43465a] dark:hover:bg-[#202020] dark:hover:text-white"
                        aria-label="Open sidebar"
                        title="Open sidebar"
                      >
                        <PanelLeftOpen className="h-5 w-5" />
                      </button>
                    </div>
                  )}
                  <div className="flex-1 flex justify-center w-full min-h-0">
                    <ChatInterface
                      onOpenSettings={() => setIsSettingsOpen(true)}
                      onOpenSidebar={() => setIsMobileSidebarOpen(true)}
                    />
                  </div>
                </div>
              </div>
            <LoginPromptModal />
            <Settings
              isOpen={isSettingsOpen}
              onClose={() => setIsSettingsOpen(false)}
            />

            {isMobileSidebarOpen && (
              <div className="fixed inset-0 z-50 flex md:hidden">
                <div
                  className="absolute inset-0 bg-black/60 backdrop-blur-sm"
                  onClick={() => setIsMobileSidebarOpen(false)}
                  aria-hidden="true"
                />
                <div className="relative z-10 h-full w-[min(20rem,90vw)] animate-slideIn bg-white dark:bg-black">
                  <Sidebar
                    onRequestClose={() => setIsMobileSidebarOpen(false)}
                  />
                  <button
                    onClick={() => setIsMobileSidebarOpen(false)}
                    className="absolute -right-3 top-[max(env(safe-area-inset-top),0.75rem)] rounded-full bg-white/95 p-3 text-gray-600 shadow-lg active:scale-95 transition-transform dark:bg-[#2d2f39] dark:text-[#ececf1]"
                    aria-label="Close menu"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>
              </div>
            )}
            </div>
          </AgentHomeNavProvider>
        </AuthGate>
      </SettingsProvider>
    </ThemeProvider>
  );
}

export default App;
