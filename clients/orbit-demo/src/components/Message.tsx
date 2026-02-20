import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import remarkGfm from 'remark-gfm';
import type { Message as MessageType } from '../types';

interface MessageProps {
  message: MessageType;
  onReplyInThread?: (message: MessageType) => void;
  threadReplies?: MessageType[];
}

export function Message({ message, onReplyInThread, threadReplies = [] }: MessageProps) {
  const isUser = message.role === 'user';
  const canReplyInThread =
    !isUser &&
    !message.isStreaming &&
    message.supportsThreading &&
    onReplyInThread;

  return (
    <div className={`message message-${message.role}`}>
      <div className={`message-bubble ${isUser ? 'message-bubble-user' : 'message-bubble-assistant'}`}>
        {isUser ? (
          <p className="message-text message-text-user">{message.content}</p>
        ) : (
          <>
            <div className="message-content">
              {message.content ? (
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    code({ node, className, children, ...props }) {
                      const match = /language-(\w+)/.exec(className ?? '');
                      return match ? (
                        <SyntaxHighlighter
                          style={oneDark}
                          language={match[1]}
                          PreTag="div"
                          {...props}
                        >
                          {String(children).replace(/\n$/, '')}
                        </SyntaxHighlighter>
                      ) : (
                        <code className={className} {...props}>
                          {children}
                        </code>
                      );
                    },
                  }}
                >
                  {message.content}
                </ReactMarkdown>
              ) : null}
              {message.isStreaming && (
                <span className="message-streaming-cursor">▌</span>
              )}
            </div>
            {canReplyInThread && (
              <div className="message-actions">
                <button
                  type="button"
                  className="btn-reply-in-thread"
                  onClick={() => onReplyInThread(message)}
                >
                  {message.threadInfo ? 'Open replies' : 'Reply in thread'}
                </button>
              </div>
            )}
          </>
        )}
      </div>
      {!isUser && threadReplies.length > 0 && (
        <div className="thread-replies">
          {threadReplies.map((reply) => (
            <div key={reply.id} className={`thread-reply thread-reply-${reply.role}`}>
              <span className="thread-reply-role">{reply.role}:</span>
              {reply.role === 'user' ? (
                <span>{reply.content}</span>
              ) : (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{reply.content}</ReactMarkdown>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
