import React, { useEffect, useState, useRef } from 'react';
import DOMPurify from 'dompurify';
import type { SVGRendererProps } from '../types';

// Comprehensive list of allowed SVG tags
const ALLOWED_SVG_TAGS = [
  // Structure
  'svg', 'g', 'defs', 'symbol', 'use', 'switch', 'desc', 'title', 'metadata',
  // Shapes
  'path', 'circle', 'ellipse', 'rect', 'line', 'polyline', 'polygon',
  // Text
  'text', 'tspan', 'textPath',
  // Gradients & Patterns
  'linearGradient', 'radialGradient', 'stop', 'pattern',
  // Filters
  'filter', 'feBlend', 'feColorMatrix', 'feComponentTransfer', 'feComposite',
  'feConvolveMatrix', 'feDiffuseLighting', 'feDisplacementMap', 'feDistantLight',
  'feFlood', 'feFuncA', 'feFuncB', 'feFuncG', 'feFuncR', 'feGaussianBlur',
  'feImage', 'feMerge', 'feMergeNode', 'feMorphology', 'feOffset', 'fePointLight',
  'feSpecularLighting', 'feSpotLight', 'feTile', 'feTurbulence',
  // Clipping & Masking
  'clipPath', 'mask',
  // Markers
  'marker',
  // Animation (safe subset)
  'animate', 'animateTransform', 'animateMotion', 'set', 'mpath',
  // Images
  'image', 'foreignObject',
];

// Comprehensive list of allowed SVG attributes
const ALLOWED_SVG_ATTRS = [
  // Core attributes
  'id', 'class', 'style', 'lang', 'tabindex',
  // Positioning & sizing
  'x', 'y', 'x1', 'y1', 'x2', 'y2', 'cx', 'cy', 'r', 'rx', 'ry',
  'width', 'height', 'viewBox', 'preserveAspectRatio',
  // Paths
  'd', 'pathLength',
  // Transforms
  'transform', 'transform-origin',
  // Presentation attributes
  'fill', 'fill-opacity', 'fill-rule', 'stroke', 'stroke-width', 'stroke-opacity',
  'stroke-linecap', 'stroke-linejoin', 'stroke-dasharray', 'stroke-dashoffset',
  'stroke-miterlimit', 'opacity', 'visibility', 'display',
  // Colors
  'color', 'color-interpolation', 'color-interpolation-filters',
  // Text
  'font-family', 'font-size', 'font-style', 'font-weight', 'font-variant',
  'text-anchor', 'dominant-baseline', 'alignment-baseline', 'baseline-shift',
  'letter-spacing', 'word-spacing', 'text-decoration', 'writing-mode',
  'dx', 'dy', 'rotate', 'textLength', 'lengthAdjust',
  // Gradients & patterns
  'gradientUnits', 'gradientTransform', 'spreadMethod', 'offset', 'stop-color', 'stop-opacity',
  'patternUnits', 'patternContentUnits', 'patternTransform',
  // Filters
  'filterUnits', 'primitiveUnits', 'in', 'in2', 'result', 'stdDeviation',
  'type', 'values', 'mode', 'operator', 'k1', 'k2', 'k3', 'k4',
  'surfaceScale', 'diffuseConstant', 'specularConstant', 'specularExponent',
  'kernelMatrix', 'order', 'divisor', 'bias', 'targetX', 'targetY',
  'edgeMode', 'kernelUnitLength', 'preserveAlpha', 'baseFrequency',
  'numOctaves', 'seed', 'stitchTiles', 'scale', 'xChannelSelector', 'yChannelSelector',
  // Clipping & masking
  'clipPathUnits', 'clip-path', 'clip-rule', 'mask', 'maskUnits', 'maskContentUnits',
  // Markers
  'markerUnits', 'markerWidth', 'markerHeight', 'orient', 'refX', 'refY',
  'marker-start', 'marker-mid', 'marker-end',
  // Links
  'href', 'xlink:href',
  // Misc
  'xmlns', 'xmlns:xlink', 'version', 'points', 'overflow', 'vector-effect',
  // Animation attributes
  'attributeName', 'attributeType', 'begin', 'dur', 'end', 'min', 'max',
  'restart', 'repeatCount', 'repeatDur', 'calcMode', 'keyTimes', 'keySplines',
  'from', 'to', 'by', 'additive', 'accumulate',
];

