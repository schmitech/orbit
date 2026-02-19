import React, { useEffect, useState, useRef } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Label,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { Formatter, NameType, ValueType } from 'recharts/types/component/DefaultTooltipContent';
import type {
  ChartConfig,
  ChartDataItem,
  ChartFormatterConfig,
  ChartReferenceLineConfig,
  ChartRendererProps,
  ChartSeriesConfig,
} from '../types';

// Default color palette for charts
export const DEFAULT_COLORS = [
  '#3b82f6',
  '#8b5cf6',
  '#ec4899',
  '#f59e0b',
  '#10b981',
  '#06b6d4',
  '#6366f1',
  '#ef4444',
];

const MONTH_ABBREVIATIONS: Record<string, string> = {
  january: 'Jan',
  february: 'Feb',
  march: 'Mar',
  april: 'Apr',
  may: 'May',
  june: 'Jun',
  july: 'Jul',
  august: 'Aug',
  september: 'Sep',
  october: 'Oct',
  november: 'Nov',
  december: 'Dec',
};

const CHART_THEME_VARS = {
  axis: 'var(--md-chart-axis, #374151)',
  grid: 'var(--md-chart-grid, #e5e7eb)',
  text: 'var(--md-chart-text, #000000)',
  tooltipBg: 'var(--md-chart-tooltip-bg, #ffffff)',
  tooltipBorder: 'var(--md-chart-tooltip-border, #ccc)',
  tooltipText: 'var(--md-chart-tooltip-text, #000000)',
  secondaryText: 'var(--md-text-secondary, #4b5563)',
} as const;

type PartialChartConfig = Partial<ChartConfig> & {
  labels?: string[];
};

interface NormalizedSeries extends ChartSeriesConfig {
  color: string;
  name: string;
  type: 'bar' | 'line' | 'area' | 'scatter';
  yAxisId: 'left' | 'right';
  opacity: number;
  stackId?: string;
  strokeWidth?: number;
  dot?: boolean;
}

const tryParseJSON = <T,>(value: string): T | null => {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
};

