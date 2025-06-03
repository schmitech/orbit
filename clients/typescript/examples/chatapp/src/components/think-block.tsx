import React, { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface ThinkBlockProps {
  content: string;
  live?: boolean;
  duration?: string;
}

export default function ThinkBlock({ content, live = false, duration }: ThinkBlockProps) {
  // Live timer state
  const [seconds, setSeconds] = useState(0);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  // Collapsible state
  const [open, setOpen] = useState(live ? true : false);

  useEffect(() => {
    if (live) {
      intervalRef.current = setInterval(() => {
        setSeconds((s) => +(s + 0.1).toFixed(2));
      }, 100);
      return () => {
        if (intervalRef.current) clearInterval(intervalRef.current);
      };
    }
  }, [live]);

  // Always open in live mode, collapsible in non-live mode
  const isOpen = live ? true : open;

  return (
    <div className={"my-4 rounded-xl border border-dashed border-blue-400 bg-background/50"}>
      <div className="flex items-center px-4 pt-2 pb-1 select-none">
        {/* Chevron (button for collapsible, static for live) */}
        {live ? (
          <span className="mr-2 inline-block transition-transform rotate-0" style={{ width: 20, height: 20 }}>
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M7 8l3 3 3-3" stroke="#60a5fa" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </span>
        ) : (
          <button
            className="mr-2 flex items-center justify-center focus:outline-none transition-transform"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            style={{ height: 24, width: 24 }}
          >
            <span
              className={`inline-block transition-transform duration-200 ${open ? "rotate-0" : "-rotate-90"}`}
              style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 20, width: 20 }}
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M7 8l3 3 3-3" stroke="#60a5fa" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </span>
          </button>
        )}
        {/* Label */}
        <span className="text-blue-400 font-medium text-sm mr-3">Thoughts</span>
        {/* Header */}
        {live ? (
          <span className="italic text-sm text-muted-foreground flex items-center gap-2">
            Thinking for {seconds.toFixed(2)} seconds
            <span className="ml-1 inline-block align-middle">
              <span className="w-4 h-4 border-2 border-blue-300 border-t-transparent rounded-full inline-block animate-spin"></span>
            </span>
          </span>
        ) : (
          <span className="italic text-sm text-muted-foreground">
            {duration ? `Thought for ${duration}` : "Thought"}
          </span>
        )}
      </div>
      {isOpen && (
        <div className="px-6 pb-4 pt-1 text-sm text-muted-foreground">
          <Markdown remarkPlugins={[remarkGfm]}>{content}</Markdown>
        </div>
      )}
    </div>
  );
} 