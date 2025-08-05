import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import 'katex/dist/katex.min.css';
import '../MarkdownStyles.css';

/**
 * Simplified markdown preprocessing that only handles essential conversions
 */
export const preprocessMarkdown = (content: string): string => {
  if (!content || typeof content !== 'string') {
    return '';
  }

  try {
    let processed = content;
    
    // Normalize line endings - this is safe and necessary
    processed = processed.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

    // Convert LaTeX-style math delimiters to markdown math syntax
    // Handle display math: \[ ... \] → $$ ... $$
    processed = processed.replace(/\\\[([\s\S]*?)\\\]/g, '\n$$$1$$\n');
    
    // Handle inline math: \( ... \) → $ ... $
    processed = processed.replace(/\\\(([\s\S]*?)\\\)/g, '$$1$');
    
    // Final cleanup: ensure single trailing newline
    processed = processed.trim();
    if (processed && !processed.endsWith('\n')) {
      processed += '\n';
    }

    return processed;

  } catch (error) {
    console.warn('Error preprocessing markdown:', error);
    return content; // Return original content if preprocessing fails
  }
};

/**
 * Custom link component for ReactMarkdown that opens links in new tabs
 */
export const MarkdownLink: React.FC<React.AnchorHTMLAttributes<HTMLAnchorElement>> = ({ 
  children, 
  href, 
  ...props 
}) => {
  return (
    <a
      {...props}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
    >
      {children}
    </a>
  );
};

export interface MarkdownRendererProps {
  content: string;
  className?: string;
}

/**
 * Enhanced Markdown renderer with CSS-based styling
 */
export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ 
  content, 
  className = '' 
}) => {
  const processedContent = preprocessMarkdown(content);

  if (!processedContent) {
    return null;
  }

  return (
    <div className={`markdown-content ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkMath, remarkGfm]}
        rehypePlugins={[rehypeKatex]}
        components={{
          // Links
          a: MarkdownLink,
        }}
      >
        {processedContent}
      </ReactMarkdown>
    </div>
  );
};