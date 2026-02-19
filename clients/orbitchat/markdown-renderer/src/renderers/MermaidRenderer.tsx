import React, { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';
import type { MermaidRendererProps } from '../types';

type MermaidTheme = 'light' | 'dark';

const DEFAULT_THEME_VARIABLES: Record<MermaidTheme, Record<string, string>> = {
  light: {
    background: '#ffffff',
    primaryColor: '#e0e7ff',
    secondaryColor: '#ddd6fe',
    tertiaryColor: '#fce7f3',
    primaryTextColor: '#111827',
    secondaryTextColor: '#4b5563',
    primaryBorderColor: '#6366f1',
    lineColor: '#111827',
    // Pie chart specific
    pie1: '#3b82f6',
    pie2: '#8b5cf6',
    pie3: '#ec4899',
    pie4: '#f59e0b',
    pie5: '#10b981',
    pie6: '#06b6d4',
    pie7: '#6366f1',
    pie8: '#ef4444',
    pieStrokeColor: '#ffffff',
    pieStrokeWidth: '2px',
    pieTitleTextColor: '#111827',
    pieLegendTextColor: '#374151',
  },
  dark: {
    background: '#1e293b',
    primaryColor: '#3b82f6',
    secondaryColor: '#8b5cf6',
    tertiaryColor: '#6366f1',
    primaryTextColor: '#f1f5f9',
    secondaryTextColor: '#cbd5e1',
    primaryBorderColor: '#60a5fa',
    lineColor: '#f1f5f9',
    // Pie chart specific - brighter colors for dark mode
    pie1: '#60a5fa',
    pie2: '#a78bfa',
    pie3: '#f472b6',
    pie4: '#fbbf24',
    pie5: '#34d399',
    pie6: '#22d3ee',
    pie7: '#818cf8',
    pie8: '#f87171',
    pieStrokeColor: '#1e293b',
    pieStrokeWidth: '2px',
    pieTitleTextColor: '#f1f5f9',
    pieLegendTextColor: '#e2e8f0',
  },
};

// Initialize mermaid once
let mermaidInitialized = false;
const initializeMermaid = () => {
  if (typeof window === 'undefined' || mermaidInitialized) return;

  try {
    mermaid.initialize({
      startOnLoad: false,
      theme: 'default',
      securityLevel: 'loose',
      themeVariables: DEFAULT_THEME_VARIABLES.light,
    });
    mermaidInitialized = true;
  } catch (err) {
    console.warn('Failed to initialize Mermaid:', err);
  }
};

const formatMermaidError = (err: unknown): string => {
  let errorMessage = 'Failed to render Mermaid diagram';

  if (err instanceof Error) {
    const message = err.message || '';

    if (message.includes('Syntax error')) {
      const lineMatch = message.match(/line\s+(\d+)/i);
      const tokenMatch = message.match(/token\s+['"]([^'"]+)['"]/i);
      const details = [];

      if (lineMatch) details.push(`Line ${lineMatch[1]}`);
      if (tokenMatch) details.push(`Unexpected token: ${tokenMatch[1]}`);

      errorMessage = `Syntax error${details.length ? ` (${details.join(', ')})` : ''}`;
    } else if (message) {
      errorMessage = message.length > 160 ? `${message.substring(0, 157)}...` : message;
    }
  } else if (typeof err === 'string') {
    errorMessage = err;
  }

  return errorMessage;
};

const readCSSVariable = (element: Element | null, name: string): string | undefined => {
  if (typeof window === 'undefined' || !element) return undefined;
  const value = window.getComputedStyle(element).getPropertyValue(name);
  if (!value) return undefined;
  const trimmed = value.trim();
  return trimmed.length ? trimmed : undefined;
};

const resolveThemeVariables = (theme: MermaidTheme, element: Element | null) => {
  const fallback = DEFAULT_THEME_VARIABLES[theme];
  if (typeof window === 'undefined' || !element) {
    return fallback;
  }

  const overrides: Record<string, string | undefined> = {
    background: readCSSVariable(element, '--md-bg-primary'),
    primaryColor: readCSSVariable(element, '--md-bg-secondary'),
    secondaryColor: readCSSVariable(element, '--md-bg-tertiary'),
    tertiaryColor: readCSSVariable(element, '--md-bg-primary'),
    primaryTextColor: readCSSVariable(element, '--md-text-primary'),
    secondaryTextColor: readCSSVariable(element, '--md-text-secondary'),
    primaryBorderColor: readCSSVariable(element, '--md-border-color'),
    lineColor: readCSSVariable(element, '--md-text-primary'),
  };

  const filteredEntries = Object.entries(overrides).filter(
    ([, value]) => typeof value === 'string' && value.length
  ) as Array<[string, string]>;

  return filteredEntries.length ? { ...fallback, ...Object.fromEntries(filteredEntries) } : fallback;
};

const detectThemeFromElement = (element: Element | null): MermaidTheme | null => {
  if (!element) return null;

  const attr = element.getAttribute('data-theme');
  if (attr === 'dark') return 'dark';
  if (attr === 'light') return 'light';

  if (element.classList.contains('dark')) return 'dark';
  if (element.classList.contains('light')) return 'light';

  return null;
};

export const MermaidRenderer: React.FC<MermaidRendererProps> = ({ code }) => {
  const hostRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const renderIdRef = useRef(0);

  const [error, setError] = useState<string | null>(null);
  const [svg, setSvg] = useState<string | null>(null);
  const [bindFunctions, setBindFunctions] = useState<((element: Element) => void) | null>(null);
  const [showErrorDetails, setShowErrorDetails] = useState(false);
  const [theme, setTheme] = useState<MermaidTheme>('light');
  const lastThemeRef = useRef<MermaidTheme>('light');

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const host = hostRef.current;
    if (!host) return;

    const markdownRoot = host.closest('.markdown-content') ?? host;
    const prefersDarkQuery = window.matchMedia?.('(prefers-color-scheme: dark)');

    const readTheme = (): MermaidTheme => {
      const prefersDark = Boolean(prefersDarkQuery?.matches);
      return (
        detectThemeFromElement(markdownRoot) ??
        detectThemeFromElement(document.documentElement) ??
        (prefersDark ? 'dark' : 'light')
      );
    };

    const updateTheme = () => {
      const next = readTheme();
      // Only update if theme actually changed to prevent re-render loops
      if (next !== lastThemeRef.current) {
        lastThemeRef.current = next;
        setTheme(next);
      }
    };

    updateTheme();

    const observer = new MutationObserver(updateTheme);
    observer.observe(markdownRoot, { attributes: true, attributeFilter: ['class', 'data-theme'] });

    let docObserver: MutationObserver | null = null;
    if (markdownRoot !== document.documentElement) {
      docObserver = new MutationObserver(updateTheme);
      docObserver.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['class', 'data-theme'],
      });
    }

    const handleMediaChange = () => updateTheme();
    prefersDarkQuery?.addEventListener('change', handleMediaChange);

    return () => {
      observer.disconnect();
      docObserver?.disconnect();
      prefersDarkQuery?.removeEventListener('change', handleMediaChange);
    };
  }, []);

  useEffect(() => {
    if (!code.trim()) {
      setSvg(null);
      setError(null);
      setBindFunctions(null);
      return;
    }

    const renderDiagram = async () => {
      const currentRenderId = ++renderIdRef.current;
      try {
        initializeMermaid();

        const diagramId = `mermaid-${Math.random().toString(36).substring(2, 11)}`;

        // Parse early to provide clearer syntax errors and avoid throwing during render
        await mermaid.parse(code);

        const themeTarget = hostRef.current?.closest('.markdown-content') ?? hostRef.current;
        const themeVariables = resolveThemeVariables(theme, themeTarget);

        // Re-initialize mermaid with current theme before rendering
        mermaid.initialize({
          startOnLoad: false,
          theme: theme === 'dark' ? 'dark' : 'default',
          securityLevel: 'loose',
          themeVariables,
          // Optimized diagram settings for readability and compact display
          flowchart: {
            useMaxWidth: true,
            htmlLabels: true,
            curve: 'basis',
            padding: 15,
            nodeSpacing: 50,
            rankSpacing: 50,
          },
          sequence: {
            useMaxWidth: true,
            diagramMarginX: 30,
            diagramMarginY: 15,
            actorMargin: 50,
            width: 120,
            height: 40,
            boxMargin: 8,
            boxTextMargin: 4,
            noteMargin: 10,
            messageMargin: 35,
            mirrorActors: true,
            actorFontSize: 13,
            messageFontSize: 12,
            noteFontSize: 12,
            wrap: true,
            wrapPadding: 10,
          },
          gantt: {
            useMaxWidth: true,
            barHeight: 24,
            barGap: 4,
            topPadding: 40,
            leftPadding: 80,
            gridLineStartPadding: 40,
            fontSize: 12,
            sectionFontSize: 13,
            numberSectionStyles: 4,
          },
          er: {
            useMaxWidth: true,
            fontSize: 12,
            entityPadding: 15,
          },
          pie: {
            useMaxWidth: true,
            textPosition: 0.75,
          },
          journey: {
            useMaxWidth: true,
            diagramMarginX: 30,
            diagramMarginY: 20,
            leftMargin: 100,
            width: 120,
            height: 50,
            boxMargin: 8,
            boxTextMargin: 4,
            noteMargin: 10,
            messageMargin: 30,
          },
          gitGraph: {
            useMaxWidth: true,
            diagramPadding: 8,
            nodeLabel: {
              width: 75,
              height: 100,
              x: -25,
              y: 0,
            },
          },
          class: {
            useMaxWidth: true,
            padding: 10,
          },
          state: {
            useMaxWidth: true,
            padding: 8,
            dividerMargin: 10,
          },
          mindmap: {
            useMaxWidth: true,
            padding: 10,
          },
          timeline: {
            useMaxWidth: true,
            padding: 10,
          },
          quadrantChart: {
            useMaxWidth: true,
          },
          sankey: {
            useMaxWidth: true,
          },
        });

        const result = await mermaid.render(diagramId, code);

        if (renderIdRef.current !== currentRenderId) {
          return;
        }

        setSvg(result.svg);
        setBindFunctions(() => (result.bindFunctions ? result.bindFunctions : null));
        setError(null);
      } catch (err) {
        if (renderIdRef.current !== currentRenderId) {
          return;
        }

        setError(formatMermaidError(err));
        setSvg(null);
        setBindFunctions(null);
        setShowErrorDetails(false); // Reset details visibility on new error
      }
    };

    renderDiagram();

    return () => {
      renderIdRef.current += 1;
    };
  }, [code, theme]);

  useEffect(() => {
    if (!svg || !bindFunctions || !containerRef.current) return;

    try {
      bindFunctions(containerRef.current);
    } catch (err) {
      console.warn('Failed to bind Mermaid interactions:', err);
    }
  }, [svg, bindFunctions]);

  const renderError = () => (
    <div className="graph-error">
      <div className="graph-error-header">
        <div className="graph-error-icon">⚠️</div>
        <div className="graph-error-content">
          <div className="graph-error-title">Mermaid Diagram Error</div>
          <div className="graph-error-message">{error}</div>
        </div>
      </div>
      <button
        className="graph-error-toggle"
        onClick={() => setShowErrorDetails(!showErrorDetails)}
        type="button"
      >
        {showErrorDetails ? 'Hide' : 'Show'} Details
      </button>
      {showErrorDetails && (
        <details className="graph-error-details" open>
          <summary style={{ cursor: 'pointer', marginBottom: '8px', fontWeight: 500 }}>
            Mermaid Code
          </summary>
          <pre
            style={{
              marginTop: '8px',
              fontSize: '0.8em',
              opacity: 0.8,
              padding: '8px',
              background: 'rgba(0, 0, 0, 0.05)',
              borderRadius: '4px',
              overflow: 'auto',
              maxHeight: '200px',
            }}
          >
            <code>{code}</code>
          </pre>
        </details>
      )}
    </div>
  );

  const renderContent = () => {
    if (error) {
      return renderError();
    }

    if (!svg) {
      return (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '30px 20px',
          color: 'var(--md-text-secondary, #6b7280)',
          minHeight: '120px',
        }}>
          <svg
            style={{
              animation: 'spin 1s linear infinite',
              marginBottom: '10px',
              width: '28px',
              height: '28px',
            }}
            viewBox="0 0 24 24"
            fill="none"
          >
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" strokeDasharray="32" strokeLinecap="round" />
          </svg>
          <span style={{ fontWeight: 500, fontSize: '14px' }}>
            Rendering diagram...
          </span>
          <style>{`
            @keyframes spin {
              from { transform: rotate(0deg); }
              to { transform: rotate(360deg); }
            }
          `}</style>
        </div>
      );
    }

    return (
      <div
        ref={containerRef}
        className="mermaid-svg-container"
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          width: '100%',
          overflow: 'auto',
        }}
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    );
  };

  return (
    <div
      className="graph-container mermaid-container"
      ref={hostRef}
      style={{
        padding: '16px',
        minHeight: '100px',
      }}
    >
      {renderContent()}
    </div>
  );
};
