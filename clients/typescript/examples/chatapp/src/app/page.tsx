"use client";

import React from "react";
import ChatPage from "@/components/chat/chat-page";

export default function Home() {
  const [chatId, setChatId] = React.useState<string>("");
  return <ChatPage chatId={chatId} setChatId={setChatId} />;
}
