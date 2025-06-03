"use client";
import { useEffect, useState } from "react";

import { Pencil2Icon } from "@radix-ui/react-icons";
import Image from "next/image";

import OllamaLogo from "../../public/orbit.png";
import { ChatOptions } from "./chat/chat-options";
import SidebarTabs from "./sidebar-tabs";
import { useChatStore } from "@/lib/chatStore";
import Link from "next/link";

// Updated Message interface to match our new structure
interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  createdAt?: Date;
}

interface SidebarProps {
  isCollapsed: boolean;
  onClick?: () => void;
  isMobile: boolean;
  chatId: string;
  setChatId: React.Dispatch<React.SetStateAction<string>>;
  chatOptions: ChatOptions;
  setChatOptions: React.Dispatch<React.SetStateAction<ChatOptions>>;
}

export function Sidebar({
  isCollapsed,
  isMobile,
  chatId,
  setChatId,
  chatOptions,
  setChatOptions,
}: SidebarProps) {
  const { newSession } = useChatStore();

  const handleNewChat = () => {
    // Clear the chatId in the URL
    setChatId("");
    // Create a new session which clears messages and generates new session ID
    newSession();
  };

  return (
    <div
      data-collapsed={isCollapsed}
      className="relative justify-between group bg-accent/20 dark:bg-card/35 flex flex-col h-full gap-4 data-[collapsed=true]:p-0 data-[collapsed=true]:hidden"
    >
      <div className="sticky left-0 right-0 top-0 z-20 p-1 rounded-sm m-2">
        <button
          className="flex w-full h-12 text-sm font-medium items-center
          border border-input bg-background hover:bg-accent hover:text-accent-foreground
          px-2 py-2 rounded-sm transition-colors"
          onClick={handleNewChat}
        >
          <div className="flex gap-3 p-2 items-center justify-between w-full">
            <div className="flex align-start gap-3">
              {!isCollapsed && !isMobile && (
                <Image
                  src={OllamaLogo}
                  alt="ORBIT AI"
                  width={40}
                  height={40}
                  className="dark:invert 2xl:block"
                />
              )}
              <span>New chat</span>
            </div>
            <Pencil2Icon className="w-4 h-4" />
          </div>
        </button>
      </div>
      <SidebarTabs
        chatOptions={chatOptions}
        setChatOptions={setChatOptions}
      />
    </div>
  );
}