// Check if SVG content appears incomplete (streaming)
const isLikelyIncomplete = (code: string): boolean => {
  const trimmed = code.trim();

  // Check for unclosed SVG tag
  if (trimmed.includes('<svg') && !trimmed.includes('</svg>')) {
    return true;
  }

  // Check for unbalanced tags (simple heuristic)
  const openTags = (trimmed.match(/<[a-zA-Z][^/>]*>/g) || []).length;
  const closeTags = (trimmed.match(/<\/[a-zA-Z][^>]*>/g) || []).length;
  const selfClosing = (trimmed.match(/<[a-zA-Z][^>]*\/>/g) || []).length;

  if (openTags > closeTags + selfClosing) {
    return true;
  }

  // Check for incomplete attribute
  if (trimmed.match(/\s+\w+\s*=\s*["'][^"']*$/)) {
    return true;
  }

  // Check for unclosed tag
  if (trimmed.match(/<[a-zA-Z][^>]*$/)) {
    return true;
  }

  return false;
};

// Ensure SVG has proper attributes for responsive display
const ensureResponsiveSvg = (svgContent: string): string => {
  // Parse to check/modify SVG attributes
  const parser = new DOMParser();
  const doc = parser.parseFromString(svgContent, 'image/svg+xml');
  const svg = doc.querySelector('svg');

  if (!svg) return svgContent;

  // If SVG has width/height but no viewBox, create one
  const width = svg.getAttribute('width');
  const height = svg.getAttribute('height');
  const viewBox = svg.getAttribute('viewBox');

  if (width && height && !viewBox) {
    const w = parseFloat(width) || 100;
    const h = parseFloat(height) || 100;
    svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  }

  // Ensure responsive sizing
  if (!svg.style.maxWidth) {
    svg.style.maxWidth = '100%';
  }
  if (!svg.style.height) {
    svg.style.height = 'auto';
  }

  return svg.outerHTML;
};

export const SVGRenderer: React.FC<SVGRendererProps> = ({ code }) => {
  const [sanitizedSvg, setSanitizedSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [showErrorDetails, setShowErrorDetails] = useState(false);
  const lastCodeRef = useRef<string>('');
  const lastUpdateTimeRef = useRef<number>(0);

  useEffect(() => {
    const trimmed = code.trim();
    if (!trimmed) {
      setSanitizedSvg(null);
      setError(null);
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
      // Don't try to render incomplete SVG
      return;
    }

    try {
      // Sanitize the SVG content with comprehensive allowlist
      const sanitized = DOMPurify.sanitize(code, {
        USE_PROFILES: { svg: true, svgFilters: true },
        ADD_TAGS: ALLOWED_SVG_TAGS,
        ADD_ATTR: ALLOWED_SVG_ATTRS,
        ALLOW_DATA_ATTR: false,
        FORBID_TAGS: ['script', 'iframe', 'object', 'embed'],
        FORBID_ATTR: ['onload', 'onerror', 'onclick', 'onmouseover'],
      });

      if (!sanitized || sanitized.trim().length === 0) {
        throw new Error('SVG sanitization resulted in empty content');
      }

      // Check if the result is actually an SVG
      if (!sanitized.includes('<svg')) {
        throw new Error('Content does not appear to be valid SVG');
      }

      // Make SVG responsive
      const responsiveSvg = ensureResponsiveSvg(sanitized);

      setSanitizedSvg(responsiveSvg);
      setError(null);
      setIsStreaming(false);
    } catch (err) {
      if (likelyStreaming) {
        setIsStreaming(true);
        setError(null);
      } else {
        setError(err instanceof Error ? err.message : 'Failed to process SVG');
        setIsStreaming(false);
      }
    }
  }, [code]);

  if (error) {
    return (
      <div className="graph-error">
        <div className="graph-error-header">
          <div className="graph-error-icon">⚠️</div>
          <div className="graph-error-content">
            <div className="graph-error-title">SVG Rendering Error</div>
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
          <pre style={{
            marginTop: '8px',
            fontSize: '0.8em',
            opacity: 0.8,
            padding: '8px',
            background: 'rgba(0, 0, 0, 0.05)',
            borderRadius: '4px',
            overflow: 'auto',
            maxHeight: '200px',
          }}>
            <code>{code}</code>
          </pre>
        )}
      </div>
    );
  }

  if (!sanitizedSvg || isStreaming) {
    return (
      <div className="graph-container svg-container">
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
            {isStreaming ? 'Receiving SVG data...' : 'Processing SVG...'}
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

  return (
    <div
      className="graph-container svg-container"
      style={{
        padding: '16px',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
      }}
    >
      <div
        dangerouslySetInnerHTML={{ __html: sanitizedSvg }}
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          maxWidth: '100%',
          overflow: 'auto',
        }}
      />
    </div>
  );
};

