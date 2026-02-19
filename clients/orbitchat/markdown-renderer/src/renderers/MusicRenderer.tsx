import React, { useEffect, useRef, useState } from 'react';
import type { MusicRendererProps } from '../types';

type AbcJsLike = {
  renderAbc: (target: HTMLElement | string, code: string, options?: Record<string, unknown>) => unknown;
};

type WindowWithAbcjs = {
  ABCJS?: AbcJsLike;
};

// Dynamic import for abcjs to handle both ESM and CommonJS
let abcjs: AbcJsLike | null = null;
const loadAbcjs = async () => {
  if (typeof window === 'undefined') {
    throw new Error('abcjs requires a browser environment');
  }

  if (abcjs) return abcjs;

  try {
    // Import abcjs (CommonJS module, will be default export in ESM)
    const abcjsModule = await import('abcjs');

    // CommonJS modules are typically the default export when imported as ESM
    const abcjsLib = abcjsModule.default || abcjsModule;

    if (!abcjsLib) {
      throw new Error('abcjs module is empty');
    }

    if (typeof abcjsLib.renderAbc !== 'function') {
      throw new Error(`renderAbc is not a function. Available methods: ${Object.keys(abcjsLib).join(', ')}`);
    }

    abcjs = abcjsLib;
    return abcjs;
  } catch (err) {
    // Fallback: try to load from window if available
    const windowWithAbcjs = window as WindowWithAbcjs;
    if (typeof window !== 'undefined' && windowWithAbcjs.ABCJS) {
      abcjs = windowWithAbcjs.ABCJS;
      return abcjs;
    }
    const errorMessage = err instanceof Error ? err.message : 'Failed to load abcjs';
    throw new Error(`Failed to load abcjs: ${errorMessage}`);
  }
};

/**
 * Detects if the code is ABC notation
 */
const isAbcNotation = (code: string): boolean => {
  const trimmed = code.trim();
  // ABC notation typically starts with headers like X:, T:, M:, L:, K:
  return /^[XMTLK]:/m.test(trimmed) || /^X:\d+/m.test(trimmed);
};

/**
 * Check if ABC notation appears incomplete (streaming)
 */
const isLikelyIncomplete = (code: string): boolean => {
  const trimmed = code.trim();

  // Must have at least X: header to start
  if (!trimmed.includes('X:')) {
    return true;
  }

  // Check if we have the minimum required headers
  // ABC notation needs at least X: and K: (key signature) to render
  const hasKey = /^K:/m.test(trimmed);
  if (!hasKey) {
    return true;
  }

  // Check if the last line looks incomplete (ends mid-header or mid-note)
  const lines = trimmed.split('\n');
  const lastLine = lines[lines.length - 1].trim();

  // Incomplete header (has colon but nothing after, or just a letter)
  if (lastLine.match(/^[A-Z]:?\s*$/) && lastLine.length < 3) {
    return true;
  }

  // Line ends with a bar that suggests more content coming
  if (lastLine.endsWith('|') && !lastLine.endsWith('|]') && !lastLine.endsWith('||')) {
    // Could be incomplete, but also could be valid - check if very short
    const noteContent = lastLine.replace(/\|/g, '').trim();
    if (noteContent.length < 2) {
      return true;
    }
  }

  return false;
};

