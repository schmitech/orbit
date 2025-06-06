import React, { useEffect, useRef } from "react";

import Image from "next/image";
import { PersonIcon } from "@radix-ui/react-icons";

import OllamaLogo from "../../../public/orbit.png";
import CodeDisplayBlock from "../code-display-block";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import ThinkBlock from "../think-block";

// Updated Message interface to match our new structure
interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  createdAt?: Date;
}

interface ChatListProps {
  messages: Message[];
  isLoading: boolean;
}

const MessageToolbar = () => (
  <div className="mt-1 flex gap-3 empty:hidden juice:flex-row-reverse">
    <div className="text-gray-400 flex self-end lg:self-center items-center justify-center lg:justify-start mt-0 -ml-1 h-7 gap-[2px] invisible">
      <span>Regenerate</span>
      <span>Edit</span>
    </div>
  </div>
);

// Utility to process <think> tags
function processThinkTags(content: string, isLoading: boolean, message: Message | undefined, prevUserMessage: Message | undefined) {
  const thinkOpen = content.indexOf("<think>");
  const thinkClose = content.indexOf("</think>");

  // If <think> is present and </think> is not, show live thinking content
  if (thinkOpen !== -1 && thinkClose === -1) {
    // Show everything before <think>, then the ThinkBlock component with live mode
    const before = content.slice(0, thinkOpen);
    const thinkContent = content.slice(thinkOpen + 7); // everything after <think>
    return [
      before,
      <ThinkBlock key="live-think" content={thinkContent.trim()} live={true} />,
    ];
  }

  // If both <think> and </think> are present, show collapsible block
  if (thinkOpen !== -1 && thinkClose !== -1) {
    const before = content.slice(0, thinkOpen);
    const thinkContent = content.slice(thinkOpen + 7, thinkClose);
    const after = content.slice(thinkClose + 8);
    // Calculate duration if timestamps are available
    let duration;
    if (message?.createdAt && prevUserMessage?.createdAt) {
      const start = new Date(prevUserMessage.createdAt).getTime();
      const end = new Date(message.createdAt).getTime();
      if (!isNaN(start) && !isNaN(end) && end > start) {
        duration = ((end - start) / 1000).toFixed(2) + " seconds";
      }
    }
    return [
      before,
      <ThinkBlock key="collapsible-think" content={thinkContent.trim()} duration={duration} />,
      after,
    ];
  }

  // No <think> tag, return as is
  return [content];
}

export default function ChatList({ messages, isLoading }: ChatListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    bottomRef.current?.scrollIntoView({ behavior: "auto", block: "end" });
  };

  useEffect(() => {
    if (isLoading) {
      return;
    }
    // if user scrolls up, disable auto-scroll
    scrollToBottom();
  }, [messages, isLoading]);

  if (messages.length === 0) {
    return (
      <div className="w-full h-full flex justify-center items-center">
        <div className="flex flex-col gap-8 items-center">
          <Image
            src={OllamaLogo}
            alt="ORBIT AI"
            width={200}
            height={200}
            className="h-48 w-48 object-contain dark:invert"
          />
          <p className="text-center text-xl text-muted-foreground">
            How can I help you today?
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      id="scroller"
      className="w-[800px] overflow-y-scroll overflow-x-hidden h-full justify-center m-auto"
    >
      <div className="px-4 py-2 justify-center text-base md:gap-6 m-auto">
        {messages
          .filter((message) => message.role !== "system")
          .map((message, index) => (
            <div
              key={message.id || index}
              className="flex flex-1 text-base mx-auto gap-3 juice:gap-4 juice:md:gap-6 md:px-5 lg:px-1 xl:px-5 md:max-w-3xl lg:max-w-[40rem] xl:max-w-[48rem]"
            >
              <div className="flex flex-1 text-base mx-auto gap-3 juice:gap-4 juice:md:gap-6 md:px-5 lg:px-1 xl:px-5 md:max-w-3xl lg:max-w-[40rem] xl:max-w-[48rem]">
                <div className="flex-shrink-0 flex flex-col relative items-end">
                  <div className="pt-0.5">
                    <div className="gizmo-shadow-stroke flex h-12 w-12 items-center justify-center overflow-hidden rounded-full">
                      {message.role === "user" ? (
                        <div className="h-8 w-8 bg-blue-500 dark:bg-blue-600 rounded-full flex items-center justify-center">
                          <PersonIcon className="w-4 h-4 text-white" />
                        </div>
                      ) : (
                        <Image
                          src={OllamaLogo}
                          alt="ORBIT AI"
                          width={48}
                          height={48}
                          className="object-contain dark:invert aspect-square h-12 w-12"
                        />
                      )}
                    </div>
                  </div>
                </div>
                {message.role === "user" && (
                  <div className="relative flex w-full min-w-0 flex-col">
                    <div className="font-semibold pb-2">You</div>
                    <div className="flex-col gap-1 md:gap-3">
                      {message.content}
                    </div>
                    <MessageToolbar />
                  </div>
                )}
                {message.role === "assistant" && (
                  <div className="relative flex w-full min-w-0 flex-col">
                    <div className="font-semibold pb-2">Assistant</div>
                    <div className="flex-col gap-1 md:gap-3">
                      <span className="whitespace-pre-wrap">
                        {/* Check if the message content contains a code block */}
                        {message.content.split("```").map((part, index) => {
                          if (index % 2 === 0) {
                            // Find previous user message
                            const prevUserMessage = messages.slice(0, messages.indexOf(message)).reverse().find(m => m.role === "user");
                            // Process <think> tags before rendering Markdown
                            return processThinkTags(part, isLoading, message, prevUserMessage).map((segment, segIdx) =>
                              typeof segment === "string" ? (
                                <Markdown key={index + "-" + segIdx} remarkPlugins={[remarkGfm]}>
                                  {segment}
                                </Markdown>
                              ) : (
                                segment // This is the <Thinking /> component
                              )
                            );
                          } else {
                            return (
                              <CodeDisplayBlock
                                key={index}
                                code={part.trim()}
                                lang=""
                              />
                            );
                          }
                        })}
                        {isLoading &&
                          messages.indexOf(message) === messages.length - 1 && (
                            <span className="animate-pulse" aria-label="Typing">
                              ...
                            </span>
                          )}
                      </span>
                    </div>
                    <MessageToolbar />
                  </div>
                )}
              </div>
            </div>
          ))}
      </div>
      <div id="anchor" ref={bottomRef}></div>
    </div>
  );
}