const stripQuotes = (value: string) => value.replace(/^['"]|['"]$/g, '');

const parseListValue = (value: string): string[] => {
  const trimmed = value.trim();
  if (!trimmed) return [];

  const parsed = tryParseJSON<string[]>(trimmed);
  if (parsed) return parsed;

  if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
    const inner = trimmed.slice(1, -1);
    return inner
      .split(',')
      .map((item) => stripQuotes(item.trim()))
      .filter(Boolean);
  }

  return trimmed
    .split(',')
    .map((item) => stripQuotes(item.trim()))
    .filter(Boolean);
};

const parseNumericValue = (value: string): number | undefined => {
  const normalized = value.trim().replace(/px$/i, '');
  if (!normalized) return undefined;
  const parsed = Number(normalized);
  return Number.isNaN(parsed) ? undefined : parsed;
};

const parseFormatterValue = (value: string): ChartFormatterConfig | undefined => {
  const trimmed = value.trim();
  if (!trimmed) return undefined;

  const parsed = tryParseJSON<ChartFormatterConfig>(trimmed);
  if (parsed) return parsed;

  return { format: trimmed as ChartFormatterConfig['format'] };
};

const applyConfigLine = (config: PartialChartConfig, key: string, rawValue: string) => {
  const trimmedKey = key.trim();
  if (!trimmedKey) return;

  const value = rawValue.trim();
  if (!value.length) return;

  const lowerKey = trimmedKey.toLowerCase();
  const boolValue = value.toLowerCase();

  const ensureFormatter = () => {
    if (!config.formatter) config.formatter = {};
    return config.formatter;
  };

  switch (lowerKey) {
    case 'type':
      config.type = value as ChartConfig['type'];
      return;
    case 'title':
      config.title = value;
      return;
    case 'description':
      config.description = value;
      return;
    case 'xaxislabel':
      config.xAxisLabel = value;
      return;
    case 'yaxislabel':
      config.yAxisLabel = value;
      return;
    case 'yaxisrightlabel':
      config.yAxisRightLabel = value;
      return;
    case 'stacked':
      config.stacked = boolValue === 'true';
      return;
    case 'showlegend':
      config.showLegend = boolValue === 'true';
      return;
    case 'showgrid':
      config.showGrid = boolValue === 'true';
      return;
    case 'height': {
      const parsed = parseNumericValue(value);
      if (typeof parsed === 'number') config.height = parsed;
      return;
    }
    case 'width': {
      const parsed = parseNumericValue(value);
      if (typeof parsed === 'number') config.width = parsed;
      return;
    }
    case 'xkey':
      config.xKey = value;
      return;
    case 'xaxistype':
      config.xAxisType = value === 'number' ? 'number' : 'category';
      return;
    case 'valueformat': {
      const formatter = ensureFormatter();
      formatter.format = value as ChartFormatterConfig['format'];
      return;
    }
    case 'valueprefix': {
      const formatter = ensureFormatter();
      formatter.prefix = value;
      return;
    }
    case 'valuesuffix': {
      const formatter = ensureFormatter();
      formatter.suffix = value;
      return;
    }
    case 'valuecurrency': {
      const formatter = ensureFormatter();
      formatter.currency = value;
      return;
    }
    case 'valuedecimals': {
      const parsed = parseNumericValue(value);
      if (typeof parsed === 'number') {
        const formatter = ensureFormatter();
        formatter.decimals = parsed;
      }
      return;
    }
    case 'formatter': {
      const parsed = parseFormatterValue(value);
      if (parsed) {
        config.formatter = { ...config.formatter, ...parsed };
      }
      return;
    }
    case 'colors':
      config.colors = parseListValue(value);
      return;
    case 'labels':
      config.labels = parseListValue(value);
      return;
    case 'datakeys':
      config.dataKeys = parseListValue(value);
      return;
    case 'data': {
      const parsed = tryParseJSON<ChartDataItem[]>(value);
      if (parsed) config.data = parsed;
      return;
    }
    case 'series': {
      const parsed = tryParseJSON<ChartSeriesConfig[]>(value);
      if (parsed) config.series = parsed;
      return;
    }
    case 'referencelines': {
      const parsed = tryParseJSON<ChartReferenceLineConfig[]>(value);
      if (parsed) config.referenceLines = parsed;
      return;
    }
    default:
      return;
  }
};

export const parseChartConfig = (code: string, language: string): ChartConfig | null => {
  try {
    // Parse JSON format
    if (language === 'chart-json') {
      return JSON.parse(code) as ChartConfig;
    }

    const lines = code.trim().split('\n');
    const config: PartialChartConfig = { colors: DEFAULT_COLORS };

    // Check if it's table format
    const hasTable = lines.some((line) => line.includes('|'));

    if (hasTable) {
      const tableLines = lines.filter((line) => line.includes('|'));

      // More robust separator detection
      const isSeparatorLine = (line: string) => {
        const trimmed = line.trim();
        if (!trimmed.includes('|')) return false;
        const withoutPipesAndSpaces = trimmed.replace(/[|\s]/g, '');
        const dashCount = (withoutPipesAndSpaces.match(/-/g) || []).length;
        return dashCount > 0 && dashCount >= withoutPipesAndSpaces.length * 0.5;
      };

      // Find separator index to properly split header from data
      const separatorIndex = tableLines.findIndex(isSeparatorLine);

      // If no separator found yet, we're still streaming - return partial config
      if (separatorIndex === -1) {
        // Still set headers if we have them
        if (tableLines.length > 0) {
          const headers = tableLines[0]
            .split('|')
            .map((h) => h.trim())
            .filter(Boolean);
          if (headers.length > 0) {
            config.xKey = headers[0];
            config.dataKeys = headers.slice(1);
          }
        }
        config.data = [];
      } else {
        const headers = tableLines[0]
          .split('|')
          .map((h) => h.trim())
          .filter(Boolean);
        const dataRows = tableLines.slice(separatorIndex + 1); // Skip everything up to and including separator

        config.data = dataRows
          .map((row) => {
            // Skip separator-like rows that might appear in data
            if (isSeparatorLine(row)) return null;

            const values = row
              .split('|')
              .map((v) => v.trim())
              .filter(Boolean);
            if (!values.length) return null;

            const obj: ChartDataItem = {};
            headers.forEach((header, idx) => {
              const value = values[idx];
              if (typeof value === 'undefined') return;
              obj[header] = value !== '' && !Number.isNaN(Number(value)) ? Number(value) : value;
            });
            return obj;
          })
          .filter(Boolean) as ChartDataItem[];

        config.xKey = headers[0];
        config.dataKeys = headers.slice(1);
      }

      for (const line of lines) {
        if (line.includes('|')) break;
        const [key, ...valueParts] = line.split(':');
        if (!key || !valueParts.length) continue;
        applyConfigLine(config, key, valueParts.join(':'));
      }
    } else {
      for (const line of lines) {
        const [key, ...valueParts] = line.split(':');
        if (!key || !valueParts.length) continue;
        applyConfigLine(config, key, valueParts.join(':'));
      }

      if (Array.isArray(config.data) && typeof config.data[0] === 'number') {
        // Handle array of numbers - convert to objects with name/value pairs
        const numericData = config.data as unknown as number[];
        const labels =
          config.labels || numericData.map((_, idx) => `Item ${idx + 1}`);
        config.data = numericData.map((value, idx) => ({
          name: labels[idx],
          value,
        }));
        config.xKey = 'name';
        config.dataKeys = ['value'];
      }
    }

    config.data = config.data ?? [];
    if (!config.colors || config.colors.length === 0) {
      config.colors = DEFAULT_COLORS;
    }

    return config as ChartConfig;
  } catch (err) {
    console.error('Failed to parse chart config:', err);
    return null;
  }
};

const inferXAxisTypeFromData = (data: ChartDataItem[], xKey?: string): 'category' | 'number' => {
  if (!Array.isArray(data) || !data.length) return 'category';
  const key = xKey || 'name';
  const values = data
    .map((item) => (item && typeof item === 'object' ? item[key] : undefined))
    .filter((value) => typeof value !== 'undefined');
  if (!values.length) return 'category';
  const allNumbers = values.every((value) => typeof value === 'number' && !Number.isNaN(value));
  return allNumbers ? 'number' : 'category';
};

const formatValue = (value: unknown, formatter?: ChartFormatterConfig) => {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return value ?? '';
  }

  if (!formatter) {
    return new Intl.NumberFormat().format(value);
  }

  const {
    format = 'number',
    currency = 'USD',
    decimals,
    minimumFractionDigits,
    maximumFractionDigits,
    prefix = '',
    suffix = '',
  } = formatter;

  const options: Intl.NumberFormatOptions = {};

  if (typeof decimals === 'number' && !Number.isNaN(decimals)) {
    options.minimumFractionDigits = decimals;
    options.maximumFractionDigits = decimals;
  } else {
    if (typeof minimumFractionDigits === 'number') {
      options.minimumFractionDigits = minimumFractionDigits;
    }
    if (typeof maximumFractionDigits === 'number') {
      options.maximumFractionDigits = maximumFractionDigits;
    }
  }

  if (format === 'currency') {
    options.style = 'currency';
    options.currency = currency || 'USD';
  } else if (format === 'percent') {
    options.style = 'percent';
  } else if (format === 'compact') {
    options.notation = 'compact';
  } else if (!options.maximumFractionDigits) {
    options.maximumFractionDigits = 2;
  }

  const formatted = new Intl.NumberFormat(undefined, options).format(value);
  return `${prefix}${formatted}${suffix}`;
};

