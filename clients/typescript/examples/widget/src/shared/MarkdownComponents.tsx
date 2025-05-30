import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSanitize from 'rehype-sanitize';
import rehypeHighlight from 'rehype-highlight';

/**
 * Custom link component for ReactMarkdown that opens links in new tabs
 */
export const MarkdownLink: React.FC<React.AnchorHTMLAttributes<HTMLAnchorElement>> = (props) => {
  return (
    <a
      {...props}
      target="_blank"
      rel="noopener noreferrer"
      className="text-orange-500 hover:text-orange-700 underline"
    >
      {props.children}
    </a>
  );
};

export interface MarkdownRendererProps {
  content: string;
}

/**
 * Custom component for rendering Markdown content with consistent styling
 * Handles code blocks, links, lists, and other markdown elements
 */
export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ content }) => {
  return (
    <div className="prose prose-slate max-w-full dark:prose-invert overflow-hidden break-words" style={{ color: 'inherit' }}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize, rehypeHighlight]}
        components={{
          a: ({ node, ...props }) => (
            <a
              {...props}
              target="_blank"
              rel="noopener noreferrer"
              className="text-orange-500 hover:text-orange-700 underline"
            />
          ),
          p: ({ node, ...props }) => (
            <p style={{ color: 'inherit', margin: '0 0 0.5em 0' }} {...props} />
          ),
          pre: ({ node, ...props }) => (
            <pre className="overflow-x-auto p-4 rounded-md bg-gray-100 dark:bg-gray-800" {...props} />
          ),
          code: ({ node, ...props }) => (
            <code className="px-1 py-0.5 rounded-md bg-gray-100 dark:bg-gray-800 text-sm" {...props} />
          ),
          ul: ({ node, ...props }) => (
            <ul style={{ color: 'inherit', margin: '0.5em 0', paddingLeft: '1.5em' }} {...props} />
          ),
          ol: ({ node, ...props }) => (
            <ol style={{ color: 'inherit', margin: '0.5em 0', paddingLeft: '1.5em' }} {...props} />
          ),
          li: ({ node, ...props }) => (
            <li style={{ color: 'inherit', marginBottom: '0.25em' }} {...props} />
          ),
          h1: ({ node, ...props }) => (
            <h1 style={{ color: 'inherit', margin: '1em 0 0.5em 0' }} {...props} />
          ),
          h2: ({ node, ...props }) => (
            <h2 style={{ color: 'inherit', margin: '1em 0 0.5em 0' }} {...props} />
          ),
          h3: ({ node, ...props }) => (
            <h3 style={{ color: 'inherit', margin: '1em 0 0.5em 0' }} {...props} />
          ),
          h4: ({ node, ...props }) => (
            <h4 style={{ color: 'inherit', margin: '1em 0 0.5em 0' }} {...props} />
          ),
          h5: ({ node, ...props }) => (
            <h5 style={{ color: 'inherit', margin: '1em 0 0.5em 0' }} {...props} />
          ),
          h6: ({ node, ...props }) => (
            <h6 style={{ color: 'inherit', margin: '1em 0 0.5em 0' }} {...props} />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
};