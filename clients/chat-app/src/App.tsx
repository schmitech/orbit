import React, { useState } from 'react';
import { ThemeProvider } from './contexts/ThemeContext';
import { ChatInterface } from './components/ChatInterface';
import { Sidebar } from './components/Sidebar';
import { Settings } from './components/Settings';

function App() {
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  return (
    <ThemeProvider>
      <div className="h-screen flex bg-gradient-to-br from-slate-100 via-white to-blue-100 dark:from-slate-900 dark:via-slate-800 dark:to-slate-900">
        {/* Sidebar */}
        <Sidebar />
        
        {/* Main Chat Interface */}
        <ChatInterface onOpenSettings={() => setIsSettingsOpen(true)} />
        
        {/* Settings Modal */}
        <Settings 
          isOpen={isSettingsOpen} 
          onClose={() => setIsSettingsOpen(false)} 
        />
      </div>
    </ThemeProvider>
  );
}

export default App;