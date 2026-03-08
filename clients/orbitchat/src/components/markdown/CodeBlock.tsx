import React, { Suspense, lazy, useState, useEffect, useRef } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus, vs } from 'react-syntax-highlighter/dist/esm/styles/prism';
import type { CodeBlockProps } from './types';

type ThemeMode = 'light' | 'dark';

const MermaidRenderer = lazy(() =>
  import('./renderers/MermaidRenderer').then((module) => ({ default: module.MermaidRenderer }))
);
const SVGRenderer = lazy(() =>
  import('./renderers/SVGRenderer').then((module) => ({ default: module.SVGRenderer }))
);
const ChartRenderer = lazy(() =>
  import('./renderers/ChartRenderer').then((module) => ({ default: module.ChartRenderer }))
);
const MusicRenderer = lazy(() =>
  import('./renderers/MusicRenderer').then((module) => ({ default: module.MusicRenderer }))
);

// Detect theme from element context (parent classes, data attributes, or system preference)
const detectTheme = (element: HTMLElement | null): ThemeMode => {
  if (!element) {
    // Fallback to system preference
    if (typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }
    return 'light';
  }

  // Check for explicit .light or .dark class on .markdown-content
  const markdownContent = element.closest('.markdown-content');
  if (markdownContent) {
    if (markdownContent.classList.contains('dark')) return 'dark';
    if (markdownContent.classList.contains('light')) return 'light';
  }

  // Check for .dark or .light class on any ancestor
  if (element.closest('.dark')) return 'dark';
  if (element.closest('.light')) return 'light';

  // Check for data-theme attribute on any ancestor
  const themedAncestor = element.closest('[data-theme]');
  if (themedAncestor) {
    const dataTheme = themedAncestor.getAttribute('data-theme');
    if (dataTheme === 'dark') return 'dark';
    if (dataTheme === 'light') return 'light';
  }

  // Fallback to system preference
  if (typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches) {
    return 'dark';
  }

  return 'light';
};

const useEffectiveTheme = (
  ref: React.RefObject<HTMLElement | null>,
  explicitTheme?: ThemeMode
): ThemeMode => {
  const [detectedTheme, setDetectedTheme] = useState<ThemeMode>('light');
  const lastThemeRef = useRef<ThemeMode>('light');

  useEffect(() => {
    if (explicitTheme) {
      return;
    }

    if (typeof window === 'undefined' || typeof document === 'undefined') {
      return;
    }

    const updateTheme = () => {
      const newTheme = detectTheme(ref.current);
      // Only update if theme actually changed to prevent re-render loops
      if (newTheme !== lastThemeRef.current) {
        lastThemeRef.current = newTheme;
        setDetectedTheme(newTheme);
      }
    };

    updateTheme();

    const prefersDarkQuery = window.matchMedia?.('(prefers-color-scheme: dark)') ?? null;
    const handleMediaChange = () => updateTheme();

    prefersDarkQuery?.addEventListener('change', handleMediaChange);

    const observer =
      typeof MutationObserver !== 'undefined'
        ? new MutationObserver(() => updateTheme())
        : null;

    if (observer) {
      const markdownContent = ref.current?.closest?.('.markdown-content') ?? null;
      if (markdownContent) {
        observer.observe(markdownContent, {
          attributes: true,
          attributeFilter: ['class', 'data-theme'],
        });
      }

      if (document.body) {
        observer.observe(document.body, {
          attributes: true,
          attributeFilter: ['class', 'data-theme'],
        });
      }
    }

    return () => {
      prefersDarkQuery?.removeEventListener('change', handleMediaChange);
      observer?.disconnect();
    };
  }, [explicitTheme, ref]);

  return explicitTheme ?? detectedTheme;
};

const LANGUAGE_ALIASES: Record<string, string> = {
  js: 'javascript',
  jsx: 'javascript',
  ts: 'typescript',
  tsx: 'tsx',
  sh: 'bash',
  shell: 'bash',
  shellsession: 'bash',
  yml: 'yaml',
  yaml: 'yaml',
  py: 'python',
  rb: 'ruby',
  kt: 'kotlin',
  md: 'markdown',
  csharp: 'csharp',
  'c#': 'csharp',
  'c++': 'cpp',
  tf: 'hcl',
  terraform: 'hcl',
  docker: 'dockerfile',
  dotenv: 'env',
  env: 'env',
  plaintext: 'text',
  text: 'text',
};

