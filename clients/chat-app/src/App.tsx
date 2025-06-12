import React, { useState } from 'react';
import { ThemeProvider } from './contexts/ThemeContext';
import { ChatInterface } from './components/ChatInterface';
import { Sidebar } from './components/Sidebar';
import { Settings } from './components/Settings';

function App() {
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  return (
    <ThemeProvider>
      <div className="h-screen flex bg-gray-100 dark:bg-gray-900">
        {/* Sidebar */}
        <Sidebar onOpenSettings={() => setIsSettingsOpen(true)} />
        
        {/* Main Chat Interface */}
        <ChatInterface />
        
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