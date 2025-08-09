import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import 'katex/dist/katex.min.css';
import '../MarkdownStyles.css';

/**
 * Utility: mask segments that must be preserved verbatim (fenced & inline code).
 */
function maskCodeSegments(src: string) {
  const masks: Record<string, string> = {};
  let i = 0;

  // Mask fenced code blocks ``` ``` and ~~~ ~~~
  src = src.replace(/(^|\n)(```|~~~)([^\n]*)\n([\s\S]*?)\n\2(\n|$)/g, (_m, p1, fence, info, body, p5) => {
    const key = `__FENCED_CODE_${i++}__`;
    masks[key] = `${p1}${fence}${info}\n${body}\n${fence}${p5}`;
    return key;
  });

  // Mask inline code `...`
  src = src.replace(/`([^`]+)`/g, (_m) => {
    const key = `__INLINE_CODE_${i++}__`;
    masks[key] = _m;
    return key;
  });

  return { masked: src, masks };
}

function unmaskCodeSegments(src: string, masks: Record<string, string>) {
  for (const [k, v] of Object.entries(masks)) {
    src = src.replace(new RegExp(k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), v);
  }
  return src;
}

/**
 * Enhanced markdown preprocessing that handles both currency and math notation
 * without clobbering each other.
 */
export const preprocessMarkdown = (content: string): string => {
  if (!content || typeof content !== 'string') return '';

  try {
    // Normalize line endings
    let processed = content.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

    // 0) Mask code blocks/inline code so we never touch them
    const { masked, masks } = maskCodeSegments(processed);
    processed = masked;

    // 1) Temporarily replace currency with placeholders
    //    - Supports negatives, parentheses, thousands, decimals, ranges, and suffixes (k/m/b, etc.)
    //    - Examples: $5, $1,299.99, ($12.50), -$3.25, $5–$10, $5-$10, $1.2k, $3M
    const currencyMap = new Map<string, string>();
    let idx = 0;

    // Range helper: replace ranges like $5-$10 or $5–$10 with placeholders for BOTH sides
    const currencyCore = String.raw`-?\$\(?\d{1,3}(?:,\d{3})*(?:\.\d+)?|\$-?\d+(?:\.\d+)?|\$-?\d+(?:\.\d+)?\)?(?:\s?(?:[KMBkmb]|[Kk]ilo|[Mm]illion|[Bb]illion))?`;
    const rangeRegex = new RegExp(
      String.raw`(${currencyCore})(\s?[–-]\s?)(${currencyCore})`,
      'g'
    );

    processed = processed.replace(rangeRegex, (_m, left, dash, right) => {
      const lph = `__CURRENCY_${idx++}__`;
      const rph = `__CURRENCY_${idx++}__`;
      currencyMap.set(lph, left);
      currencyMap.set(rph, right);
      return `${lph}${dash}${rph}`;
    });

    // Single currency amounts
    const singleCurrencyRegex = new RegExp(currencyCore, 'g');
    processed = processed.replace(singleCurrencyRegex, (match) => {
      const ph = `__CURRENCY_${idx++}__`;
      currencyMap.set(ph, match);
      return ph;
    });

    // 2) Normalize LaTeX delimiters to markdown-math friendly forms
    //    \[...\] -> $$...$$   and   \(...\) -> $...$
    processed = processed.replace(/\\\[([\s\S]*?)\\\]/g, (_m, p1) => `\n$$${p1}$$\n`);
    processed = processed.replace(/\\\(([\s\S]*?)\\\)/g, (_m, p1) => `$${p1}$`);

    // 3) Protect stray $ that aren’t math (e.g., isolated dollar signs in prose)
    //    If we see $word$ that doesn't look like math, escape both sides.
    processed = processed.replace(
      /(?<!\\)\$(?!\$)([^$\n]+?)(?<!\\)\$(?!\$)/g,
      (m, inner) => {
        // Looks like math if letters/symbols typical for LaTeX appear
        const isProbablyMath =
          /[a-zA-Z\\{}_^]|[+\-*/=<>]|\\frac|\\sum|\\int|\\alpha|\\beta|\\gamma/.test(inner);
        if (isProbablyMath) return m;
        return `\\$${inner}\\$`;
      }
    );

    // 4) Restore currency placeholders BUT escape the leading '$' so remark-math won’t pair them
    //    This is the key to allowing $…$ math while keeping $ amounts literal.
    currencyMap.forEach((original, ph) => {
      const escaped = original.replace(/\$/g, '\\$');
      processed = processed.replace(new RegExp(ph.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), escaped);
    });

    // 5) Unmask code segments
    processed = unmaskCodeSegments(processed, masks);

    // 6) Final tidy
    processed = processed.trimEnd() + '\n';
    return processed;
  } catch (err) {
    console.warn('Error preprocessing markdown:', err);
    return content;
  }
};

/**
 * Custom link component for ReactMarkdown that opens links in new tabs
 */
export const MarkdownLink: React.FC<React.AnchorHTMLAttributes<HTMLAnchorElement>> = ({
  children,
  href,
  ...props
}) => (
  <a {...props} href={href} target="_blank" rel="noopener noreferrer">
    {children}
  </a>
);

export interface MarkdownRendererProps {
  content: string;
  className?: string;
  /**
   * Optional flag to disable math rendering entirely if needed
   */
  disableMath?: boolean;
}

/**
 * Enhanced Markdown renderer with robust currency and math handling
 */
export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({
  content,
  className = '',
  disableMath = false,
}) => {
  const processedContent = preprocessMarkdown(content);
  if (!processedContent) return null;

  const remarkPlugins = disableMath
    ? [remarkGfm]
    : [[remarkMath, { singleDollarTextMath: true }], remarkGfm];

  const rehypePlugins = disableMath ? [] : [rehypeKatex];

  return (
    <div className={`markdown-content ${className}`}>
      <ReactMarkdown remarkPlugins={remarkPlugins as any} rehypePlugins={rehypePlugins}>
        {processedContent}
      </ReactMarkdown>
    </div>
  );
};

// Utility: detect likely math without false positives from currency
export const containsMathNotation = (text: string): boolean => {
  const withoutCurrency = text.replace(/\$\s?\d+(?:,\d{3})*(?:\.\d+)?\b/gi, '');
  const patterns = [
    /\$\$[\s\S]+?\$\$/,
    /(?<!\\)\$[^$\n]+?(?<!\\)\$/,
    /\\\[[\s\S]+?\\\]/,
    /\\\([^)]+?\\\)/,
  ];
  return patterns.some((re) => re.test(withoutCurrency));
};
