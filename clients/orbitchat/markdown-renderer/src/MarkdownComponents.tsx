import React from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import type { PluggableList } from 'unified';
import 'katex/dist/katex.min.css';
// Load mhchem for chemistry support (ESM build so it patches the same KaTeX instance)
import 'katex/contrib/mhchem';

import { preprocessMarkdown, containsMathNotation } from './preprocessing';
import { CodeBlock } from './CodeBlock';
import { BLOCK_LEVEL_TAGS, type MarkdownRendererProps } from './types';

/**
 * Custom link component for ReactMarkdown that opens links in new tabs
 */
export const MarkdownLink: React.FC<React.AnchorHTMLAttributes<HTMLAnchorElement>> = ({
  children,
  href = '',
  className = '',
  ...props
}) => {
  const childText = React.Children.toArray(children)
    .map((child) => (typeof child === 'string' ? child : ''))
    .join('')
    .trim();

  const isHttpLink = /^https?:\/\//i.test(href);
  const isBareUrl = Boolean(isHttpLink && childText && normalizeUrlText(childText) === normalizeUrlText(href));

  const parsed = isHttpLink ? parseUrl(href) : null;
  const showCardStyle = Boolean(isBareUrl && parsed);
  const classes = ['markdown-link', showCardStyle ? 'markdown-link--card' : 'markdown-link--inline', className]
    .filter(Boolean)
    .join(' ');

  return (
    <a
      {...props}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={classes}
    >
      <span className="markdown-link__content">
        {showCardStyle && parsed ? (
          <>
            <span className="markdown-link__hostname">{parsed.hostname}</span>
            {parsed.path && parsed.path !== '/' && (
              <span className="markdown-link__path">{parsed.path}</span>
            )}
          </>
        ) : (
          children
        )}
      </span>
      {isHttpLink && (
        <span className="markdown-link__icon" aria-hidden="true">
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              d="M8 16L16 8M16 8H9M16 8V15"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
      )}
    </a>
  );
};

function normalizeUrlText(value: string): string {
  return value.trim().replace(/\/$/, '');
}

function parseUrl(raw: string) {
  try {
    const url = new URL(raw);
    const hostname = url.hostname.replace(/^www\./i, '');
    const path = `${url.pathname}${url.search}${url.hash}` || '/';
    return { hostname, path };
  } catch {
    return null;
  }
}

/**
 * Enhanced Markdown renderer with robust currency and math handling
 */
export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({
  content,
  className = '',
  disableMath = false,
  enableGraphs = true,
  enableMermaid = true,
  enableSVG = true,
  enableCharts = true,
  enableMusic = true,
  enableSyntaxHighlighting = true,
  syntaxTheme = 'dark',
}) => {
  const processedContent = preprocessMarkdown(content);
  if (!processedContent) return null;

  const remarkPlugins: PluggableList = disableMath
    ? [remarkGfm]
    : [remarkGfm, [remarkMath, { singleDollarTextMath: true }]];

  const rehypePlugins: PluggableList = [];
  if (!disableMath) {
    rehypePlugins.push([rehypeKatex, {
      throwOnError: false,
      errorColor: '#cc0000',
      strict: false,
      trust: true,
      macros: {
        "\\RR": "\\mathbb{R}",
        "\\NN": "\\mathbb{N}",
        "\\ZZ": "\\mathbb{Z}",
        "\\QQ": "\\mathbb{Q}",
        "\\CC": "\\mathbb{C}",
        "\\dx": "\\,dx",
        "\\dy": "\\,dy",
        "\\dt": "\\,dt",
        "\\dz": "\\,dz",
      }
    }]);
  }

  const components: Partial<Components> = {
    a: MarkdownLink,
    code: (props) => {
      const { className, children, ...rest } = props;
      
      // Properly detect inline code:
      // In react-markdown v10, the most reliable way is:
      // 1. If inline prop is explicitly set, use that
      // 2. If there's a language- class, it's a block code (fenced code blocks have language)
      // 3. If no language class, it's inline code (single backticks like `word`)
      const hasLanguageClass = className && /language-/.test(className);
      const isInlineCode = 
        ('inline' in props && typeof props.inline === 'boolean' && props.inline) ||
        !hasLanguageClass;
      
      // Block-level code: fenced code blocks have language class
      const isBlockLevel = hasLanguageClass;
      
      return (
        <CodeBlock
          inline={isInlineCode}
          className={className}
          enableGraphs={enableGraphs}
          enableMermaid={enableMermaid}
          enableSVG={enableSVG}
          enableCharts={enableCharts}
          enableMusic={enableMusic}
          enableSyntaxHighlighting={enableSyntaxHighlighting}
          syntaxTheme={syntaxTheme}
          data-block-code={isBlockLevel ? 'true' : undefined}
          {...rest}
        >
          {children}
        </CodeBlock>
      );
    },
    p: ({ node, ...props }) => {
      const meaningfulChildren = React.Children.toArray(props.children).filter((child) => {
        return !(typeof child === 'string' && child.trim() === '');
      });

      const reactHasBlock = meaningfulChildren.some((child) => {
        if (!React.isValidElement(child)) return false;
        const childProps = child.props as Record<string, unknown> | undefined;
        if (childProps?.['data-block-code'] === 'true') return true;

        if (typeof child.type === 'string') {
          return BLOCK_LEVEL_TAGS.has(child.type);
        }

        return false;
      });

      const mdastHasBlock = node?.children?.some((child: { type: string; tagName?: string; properties?: { className?: string[] } }) => {
        if (child.type === 'code') return true; // fenced code blocks

        if (child.type === 'element') {
          if (child.tagName && BLOCK_LEVEL_TAGS.has(child.tagName)) return true;

          if (child.tagName === 'code') {
            const className = child.properties?.className;
            if (Array.isArray(className)) {
              return className.some((name) => typeof name === 'string' && name.startsWith('language-'));
            }
            return true;
          }
        }

        return false;
      });

      if (reactHasBlock || mdastHasBlock) {
        return <>{props.children}</>;
      }

      return <p {...props} />;
    },
  };

  return (
    <div className={`markdown-content ${className}`}>
      <ReactMarkdown
        remarkPlugins={remarkPlugins}
        rehypePlugins={rehypePlugins}
        components={components}
      >
        {processedContent}
      </ReactMarkdown>
    </div>
  );
};

// Re-export public APIs for backward compatibility
export { preprocessMarkdown, containsMathNotation };
export type { MarkdownRendererProps };
