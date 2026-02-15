import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Platform, StyleSheet, Text, View } from 'react-native';
import { ScrollView } from 'react-native-gesture-handler';
import Markdown, { ASTNode, RenderRules } from 'react-native-markdown-display';
import { ThemeColors } from '../theme/colors';

interface Props {
  content: string;
  theme: ThemeColors;
  variant?: 'chat' | 'preview' | 'notes';
  textColor?: string;
}

interface TableScrollProps {
  children: React.ReactNode;
  showIndicator: boolean;
  darkMode: boolean;
  fadeColor: string;
}

function TableScrollView({ children, showIndicator, darkMode, fadeColor }: TableScrollProps) {
  const scrollRef = useRef<ScrollView>(null);
  const [showFade, setShowFade] = useState(false);
  const sizesRef = useRef({ container: 0, content: 0 });

  useEffect(() => {
    if (Platform.OS !== 'web') {
      const timer = setTimeout(() => {
        (scrollRef.current as any)?.flashScrollIndicators?.();
      }, 500);
      return () => clearTimeout(timer);
    }
  }, []);

  const checkFade = useCallback((scrollX = 0) => {
    const { container, content } = sizesRef.current;
    if (container === 0 || content === 0) return;
    const canScroll = content > container + 2;
    const atEnd = scrollX + container >= content - 4;
    setShowFade(canScroll && !atEnd);
  }, []);

  if (Platform.OS === 'web') {
    return (
      <View style={{ overflowX: 'auto' } as any}>
        {children}
      </View>
    );
  }

  return (
    <View>
      <ScrollView
        ref={scrollRef}
        horizontal
        nestedScrollEnabled
        bounces={false}
        showsHorizontalScrollIndicator={showIndicator}
        indicatorStyle={darkMode ? 'white' : 'black'}
        onScroll={(e) => {
          sizesRef.current.container = e.nativeEvent.layoutMeasurement.width;
          sizesRef.current.content = e.nativeEvent.contentSize.width;
          checkFade(e.nativeEvent.contentOffset.x);
        }}
        scrollEventThrottle={100}
        onContentSizeChange={(w) => {
          sizesRef.current.content = w;
          checkFade();
        }}
        onLayout={(e) => {
          sizesRef.current.container = e.nativeEvent.layout.width;
          checkFade();
        }}
      >
        {children}
      </ScrollView>
      {showFade && (
        <View style={fadeStyles.container} pointerEvents="none">
          <View style={[fadeStyles.strip, { backgroundColor: fadeColor, opacity: 0 }]} />
          <View style={[fadeStyles.strip, { backgroundColor: fadeColor, opacity: 0.4 }]} />
          <View style={[fadeStyles.strip, { backgroundColor: fadeColor, opacity: 0.7 }]} />
          <View style={[fadeStyles.strip, { backgroundColor: fadeColor, opacity: 0.95 }]} />
        </View>
      )}
    </View>
  );
}

const fadeStyles = StyleSheet.create({
  container: {
    position: 'absolute',
    right: 0,
    top: 0,
    bottom: 0,
    width: 24,
    flexDirection: 'row',
  },
  strip: {
    flex: 1,
  },
});

interface ChartConfigLite {
  title?: string;
  description?: string;
  xKey: string;
  dataKeys: string[];
  data: Array<Record<string, string | number>>;
}

function isMarkdownTableContent(content: string): boolean {
  const lines = content.trim().split('\n');
  if (lines.length < 2) return false;

  const first = lines[0].trim();
  if (!first.startsWith('|') || (first.match(/\|/g) || []).length < 2) return false;

  const second = lines[1].trim();
  if (!second.startsWith('|') || !/^[\s|:-]+$/.test(second) || !second.includes('-')) {
    return false;
  }

  for (let i = 2; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    if (!line.startsWith('|')) return false;
  }

  return true;
}

