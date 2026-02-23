import { useState } from 'react';
import { ThemeProvider } from './contexts/ThemeContext';
import { SettingsProvider } from './contexts/SettingsContext';
import { ChatInterface } from './components/ChatInterface';
import { Sidebar } from './components/Sidebar';
import { Settings } from './components/Settings';
import { X } from 'lucide-react';
import { getOutOfServiceMessage } from './utils/runtimeConfig';
import { OutOfServicePage } from './components/OutOfServicePage';
import { AuthGate } from './components/AuthGate';
import { LoginPromptModal } from './components/LoginPromptModal';
import { AppHeader } from './components/AppHeader';

function App() {
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const outOfServiceMessage = getOutOfServiceMessage();
  if (outOfServiceMessage) {
    return (
      <ThemeProvider>
        <OutOfServicePage message={outOfServiceMessage} />
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider>
      <SettingsProvider>
        <AuthGate>
          <div className="h-dvh flex flex-col bg-white dark:bg-[#212121] text-slate-900 dark:text-slate-100">
            <div className="flex-1 flex flex-col md:flex-row md:pl-4 min-h-0">
              <div className="hidden md:flex md:h-full">
                <Sidebar onOpenSettings={() => setIsSettingsOpen(true)} />
              </div>
              <div className="flex-1 flex flex-col w-full min-h-0">
                <AppHeader />
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
                <div className="relative z-10 h-full w-[min(20rem,90vw)] animate-slideIn bg-white dark:bg-[#212121]">
                  <Sidebar
                    onRequestClose={() => setIsMobileSidebarOpen(false)}
                    onOpenSettings={() => {
                      setIsSettingsOpen(true);
                      setIsMobileSidebarOpen(false);
                    }}
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
        </AuthGate>
      </SettingsProvider>
    </ThemeProvider>
  );
}

export default App;
