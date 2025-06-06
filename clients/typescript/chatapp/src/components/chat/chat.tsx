import React from "react";

import ChatBottombar from "./chat-bottombar";
import ChatList from "./chat-list";
import { ChatOptions } from "./chat-options";
import ChatTopbar from "./chat-topbar";

// Updated Message interface to match our new structure
interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  createdAt?: Date;
}

export interface ChatProps {
  chatId?: string;
  setChatId: React.Dispatch<React.SetStateAction<string>>;
  messages: Message[];
  input: string;
  handleInputChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  handleSubmit: (e: React.FormEvent<HTMLFormElement>) => void;
  isLoading: boolean;
  error: undefined | Error;
  stop: () => void;
  isCollapsed: boolean;
  toggleSidebar: () => void;
}

export interface ChatTopbarProps {
  chatOptions: ChatOptions;
  setChatOptions: React.Dispatch<React.SetStateAction<ChatOptions>>;
}

export default function Chat({
  messages,
  input,
  handleInputChange,
  handleSubmit,
  isLoading,
  error,
  stop,
  chatOptions,
  setChatOptions,
  chatId,
  setChatId,
  isCollapsed,
  toggleSidebar,
}: ChatProps & ChatTopbarProps) {
  return (
    <div className="flex flex-col justify-between w-full h-full  ">
      <ChatTopbar
        chatOptions={chatOptions}
        setChatOptions={setChatOptions}
        isLoading={isLoading}
        chatId={chatId}
        setChatId={setChatId}
        messages={messages}
        isCollapsed={isCollapsed}
        toggleSidebar={toggleSidebar}
      />

      <ChatList
        messages={messages}
        isLoading={isLoading}
      />

      <ChatBottombar
        input={input}
        handleInputChange={handleInputChange}
        handleSubmit={handleSubmit}
        isLoading={isLoading}
        stop={stop}
      />
    </div>
  );
}
