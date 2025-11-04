import React, { useState } from 'react';
import { ThemeProvider } from './contexts/ThemeContext';
import { ChatInterface } from './components/ChatInterface';
import { Sidebar } from './components/Sidebar';
import { Settings } from './components/Settings';

function App() {
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  return (
    <ThemeProvider>
      <div className="min-h-screen flex bg-white dark:bg-[#212121] text-slate-900 dark:text-slate-100">
        <Sidebar />
        <div className="flex-1 flex justify-center">
          <ChatInterface onOpenSettings={() => setIsSettingsOpen(true)} />
        </div>
        <Settings
          isOpen={isSettingsOpen}
          onClose={() => setIsSettingsOpen(false)}
        />
      </div>
    </ThemeProvider>
  );
}

export default App;
