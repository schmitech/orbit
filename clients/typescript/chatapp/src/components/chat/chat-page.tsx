"use client";

import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import useLocalStorageState from "use-local-storage-state";

import { ChatLayout } from "@/components/chat/chat-layout";
import { ChatOptions } from "@/components/chat/chat-options";
import { useChatStore, Message as ChatStoreMessage } from "@/lib/chatStore";

interface ChatPageProps {
  chatId: string;
  setChatId: React.Dispatch<React.SetStateAction<string>>;
}

// Convert ChatStore Message to AI SDK Message format for compatibility
const convertMessage = (msg: ChatStoreMessage) => ({
  id: msg.id,
  role: msg.role,
  content: msg.content,
  createdAt: msg.createdAt,
});

export default function ChatPage({ chatId, setChatId }: ChatPageProps) {
  const {
    messages: chatStoreMessages,
    isLoading,
    error: chatError,
    sendMessage,
    clearMessages,
    configureChat,
    apiConfigured,
    getSessionId,
  } = useChatStore();

  const [input, setInput] = useState("");
  
  const [chatOptions, setChatOptions] = useLocalStorageState<ChatOptions>(
    "chatOptions",
    {
      defaultValue: {
        apiUrl: process.env.NEXT_PUBLIC_API_URL || "http://localhost:3000",
        apiKey: process.env.NEXT_PUBLIC_API_KEY || "",
      },
    }
  );

  // Effect to ensure environment variables are applied if they exist
  useEffect(() => {
    const envApiUrl = process.env.NEXT_PUBLIC_API_URL;
    const envApiKey = process.env.NEXT_PUBLIC_API_KEY;
    
    // If environment variables exist, they should always take precedence
    if (envApiUrl || envApiKey) {
      const mergedOptions = {
        apiUrl: envApiUrl || chatOptions.apiUrl || "http://localhost:3000",
        apiKey: envApiKey || chatOptions.apiKey || "",
      };
      
      // Update if environment variables are different from current values
      if ((envApiUrl && envApiUrl !== chatOptions.apiUrl) || 
          (envApiKey && envApiKey !== chatOptions.apiKey)) {
        console.log('Applying environment variables:', { 
          envApiKey: envApiKey ? `${envApiKey.slice(0, 10)}...` : 'not set',
          currentApiKey: chatOptions.apiKey ? `${chatOptions.apiKey.slice(0, 10)}...` : 'not set'
        });
        setChatOptions(mergedOptions);
      }
    }
  }, []); // Empty dependency array - only run once on mount

  // Convert messages for compatibility with existing components
  const messages = chatStoreMessages.map(convertMessage);
  
  // Convert error to Error type for compatibility
  const error = chatError ? new Error(chatError) : undefined;

  // Configure the API when options change
  useEffect(() => {
    if (chatOptions.apiUrl && chatOptions.apiKey) {
      configureChat(chatOptions.apiUrl, chatOptions.apiKey);
    }
  }, [chatOptions.apiUrl, chatOptions.apiKey, configureChat]);

  // Reconfigure API when it becomes unconfigured (e.g., after new session)
  useEffect(() => {
    if (!apiConfigured && chatOptions.apiUrl && chatOptions.apiKey) {
      console.log("API became unconfigured, reconfiguring...");
      configureChat(chatOptions.apiUrl, chatOptions.apiKey);
    }
  }, [apiConfigured, chatOptions.apiUrl, chatOptions.apiKey, configureChat]);

  // Show errors as toasts
  useEffect(() => {
    if (chatError) {
      toast.error("Something went wrong: " + chatError);
    }
  }, [chatError]);

  // Display session ID in console for debugging
  useEffect(() => {
    const sessionId = getSessionId();
    console.log("App Session ID:", sessionId);
  }, [getSessionId]);

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    
    if (!input.trim()) return;
    
    if (!apiConfigured) {
      toast.error("API not configured. Please check your settings.");
      return;
    }

    const messageToSend = input.trim();
    setInput("");

    try {
      await sendMessage(messageToSend);
    } catch (error) {
      console.error("Failed to send message:", error);
      toast.error("Failed to send message");
    }
  };

  const stop = () => {
    // Since we're using streaming, we could implement a cancellation mechanism
    // For now, we'll just log that stop was requested
    console.log("Stop requested");
  };

  return (
    <main className="flex h-[calc(100dvh)] flex-col items-center ">
      <ChatLayout
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
        navCollapsedSize={10}
        defaultLayout={[30, 160]}
      />
    </main>
  );
}