export const MusicRenderer: React.FC<MusicRendererProps> = ({ code }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isAbc, setIsAbc] = useState(false);
  const [showErrorDetails, setShowErrorDetails] = useState(false);
  const lastCodeRef = useRef<string>('');
  const lastUpdateTimeRef = useRef<number>(0);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // First effect: Detect ABC notation and streaming state
  useEffect(() => {
    const trimmed = code.trim();
    if (!trimmed) {
      setIsLoading(false);
      setIsAbc(false);
      setIsStreaming(false);
      return;
    }

    const now = Date.now();
    const timeSinceLastUpdate = now - lastUpdateTimeRef.current;
    const codeChanged = code !== lastCodeRef.current;

    lastCodeRef.current = code;
    lastUpdateTimeRef.current = now;

    // Detect streaming
    const incomplete = isLikelyIncomplete(trimmed);
    const rapidUpdate = codeChanged && timeSinceLastUpdate < 500 && timeSinceLastUpdate > 0;
    const likelyStreaming = incomplete || rapidUpdate;

    if (incomplete) {
      setIsStreaming(true);
      setIsLoading(true);
      setError(null);
      return;
    }

    if (isAbcNotation(code)) {
      setIsAbc(true);
      setError(null);
      if (likelyStreaming) {
        setIsStreaming(true);
      }
    } else {
      setIsAbc(false);
      if (likelyStreaming) {
        setIsStreaming(true);
        setError(null);
      } else {
        setError('Unable to detect ABC notation. Expected ABC notation starting with headers like X:, T:, M:, L:, or K:');
        setIsLoading(false);
        setIsStreaming(false);
      }
    }
  }, [code]);

  // Second effect: Render ABC notation after container is mounted
  useEffect(() => {
    if (!isAbc || !code.trim()) {
      return;
    }

    // If streaming, debounce the render
    if (isStreaming) {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }

      debounceTimerRef.current = setTimeout(() => {
        setIsStreaming(false);
      }, 400);
    }

    const renderAbc = async () => {
      try {
        setIsLoading(true);

        // Wait for container to be available (with retries)
        let retries = 0;
        const maxRetries = 10;
        while (!containerRef.current && retries < maxRetries) {
          await new Promise(resolve => setTimeout(resolve, 50));
          retries++;
        }

        if (!containerRef.current) {
          throw new Error('Container element not found after waiting');
        }

        const abcjsLib = await loadAbcjs();

        // Clear previous content
        containerRef.current.innerHTML = '';

        // Render ABC notation
        abcjsLib.renderAbc(containerRef.current, code, {
          responsive: 'resize',
          staffwidth: 740,
          paddingleft: 0,
          paddingright: 0,
          paddingtop: 15,
          paddingbottom: 15,
          scale: 1.0,
        });

        setError(null);
        setIsLoading(false);
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Failed to render ABC notation';
        setError(errorMessage);
        setIsLoading(false);
      }
    };

    renderAbc();

    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [code, isAbc, isStreaming]);

  if (error) {
    return (
      <div className="graph-error">
        <div className="graph-error-header">
          <div className="graph-error-icon">⚠️</div>
          <div className="graph-error-content">
            <div className="graph-error-title">ABC Notation Rendering Error</div>
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
              ABC Notation Code
            </summary>
            <pre style={{ 
              marginTop: '8px', 
              fontSize: '0.8em', 
              opacity: 0.8,
              padding: '8px',
              background: 'rgba(0, 0, 0, 0.05)',
              borderRadius: '4px',
              overflow: 'auto',
              maxHeight: '200px'
            }}>
              <code>{code}</code>
            </pre>
          </details>
        )}
      </div>
    );
  }

  // Show loading/streaming state
  if ((isLoading || isStreaming) && !isAbc) {
    return (
      <div className="graph-container music-container abc-container">
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
            {isStreaming ? 'Receiving music notation...' : 'Loading music notation...'}
          </span>
          <style>{`
            @keyframes spin {
              from { transform: rotate(0deg); }
              to { transform: rotate(360deg); }
            }
          `}</style>
        </div>
      </div>
    );
  }

  // Render ABC notation - always render container so ref is available
  if (isAbc) {
    return (
      <div
        className="graph-container music-container abc-container"
        style={{
          padding: '16px',
          position: 'relative',
        }}
      >
        {isStreaming && (
          <div
            style={{
              position: 'absolute',
              top: '8px',
              right: '8px',
              display: 'flex',
              alignItems: 'center',
              padding: '4px 8px',
              backgroundColor: 'rgba(59, 130, 246, 0.1)',
              borderRadius: '4px',
              fontSize: '12px',
              color: '#3b82f6',
              zIndex: 10,
            }}
          >
            <svg
              style={{
                animation: 'spin 1s linear infinite',
                marginRight: '4px',
                width: '12px',
                height: '12px'
              }}
              viewBox="0 0 24 24"
              fill="none"
            >
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" strokeDasharray="32" strokeLinecap="round" />
            </svg>
            Updating...
            <style>{`
              @keyframes spin {
                from { transform: rotate(0deg); }
                to { transform: rotate(360deg); }
              }
            `}</style>
          </div>
        )}
        {isLoading && !isStreaming && (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '20px',
            color: 'var(--md-text-secondary, #6b7280)',
            minHeight: '80px',
          }}>
            <svg
              style={{
                animation: 'spin 1s linear infinite',
                marginBottom: '8px',
                width: '24px',
                height: '24px',
              }}
              viewBox="0 0 24 24"
              fill="none"
            >
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" strokeDasharray="32" strokeLinecap="round" />
            </svg>
            <span style={{ fontSize: '13px' }}>Rendering notation...</span>
            <style>{`
              @keyframes spin {
                from { transform: rotate(0deg); }
                to { transform: rotate(360deg); }
              }
            `}</style>
          </div>
        )}
        <div
          ref={containerRef}
          style={{
            display: 'flex',
            justifyContent: 'center',
            overflow: 'auto',
          }}
        />
      </div>
    );
  }

  return null;
};
