"use client";

import React, { useEffect } from "react";

import {
  CheckCircledIcon,
  CrossCircledIcon,
  DotFilledIcon,
  HamburgerMenuIcon,
} from "@radix-ui/react-icons";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useHasMounted } from "@/lib/utils";
import { useChatStore } from "@/lib/chatStore";
import { Sidebar } from "../sidebar";
import { ChatOptions } from "./chat-options";

// Updated Message interface to match our new structure
interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  createdAt?: Date;
}

interface ChatTopbarProps {
  chatOptions: ChatOptions;
  setChatOptions: React.Dispatch<React.SetStateAction<ChatOptions>>;
  isLoading: boolean;
  chatId?: string;
  setChatId: React.Dispatch<React.SetStateAction<string>>;
  messages: Message[];
  isCollapsed: boolean;
  toggleSidebar: () => void;
}

export default function ChatTopbar({
  chatOptions,
  setChatOptions,
  isLoading,
  chatId,
  setChatId,
  messages,
  isCollapsed,
  toggleSidebar,
}: ChatTopbarProps) {
  const hasMounted = useHasMounted();
  const { getSessionId } = useChatStore();
  const [connectionStatus, setConnectionStatus] = React.useState<'connecting' | 'connected' | 'error'>('connecting');

  // Check API configuration on mount
  useEffect(() => {
    if (hasMounted) {
      // Check if API is configured
      if (chatOptions.apiUrl && chatOptions.apiKey) {
        setConnectionStatus('connected');
      } else {
        setConnectionStatus('error');
      }
    }
  }, [hasMounted, chatOptions.apiUrl, chatOptions.apiKey]);

  if (!hasMounted) {
    return (
      <div className="md:w-full flex px-4 py-6 items-center gap-1 md:justify-center">
        <DotFilledIcon className="w-4 h-4 text-blue-500" />
        <span className="text-xs">Booting up..</span>
      </div>
    );
  }

  const sessionId = getSessionId();

  return (
    <div className="md:w-full flex px-4 py-4 items-center justify-between md:justify-center">
      <div className="flex items-center gap-2">
        {/* Desktop sidebar toggle */}
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                onClick={toggleSidebar}
                className="hidden md:flex h-8 w-8"
              >
                <HamburgerMenuIcon className="w-4 h-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent
              sideOffset={4}
              className="bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 p-2 rounded-sm text-xs"
            >
              <p>{isCollapsed ? "Show" : "Hide"} sidebar</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>

        {/* Mobile sidebar sheet */}
        <Sheet>
          <SheetTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden h-8 w-8"
            >
              <HamburgerMenuIcon className="w-4 h-4" />
            </Button>
          </SheetTrigger>
          <SheetContent side="left">
            <div>
              <Sidebar
                chatId={chatId || ""}
                setChatId={setChatId}
                isCollapsed={false}
                isMobile={true}
                chatOptions={chatOptions}
                setChatOptions={setChatOptions}
              />
            </div>
          </SheetContent>
        </Sheet>
      </div>

      <div className="flex justify-center md:justify-between gap-4 w-full">
        <div className="gap-1 flex items-center">
          {connectionStatus === 'connected' && (
            <>
              {isLoading ? (
                <DotFilledIcon className="w-4 h-4 text-blue-500" />
              ) : (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger>
                      <span className="cursor-help">
                        <CheckCircledIcon className="w-4 h-4 text-green-500" />
                      </span>
                    </TooltipTrigger>
                    <TooltipContent
                      sideOffset={4}
                      className="bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 p-2 rounded-sm text-xs"
                    >
                      <p className="font-bold">ORBIT API</p>
                      <p className="text-gray-500">Connected to {chatOptions.apiUrl}</p>
                      <p className="text-gray-500">Session: {sessionId}</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )}
              <span className="text-xs">
                {isLoading ? "Generating.." : "Ready"}
              </span>
            </>
          )}
          {connectionStatus === 'error' && (
            <>
              <CrossCircledIcon className="w-4 h-4 text-red-500" />
              <span className="text-xs">API not configured</span>
            </>
          )}
          {connectionStatus === 'connecting' && (
            <>
              <DotFilledIcon className="w-4 h-4 text-blue-500" />
              <span className="text-xs">Connecting...</span>
            </>
          )}
        </div>
        <div className="flex items-end gap-2">
          {messages.length > 0 && (
            <span className="text-xs text-gray-500">
              {messages.length} message{messages.length > 1 ? "s" : ""}
            </span>
          )}
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger>
                <span className="cursor-help text-xs text-gray-400 font-mono">
                  {sessionId.substring(8, 16)}
                </span>
              </TooltipTrigger>
              <TooltipContent
                sideOffset={4}
                className="bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 p-2 rounded-sm text-xs"
              >
                <p className="font-bold">Session ID</p>
                <p className="font-mono">{sessionId}</p>
                <p className="text-gray-500">Used for conversation tracking</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      </div>
    </div>
  );
}
