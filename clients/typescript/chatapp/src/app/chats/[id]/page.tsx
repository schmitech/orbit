"use client";

import React from "react";

import ChatPage from "@/components/chat/chat-page";

export default function Page({ params }: { params: { id: string } }) {
  const [chatId, setChatId] = React.useState<string>("");
  React.useEffect(() => {
    if (params.id) {
      setChatId(params.id);
    }
  }, [params.id]);
  return <ChatPage chatId={chatId} setChatId={setChatId} />;
}
