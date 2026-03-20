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
import type { DefaultLegendContentProps, TooltipContentProps } from 'recharts';
import type {
  ChartConfig,
  ChartDataItem,
  ChartFormatterConfig,
  ChartReferenceLineConfig,
  ChartRendererProps,
  ChartSeriesConfig,
} from '../types';

// Premium color palette — WCAG AA-accessible against both light and dark backgrounds
const DEFAULT_COLORS = [
  '#6366f1', // indigo-500
  '#06b6d4', // cyan-500
  '#f59e0b', // amber-500
  '#ec4899', // pink-500
  '#10b981', // emerald-500
  '#8b5cf6', // violet-500
  '#f97316', // orange-500
  '#14b8a6', // teal-500
  '#e11d48', // rose-600
  '#2563eb', // blue-600
];

const ANIMATION_DEFAULTS = {
  duration: 750,
  easing: 'ease-out',
} as const;

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

/** Chart key/value lines (type:, title:, …) — may contain `|` inside the value; must not count as table rows. */
const isChartKeyValueLine = (line: string) => /^\s*[\w.-]+\s*:\s/.test(line);

/** Markdown table rows only (leading `|`). Excludes `title: A | B` style config lines. */
const getChartMarkdownTableLines = (lines: string[]): string[] =>
  lines.filter((line) => {
    const t = line.trim();
    return t.startsWith('|') && t.includes('|') && !isChartKeyValueLine(line);
  });

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
  const tableLines = getChartMarkdownTableLines(lines);

  if (tableLines.length > 0) {
    // Check for table with header but no data rows yet
    // A valid table needs: header row, separator row (---|---), and at least one data row
    // More lenient separator detection - any line with mostly dashes and pipes
    const isSeparatorLine = (line: string) => {
      const trimmed = line.trim();
      if (!trimmed.includes('|')) return false;
      // Count dashes vs other chars (excluding pipes and spaces); models often emit en/em dashes
      const withoutPipesAndSpaces = trimmed.replace(/[|\s]/g, '');
      const dashCount = (withoutPipesAndSpaces.match(/[-\u2013\u2014\u2015]/g) || []).length;
      // If more than 50% are dashes (and has some dashes), it's likely a separator
      return dashCount > 0 && dashCount >= withoutPipesAndSpaces.length * 0.5;
    };

    const separatorLines = tableLines.filter(isSeparatorLine);
    const nonSeparatorLines = tableLines.filter((line) => !isSeparatorLine(line));

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
        const headerCols = headerLine.split('|').filter((s) => s.trim()).length;
        const lastRowCols = lastTableLine.split('|').filter((s) => s.trim()).length;

        // If last row has fewer columns than header, it's incomplete
        if (lastRowCols > 0 && lastRowCols < headerCols) {
          return true;
        }
      }
    }
  }

  // Check for trailing incomplete key-value pairs (key: with nothing after)
  const lastNonEmptyLine = lines.filter((l) => l.trim()).pop() || '';
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