function unwrapTablesFromCodeBlocks(src: string): string {
  return src.replace(
    /(^|\n)(```|~~~)\s*([^\n]*)\n([\s\S]*?)\n\2(\n|$)/g,
    (match, prefix, _fence, info, body, suffix) => {
      const language = String(info || '').trim().toLowerCase();
      const allowUnwrap =
        language === '' ||
        language === 'markdown' ||
        language === 'md' ||
        language === 'table' ||
        language === 'text' ||
        language === 'plaintext' ||
        language === 'txt';

      if (allowUnwrap && isMarkdownTableContent(body)) {
        return `${prefix}\n${body.trim()}\n${suffix}`;
      }
      return match;
    }
  );
}

function normalizeInlineTables(src: string): string {
  const lines = src.split('\n');

  for (let i = 0; i < lines.length - 1; i++) {
    const line = lines[i];
    const nextLine = lines[i + 1] ?? '';
    const nextTrim = nextLine.trim();
    const looksLikeSeparator = nextTrim.startsWith('|') && nextTrim.includes('-');
    if (!looksLikeSeparator) continue;

    const firstPipe = line.indexOf('|');
    if (firstPipe <= 0) continue;

    const prefix = line.slice(0, firstPipe);
    if (!prefix.trim()) continue;
    const normalizedHeader = line.slice(firstPipe).replace(/^\s+/, '');
    if ((normalizedHeader.match(/\|/g) || []).length < 2) continue;

    lines.splice(i, 1, prefix.replace(/\s+$/, ''), normalizedHeader);
    i++;
  }

  const result: string[] = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const next = lines[i + 1] ?? '';
    const lineTrim = line.trim();
    const nextTrim = next.trim();

    const isHeader =
      lineTrim.startsWith('|') &&
      (lineTrim.match(/\|/g) || []).length >= 2 &&
      nextTrim.startsWith('|') &&
      /^[\s|:-]+$/.test(nextTrim) &&
      nextTrim.includes('-');

    if (isHeader && result.length > 0 && result[result.length - 1].trim() !== '') {
      result.push('');
    }
    result.push(line);
  }

  return result.join('\n');
}

function preprocessMarkdownForMobile(content: string): string {
  let processed = content.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  processed = unwrapTablesFromCodeBlocks(processed);
  processed = processed.replace(/<br\s*\/?>/gi, '\n');
  processed = normalizeInlineTables(processed);
  return processed;
}

function parseTableRows(tableLines: string[]): ChartConfigLite | null {
  if (tableLines.length < 2) return null;

  const isSeparatorLine = (line: string) => {
    const trimmed = line.trim();
    if (!trimmed.includes('|')) return false;
    const normalized = trimmed.replace(/[|\s]/g, '');
    return normalized.length > 0 && /^[:\-]+$/.test(normalized);
  };

  const separatorIdx = tableLines.findIndex(isSeparatorLine);
  if (separatorIdx < 1) return null;

  const headers = tableLines[0]
    .split('|')
    .map((h) => h.trim())
    .filter(Boolean);
  if (headers.length < 2) return null;

  const data = tableLines
    .slice(separatorIdx + 1)
    .map((line) => {
      if (!line.trim() || isSeparatorLine(line)) return null;
      const values = line
        .split('|')
        .map((v) => v.trim())
        .filter(Boolean);
      if (values.length === 0) return null;

      const row: Record<string, string | number> = {};
      headers.forEach((header, idx) => {
        const value = values[idx] ?? '';
        const asNumber = Number(value);
        row[header] = Number.isNaN(asNumber) || value.trim() === '' ? value : asNumber;
      });
      return row;
    })
    .filter((row): row is Record<string, string | number> => row !== null);

  return {
    xKey: headers[0],
    dataKeys: headers.slice(1),
    data,
  };
}

function parseChartCodeFence(code: string, language: string): ChartConfigLite | null {
  const lang = language.trim().toLowerCase();
  const lines = code.trim().split('\n');

  if (lang === 'chart-json') {
    try {
      const parsed = JSON.parse(code) as Partial<ChartConfigLite> & { data?: Array<Record<string, any>> };
      if (!Array.isArray(parsed.data) || parsed.data.length === 0) return null;
      const xKey = parsed.xKey || Object.keys(parsed.data[0])[0];
      const dataKeys = parsed.dataKeys || Object.keys(parsed.data[0]).filter((k) => k !== xKey);
      if (!xKey || dataKeys.length === 0) return null;
      return {
        title: parsed.title,
        description: parsed.description,
        xKey,
        dataKeys,
        data: parsed.data as Array<Record<string, string | number>>,
      };
    } catch {
      return null;
    }
  }

  const tableLines = lines.filter((line) => line.includes('|'));
  const tableConfig = parseTableRows(tableLines);
  if (!tableConfig) return null;

  if (lang === 'chart-table') {
    return tableConfig;
  }

  // `chart` fence: extract simple metadata lines above the table.
  let title: string | undefined;
  let description: string | undefined;
  for (const line of lines) {
    if (line.includes('|')) break;
    const [rawKey, ...rest] = line.split(':');
    if (!rawKey || rest.length === 0) continue;
    const key = rawKey.trim().toLowerCase();
    const value = rest.join(':').trim();
    if (key === 'title') title = value;
    if (key === 'description') description = value;
  }

  return { ...tableConfig, title, description };
}

export function MarkdownContent({
  content,
  theme,
  variant = 'chat',
  textColor,
}: Props) {
  const isPreview = variant === 'preview';
  const isNotes = variant === 'notes';
  const resolvedColor = textColor || theme.assistantBubbleText;
  const processedContent = preprocessMarkdownForMobile(content);

  const markdownStyles = StyleSheet.create({
    body: {
      color: resolvedColor,
      fontSize: isPreview ? 14 : isNotes ? 17 : 16,
      lineHeight: isPreview ? 18 : isNotes ? 25 : 22,
      width: '100%',
      flexShrink: 1,
    },
    text: {
      color: resolvedColor,
      flexShrink: 1,
      maxWidth: '100%',
    },
    paragraph: {
      marginTop: 0,
      marginBottom: isPreview ? 0 : isNotes ? 12 : 8,
      width: '100%',
      flexDirection: 'column',
      flexWrap: 'nowrap',
      alignItems: 'stretch',
      justifyContent: 'flex-start',
    },
    heading1: {
      color: resolvedColor,
      fontSize: isPreview ? 14 : isNotes ? 24 : 22,
      fontWeight: '700' as const,
      marginBottom: isPreview ? 0 : isNotes ? 10 : 8,
    },
    heading2: {
      color: resolvedColor,
      fontSize: isPreview ? 14 : isNotes ? 22 : 20,
      fontWeight: '600' as const,
      marginBottom: isPreview ? 0 : isNotes ? 8 : 6,
    },
    heading3: {
      color: resolvedColor,
      fontSize: isPreview ? 14 : isNotes ? 20 : 18,
      fontWeight: '600' as const,
      marginBottom: isPreview ? 0 : isNotes ? 6 : 4,
    },
    code_inline: {
      backgroundColor: theme.surfaceSecondary,
      color: theme.primary,
      paddingHorizontal: 5,
      paddingVertical: isPreview ? 1 : 2,
      borderRadius: 4,
      fontSize: isPreview ? 12 : 14,
      fontFamily: 'Menlo',
    },
    fence: {
      backgroundColor: theme.surfaceSecondary,
      padding: isPreview ? 6 : 12,
      borderRadius: 8,
      fontSize: isPreview ? 12 : 13,
      fontFamily: 'Menlo',
      color: resolvedColor,
      marginVertical: isPreview ? 2 : 8,
    },
    code_block: {
      backgroundColor: theme.surfaceSecondary,
      padding: isPreview ? 6 : 12,
      borderRadius: 8,
      fontSize: isPreview ? 12 : 13,
      fontFamily: 'Menlo',
      color: resolvedColor,
    },
    link: {
      color: theme.primary,
    },
    blockquote: {
      backgroundColor: theme.surfaceSecondary,
      borderLeftColor: theme.primary,
      borderLeftWidth: 3,
      paddingLeft: isPreview ? 8 : 12,
      paddingVertical: isPreview ? 2 : 4,
      marginVertical: isPreview ? 2 : 8,
    },
    bullet_list_icon: {
      color: resolvedColor,
    },
    ordered_list_icon: {
      color: resolvedColor,
    },
    list_item: {
      marginVertical: isPreview ? 0 : 2,
    },
    hr: {
      backgroundColor: theme.border,
      height: 1,
      marginVertical: 12,
    },
    table: {
      backgroundColor: 'transparent',
      alignSelf: 'flex-start',
    },
    tr: {
      flexDirection: 'row',
      alignItems: 'stretch',
      alignSelf: 'flex-start',
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderColor: theme.border,
    },
    th: {
      borderColor: theme.border,
      borderRightWidth: StyleSheet.hairlineWidth,
      flexGrow: 0,
      flexShrink: 0,
      paddingHorizontal: isPreview ? 6 : 8,
      paddingVertical: isPreview ? 4 : 6,
      width: isPreview ? 110 : 130,
      backgroundColor: 'transparent',
    },
    td: {
      borderColor: theme.border,
      borderRightWidth: StyleSheet.hairlineWidth,
      flexGrow: 0,
      flexShrink: 0,
      paddingHorizontal: isPreview ? 6 : 8,
      paddingVertical: isPreview ? 4 : 6,
      width: isPreview ? 110 : 130,
      backgroundColor: 'transparent',
    },
    tableViewport: {
      marginVertical: isPreview ? 2 : 8,
    },
    tableFrame: {
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.border,
      borderRadius: 8,
      backgroundColor: 'transparent',
      alignSelf: 'flex-start',
      minWidth: '100%',
    },
    chartContainer: {
      marginVertical: isPreview ? 2 : 8,
      backgroundColor: 'transparent',
      padding: 0,
    },
    chartTitle: {
      color: resolvedColor,
      fontSize: isPreview ? 13 : 14,
      fontWeight: '600' as const,
      marginBottom: 2,
    },
    chartDescription: {
      color: theme.textSecondary,
      fontSize: isPreview ? 11 : 12,
      marginBottom: 8,
    },
    chartTable: {
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.border,
      borderRadius: 6,
      overflow: 'hidden',
      backgroundColor: 'transparent',
      minWidth: isPreview ? 340 : 480,
    },
    chartRow: {
      flexDirection: 'row',
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderColor: theme.border,
    },
    chartHeaderCell: {
      minWidth: isPreview ? 90 : 110,
      paddingHorizontal: isPreview ? 6 : 8,
      paddingVertical: isPreview ? 4 : 6,
      backgroundColor: 'transparent',
      borderRightWidth: StyleSheet.hairlineWidth,
      borderColor: theme.border,
    },
    chartCell: {
      minWidth: isPreview ? 90 : 110,
      paddingHorizontal: isPreview ? 6 : 8,
      paddingVertical: isPreview ? 4 : 6,
      borderRightWidth: StyleSheet.hairlineWidth,
      borderColor: theme.border,
    },
    chartHeaderText: {
      color: resolvedColor,
      fontSize: isPreview ? 11 : 12,
      fontWeight: '600' as const,
    },
    chartCellText: {
      color: resolvedColor,
      fontSize: isPreview ? 11 : 12,
    },
    strong: {
      fontWeight: '700' as const,
    },
  });

  const markdownRules: RenderRules = {
    table: (node: ASTNode, children) => {
      const isDarkMode = theme.background === '#000000';
      const tableContent = (
        <View style={markdownStyles.tableFrame}>
          <View style={markdownStyles.table}>{children}</View>
        </View>
      );

      return (
        <View key={node.key} style={markdownStyles.tableViewport}>
          <TableScrollView
            showIndicator={!isPreview}
            darkMode={isDarkMode}
            fadeColor={theme.background}
          >
            {tableContent}
          </TableScrollView>
        </View>
      );
    },
    thead: (node: ASTNode, children) => (
      <View key={node.key}>{children}</View>
    ),
    tbody: (node: ASTNode, children) => (
      <View key={node.key}>{children}</View>
    ),
    tr: (node: ASTNode, children) => (
      <View key={node.key} style={markdownStyles.tr}>{children}</View>
    ),
    th: (node: ASTNode, children) => (
      <View key={node.key} style={markdownStyles.th}>{children}</View>
    ),
    td: (node: ASTNode, children) => (
      <View key={node.key} style={markdownStyles.td}>{children}</View>
    ),
    fence: (node: ASTNode & { sourceInfo?: string }, _children, _parent, styles) => {
      const language = (node.sourceInfo || '').trim().toLowerCase();
      if (language !== 'chart' && language !== 'chart-table' && language !== 'chart-json') {
        const raw = typeof node.content === 'string' ? node.content : '';
        const code = raw.endsWith('\n') ? raw.slice(0, -1) : raw;
        return (
          <Text key={node.key} style={styles.fence}>
            {code}
          </Text>
        );
      }

      const parsed = parseChartCodeFence(node.content || '', language);
      if (!parsed || parsed.data.length === 0) {
        return (
          <Text key={node.key} style={styles.fence}>
            {node.content}
          </Text>
        );
      }

      const headers = [parsed.xKey, ...parsed.dataKeys];

      return (
        <View key={node.key} style={styles.chartContainer}>
          {parsed.title ? <Text style={styles.chartTitle}>{parsed.title}</Text> : null}
          {parsed.description ? (
            <Text style={styles.chartDescription}>{parsed.description}</Text>
          ) : null}
          <ScrollView
            horizontal
            nestedScrollEnabled
            showsHorizontalScrollIndicator={!isPreview}
          >
            <View style={styles.chartTable}>
              <View style={styles.chartRow}>
                {headers.map((header) => (
                  <View key={`h-${header}`} style={styles.chartHeaderCell}>
                    <Text style={styles.chartHeaderText}>{header}</Text>
                  </View>
                ))}
              </View>
              {parsed.data.map((row, rowIndex) => (
                <View key={`r-${rowIndex}`} style={styles.chartRow}>
                  {headers.map((header) => (
                    <View key={`${rowIndex}-${header}`} style={styles.chartCell}>
                      <Text style={styles.chartCellText}>
                        {String(row[header] ?? '')}
                      </Text>
                    </View>
                  ))}
                </View>
              ))}
            </View>
          </ScrollView>
        </View>
      );
    },
  };

  return (
    <Markdown style={markdownStyles} rules={markdownRules}>
      {processedContent}
    </Markdown>
  );
}
