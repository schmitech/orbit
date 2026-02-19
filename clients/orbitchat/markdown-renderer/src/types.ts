import type { ReactNode } from 'react';

/**
 * Props for Mermaid diagram renderer
 */
export interface MermaidRendererProps {
  code: string;
}

/**
 * Props for SVG renderer
 */
export interface SVGRendererProps {
  code: string;
}

/**
 * Props for chart renderer
 */
export interface ChartRendererProps {
  code: string;
  language: string;
}

/**
 * Props for music notation renderer
 */
export interface MusicRendererProps {
  code: string;
}

export type ChartValueFormat = 'number' | 'compact' | 'currency' | 'percent';

export interface ChartFormatterConfig {
  format?: ChartValueFormat;
  currency?: string;
  decimals?: number;
  minimumFractionDigits?: number;
  maximumFractionDigits?: number;
  prefix?: string;
  suffix?: string;
}

export interface ChartSeriesConfig {
  key: string;
  name?: string;
  type?: 'bar' | 'line' | 'area' | 'scatter';
  color?: string;
  yAxisId?: 'left' | 'right';
  stackId?: string;
  strokeWidth?: number;
  dot?: boolean;
  opacity?: number;
}

export interface ChartReferenceLineConfig {
  x?: string | number;
  y?: string | number;
  label?: string;
  color?: string;
  strokeDasharray?: string;
  position?: 'start' | 'middle' | 'end';
}

/**
 * Chart configuration interface
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type ChartDataItem = Record<string, any>;

export interface ChartConfig {
  type: 'bar' | 'line' | 'pie' | 'area' | 'scatter' | 'composed';
  title?: string;
  description?: string;
  data: ChartDataItem[];
  dataKeys?: string[];
  xKey?: string;
  xAxisType?: 'category' | 'number';
  colors?: string[];
  width?: number;
  height?: number;
  stacked?: boolean;
  showLegend?: boolean;
  showGrid?: boolean;
  xAxisLabel?: string;
  yAxisLabel?: string;
  yAxisRightLabel?: string;
  formatter?: ChartFormatterConfig;
  series?: ChartSeriesConfig[];
  referenceLines?: ChartReferenceLineConfig[];
}

/**
 * Props for the main MarkdownRenderer component
 */
export interface MarkdownRendererProps {
  content: string;
  className?: string;
  /**
   * Optional flag to disable math rendering entirely if needed
   */
  disableMath?: boolean;
  /**
   * Enable graph rendering (default: true)
   */
  enableGraphs?: boolean;
  /**
   * Enable Mermaid diagram rendering (default: true)
   */
  enableMermaid?: boolean;
  /**
   * Enable SVG rendering (default: true)
   */
  enableSVG?: boolean;
  /**
   * Enable syntax highlighting for code blocks (default: true)
   */
  enableSyntaxHighlighting?: boolean;
  /**
   * Syntax highlighting theme: 'dark' or 'light' (default: 'dark')
   */
  syntaxTheme?: 'dark' | 'light';
  /**
   * Enable chart rendering (default: true)
   */
  enableCharts?: boolean;
  /**
   * Enable music notation rendering (default: true)
   */
  enableMusic?: boolean;
}

/**
 * Props for CodeBlock component
 */
export interface CodeBlockProps {
  inline?: boolean;
  className?: string;
  children?: ReactNode;
  'data-block-code'?: string;
  enableGraphs?: boolean;
  enableMermaid?: boolean;
  enableSVG?: boolean;
  enableCharts?: boolean;
  enableMusic?: boolean;
  enableSyntaxHighlighting?: boolean;
  syntaxTheme?: 'dark' | 'light';
}

/**
 * Set of block-level HTML tags that should not be wrapped in paragraph tags
 */
export const BLOCK_LEVEL_TAGS = new Set([
  'div',
  'pre',
  'blockquote',
  'ul',
  'ol',
  'table',
  'thead',
  'tbody',
  'tr',
  'td',
  'th',
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'section',
  'article',
  'figure',
]);
