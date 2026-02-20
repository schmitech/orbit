import { useState, useEffect } from 'react';
import { getStoredConnection } from './config/connection';
import type { ConnectionConfig } from './config/connection';
import { useChatStore } from './stores/chatStore';
import { ConnectionDialog } from './components/ConnectionDialog';
import { Sidebar } from './components/Sidebar';
import { ChatView } from './components/ChatView';

export default function App() {
  const [showConfig, setShowConfig] = useState(false);
  const [connectionConfig, setConnectionConfig] = useState<ConnectionConfig | null>(() =>
    getStoredConnection()
  );
  const hasConnection = connectionConfig != null;

  const hydrate = useChatStore((s) => s.hydrate);
  const currentConversationId = useChatStore((s) => s.currentConversationId);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  const showDialog = !hasConnection || showConfig;

  const handleSaved = (config: ConnectionConfig) => {
    setConnectionConfig(config);
    setShowConfig(false);
  };

  return (
    <>
      {showDialog && (
        <ConnectionDialog
          isOpen={showDialog}
          onClose={() => setShowConfig(false)}
          onSaved={handleSaved}
        />
      )}
      {hasConnection && (
        <div className="app-layout">
          <Sidebar onOpenConfig={() => setShowConfig(true)} />
          <ChatView conversationId={currentConversationId} />
        </div>
      )}
    </>
  );
}
