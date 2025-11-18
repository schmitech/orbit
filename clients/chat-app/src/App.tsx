import React, { useState } from 'react';
import { ThemeProvider } from './contexts/ThemeContext';
import { SettingsProvider } from './contexts/SettingsContext';
import { ChatInterface } from './components/ChatInterface';
import { Sidebar } from './components/Sidebar';
import { Settings } from './components/Settings';
import { X } from 'lucide-react';

function App() {
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);

  return (
    <ThemeProvider>
      <SettingsProvider>
        <div className="min-h-screen flex flex-col md:flex-row bg-white dark:bg-[#212121] text-slate-900 dark:text-slate-100">
          <div className="hidden md:flex md:min-h-screen">
            <Sidebar />
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
                className="absolute inset-0 bg-black/60"
                onClick={() => setIsMobileSidebarOpen(false)}
                aria-hidden="true"
              />
              <div className="relative z-10 h-full w-[min(18rem,85vw)]">
                <Sidebar onRequestClose={() => setIsMobileSidebarOpen(false)} />
                <button
                  onClick={() => setIsMobileSidebarOpen(false)}
                  className="absolute -right-3 top-3 rounded-full bg-white/90 p-2 text-gray-600 shadow dark:bg-[#2d2f39] dark:text-[#ececf1]"
                  aria-label="Close menu"
                >
                  <X className="h-4 w-4" />
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
