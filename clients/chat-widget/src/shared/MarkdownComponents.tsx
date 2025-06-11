import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import 'katex/dist/katex.min.css';

/**
 * Preprocesses markdown content to handle common formatting issues
 */
export const preprocessMarkdown = (content: string): string => {
  if (!content || typeof content !== 'string') {
    return '';
  }

  let processed = content;

  try {
    // Normalize line endings
    processed = processed.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

    // Convert LaTeX-style math delimiters to markdown math syntax
    // Handle display math: \[ ... \] → $$ ... $$
    processed = processed.replace(/\\\[\s*([\s\S]*?)\s*\\\]/g, (match, mathContent) => {
      const cleanContent = mathContent.trim();
      return cleanContent ? `\n$$${cleanContent}$$\n` : match;
    });
    
    // Handle inline math: \( ... \) → $ ... $
    processed = processed.replace(/\\\(\s*([\s\S]*?)\s*\\\)/g, (match, mathContent) => {
      const cleanContent = mathContent.trim();
      return cleanContent ? `$${cleanContent}$` : match;
    });

    // Fix any malformed math delimiters that might exist
    // Clean up any double dollars that got concatenated incorrectly
    processed = processed.replace(/\$\$\$+/g, '$$');
    processed = processed.replace(/\$+([^$\n]+)\$+/g, '$$$1$$');
    
    // Ensure proper spacing around display math blocks
    processed = processed.replace(/([^\n])\$\$([^$\n])/g, '$1\n$$$$2');
    processed = processed.replace(/([^$\n])\$\$([^\n])/g, '$$1$$\n$2');

    // Fix excessive whitespace and normalize paragraph breaks
    processed = processed.replace(/\n{3,}/g, '\n\n');
    
    // Handle list items with proper spacing
    processed = processed.replace(/\n(\s*[-*+])\s*/g, '\n$1 ');
    processed = processed.replace(/\n(\s*\d+\.)\s*/g, '\n$1 ');
    
    // Fix spacing around headers
    processed = processed.replace(/\n(#{1,6})\s*([^\n]+)\n/g, '\n\n$1 $2\n\n');
    
    // Ensure code blocks have proper spacing
    processed = processed.replace(/\n```/g, '\n\n```');
    processed = processed.replace(/```\n/g, '```\n\n');
    
    // Clean up trailing whitespace on lines
    processed = processed.replace(/[ \t]+$/gm, '');
    
    // Auto-linkify URLs that aren't already markdown links (but not inside math blocks)
    const urlRegex = /(?<!\]\()(?<!\$)(https?:\/\/[^\s)$]+)(?!\))(?!\$)/g;
    processed = processed.replace(urlRegex, '[$1]($1)');
    
    // Final cleanup: ensure single trailing newline
    processed = processed.trim();
    if (processed && !processed.endsWith('\n')) {
      processed += '\n';
    }

  } catch (error) {
    console.warn('Error preprocessing markdown:', error);
    return content; // Return original content if preprocessing fails
  }

  return processed;
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
      className="text-blue-600 hover:text-blue-800 underline decoration-1 underline-offset-2 transition-colors duration-200"
      style={{
        wordBreak: 'break-word',
        overflowWrap: 'break-word'
      }}
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
 * Enhanced Markdown renderer with better formatting and spacing control
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
    <div 
      className={`markdown-content ${className}`}
      style={{
        color: 'inherit',
        fontSize: 'inherit',
        lineHeight: '1.6',
        wordBreak: 'break-word',
        overflowWrap: 'break-word',
        maxWidth: '100%'
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkMath, remarkGfm]}
        rehypePlugins={[rehypeKatex]}
        components={{
          // Links
          a: MarkdownLink,
          
          // Paragraphs with proper spacing
          p: ({ children, ...props }) => (
            <p 
              {...props}
              style={{ 
                color: 'inherit',
                margin: '0 0 12px 0',
                lineHeight: '1.6',
                wordBreak: 'break-word',
                overflowWrap: 'break-word'
              }}
            >
              {children}
            </p>
          ),

          // Headers with consistent spacing
          h1: ({ children, ...props }) => (
            <h1 {...props} style={{ 
              color: 'inherit', 
              margin: '20px 0 12px 0', 
              fontSize: '1.5em',
              fontWeight: '600',
              lineHeight: '1.4'
            }}>
              {children}
            </h1>
          ),
          h2: ({ children, ...props }) => (
            <h2 {...props} style={{ 
              color: 'inherit', 
              margin: '18px 0 10px 0', 
              fontSize: '1.3em',
              fontWeight: '600',
              lineHeight: '1.4'
            }}>
              {children}
            </h2>
          ),
          h3: ({ children, ...props }) => (
            <h3 {...props} style={{ 
              color: 'inherit', 
              margin: '16px 0 8px 0', 
              fontSize: '1.2em',
              fontWeight: '600',
              lineHeight: '1.4'
            }}>
              {children}
            </h3>
          ),
          h4: ({ children, ...props }) => (
            <h4 {...props} style={{ 
              color: 'inherit', 
              margin: '14px 0 6px 0', 
              fontSize: '1.1em',
              fontWeight: '600',
              lineHeight: '1.4'
            }}>
              {children}
            </h4>
          ),
          h5: ({ children, ...props }) => (
            <h5 {...props} style={{ 
              color: 'inherit', 
              margin: '12px 0 6px 0', 
              fontSize: '1.05em',
              fontWeight: '600',
              lineHeight: '1.4'
            }}>
              {children}
            </h5>
          ),
          h6: ({ children, ...props }) => (
            <h6 {...props} style={{ 
              color: 'inherit', 
              margin: '12px 0 6px 0', 
              fontSize: '1em',
              fontWeight: '600',
              lineHeight: '1.4'
            }}>
              {children}
            </h6>
          ),

          // Lists with proper spacing
          ul: ({ children, ...props }) => (
            <ul 
              {...props}
              style={{ 
                color: 'inherit', 
                margin: '8px 0 12px 0', 
                paddingLeft: '20px',
                listStyleType: 'disc'
              }}
            >
              {children}
            </ul>
          ),
          ol: ({ children, ...props }) => (
            <ol 
              {...props}
              style={{ 
                color: 'inherit', 
                margin: '8px 0 12px 0', 
                paddingLeft: '20px',
                listStyleType: 'decimal'
              }}
            >
              {children}
            </ol>
          ),
          li: ({ children, ...props }) => (
            <li 
              {...props}
              style={{ 
                color: 'inherit', 
                marginBottom: '4px',
                lineHeight: '1.6'
              }}
            >
              {children}
            </li>
          ),

          // Code blocks with better styling
          pre: ({ children, ...props }) => (
            <pre 
              {...props}
              style={{
                overflow: 'auto',
                padding: '12px 16px',
                margin: '12px 0',
                borderRadius: '6px',
                backgroundColor: 'rgba(0, 0, 0, 0.06)',
                border: '1px solid rgba(0, 0, 0, 0.1)',
                fontSize: '0.9em',
                lineHeight: '1.4',
                fontFamily: 'Monaco, Consolas, "Liberation Mono", "Courier New", monospace'
              }}
            >
              {children}
            </pre>
          ),

          // Inline code
          code: ({ children, ...props }) => {
            const codeProps = props as any; // Type assertion to handle ReactMarkdown's custom props
            if (codeProps.inline) {
              return (
                <code 
                  {...props}
                  style={{
                    padding: '2px 6px',
                    borderRadius: '4px',
                    backgroundColor: 'rgba(0, 0, 0, 0.06)',
                    border: '1px solid rgba(0, 0, 0, 0.1)',
                    fontSize: '0.9em',
                    fontFamily: 'Monaco, Consolas, "Liberation Mono", "Courier New", monospace'
                  }}
                >
                  {children}
                </code>
              );
            }
            return (
              <code 
                {...props}
                style={{
                  fontSize: '0.9em',
                  fontFamily: 'Monaco, Consolas, "Liberation Mono", "Courier New", monospace'
                }}
              >
                {children}
              </code>
            );
          },

          // Blockquotes
          blockquote: ({ children, ...props }) => (
            <blockquote 
              {...props}
              style={{
                margin: '12px 0',
                paddingLeft: '16px',
                borderLeft: '4px solid rgba(0, 0, 0, 0.2)',
                fontStyle: 'italic',
                color: 'inherit',
                opacity: 0.8
              }}
            >
              {children}
            </blockquote>
          ),

          // Horizontal rules
          hr: ({ ...props }) => (
            <hr 
              {...props}
              style={{
                margin: '20px 0',
                border: 'none',
                borderTop: '1px solid rgba(0, 0, 0, 0.2)',
                opacity: 0.5
              }}
            />
          ),

          // Tables
          table: ({ children, ...props }) => (
            <div style={{ overflowX: 'auto', margin: '12px 0' }}>
              <table 
                {...props}
                style={{
                  width: '100%',
                  borderCollapse: 'collapse',
                  fontSize: '0.9em'
                }}
              >
                {children}
              </table>
            </div>
          ),
          thead: ({ children, ...props }) => (
            <thead {...props} style={{ backgroundColor: 'rgba(0, 0, 0, 0.05)' }}>
              {children}
            </thead>
          ),
          th: ({ children, ...props }) => (
            <th 
              {...props}
              style={{
                padding: '8px 12px',
                border: '1px solid rgba(0, 0, 0, 0.2)',
                fontWeight: '600',
                textAlign: 'left'
              }}
            >
              {children}
            </th>
          ),
          td: ({ children, ...props }) => (
            <td 
              {...props}
              style={{
                padding: '8px 12px',
                border: '1px solid rgba(0, 0, 0, 0.2)'
              }}
            >
              {children}
            </td>
          ),

          // Line breaks
          br: ({ ...props }) => <br {...props} />,

        }}
      >
        {processedContent}
      </ReactMarkdown>
    </div>
  );
};