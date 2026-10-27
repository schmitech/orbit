import React, { Suspense, lazy, useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark, oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import type { CodeBlockProps } from './types';

type ThemeMode = 'light' | 'dark';

// oneDark's default comment color (hsl(220, 10%, 40%)) sits too close to the
// code block background to read comfortably. Lighten it, and make sure no
// background ever sneaks in behind the comment text.
const CODE_SYNTAX_THEMES: Record<ThemeMode, typeof oneDark> = {
  light: oneLight,
  dark: {
    ...oneDark,
    comment: { ...oneDark.comment, color: '#8992a4', background: 'transparent' },
    prolog: { ...oneDark.prolog, color: '#8992a4', background: 'transparent' },
    cdata: { ...oneDark.cdata, color: '#8992a4', background: 'transparent' },
  },
};

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

// Display casing for the language label shown in the code block header.
// Defaults to the raw language string when not listed here.
const LANGUAGE_LABELS: Record<string, string> = {
  javascript: 'JavaScript',
  typescript: 'TypeScript',
  tsx: 'TSX',
  jsx: 'JSX',
  bash: 'Bash',
  yaml: 'YAML',
  python: 'Python',
  ruby: 'Ruby',
  kotlin: 'Kotlin',
  markdown: 'Markdown',
  csharp: 'C#',
  cpp: 'C++',
  hcl: 'Terraform',
  dockerfile: 'Dockerfile',
  env: 'Env',
  json: 'JSON',
  html: 'HTML',
  css: 'CSS',
  sql: 'SQL',
  graphql: 'GraphQL',
  text: 'Plain text',
};

const getLanguageLabel = (language: string): string => LANGUAGE_LABELS[language] ?? language;

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

// Some models label an SVG fence as `xml`/`html` or leave it untagged. When the
// declared language doesn't say "svg" but the content plainly is one, still
// route it to SVGRenderer instead of falling back to a plain code block.
const SVG_FALLBACK_LANGUAGES = new Set(['', 'xml', 'html']);

const looksLikeRawSvg = (code: string): boolean => {
  const trimmed = code.trim();
  return trimmed.startsWith('<svg') && trimmed.endsWith('</svg>');
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
  const { t } = useTranslation();
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
      title={copied ? t('markdown.codeBlock.copied') : t('markdown.codeBlock.copyTitle')}
      aria-label={copied ? t('markdown.codeBlock.copied') : t('markdown.codeBlock.copyAriaLabel')}
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
      <span className="code-copy-button-text">{copied ? t('markdown.codeBlock.copied') : t('markdown.codeBlock.copyLabel')}</span>
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
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const effectiveTheme = useEffectiveTheme(containerRef, syntaxTheme);
  const rendererFallback = <div className="markdown-code-block code-block-container">{t('markdown.codeBlock.loadingRenderer')}</div>;

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

    if (
      enableSVG &&
      (language === 'svg' || (SVG_FALLBACK_LANGUAGES.has(language) && looksLikeRawSvg(code)))
    ) {
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
    const style = CODE_SYNTAX_THEMES[effectiveTheme];
    const lineCount = code.split('\n').length;
    return (
      <div ref={containerRef} className={`code-block code-block--${effectiveTheme}`}>
        <div className="code-block-header">
          <span className="code-block-language">{getLanguageLabel(language)}</span>
          <CopyButton code={code} />
        </div>
        <SyntaxHighlighter
          language={language}
          style={style}
          customStyle={{ margin: 0, padding: '14px 16px' }}
          codeTagProps={{ style: { fontFamily: 'inherit' } }}
          showLineNumbers={lineCount > 1}
          lineNumberStyle={{ color: effectiveTheme === 'light' ? '#9d9d9f' : '#5c6370' }}
        >
          {code}
        </SyntaxHighlighter>
      </div>
    );
  }

  // Fallback: render as a plain code block with the same editor-style chrome
  return (
    <div ref={containerRef} className={`code-block code-block--${effectiveTheme} ${className}`.trim()}>
      <div className="code-block-header">
        <span className="code-block-language">{getLanguageLabel(language || 'text')}</span>
        <CopyButton code={code} />
      </div>
      <pre className="code-block-body">
        <code>{code}</code>
      </pre>
    </div>
  );
};