const buildSeries = (config: ChartConfig, colors: string[]): NormalizedSeries[] => {
  const fallbackSeries: ChartSeriesConfig[] =
    config.dataKeys && config.dataKeys.length
      ? config.dataKeys.map((key) => ({ key }))
      : [{ key: 'value' }];

  const baseSeries: ChartSeriesConfig[] = (config.series && config.series.length ? config.series : fallbackSeries).filter(
    (series): series is ChartSeriesConfig => Boolean(series.key),
  );

  const defaultType: NormalizedSeries['type'] =
    config.type === 'line'
      ? 'line'
      : config.type === 'area'
      ? 'area'
      : config.type === 'scatter'
      ? 'scatter'
      : 'bar';

  return baseSeries.map((series, idx) => {
    const resolvedType = config.type === 'composed' ? series.type || defaultType : defaultType;
    return {
      ...series,
      type: resolvedType,
      key: series.key as string,
      name: series.name ?? (series.key as string),
      color: series.color ?? colors[idx % colors.length],
      yAxisId: (series.yAxisId ?? 'left') as 'left' | 'right',
      stackId:
        typeof series.stackId !== 'undefined'
          ? series.stackId
          : config.stacked
          ? 'stack'
          : undefined,
      strokeWidth: series.strokeWidth ?? (resolvedType === 'line' ? 2 : 1),
      dot: typeof series.dot === 'boolean' ? series.dot : true,
      opacity: series.opacity ?? (resolvedType === 'area' ? 0.55 : 1),
    };
  });
};

const renderReferenceLines = (referenceLines?: ChartReferenceLineConfig[]) => {
  if (!referenceLines?.length) return null;
  return referenceLines
    .filter((line) => typeof line.y !== 'undefined' || typeof line.x !== 'undefined')
    .map((line, idx) => {
      // Map position values to valid Recharts LabelPosition values
      const mapPosition = (pos?: 'start' | 'middle' | 'end'): 'insideStart' | 'middle' | 'end' => {
        if (pos === 'start') return 'insideStart';
        if (pos === 'middle') return 'middle';
        if (pos === 'end') return 'end';
        return 'end';
      };
      
      return (
        <ReferenceLine
          key={`reference-${idx}`}
          y={line.y}
          x={line.x}
          stroke={line.color || '#9ca3af'}
          strokeDasharray={line.strokeDasharray || '4 4'}
          label={
            line.label
              ? {
                  value: line.label,
                  position: mapPosition(line.position),
                  fill: line.color || '#4b5563',
                }
              : undefined
          }
        />
      );
    });
};

const inferAxisLabel = (series: NormalizedSeries[], axis: 'left' | 'right'): string | undefined => {
  const axisSeries = series.filter((item) => item.yAxisId === axis);
  if (!axisSeries.length) return undefined;
  const labels = axisSeries
    .map((item) => item.name || item.key)
    .filter((name): name is string => Boolean(name));
  if (!labels.length) return undefined;
  const unique = Array.from(new Set(labels));
  return unique.join(' / ');
};

const renderYAxisLabel = (value: string | undefined, orientation: 'left' | 'right') => {
  if (!value) return null;
  const offset = orientation === 'right' ? 20 : -20;
  const position = orientation === 'right' ? 'insideRight' : 'insideLeft';
  return (
    <Label
      value={value}
      angle={orientation === 'right' ? 90 : -90}
      position={position}
      style={{ textAnchor: 'middle', fill: CHART_THEME_VARS.axis, fontSize: 12, fontWeight: 500 }}
      offset={offset}
    />
  );
};