const parseChartConfig = (code: string, language: string): ChartConfig | null => {
  try {
    // Parse JSON format (strict JSON only — trailing commas / comments / single-quoted keys will throw)
    if (language === 'chart-json') {
      let parsed: ChartConfig;
      try {
        parsed = JSON.parse(code) as ChartConfig;
      } catch (jsonErr) {
        // Streaming sends partial chart-json; braces often balance late, so still log only when structure looks complete.
        if (isLikelyIncomplete(code)) {
          return null;
        }
        const hint =
          jsonErr instanceof Error ? jsonErr.message : String(jsonErr);
        console.warn(
          '[ChartRenderer] chart-json is not valid JSON (fix the fence body or use `chart` / `chart-table`).',
          hint
        );
        return null;
      }
      // Normalize formatter from string shorthand (LLMs often output "formatter": "currency" instead of an object)
      if (typeof parsed.formatter === 'string') {
        parsed.formatter = { format: parsed.formatter as ChartFormatterConfig['format'] };
      }
      return parsed;
    }

    const lines = code.trim().split('\n');
    const config: PartialChartConfig = { colors: DEFAULT_COLORS };

    // Table rows = GFM-style lines starting with `|` (not `title: A | B` config lines)
    const tableLines = getChartMarkdownTableLines(lines);
    const hasTable = tableLines.length > 0;

    if (hasTable) {
      // More robust separator detection
      const isSeparatorLine = (line: string) => {
        const trimmed = line.trim();
        if (!trimmed.includes('|')) return false;
        const withoutPipesAndSpaces = trimmed.replace(/[|\s]/g, '');
        const dashCount = (withoutPipesAndSpaces.match(/[-\u2013\u2014\u2015]/g) || []).length;
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

      // Parse config lines before the table, with multi-line JSON support
      let tPendingKey: string | null = null;
      let tPendingValue = '';
      const tFlush = () => {
        if (tPendingKey) {
          applyConfigLine(config, tPendingKey, tPendingValue);
          tPendingKey = null;
          tPendingValue = '';
        }
      };
      for (const line of lines) {
        const row = line.trim();
        if (row.startsWith('|')) {
          tFlush();
          break;
        }
        if (tPendingKey) {
          tPendingValue += line.trim();
          const opens = (tPendingValue.match(/[{[]/g) || []).length;
          const closes = (tPendingValue.match(/[}\]]/g) || []).length;
          if (opens > 0 && opens <= closes) tFlush();
          continue;
        }
        const colonIdx = line.indexOf(':');
        if (colonIdx === -1) continue;
        const key = line.substring(0, colonIdx);
        const value = line.substring(colonIdx + 1);
        if (!key.trim()) continue;
        const trimmedVal = value.trim();
        if (trimmedVal.length > 0) {
          const opens = (trimmedVal.match(/[{[]/g) || []).length;
          const closes = (trimmedVal.match(/[}\]]/g) || []).length;
          if (opens > 0 && opens > closes) {
            tPendingKey = key;
            tPendingValue = trimmedVal;
            continue;
          }
        }
        applyConfigLine(config, key, value);
      }
    } else {
      // Parse key/value lines, accumulating multi-line JSON values.
      // LLMs sometimes output data/series across multiple indented lines:
      //   data: [
      //     {"x":"A","y":1},
      //     {"x":"B","y":2}
      //   ]
      let pendingKey: string | null = null;
      let pendingValue = '';
      const flushPending = () => {
        if (pendingKey) {
          applyConfigLine(config, pendingKey, pendingValue);
          pendingKey = null;
          pendingValue = '';
        }
      };
      for (const line of lines) {
        if (pendingKey) {
          // We're accumulating a multi-line value
          pendingValue += line.trim();
          // Check if brackets/braces are balanced now
          const opens = (pendingValue.match(/[{[]/g) || []).length;
          const closes = (pendingValue.match(/[}\]]/g) || []).length;
          if (opens > 0 && opens <= closes) {
            flushPending();
          }
          continue;
        }
        const colonIdx = line.indexOf(':');
        if (colonIdx === -1) continue;
        const key = line.substring(0, colonIdx);
        const value = line.substring(colonIdx + 1);
        if (!key.trim()) continue;
        // Detect start of a multi-line JSON value: value contains opening
        // bracket/brace but brackets aren't balanced on this line
        const trimmedVal = value.trim();
        if (trimmedVal.length > 0) {
          const opens = (trimmedVal.match(/[{[]/g) || []).length;
          const closes = (trimmedVal.match(/[}\]]/g) || []).length;
          if (opens > 0 && opens > closes) {
            pendingKey = key;
            pendingValue = trimmedVal;
            continue;
          }
        }
        applyConfigLine(config, key, value);
      }
      flushPending();

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

    // Reconcile xKey case with actual data keys — LLMs and table headers often
    // differ in casing (e.g. config has "month" but table header produced "Month").
    if (config.xKey && Array.isArray(config.data) && config.data.length > 0) {
      const firstItem = config.data[0];
      if (firstItem && typeof firstItem === 'object' && !(config.xKey in firstItem)) {
        const lowerXKey = config.xKey.toLowerCase();
        const match = Object.keys(firstItem).find((k) => k.toLowerCase() === lowerXKey);
        if (match) {
          config.xKey = match;
        }
      }
    }

    // Populate dataKeys from series when not already set (common in chart-json
    // where series is provided but dataKeys is not)
    if ((!config.dataKeys || config.dataKeys.length === 0) && config.series && config.series.length > 0) {
      config.dataKeys = config.series
        .map((s) => {
          const r = s as unknown as Record<string, unknown>;
          return (r.key as string) || (r.dataKey as string);
        })
        .filter(Boolean);
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

/** Integers in this range are formatted without grouping so years read as 2017, not 2,017. */
const CALENDAR_YEAR_TICK_MIN = 1800;
const CALENDAR_YEAR_TICK_MAX = 2300;

const isLikelyCalendarYearTick = (value: number): boolean =>
  Number.isFinite(value) &&
  Number.isInteger(value) &&
  value >= CALENDAR_YEAR_TICK_MIN &&
  value <= CALENDAR_YEAR_TICK_MAX;

/** Axis ticks only — keeps thousands separators for counts (e.g. 20,000) on Y. */
const formatNumericAxisTick = (value: unknown, formatter?: ChartFormatterConfig): string => {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return String(value ?? '');
  }
  if (isLikelyCalendarYearTick(value)) {
    return new Intl.NumberFormat(undefined, {
      useGrouping: false,
      maximumFractionDigits: 0,
    }).format(value);
  }
  return String(formatValue(value, formatter));
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

  // Normalize dataKey → key: LLMs (especially GPT) often output the Recharts `dataKey`
  // convention instead of our `key` property. Accept both.
  const rawSeries = config.series && config.series.length ? config.series : fallbackSeries;
  const baseSeries: ChartSeriesConfig[] = rawSeries
    .map((series) => {
      const r = series as unknown as Record<string, unknown>;
      if (!series.key && r.dataKey) {
        return { ...series, key: r.dataKey as string };
      }
      return series;
    })
    .filter((series): series is ChartSeriesConfig => Boolean(series.key));

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

// ---------------------------------------------------------------------------
// Premium custom tooltip
// ---------------------------------------------------------------------------
type CustomChartTooltipProps = Pick<TooltipContentProps, 'active' | 'payload' | 'label'> & {
  formatter?: ChartFormatterConfig;
  labelFormatter?: (label: unknown) => string;
};

const CustomChartTooltip: React.FC<CustomChartTooltipProps> = ({
  active,
  payload,
  label,
  formatter,
  labelFormatter,
}) => {
  if (!active || !payload?.length) return null;
  const displayLabel = labelFormatter ? labelFormatter(label) : label;
  return (
    <div
      role="tooltip"
      style={{
        background: 'var(--md-chart-tooltip-bg, #ffffff)',
        border: '1px solid var(--md-chart-tooltip-border, #e5e7eb)',
        borderRadius: '8px',
        padding: '10px 14px',
        boxShadow: '0 4px 14px rgba(0,0,0,0.08), 0 1px 3px rgba(0,0,0,0.04)',
        color: 'var(--md-chart-tooltip-text, #1f2937)',
        fontSize: '13px',
        lineHeight: 1.5,
        maxWidth: '300px',
        pointerEvents: 'none' as const,
      }}
    >
      {displayLabel != null && displayLabel !== '' && (
        <div style={{ fontWeight: 600, marginBottom: '6px', borderBottom: '1px solid var(--md-chart-grid, #e5e7eb)', paddingBottom: '5px' }}>
          {String(displayLabel)}
        </div>
      )}
      {payload.map((entry, idx) => (
        <div
          key={idx}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '16px',
            padding: '2px 0',
          }}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0 }}>
            <span
              style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                backgroundColor: entry.color ?? '#6366f1',
                flexShrink: 0,
                boxShadow: `0 0 0 2px ${(entry.color ?? '#6366f1')}33`,
              }}
            />
            <span style={{ opacity: 0.75, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {entry.name != null ? String(entry.name) : ''}
            </span>
          </span>
          <span style={{ fontWeight: 600, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>
            {String(formatValue(entry.value, formatter))}
          </span>
        </div>
      ))}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Custom active dot for line / area hover
// ---------------------------------------------------------------------------
const CustomActiveDot: React.FC<{
  cx?: number;
  cy?: number;
  fill?: string;
  stroke?: string;
}> = ({ cx, cy, fill, stroke }) => {
  if (typeof cx !== 'number' || typeof cy !== 'number') return null;
  return (
    <g>
      <circle cx={cx} cy={cy} r={7} fill={fill || stroke || '#6366f1'} fillOpacity={0.15} stroke="none" />
      <circle cx={cx} cy={cy} r={4} fill="#fff" stroke={stroke || fill || '#6366f1'} strokeWidth={2} />
    </g>
  );
};

// ---------------------------------------------------------------------------
// SVG gradient definitions for area charts
// ---------------------------------------------------------------------------
const renderGradientDefs = (series: NormalizedSeries[]) => {
  const areaSeries = series.filter((s) => s.type === 'area');
  if (!areaSeries.length) return null;
  return (
    <defs>
      {areaSeries.map((s) => (
        <linearGradient key={`grad-${s.key}`} id={`gradient-${s.key}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={s.color} stopOpacity={0.45} />
          <stop offset="95%" stopColor={s.color} stopOpacity={0.03} />
        </linearGradient>
      ))}
    </defs>
  );
};

// ---------------------------------------------------------------------------
// Generate accessible data summary for screen readers
// ---------------------------------------------------------------------------
const buildA11ySummary = (config: ChartConfig, series: NormalizedSeries[]): string => {
  const parts: string[] = [];
  parts.push(`${config.type} chart`);
  if (config.title) parts.push(`titled "${config.title}"`);
  parts.push(`with ${config.data.length} data point${config.data.length !== 1 ? 's' : ''}`);
  if (series.length > 1) parts.push(`and ${series.length} series: ${series.map((s) => s.name).join(', ')}`);
  return parts.join(' ');
};

export const ChartRenderer: React.FC<ChartRendererProps> = ({ code, language }) => {
  const [error, setError] = useState<string | null>(null);
  const [config, setConfig] = useState<ChartConfig | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isWaitingForData, setIsWaitingForData] = useState(false);
  const [containerWidth, setContainerWidth] = useState(0);
  const [hiddenSeries, setHiddenSeries] = useState<Set<string>>(new Set());
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastCodeRef = useRef<string>('');
  const lastUpdateTimeRef = useRef<number>(0);
  const streamingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const chartViewportRef = useRef<HTMLDivElement>(null);

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
        setIsWaitingForData(true); // eslint-disable-line react-hooks/set-state-in-effect -- intentional state sync from prop
        setIsStreaming(true);
        setError(null);
        setConfig(null);
        if (streamingTimeoutRef.current) {
          clearTimeout(streamingTimeoutRef.current);
        }
        streamingTimeoutRef.current = setTimeout(() => {
          const currentParsed = parseChartConfig(lastCodeRef.current, language);
          if (!currentParsed) {
            setError('Failed to parse chart configuration');
            setIsStreaming(false);
            setIsWaitingForData(false);
          }
        }, 5000);
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
        if (streamingTimeoutRef.current) {
          clearTimeout(streamingTimeoutRef.current);
        }
        streamingTimeoutRef.current = setTimeout(() => {
          const current = parseChartConfig(lastCodeRef.current, language);
          if (!current?.type) {
            setError('Chart type is required (bar, line, pie, area, scatter, composed)');
            setIsStreaming(false);
            setIsWaitingForData(false);
          }
        }, 5000);
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
        const latest = lastCodeRef.current;
        const finalParsed = parseChartConfig(latest, language);
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

  useEffect(() => {
    const node = chartViewportRef.current;
    if (!node || typeof window === 'undefined' || typeof window.ResizeObserver === 'undefined') return;

    const observer = new window.ResizeObserver((entries) => {
      const width = entries[0]?.contentRect?.width ?? 0;
      if (width > 0) {
        setContainerWidth(width);
      }
    });
    observer.observe(node);

    return () => observer.disconnect();
  }, []);

  if (error) {
    return (
      <div className="graph-error" role="alert">
        <div className="graph-error-header">
          <div className="graph-error-icon" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M10 6v4m0 4h.01M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </div>
          <div className="graph-error-content">
            <div className="graph-error-title">Chart Rendering Error</div>
            <div className="graph-error-message">{error}</div>
          </div>
        </div>
        <details style={{ marginTop: '4px' }}>
          <summary className="graph-error-toggle" style={{ cursor: 'pointer', listStyle: 'none', userSelect: 'none' }}>
            Show raw source
          </summary>
          <div className="graph-error-details">
            <pre><code>{code}</code></pre>
          </div>
        </details>
      </div>
    );
  }

  if (!config) {
    return (
      <div className="graph-container chart-container" role="status" aria-label="Loading chart">
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'stretch',
          width: '100%',
          padding: '16px 20px',
          minHeight: '220px',
          gap: '12px',
        }}>
          {/* Skeleton title */}
          <div style={{ height: '16px', width: '40%', borderRadius: '6px', background: 'var(--md-chart-grid, #e5e7eb)', opacity: 0.5, animation: 'chartPulse 1.5s ease-in-out infinite' }} />
          {/* Skeleton chart area */}
          <div style={{ flex: 1, display: 'flex', alignItems: 'flex-end', gap: '8px', padding: '16px 0 8px', minHeight: '140px' }}>
            {[0.45, 0.7, 0.55, 0.85, 0.6, 0.4, 0.75].map((h, i) => (
              <div
                key={i}
                style={{
                  flex: 1,
                  height: `${h * 100}%`,
                  borderRadius: '4px 4px 0 0',
                  background: 'var(--md-chart-grid, #e5e7eb)',
                  opacity: 0.35,
                  animation: `chartPulse 1.5s ease-in-out ${i * 0.1}s infinite`,
                }}
              />
            ))}
          </div>
          {/* Skeleton axis */}
          <div style={{ height: '1px', background: 'var(--md-chart-grid, #e5e7eb)', opacity: 0.4 }} />
          {/* Status label */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', color: 'var(--md-text-secondary, #6b7280)', fontSize: '13px' }}>
            <svg style={{ animation: 'chartSpin 1s linear infinite', width: '14px', height: '14px', color: isWaitingForData ? '#6366f1' : 'currentColor' }} viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" strokeDasharray="32" strokeLinecap="round" />
            </svg>
            <span style={{ fontWeight: 500 }}>
              {isWaitingForData ? 'Receiving chart data\u2026' : 'Loading chart\u2026'}
            </span>
          </div>
        </div>
        <style>{`
          @keyframes chartSpin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
          @keyframes chartPulse { 0%, 100% { opacity: 0.25; } 50% { opacity: 0.45; } }
        `}</style>
      </div>
    );
  }

  const colors = config.colors && config.colors.length ? config.colors : DEFAULT_COLORS;
  const allSeries = buildSeries(config, colors);
  // Filter out hidden series for interactive legend toggle
  const derivedSeries = allSeries.filter((s) => !hiddenSeries.has(s.key));

  const hasRightAxis = derivedSeries.some((series) => series.yAxisId === 'right');
  const showLegend = config.showLegend ?? (config.type === 'pie' || derivedSeries.length > 1);
  const showGrid = config.showGrid ?? true;

  const referenceLineElements = renderReferenceLines(config.referenceLines);
  const gradientDefs = renderGradientDefs(derivedSeries);
  const a11ySummary = buildA11ySummary(config, derivedSeries);

  // Interactive legend click handler — toggles series visibility
  const handleLegendClick = (dataKey: string) => {
    setHiddenSeries((prev) => {
      const next = new Set(prev);
      if (next.has(dataKey)) {
        next.delete(dataKey);
      } else {
        // Don't allow hiding ALL series
        if (next.size < allSeries.length - 1) {
          next.add(dataKey);
        }
      }
      return next;
    });
  };
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
  const isCompactViewport = containerWidth > 0 && containerWidth < 640;
  const height = config.height || (isCompactViewport ? 380 : 320);
  
  // Calculate data point count and determine label rotation/truncation needs
  const dataPointCount = config.data?.length || 0;
  const defaultChartWidth = isCompactViewport ? 520 : 720;
  const estimatedPerPointWidth =
    config.type === 'bar' || config.type === 'composed'
      ? (isCompactViewport ? 92 : 72)
      : config.type === 'line' || config.type === 'area'
      ? (isCompactViewport ? 84 : 64)
      : (isCompactViewport ? 64 : 56);
  const intrinsicChartWidth = config.width ?? (isCategoryXAxis ? Math.max(defaultChartWidth, dataPointCount * estimatedPerPointWidth) : defaultChartWidth);
  
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
  const estimatedCategorySlotWidth =
    isCategoryXAxis && dataPointCount > 0
      ? Math.max((intrinsicChartWidth - 48) / dataPointCount, 0)
      : 0;
  const labelsNeedCompaction =
    isCategoryXAxis &&
    (estimatedCategorySlotWidth < 84 ||
      (estimatedCategorySlotWidth < 108 && labelAnalysis.maxLength > 12));
  const shouldRotateLabels =
    isCategoryXAxis && (dataPointCount > 6 || (labelAnalysis.maxLength > 12 && estimatedCategorySlotWidth < 96));
  // Truncate when the slot width is too narrow or the labels are long enough to crowd the axis.
  const shouldTruncateLabels =
    isCategoryXAxis &&
    (labelsNeedCompaction || (dataPointCount > 4 && labelAnalysis.avgLength > 15));
  const maxCharsPerLabel = estimatedCategorySlotWidth > 0
    ? Math.max(Math.floor(estimatedCategorySlotWidth / 7), 8)
    : Infinity;
  const maxLabelLength = shouldTruncateLabels
    ? Math.min(dataPointCount > 10 ? 12 : 20, maxCharsPerLabel)
    : Infinity;
  const labelLengthForSizing = shouldTruncateLabels
    ? (dataPointCount > 10 ? 12 : 20)
    : labelAnalysis.maxLength || 0;
  
  // Calculate interval to show fewer labels when there are many
  // With rotated labels, we can show more labels before needing intervals
  const calculateInterval = (count: number, slotWidth: number, maxLength: number): number => {
    if (slotWidth > 0 && (slotWidth < 68 || (slotWidth < 84 && maxLength > 14))) {
      return 1;
    }
    if (slotWidth > 0 && slotWidth < 56) {
      return 2;
    }
    if (count <= 12) return 0; // Show all labels (common case like 12 months)
    if (count <= 16) return 1; // Show every other label
    if (count <= 24) return Math.floor(count / 12); // Show ~12 labels
    return Math.floor(count / 15); // Show ~15 labels max for very large datasets
  };
  
  const labelInterval = isCategoryXAxis
    ? calculateInterval(dataPointCount, estimatedCategorySlotWidth, labelAnalysis.maxLength)
    : 0;

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
    ? Math.min(Math.max(estimatedTickLabelHeight + (isCompactViewport ? 12 : 16), isCompactViewport ? 64 : 80), isCompactViewport ? 140 : 160)
    : Math.max(estimatedTickLabelHeight + 12, isCompactViewport ? 32 : 36);

  // Note: Don't set scale: 'band' explicitly - Recharts handles this automatically
  // for bar charts, and setting it can interfere with rendering in some cases
  const categoricalXAxisProps = {
    type: 'category' as const,
    interval: labelInterval as number,
    allowDuplicatedCategory: false,
    padding: { left: 16, right: 16 },
    minTickGap: shouldRotateLabels ? 4 : 12,
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

  // Cursor style for hover highlight
  const tooltipCursor = {
    fill: gridColor,
    fillOpacity: 0.2,
    strokeWidth: 0,
  };

  // Custom tooltip renderer using the premium CustomChartTooltip component
  const renderCustomTooltip = (props: TooltipContentProps) => (
    <CustomChartTooltip
      active={props.active}
      payload={props.payload}
      label={props.label}
      formatter={config.formatter}
      labelFormatter={tooltipLabelFormatter}
    />
  );

  const axisTickFormatter = (value: unknown) => formatNumericAxisTick(value, config.formatter);

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
    if (!isCategoryXAxis) return formatNumericAxisTick(value, config.formatter);
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
    left: leftAxisLabelText ? (isCompactViewport ? 68 : 80) : 10,
    right: rightAxisLabelText ? (isCompactViewport ? 68 : 80) : 10,
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
    marginTop: xAxisHasLabel ? (isCompactViewport ? 12 : 16) + xAxisLabelOffset : (isCompactViewport ? 8 : 12),
    paddingTop: shouldRotateLabels ? Math.min(Math.max(estimatedTickLabelHeight - 50, 8), isCompactViewport ? 22 : 30) : 8,
    display: 'flex',
    justifyContent: 'center',
    flexWrap: 'wrap',
    gap: useLegendVerticalLayout ? '6px' : (isCompactViewport ? '8px' : '14px'),
    flexDirection: useLegendVerticalLayout ? 'column' : 'row',
    alignItems: useLegendVerticalLayout ? 'center' : undefined,
  };

  // Interactive legend content renderer — supports click-to-toggle series
  const renderInteractiveLegend = (props: DefaultLegendContentProps) => {
    if (!props.payload) return null;
    return (
      <div style={legendWrapperStyle} role="list" aria-label="Chart legend">
        {props.payload.map((entry, idx) => {
          const key = String(entry.dataKey ?? entry.value ?? idx);
          const isHidden = hiddenSeries.has(key);
          return (
            <button
              key={idx}
              type="button"
              role="listitem"
              onClick={() => handleLegendClick(key)}
              aria-pressed={!isHidden}
              aria-label={`${isHidden ? 'Show' : 'Hide'} ${entry.value ?? ''}`}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                cursor: 'pointer',
                background: 'none',
                border: 'none',
                padding: '3px 6px',
                borderRadius: '4px',
                fontSize: '12px',
                color: textColor,
                opacity: isHidden ? 0.35 : 1,
                textDecoration: isHidden ? 'line-through' : 'none',
                transition: 'opacity 0.2s, background 0.15s',
              }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--md-chart-grid, #f3f4f6)'; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'none'; }}
            >
              <span
                style={{
                  width: '10px',
                  height: '10px',
                  borderRadius: '2px',
                  backgroundColor: entry.color ?? '#6366f1',
                  flexShrink: 0,
                  opacity: isHidden ? 0.3 : 1,
                  transition: 'opacity 0.2s',
                }}
              />
              {entry.value}
            </button>
          );
        })}
      </div>
    );
  };

  return (
    <>
      <div
        className="graph-container chart-container"
        role="figure"
        aria-label={a11ySummary}
        tabIndex={0}
        style={{ flexDirection: 'column', alignItems: 'stretch', position: 'relative' }}
      >
        {isStreaming && (
          <div className="md-expandable-actions" aria-live="polite">
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                padding: '4px 10px',
                backgroundColor: 'rgba(99, 102, 241, 0.08)',
                borderRadius: '6px',
                fontSize: '12px',
                color: '#6366f1',
                fontWeight: 500,
              }}
            >
              <svg
                style={{
                  animation: 'chartSpin 1s linear infinite',
                  marginRight: '6px',
                  width: '12px',
                  height: '12px'
                }}
                viewBox="0 0 24 24"
                fill="none"
              >
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" strokeDasharray="32" strokeLinecap="round" />
              </svg>
              Updating\u2026
              <style>{`
                @keyframes chartSpin {
                  from { transform: rotate(0deg); }
                  to { transform: rotate(360deg); }
                }
              `}</style>
            </div>
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
        <div ref={chartViewportRef} style={{ width: '100%', overflowX: 'auto', overflowY: 'hidden' }}>
          <div style={{ minWidth: '100%' }}>
            <ResponsiveContainer width={intrinsicChartWidth} height={height}>
        {config.type === 'bar' && (
          <BarChart data={config.data} margin={chartMargin} barCategoryGap="20%">
            {showGrid && <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />}
            <XAxis
              dataKey={config.xKey || 'name'}
              label={xAxisLabel}
              {...axisStylingProps}
              {...xAxisProps}
              tickFormatter={xAxisTickFormatter}
            />
            <YAxis
              yAxisId="left"
              width={isCompactViewport ? 68 : 80}
              tickFormatter={axisTickFormatter}
              {...axisStylingProps}
            >
              {renderYAxisLabel(leftAxisLabelText, 'left')}
            </YAxis>
            {hasRightAxis && (
              <YAxis
                yAxisId="right"
                orientation="right"
                width={isCompactViewport ? 68 : 80}
                tickFormatter={axisTickFormatter}
                {...axisStylingProps}
              >
                {renderYAxisLabel(rightAxisLabelText, 'right')}
              </YAxis>
            )}
            <Tooltip content={renderCustomTooltip} cursor={tooltipCursor} />
            {showLegend && <Legend content={renderInteractiveLegend} />}
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
                animationDuration={ANIMATION_DEFAULTS.duration}
                animationEasing={ANIMATION_DEFAULTS.easing}
              />
            ))}
          </BarChart>
        )}

        {config.type === 'line' && (
          <LineChart data={config.data} margin={chartMargin}>
            {showGrid && <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />}
            <XAxis
              dataKey={config.xKey || 'name'}
              label={xAxisLabel}
              {...axisStylingProps}
              {...xAxisProps}
              tickFormatter={xAxisTickFormatter}
            />
            <YAxis
              yAxisId="left"
              width={isCompactViewport ? 68 : 80}
              tickFormatter={axisTickFormatter}
              {...axisStylingProps}
            >
              {renderYAxisLabel(leftAxisLabelText, 'left')}
            </YAxis>
            {hasRightAxis && (
              <YAxis
                yAxisId="right"
                orientation="right"
                width={isCompactViewport ? 68 : 80}
                tickFormatter={axisTickFormatter}
                {...axisStylingProps}
              >
                {renderYAxisLabel(rightAxisLabelText, 'right')}
              </YAxis>
            )}
            <Tooltip content={renderCustomTooltip} cursor={{ stroke: gridColor, strokeDasharray: '4 4' }} />
            {showLegend && <Legend content={renderInteractiveLegend} />}
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
                dot={series.dot ? { r: 3, strokeWidth: 2, fill: '#fff' } : false}
                activeDot={<CustomActiveDot stroke={series.color} />}
                animationDuration={ANIMATION_DEFAULTS.duration}
                animationEasing={ANIMATION_DEFAULTS.easing}
              />
            ))}
          </LineChart>
        )}

        {config.type === 'area' && (
          <AreaChart data={config.data} margin={chartMargin}>
            {gradientDefs}
            {showGrid && <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />}
            <XAxis
              dataKey={config.xKey || 'name'}
              label={xAxisLabel}
              {...axisStylingProps}
              {...xAxisProps}
              tickFormatter={xAxisTickFormatter}
            />
            <YAxis
              yAxisId="left"
              width={isCompactViewport ? 68 : 80}
              tickFormatter={axisTickFormatter}
              {...axisStylingProps}
            >
              {renderYAxisLabel(leftAxisLabelText, 'left')}
            </YAxis>
            {hasRightAxis && (
              <YAxis
                yAxisId="right"
                orientation="right"
                width={isCompactViewport ? 68 : 80}
                tickFormatter={axisTickFormatter}
                {...axisStylingProps}
              >
                {renderYAxisLabel(rightAxisLabelText, 'right')}
              </YAxis>
            )}
            <Tooltip content={renderCustomTooltip} cursor={{ stroke: gridColor, strokeDasharray: '4 4' }} />
            {showLegend && <Legend content={renderInteractiveLegend} />}
            {referenceLineElements}
            {derivedSeries.map((series) => (
              <Area
                name={series.name}
                key={series.key}
                type="monotone"
                dataKey={series.key}
                stroke={series.color}
                strokeWidth={2}
                yAxisId={series.yAxisId}
                fill={`url(#gradient-${series.key})`}
                fillOpacity={1}
                stackId={series.stackId}
                activeDot={<CustomActiveDot stroke={series.color} />}
                animationDuration={ANIMATION_DEFAULTS.duration}
                animationEasing={ANIMATION_DEFAULTS.easing}
              />
            ))}
          </AreaChart>
        )}

        {config.type === 'composed' && (
          <ComposedChart data={config.data} margin={chartMargin}>
            {gradientDefs}
            {showGrid && <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />}
            <XAxis
              dataKey={config.xKey || 'name'}
              label={xAxisLabel}
              {...axisStylingProps}
              {...xAxisProps}
              tickFormatter={xAxisTickFormatter}
            />
            <YAxis
              yAxisId="left"
              width={isCompactViewport ? 68 : 80}
              tickFormatter={axisTickFormatter}
              {...axisStylingProps}
            >
              {renderYAxisLabel(leftAxisLabelText, 'left')}
            </YAxis>
            {hasRightAxis && (
              <YAxis
                yAxisId="right"
                orientation="right"
                width={isCompactViewport ? 68 : 80}
                tickFormatter={axisTickFormatter}
                {...axisStylingProps}
              >
                {renderYAxisLabel(rightAxisLabelText, 'right')}
              </YAxis>
            )}
            <Tooltip content={renderCustomTooltip} cursor={tooltipCursor} />
            {showLegend && <Legend content={renderInteractiveLegend} />}
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
                      dot={series.dot ? { r: 3, strokeWidth: 2, fill: '#fff' } : false}
                      activeDot={<CustomActiveDot stroke={series.color} />}
                      animationDuration={ANIMATION_DEFAULTS.duration}
                      animationEasing={ANIMATION_DEFAULTS.easing}
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
                      strokeWidth={2}
                      yAxisId={series.yAxisId}
                      fill={`url(#gradient-${series.key})`}
                      fillOpacity={1}
                      stackId={series.stackId}
                      activeDot={<CustomActiveDot stroke={series.color} />}
                      animationDuration={ANIMATION_DEFAULTS.duration}
                      animationEasing={ANIMATION_DEFAULTS.easing}
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
                      animationDuration={ANIMATION_DEFAULTS.duration}
                      animationEasing={ANIMATION_DEFAULTS.easing}
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
                      animationDuration={ANIMATION_DEFAULTS.duration}
                      animationEasing={ANIMATION_DEFAULTS.easing}
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
              dataKey={derivedSeries[0]?.key || config.dataKeys?.[0] || 'value'}
              nameKey={config.xKey || 'name'}
              cx="50%"
              cy="50%"
              outerRadius={height / 3}
              innerRadius={height / 6}
              paddingAngle={2}
              strokeWidth={0}
              label={({ name, percent }) => `${name ?? ''} ${((percent ?? 0) * 100).toFixed(0)}%`}
              labelLine={{ stroke: axisColor, strokeWidth: 1 }}
              animationDuration={ANIMATION_DEFAULTS.duration}
              animationEasing={ANIMATION_DEFAULTS.easing}
            >
              {config.data.map((_: unknown, index: number) => (
                <Cell key={`cell-${index}`} fill={colors[index % colors.length]} />
              ))}
            </Pie>
            <Tooltip content={renderCustomTooltip} />
            {showLegend && <Legend content={renderInteractiveLegend} />}
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
              dataKey={derivedSeries[0]?.key || config.dataKeys?.[0] || 'y'}
              width={isCompactViewport ? 68 : 80}
              tickFormatter={axisTickFormatter}
              {...axisStylingProps}
            >
              {renderYAxisLabel(leftAxisLabelText, 'left')}
            </YAxis>
            <Tooltip content={renderCustomTooltip} cursor={tooltipCursor} />
            {showLegend && <Legend content={renderInteractiveLegend} />}
            {referenceLineElements}
            {derivedSeries.map((series) => (
              <Scatter
                key={series.key}
                name={series.name}
                data={config.data}
                fill={series.color}
                animationDuration={ANIMATION_DEFAULTS.duration}
                animationEasing={ANIMATION_DEFAULTS.easing}
              />
            ))}
          </ScatterChart>
        )}
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </>
  );
};
