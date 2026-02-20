import { useRef, useEffect } from 'react';
import { Message } from './Message';
import type { Message as MessageType } from '../types';

interface MessageListProps {
  messages: MessageType[];
  onReplyInThread?: (message: MessageType) => void;
}

export function MessageList({ messages, onReplyInThread }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  const topLevel = messages.filter((m) => !m.isThreadMessage);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, messages[messages.length - 1]?.content?.length]);

  return (
    <div className="message-list">
      {topLevel.map((msg) => {
        const threadReplies = messages.filter((m) => m.parentMessageId === msg.id);
        return (
          <Message
            key={msg.id}
            message={msg}
            onReplyInThread={onReplyInThread}
            threadReplies={threadReplies}
          />
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