// Heuristics to detect if chart data appears incomplete/streaming
const isLikelyIncomplete = (code: string): boolean => {
  // Check for incomplete JSON structures
  const openBraces = (code.match(/\{/g) || []).length;
  const closeBraces = (code.match(/\}/g) || []).length;
  const openBrackets = (code.match(/\[/g) || []).length;
  const closeBrackets = (code.match(/\]/g) || []).length;

  if (openBraces !== closeBraces || openBrackets !== closeBrackets) {
    return true;
  }

  const lines = code.split('\n');
  const tableLines = lines.filter(line => line.trim().includes('|'));

  if (tableLines.length > 0) {
    // Check for table with header but no data rows yet
    // A valid table needs: header row, separator row (---|---), and at least one data row
    // More lenient separator detection - any line with mostly dashes and pipes
    const isSeparatorLine = (line: string) => {
      const trimmed = line.trim();
      if (!trimmed.includes('|')) return false;
      // Count dashes vs other chars (excluding pipes and spaces)
      const withoutPipesAndSpaces = trimmed.replace(/[|\s]/g, '');
      const dashCount = (withoutPipesAndSpaces.match(/-/g) || []).length;
      // If more than 50% are dashes (and has some dashes), it's likely a separator
      return dashCount > 0 && dashCount >= withoutPipesAndSpaces.length * 0.5;
    };

    const separatorLines = tableLines.filter(isSeparatorLine);
    const nonSeparatorLines = tableLines.filter(line => !isSeparatorLine(line));

    // If we have table content but no separator row yet, it's incomplete
    if (nonSeparatorLines.length > 0 && separatorLines.length === 0) {
      return true;
    }

    // If we have header + separator but no data rows, it's incomplete
    if (separatorLines.length > 0 && nonSeparatorLines.length <= 1) {
      return true;
    }

    // Check if last line ends with | but has fewer columns (incomplete row being typed)
    const lastTableLine = tableLines[tableLines.length - 1].trim();
    if (lastTableLine && !isSeparatorLine(lastTableLine)) {
      const headerLine = nonSeparatorLines[0];
      if (headerLine) {
        const headerCols = headerLine.split('|').filter(s => s.trim()).length;
        const lastRowCols = lastTableLine.split('|').filter(s => s.trim()).length;

        // If last row has fewer columns than header, it's incomplete
        if (lastRowCols > 0 && lastRowCols < headerCols) {
          return true;
        }
      }
    }
  }

  // Check for trailing incomplete key-value pairs (key: with nothing after)
  const lastNonEmptyLine = lines.filter(l => l.trim()).pop() || '';
  if (lastNonEmptyLine.match(/^\w+:\s*$/) && !lastNonEmptyLine.includes('|')) {
    return true;
  }

  // Check if the last line looks like it's mid-typing (ends with partial content)
  // e.g., "| January | 156 |" when more columns are expected
  if (lastNonEmptyLine.endsWith('|') && tableLines.length > 0) {
    // Could be mid-row, check if it's likely incomplete
    const pipeCount = (lastNonEmptyLine.match(/\|/g) || []).length;
    const headerPipes = tableLines[0] ? (tableLines[0].match(/\|/g) || []).length : 0;
    if (pipeCount > 0 && pipeCount < headerPipes) {
      return true;
    }
  }

  return false;
};