const extractLanguageFromClassName = (className?: string | null): string => {
  if (!className) return '';

  const languageMatch = className.match(/(?:^|\s)language-([^\s]+)/);
  if (!languageMatch) return '';

  const raw = languageMatch[1].toLowerCase();
  const sanitized = raw
    .split('{')[0]
    .split('[')[0]
    .split('<')[0]
    .split(':')[0]
    .trim()
    .replace(/[^a-z0-9+#-]+$/g, '');

  if (!sanitized) return '';

  return LANGUAGE_ALIASES[sanitized] ?? sanitized;
};

const getCodeFromChildren = (children: React.ReactNode): string => {
  return React.Children.toArray(children)
    .map((child) => {
      if (typeof child === 'string' || typeof child === 'number') {
        return String(child);
      }
      return '';
    })
    .join('')
    .replace(/\n$/, '');
};

// Copy button component for code blocks
const CopyButton: React.FC<{ code: string }> = ({ code }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = code;
      textArea.style.position = 'fixed';
      textArea.style.opacity = '0';
      document.body.appendChild(textArea);
      textArea.select();
      try {
        document.execCommand('copy');
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch (fallbackErr) {
        console.error('Failed to copy code:', fallbackErr);
      }
      document.body.removeChild(textArea);
    }
  };

  return (
    <button
      className="code-copy-button"
      onClick={handleCopy}
      title={copied ? 'Copied!' : 'Copy code'}
      aria-label={copied ? 'Copied!' : 'Copy code to clipboard'}
    >
      {copied ? (
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M13.5 4.5L6 12L2.5 8.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M5.5 4.5H3.5C2.94772 4.5 2.5 4.94772 2.5 5.5V12.5C2.5 13.0523 2.94772 13.5 3.5 13.5H10.5C11.0523 13.5 11.5 13.0523 11.5 12.5V10.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M6.5 2.5H12.5C13.0523 2.5 13.5 2.94772 13.5 3.5V9.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M9.5 6.5L13.5 2.5L9.5 2.5V6.5Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      )}
      <span className="code-copy-button-text">{copied ? 'Copied!' : 'Copy'}</span>
    </button>
  );
};

export const CodeBlock: React.FC<CodeBlockProps> = ({
  inline,
  className = '',
  children,
  enableGraphs = true,
  enableMermaid = true,
  enableSVG = true,
  enableCharts = true,
  enableMusic = true,
  enableSyntaxHighlighting = true,
  syntaxTheme,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const effectiveTheme = useEffectiveTheme(containerRef, syntaxTheme);
  const rendererFallback = <div className="markdown-code-block code-block-container">Loading renderer...</div>;

  // Handle inline code (always render as code)
  if (inline) {
    return <code className={className}>{children}</code>;
  }

  // Extract language from className (e.g., "language-mermaid" -> "mermaid")
  const language = extractLanguageFromClassName(className);
  const code = getCodeFromChildren(children);

  // Route to chart renderer (if enabled)
  if (enableCharts && (language === 'chart' || language === 'chart-json' || language === 'chart-table')) {
    return (
      <div ref={containerRef}>
        <Suspense fallback={rendererFallback}>
          <ChartRenderer code={code} language={language} />
        </Suspense>
      </div>
    );
  }

  // Route to music notation renderer (if enabled) - ABC notation only
  if (enableMusic && (language === 'abc' || language === 'music')) {
    return (
      <div ref={containerRef}>
        <Suspense fallback={rendererFallback}>
          <MusicRenderer code={code} />
        </Suspense>
      </div>
    );
  }

  // Route to graph renderers (if enabled)
  if (enableGraphs) {
    if (language === 'mermaid' && enableMermaid) {
      return (
        <div ref={containerRef}>
          <Suspense fallback={rendererFallback}>
            <MermaidRenderer code={code} />
          </Suspense>
        </div>
      );
    }

    if (language === 'svg' && enableSVG) {
      return (
        <div ref={containerRef}>
          <Suspense fallback={rendererFallback}>
            <SVGRenderer code={code} />
          </Suspense>
        </div>
      );
    }
  }

  // Use syntax highlighting for regular code blocks
  if (enableSyntaxHighlighting && language) {
    const style = effectiveTheme === 'light' ? vs : vscDarkPlus;
    return (
      <div ref={containerRef} className="syntax-highlighted-wrapper code-block-container">
        <CopyButton code={code} />
        <SyntaxHighlighter
          language={language}
          style={style}
          customStyle={{
            margin: '12px 0',
            borderRadius: '6px',
            fontSize: '0.9em',
          }}
          showLineNumbers={false}
        >
          {code}
        </SyntaxHighlighter>
      </div>
    );
  }

  // Fallback: render as normal code block
  // Use div instead of pre to avoid nesting issues with ReactMarkdown paragraph wrapping
  return (
    <div ref={containerRef} className={`markdown-code-block code-block-container ${className}`.trim()}>
      <CopyButton code={code} />
      <pre style={{ margin: 0, padding: 0, background: 'transparent', border: 'none' }}>
        <code>{code}</code>
      </pre>
    </div>
  );
};
