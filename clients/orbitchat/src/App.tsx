import React, { useState } from 'react';
import { ThemeProvider } from './contexts/ThemeContext';
import { SettingsProvider } from './contexts/SettingsContext';
import { ChatInterface } from './components/ChatInterface';
import { Sidebar } from './components/Sidebar';
import { Settings } from './components/Settings';
import { X } from 'lucide-react';
import { getOutOfServiceMessage } from './utils/runtimeConfig';
import { OutOfServicePage } from './components/OutOfServicePage';

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
        <div className="min-h-screen flex flex-col md:flex-row bg-white dark:bg-[#212121] text-slate-900 dark:text-slate-100">
          <div className="hidden md:flex md:min-h-screen">
            <Sidebar onOpenSettings={() => setIsSettingsOpen(true)} />
          </div>
          <div className="flex-1 flex justify-center w-full">
            <ChatInterface
              onOpenSettings={() => setIsSettingsOpen(true)}
              onOpenSidebar={() => setIsMobileSidebarOpen(true)}
            />
          </div>
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
              <div className="relative z-10 h-full w-[min(18rem,85vw)] animate-slideIn">
                <Sidebar
                  onRequestClose={() => setIsMobileSidebarOpen(false)}
                  onOpenSettings={() => {
                    setIsSettingsOpen(true);
                    setIsMobileSidebarOpen(false);
                  }}
                />
                <button
                  onClick={() => setIsMobileSidebarOpen(false)}
                  className="absolute -right-3 top-[max(env(safe-area-inset-top),0.75rem)] rounded-full bg-white/95 p-2.5 text-gray-600 shadow-lg active:scale-95 transition-transform dark:bg-[#2d2f39] dark:text-[#ececf1]"
                  aria-label="Close menu"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
            </div>
          )}
        </div>
      </SettingsProvider>
    </ThemeProvider>
  );
}

export default App;
