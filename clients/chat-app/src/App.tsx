import React, { useState } from 'react';
import { ThemeProvider } from './contexts/ThemeContext';
import { ChatInterface } from './components/ChatInterface';
import { Sidebar } from './components/Sidebar';
import { Settings } from './components/Settings';

function App() {
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  return (
    <ThemeProvider>
      <div className="h-screen flex bg-gradient-to-br from-slate-50/90 via-white/95 to-blue-50/90 dark:from-slate-950/95 dark:via-slate-900/90 dark:to-slate-950/95 relative overflow-hidden">
        {/* Subtle global overlay for depth */}
        <div className="absolute inset-0 bg-gradient-to-br from-blue-50/10 via-transparent to-indigo-50/10 dark:from-blue-950/20 dark:via-transparent dark:to-indigo-950/20 pointer-events-none"></div>
        
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