export const ChartRenderer: React.FC<ChartRendererProps> = ({ code, language }) => {
  const [error, setError] = useState<string | null>(null);
  const [config, setConfig] = useState<ChartConfig | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isWaitingForData, setIsWaitingForData] = useState(false);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastCodeRef = useRef<string>('');
  const lastUpdateTimeRef = useRef<number>(0);
  const streamingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const now = Date.now();
    const timeSinceLastUpdate = now - lastUpdateTimeRef.current;
    const codeChanged = code !== lastCodeRef.current;

    // Update refs
    lastCodeRef.current = code;
    lastUpdateTimeRef.current = now;

    // Check if data appears incomplete (streaming in progress)
    const incomplete = isLikelyIncomplete(code);

    // Detect rapid updates (streaming) - updates faster than 500ms apart
    // LLM streaming can have variable timing, so we use a more generous threshold
    const rapidUpdate = codeChanged && timeSinceLastUpdate < 500 && timeSinceLastUpdate > 0;
    const likelyStreaming = incomplete || rapidUpdate;

    // Parse the current code
    const parsed = parseChartConfig(code, language);

    // Validation - but handle differently if we're streaming
    if (!parsed) {
      if (likelyStreaming) {
        // During streaming, show waiting state instead of error
        setIsWaitingForData(true);
        setIsStreaming(true);
        setError(null);
        setConfig(null);
      } else {
        setConfig(null);
        setError('Failed to parse chart configuration');
        setIsStreaming(false);
        setIsWaitingForData(false);
      }
      return;
    }

    if (!Array.isArray(parsed.data) || parsed.data.length === 0) {
      if (likelyStreaming) {
        // During streaming with no data yet, show waiting state
        setIsWaitingForData(true);
        setIsStreaming(true);
        setError(null);
        setConfig(null);

        // Clear any existing streaming timeout
        if (streamingTimeoutRef.current) {
          clearTimeout(streamingTimeoutRef.current);
        }

        // After 5 seconds of no valid data, show error (streaming likely failed)
        streamingTimeoutRef.current = setTimeout(() => {
          const currentParsed = parseChartConfig(lastCodeRef.current, language);
          if (!currentParsed || !Array.isArray(currentParsed.data) || currentParsed.data.length === 0) {
            setError('Chart data is empty');
            setIsStreaming(false);
            setIsWaitingForData(false);
          }
        }, 5000);
      } else {
        setConfig(null);
        setError('Chart data is empty');
        setIsStreaming(false);
        setIsWaitingForData(false);
      }
      return;
    }

    if (!parsed.type) {
      if (likelyStreaming) {
        // Type not yet received during streaming
        setIsWaitingForData(true);
        setIsStreaming(true);
        setError(null);
        setConfig(null);
      } else {
        setConfig(null);
        setError('Chart type is required (bar, line, pie, area, scatter, composed)');
        setIsStreaming(false);
        setIsWaitingForData(false);
      }
      return;
    }

    // Clear waiting state - we have valid data now
    setIsWaitingForData(false);

    // Clear streaming timeout if we got valid data
    if (streamingTimeoutRef.current) {
      clearTimeout(streamingTimeoutRef.current);
      streamingTimeoutRef.current = null;
    }

    if (likelyStreaming) {
      setIsStreaming(true);

      // Clear any existing debounce timer
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }

      // Debounce: wait for data to stabilize before final render
      // Use longer debounce (400ms) to handle LLM streaming variability
      debounceTimerRef.current = setTimeout(() => {
        setIsStreaming(false);
        // Re-parse in case code changed during debounce
        const finalParsed = parseChartConfig(code, language);
        if (finalParsed && Array.isArray(finalParsed.data) && finalParsed.data.length > 0) {
          setError(null);
          setConfig(finalParsed);
        }
      }, 400);

      // Show partial data while streaming (but still set it)
      setError(null);
      setConfig(parsed);
    } else {
      // Data is complete and not rapidly updating - render immediately
      setIsStreaming(false);
      setError(null);
      setConfig(parsed);
    }

    // Cleanup
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
      if (streamingTimeoutRef.current) {
        clearTimeout(streamingTimeoutRef.current);
      }
    };
  }, [code, language]);

  if (error) {
    return (
      <div className="graph-error">
        <div className="graph-error-title">Chart Rendering Error</div>
        <div className="graph-error-message">{error}</div>
        <pre style={{ marginTop: '8px', fontSize: '0.8em', opacity: 0.7 }}>
          <code>{code}</code>
        </pre>
      </div>
    );
  }

  if (!config) {
    return (
      <div className="graph-container chart-container">
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '40px 20px',
          color: 'var(--md-text-secondary, #6b7280)',
          minHeight: '200px',
        }}>
          <svg
            style={{
              animation: 'spin 1s linear infinite',
              marginBottom: '12px',
              width: '32px',
              height: '32px',
              color: isWaitingForData ? '#3b82f6' : 'currentColor',
            }}
            viewBox="0 0 24 24"
            fill="none"
          >
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" strokeDasharray="32" strokeLinecap="round" />
          </svg>
          <span style={{ fontWeight: 500 }}>
            {isWaitingForData ? 'Receiving chart data...' : 'Loading chart...'}
          </span>
          {isWaitingForData && (
            <span style={{ fontSize: '0.85em', marginTop: '4px', opacity: 0.7 }}>
              Waiting for complete data from stream
            </span>
          )}
        </div>
        <style>{`
          @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    );
  }

  const colors = config.colors && config.colors.length ? config.colors : DEFAULT_COLORS;
  const height = config.height || 320;
  const derivedSeries = buildSeries(config, colors);

  const hasRightAxis = derivedSeries.some((series) => series.yAxisId === 'right');
  const showLegend = config.showLegend ?? (config.type === 'pie' || derivedSeries.length > 1);
  const showGrid = config.showGrid ?? true;

  const referenceLineElements = renderReferenceLines(config.referenceLines);
  const inferredLeftLabel = inferAxisLabel(derivedSeries, 'left');
  const inferredRightLabel = inferAxisLabel(derivedSeries, 'right');
  const leftAxisLabelText = config.yAxisLabel ?? inferredLeftLabel ?? 'Value';
  const rightAxisLabelText = hasRightAxis
    ? config.yAxisRightLabel ?? inferredRightLabel ?? 'Value'
    : undefined;

  // Use CSS custom properties for theme-aware styling
  // These will be read from the computed styles of the container
  const axisColor = CHART_THEME_VARS.axis;
  const gridColor = CHART_THEME_VARS.grid;
  const textColor = CHART_THEME_VARS.text;
  const tooltipTextColor = CHART_THEME_VARS.tooltipText;
  const tooltipBgColor = CHART_THEME_VARS.tooltipBg;
  const tooltipBorderColor = CHART_THEME_VARS.tooltipBorder;
  const secondaryTextColor = CHART_THEME_VARS.secondaryText;
  const axisStylingProps = {
    tick: { fill: axisColor },
    axisLine: { stroke: axisColor },
    tickLine: { stroke: axisColor },
  };
  const xAxisType =
    config.xAxisType ??
    (config.type === 'scatter' ? 'number' : inferXAxisTypeFromData(config.data, config.xKey));
  const isCategoryXAxis = xAxisType === 'category';
  
  // Calculate data point count and determine label rotation/truncation needs
  const dataPointCount = config.data?.length || 0;
  
  // Analyze actual label lengths for smarter truncation decisions
  const analyzeLabelLengths = (): { maxLength: number; avgLength: number } => {
    if (!isCategoryXAxis || !config.data || dataPointCount === 0) {
      return { maxLength: 0, avgLength: 0 };
    }
    const xKey = config.xKey || 'name';
    const lengths = config.data
      .map((item: ChartDataItem) => {
        const value = item && typeof item === 'object' ? item[xKey] : undefined;
        return value ? String(value).length : 0;
      })
      .filter((len: number) => len > 0);
    
    if (lengths.length === 0) return { maxLength: 0, avgLength: 0 };
    
    const maxLength = Math.max(...lengths);
    const avgLength = lengths.reduce((sum: number, len: number) => sum + len, 0) / lengths.length;
    return { maxLength, avgLength };
  };
  
  const labelAnalysis = analyzeLabelLengths();
  const shouldRotateLabels = isCategoryXAxis && dataPointCount > 6;
  // Only truncate if we have many data points AND labels are actually long
  const shouldTruncateLabels = isCategoryXAxis && dataPointCount > 4 && labelAnalysis.avgLength > 15;
  const maxLabelLength = shouldTruncateLabels ? (dataPointCount > 10 ? 12 : 20) : Infinity;
  const labelLengthForSizing = shouldTruncateLabels
    ? (dataPointCount > 10 ? 12 : 20)
    : labelAnalysis.maxLength || 0;
  
  // Calculate interval to show fewer labels when there are many
  // With rotated labels, we can show more labels before needing intervals
  const calculateInterval = (count: number): number => {
    if (count <= 12) return 0; // Show all labels (common case like 12 months)
    if (count <= 16) return 1; // Show every other label
    if (count <= 24) return Math.floor(count / 12); // Show ~12 labels
    return Math.floor(count / 15); // Show ~15 labels max for very large datasets
  };
  
  const labelInterval = isCategoryXAxis ? calculateInterval(dataPointCount) : 0;

  const estimateTickLabelHeight = () => {
    if (!isCategoryXAxis || dataPointCount === 0) return 24;
    const baseHeight = 24;
    if (!shouldRotateLabels) {
      const longLabelBonus = Math.max(labelLengthForSizing - 12, 0) * 1.5;
      return Math.min(baseHeight + longLabelBonus, 48);
    }
    const approxCharWidth = 6.5;
    const rotationRadians = (45 * Math.PI) / 180;
    const approxWidth = labelLengthForSizing * approxCharWidth;
    const rotatedHeight = Math.sin(rotationRadians) * approxWidth;
    return Math.min(Math.max(baseHeight, rotatedHeight + 12), 140);
  };

  const estimatedTickLabelHeight = estimateTickLabelHeight();
  const xAxisHeight = shouldRotateLabels
    ? Math.min(Math.max(estimatedTickLabelHeight + 16, 80), 160)
    : Math.max(estimatedTickLabelHeight + 12, 36);

  // Note: Don't set scale: 'band' explicitly - Recharts handles this automatically
  // for bar charts, and setting it can interfere with rendering in some cases
  const categoricalXAxisProps = {
    type: 'category' as const,
    interval: labelInterval as number,
    allowDuplicatedCategory: false,
    padding: { left: 16, right: 16 },
    angle: shouldRotateLabels ? -45 : 0,
    textAnchor: shouldRotateLabels ? 'end' as const : 'middle' as const,
    height: xAxisHeight,
  };
  const numericXAxisProps = {
    type: 'number' as const,
    domain: ['dataMin', 'dataMax'] as const,
    allowDuplicatedCategory: true,
  };
  const xAxisProps = isCategoryXAxis ? categoricalXAxisProps : numericXAxisProps;

  const tooltipStyle = {
    backgroundColor: tooltipBgColor,
    border: `1px solid ${tooltipBorderColor}`,
    borderRadius: '4px',
    padding: '8px',
    color: tooltipTextColor,
  };

  const tooltipLabelStyle = {
    color: tooltipTextColor,
    fontWeight: 600,
    marginBottom: '4px',
  };

  const tooltipItemStyle = {
    color: tooltipTextColor,
  };

  // Cursor style for hover highlight - semi-transparent for better UX
  const tooltipCursor = {
    fill: gridColor,
    fillOpacity: 0.3,
  };

  const tooltipFormatter: Formatter<ValueType, NameType> = (value, name) => {
    const safeName = (name ?? '') as NameType;
    if (typeof value === 'number') {
      const formatted = formatValue(value, config.formatter);
      return [String(formatted ?? value), safeName];
    }
    if (Array.isArray(value)) {
      return [value.join(', '), safeName];
    }
    if (typeof value === 'string') {
      return [value, safeName];
    }
    return ['', safeName];
  };

  const axisTickFormatter = (value: unknown) => {
    if (typeof value !== 'number') return String(value ?? '');
    const formatted = formatValue(value, config.formatter);
    return String(formatted ?? '');
  };

  const formatCategoryLabel = (value: unknown) => {
    if (typeof value !== 'string') return String(value ?? '');
    const normalized = value.trim().toLowerCase();
    const monthAbbrev = MONTH_ABBREVIATIONS[normalized];
    if (monthAbbrev) return monthAbbrev;
    return value;
  };

  const truncateLabel = (label: string, maxLength: number): string => {
    if (!label || typeof label !== 'string') return String(label ?? '');
    if (label.length <= maxLength) return label;
    // Truncate at word boundary when possible for better readability
    const truncated = label.substring(0, maxLength - 3);
    const lastSpace = truncated.lastIndexOf(' ');
    if (lastSpace > maxLength * 0.6) {
      // If we can truncate at a word boundary without losing too much, do it
      return truncated.substring(0, lastSpace) + '...';
    }
    return truncated + '...';
  };

  const xAxisTickFormatter = (value: unknown) => {
    if (!isCategoryXAxis) return axisTickFormatter(value);
    const formatted = formatCategoryLabel(value);
    return shouldTruncateLabels ? truncateLabel(formatted, maxLabelLength) : formatted;
  };

  // Tooltip label formatter: always show full original label, even if axis label is truncated
  const tooltipLabelFormatter = (label: unknown) => {
    if (!isCategoryXAxis) return String(label ?? '');
    // Return the original formatted label (before truncation) for tooltip
    return formatCategoryLabel(label);
  };

  const xAxisHasLabel = Boolean(config.xAxisLabel);

  // Keep margins modest so the plotting area stays visible even with rotated labels
  const baseBottomMargin = 16;
  const axisLabelSpace = xAxisHasLabel ? 28 : 10;
  const legendSpace = showLegend ? 26 : 6;
  const rotatedPadding = shouldRotateLabels
    ? Math.min(Math.max(estimatedTickLabelHeight - 48, 0), 28)
    : 0;
  // Extra space when both rotated labels and axis label are present to prevent overlap
  const rotatedWithLabelExtra = shouldRotateLabels && xAxisHasLabel ? 16 : 0;
  const bottomMargin = baseBottomMargin + axisLabelSpace + legendSpace + rotatedPadding + rotatedWithLabelExtra;

  const chartMargin = {
    left: leftAxisLabelText ? 80 : 10,
    right: rightAxisLabelText ? 80 : 10,
    top: 10,
    bottom: bottomMargin,
  };

  // Calculate offset based on rotated label height to prevent overlap
  const xAxisLabelOffset = shouldRotateLabels
    ? Math.min(Math.max(estimatedTickLabelHeight - 60, 0), 36)
    : 0;
  const xAxisLabel = xAxisHasLabel
    ? {
        value: config.xAxisLabel,
        position: 'bottom' as const,
        offset: xAxisLabelOffset,
      }
    : undefined;

  // When labels are long and rotated, they squeeze the legend horizontally
  // Use vertical layout for legend in those cases
  const useLegendVerticalLayout = shouldRotateLabels && labelAnalysis.avgLength > 20;

  const legendWrapperStyle: React.CSSProperties = {
    color: textColor,
    marginTop: xAxisHasLabel ? 16 + xAxisLabelOffset : 12,
    paddingTop: shouldRotateLabels ? Math.min(Math.max(estimatedTickLabelHeight - 50, 8), 30) : 8,
    display: 'flex',
    justifyContent: 'center',
    gap: useLegendVerticalLayout ? '8px' : '16px',
    flexDirection: useLegendVerticalLayout ? 'column' : 'row',
    alignItems: useLegendVerticalLayout ? 'center' : undefined,
  };

  return (
    <div
      className="graph-container chart-container"
      style={{ flexDirection: 'column', alignItems: 'stretch', position: 'relative' }}
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
      {config.title && (
        <h4
          style={{
            textAlign: 'center',
            marginBottom: config.description ? '4px' : '12px',
            marginTop: 0,
            color: textColor,
            fontWeight: 600,
            background: 'transparent',
          }}
        >
          {config.title}
        </h4>
      )}
      {config.description && (
        <p
          style={{
            textAlign: 'center',
            marginTop: 0,
            marginBottom: '12px',
            color: secondaryTextColor,
            fontSize: '0.9rem',
          }}
        >
          {config.description}
        </p>
      )}
      <ResponsiveContainer width="100%" height={height}>
        {config.type === 'bar' && (
          <BarChart data={config.data} margin={chartMargin} barCategoryGap="20%">
            {showGrid && <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />}
            <XAxis
              dataKey={config.xKey || 'name'}
              label={xAxisLabel}
              {...axisStylingProps}
              {...xAxisProps}
              tickFormatter={xAxisTickFormatter}
            />
            <YAxis
              yAxisId="left"
              width={80}
              tickFormatter={axisTickFormatter}
              {...axisStylingProps}
            >
              {renderYAxisLabel(leftAxisLabelText, 'left')}
            </YAxis>
            {hasRightAxis && (
              <YAxis
                yAxisId="right"
                orientation="right"
                width={80}
                tickFormatter={axisTickFormatter}
                {...axisStylingProps}
              >
                {renderYAxisLabel(rightAxisLabelText, 'right')}
              </YAxis>
            )}
            <Tooltip
              contentStyle={tooltipStyle}
              labelStyle={tooltipLabelStyle}
              itemStyle={tooltipItemStyle}
              formatter={tooltipFormatter}
              labelFormatter={tooltipLabelFormatter}
              cursor={tooltipCursor}
            />
            {showLegend && <Legend wrapperStyle={legendWrapperStyle} iconSize={10} iconType="square" />}
            {referenceLineElements}
            {derivedSeries.map((series) => (
              <Bar
                name={series.name}
                key={series.key}
                dataKey={series.key}
                fill={series.color}
                stackId={series.stackId}
                yAxisId={series.yAxisId}
                radius={[4, 4, 0, 0]}
              />
            ))}
          </BarChart>
        )}

        {config.type === 'line' && (
          <LineChart data={config.data} margin={chartMargin}>
            {showGrid && <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />}
            <XAxis
              dataKey={config.xKey || 'name'}
              label={xAxisLabel}
              {...axisStylingProps}
              {...xAxisProps}
              tickFormatter={xAxisTickFormatter}
            />
            <YAxis
              yAxisId="left"
              width={80}
              tickFormatter={axisTickFormatter}
              {...axisStylingProps}
            >
              {renderYAxisLabel(leftAxisLabelText, 'left')}
            </YAxis>
            {hasRightAxis && (
              <YAxis
                yAxisId="right"
                orientation="right"
                width={80}
                tickFormatter={axisTickFormatter}
                {...axisStylingProps}
              >
                {renderYAxisLabel(rightAxisLabelText, 'right')}
              </YAxis>
            )}
            <Tooltip
              contentStyle={tooltipStyle}
              labelStyle={tooltipLabelStyle}
              itemStyle={tooltipItemStyle}
              formatter={tooltipFormatter}
              labelFormatter={tooltipLabelFormatter}
              cursor={tooltipCursor}
            />
            {showLegend && <Legend wrapperStyle={legendWrapperStyle} iconSize={10} iconType="square" />}
            {referenceLineElements}
            {derivedSeries.map((series) => (
              <Line
                name={series.name}
                key={series.key}
                type="monotone"
                dataKey={series.key}
                stroke={series.color}
                yAxisId={series.yAxisId}
                strokeWidth={series.strokeWidth}
                dot={series.dot}
              />
            ))}
          </LineChart>
        )}

        {config.type === 'area' && (
          <AreaChart data={config.data} margin={chartMargin}>
            {showGrid && <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />}
            <XAxis
              dataKey={config.xKey || 'name'}
              label={xAxisLabel}
              {...axisStylingProps}
              {...xAxisProps}
              tickFormatter={xAxisTickFormatter}
            />
            <YAxis
              yAxisId="left"
              width={80}
              tickFormatter={axisTickFormatter}
              {...axisStylingProps}
            >
              {renderYAxisLabel(leftAxisLabelText, 'left')}
            </YAxis>
            {hasRightAxis && (
              <YAxis
                yAxisId="right"
                orientation="right"
                width={80}
                tickFormatter={axisTickFormatter}
                {...axisStylingProps}
              >
                {renderYAxisLabel(rightAxisLabelText, 'right')}
              </YAxis>
            )}
            <Tooltip
              contentStyle={tooltipStyle}
              labelStyle={tooltipLabelStyle}
              itemStyle={tooltipItemStyle}
              formatter={tooltipFormatter}
              labelFormatter={tooltipLabelFormatter}
              cursor={tooltipCursor}
            />
            {showLegend && <Legend wrapperStyle={legendWrapperStyle} iconSize={10} iconType="square" />}
            {referenceLineElements}
            {derivedSeries.map((series) => (
              <Area
                name={series.name}
                key={series.key}
                type="monotone"
                dataKey={series.key}
                stroke={series.color}
                yAxisId={series.yAxisId}
                fill={series.color}
                fillOpacity={series.opacity}
                stackId={series.stackId}
              />
            ))}
          </AreaChart>
        )}

        {config.type === 'composed' && (
          <ComposedChart data={config.data} margin={chartMargin}>
            {showGrid && <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />}
            <XAxis
              dataKey={config.xKey || 'name'}
              label={xAxisLabel}
              {...axisStylingProps}
              {...xAxisProps}
              tickFormatter={xAxisTickFormatter}
            />
            <YAxis
              yAxisId="left"
              width={80}
              tickFormatter={axisTickFormatter}
              {...axisStylingProps}
            >
              {renderYAxisLabel(leftAxisLabelText, 'left')}
            </YAxis>
            {hasRightAxis && (
              <YAxis
                yAxisId="right"
                orientation="right"
                width={80}
                tickFormatter={axisTickFormatter}
                {...axisStylingProps}
              >
                {renderYAxisLabel(rightAxisLabelText, 'right')}
              </YAxis>
            )}
            <Tooltip
              contentStyle={tooltipStyle}
              labelStyle={tooltipLabelStyle}
              itemStyle={tooltipItemStyle}
              formatter={tooltipFormatter}
              labelFormatter={tooltipLabelFormatter}
              cursor={tooltipCursor}
            />
            {showLegend && <Legend wrapperStyle={legendWrapperStyle} iconSize={10} iconType="square" />}
            {referenceLineElements}
            {derivedSeries.map((series) => {
              switch (series.type) {
                case 'line':
                  return (
                    <Line
                      name={series.name}
                      key={series.key}
                      type="monotone"
                      dataKey={series.key}
                      stroke={series.color}
                      yAxisId={series.yAxisId}
                      strokeWidth={series.strokeWidth}
                      dot={series.dot}
                    />
                  );
                case 'area':
                  return (
                    <Area
                      name={series.name}
                      key={series.key}
                      type="monotone"
                      dataKey={series.key}
                      stroke={series.color}
                      yAxisId={series.yAxisId}
                      fill={series.color}
                      fillOpacity={series.opacity}
                      stackId={series.stackId}
                    />
                  );
                case 'scatter':
                  return (
                    <Scatter
                      name={series.name}
                      key={series.key}
                      dataKey={series.key}
                      fill={series.color}
                      yAxisId={series.yAxisId}
                    />
                  );
                default:
                  return (
                    <Bar
                      name={series.name}
                      key={series.key}
                      dataKey={series.key}
                      fill={series.color}
                      stackId={series.stackId}
                      yAxisId={series.yAxisId}
                      radius={[4, 4, 0, 0]}
                    />
                  );
              }
            })}
          </ComposedChart>
        )}

        {config.type === 'pie' && (
          <PieChart>
            <Pie
              data={config.data}
              dataKey={config.dataKeys?.[0] || 'value'}
              nameKey={config.xKey || 'name'}
              cx="50%"
              cy="50%"
              outerRadius={height / 3}
              label={{ fill: textColor }}
            >
              {config.data.map((_: unknown, index: number) => (
                <Cell key={`cell-${index}`} fill={colors[index % colors.length]} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={tooltipStyle}
              itemStyle={tooltipItemStyle}
              formatter={tooltipFormatter}
            />
            {showLegend && <Legend wrapperStyle={legendWrapperStyle} iconSize={10} iconType="square" />}
          </PieChart>
        )}

        {config.type === 'scatter' && (
          <ScatterChart margin={chartMargin}>
            {showGrid && <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />}
            <XAxis
              dataKey={config.xKey || 'x'}
              label={xAxisLabel}
              {...axisStylingProps}
              {...xAxisProps}
              tickFormatter={xAxisTickFormatter}
            />
            <YAxis
              dataKey={config.dataKeys?.[0] || 'y'}
              width={80}
              tickFormatter={axisTickFormatter}
              {...axisStylingProps}
            >
              {renderYAxisLabel(leftAxisLabelText, 'left')}
            </YAxis>
            <Tooltip
              contentStyle={tooltipStyle}
              labelStyle={tooltipLabelStyle}
              itemStyle={tooltipItemStyle}
              formatter={tooltipFormatter}
              labelFormatter={tooltipLabelFormatter}
              cursor={tooltipCursor}
            />
            {showLegend && <Legend wrapperStyle={legendWrapperStyle} iconSize={10} iconType="square" />}
            {referenceLineElements}
            <Scatter name="Data" data={config.data} fill={colors[0]} />
          </ScatterChart>
        )}
      </ResponsiveContainer>
    </div>
  );
};
