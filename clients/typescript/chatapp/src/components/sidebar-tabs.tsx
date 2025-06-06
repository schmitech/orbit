"use client";

import React from "react";

import { ChatOptions } from "./chat/chat-options";
import Settings from "./settings";

interface SidebarTabsProps {
  chatOptions: ChatOptions;
  setChatOptions: React.Dispatch<React.SetStateAction<ChatOptions>>;
}

const SidebarTabs = ({
  chatOptions,
  setChatOptions,
}: SidebarTabsProps) => (
  <div className="overflow-hidden h-full bg-accent/20 dark:bg-card/35">
    <div className="text-sm h-full">
      <div className="h-screen overflow-y-auto">
        <div className="h-full mb-16 pl-2">
          <Settings chatOptions={chatOptions} setChatOptions={setChatOptions} />
        </div>
      </div>
    </div>
  </div>
);

export default SidebarTabs;
