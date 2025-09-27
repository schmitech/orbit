import React, { useState } from 'react';
import { ThemeProvider } from './contexts/ThemeContext';
import { ChatInterface } from './components/ChatInterface';
import { Sidebar } from './components/Sidebar';
import { Settings } from './components/Settings';

function App() {
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  return (
    <ThemeProvider>
      <div className="h-screen flex bg-slate-100 dark:bg-[#0a0f1a] text-slate-900 dark:text-slate-100 relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.12),_transparent_55%)] dark:bg-[radial-gradient(circle_at_top,_rgba(56,189,248,0.18),_transparent_60%)]" />
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(120deg,_rgba(15,23,42,0.05),_transparent_45%,_rgba(15,23,42,0.08))] dark:bg-[linear-gradient(130deg,_rgba(15,118,110,0.12),_transparent_45%,_rgba(31,41,55,0.32))]" />

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
