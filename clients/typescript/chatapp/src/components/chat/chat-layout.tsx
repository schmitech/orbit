"use client";

import React, { useEffect, useState } from "react";

import { Sidebar } from "../sidebar";
import Chat, { ChatProps, ChatTopbarProps } from "./chat";

interface ChatLayoutProps {
  defaultLayout: number[] | undefined;
  defaultCollapsed?: boolean;
  navCollapsedSize: number;
  chatId: string;
}

// Since ChatProps now includes isCollapsed and toggleSidebar, we need to handle them in the layout
type MergedProps = Omit<ChatLayoutProps & ChatProps & ChatTopbarProps, 'isCollapsed' | 'toggleSidebar'>;

export function ChatLayout({
  defaultLayout = [30, 160],
  defaultCollapsed = false,
  navCollapsedSize = 768,
  messages,
  input,
  handleInputChange,
  handleSubmit,
  isLoading,
  error,
  stop,
  chatId,
  setChatId,
  chatOptions,
  setChatOptions,
}: MergedProps) {
  const [isCollapsed, setIsCollapsed] = React.useState(defaultCollapsed || false);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const checkScreenWidth = () => {
      setIsMobile(window.innerWidth <= 768);
      // On mobile, auto-collapse sidebar, but allow manual override on desktop
      if (window.innerWidth <= 768) {
        setIsCollapsed(true);
      }
    };

    // Initial check
    checkScreenWidth();

    // Event listener for screen width changes
    window.addEventListener("resize", checkScreenWidth);

    // Cleanup the event listener on component unmount
    return () => {
      window.removeEventListener("resize", checkScreenWidth);
    };
  }, []);

  const toggleSidebar = () => {
    setIsCollapsed(!isCollapsed);
  };

  return (
    <div className="relative z-0 flex h-full w-full overflow-hidden">
      {!isCollapsed && (
        <div className="flex-shrink-0 overflow-x-hidden bg-token-sidebar-surface-primary w-[260px] transition-all duration-300">
          <Sidebar
            isCollapsed={false}
            isMobile={isMobile}
            chatId={chatId}
            setChatId={setChatId}
            chatOptions={chatOptions}
            setChatOptions={setChatOptions}
          />
        </div>
      )}
      <div className="relative flex h-full max-w-full flex-1 flex-col overflow-hidden">
        <Chat
          chatId={chatId}
          setChatId={setChatId}
          chatOptions={chatOptions}
          setChatOptions={setChatOptions}
          messages={messages}
          input={input}
          handleInputChange={handleInputChange}
          handleSubmit={handleSubmit}
          isLoading={isLoading}
          error={error}
          stop={stop}
          isCollapsed={isCollapsed}
          toggleSidebar={toggleSidebar}
        />
      </div>
    </div>
  );
}
