/**
 * Detect if content inside a code block is actually a markdown table that should be rendered
 * as a GFM table rather than as code. This handles cases where LLMs wrap tables in code blocks.
 */
function isMarkdownTableContent(content: string): boolean {
  const lines = content.trim().split('\n');
  if (lines.length < 2) return false;

  // Check if first line looks like a table header (starts with | and has multiple |)
  const firstLine = lines[0].trim();
  if (!firstLine.startsWith('|') || (firstLine.match(/\|/g) || []).length < 2) {
    return false;
  }

  // Check if second line is a separator row (contains |, -, and optionally :)
  const secondLine = lines[1].trim();
  if (!secondLine.startsWith('|') || !/^[\s|:|-]+$/.test(secondLine) || !secondLine.includes('-')) {
    return false;
  }

  // Check remaining lines also look like table rows
  for (let i = 2; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line === '') continue; // Allow empty lines
    if (!line.startsWith('|')) return false;
  }

  return true;
}

/**
 * Unwrap markdown tables that are incorrectly wrapped in fenced code blocks.
 * LLMs sometimes wrap tables in ```...``` which prevents them from being rendered as GFM tables.
 */
function unwrapTablesFromCodeBlocks(src: string): string {
  // Match fenced code blocks (``` or ~~~) without a language specifier or with empty language
  // that contain what looks like a markdown table
  return src.replace(
    /(^|\n)(```|~~~)\s*\n([\s\S]*?)\n\2(\n|$)/g,
    (match, prefix, _fence, content, suffix) => {
      // Check if the content is a markdown table
      if (isMarkdownTableContent(content)) {
        // Unwrap the table - return it without the code fences
        // Add blank lines around it to ensure proper GFM parsing
        return `${prefix}\n${content.trim()}\n${suffix}`;
      }
      // Not a table, keep the code block as-is
      return match;
    }
  );
}

/**
 * Utility: mask segments that must be preserved verbatim (fenced & inline code, math blocks).
 */
function maskCodeSegments(src: string) {
  const masks: Record<string, string> = {};
  let i = 0;

  // Mask display math blocks $$...$$ first (before code blocks to avoid conflicts)
  // Handle both empty and non-empty math blocks
  src = src.replace(/\$\$([\s\S]*?)\$\$/g, (_m, body) => {
    const key = `__DISPLAY_MATH_${i++}__`;
    // Preserve empty math blocks as-is (they'll be rendered by KaTeX)
    masks[key] = `$$${body}$$`;
    return key;
  });

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

/**
 * Mask inline math $...$ but only if it doesn't look like currency
 */
function maskInlineMath(src: string) {
  const masks: Record<string, string> = {};
  let i = 0;

  // Mask inline math $...$ (but not $$...$$ which are already masked)
  // Only mask if it doesn't look like currency (must be ONLY a number, not starting with a number)
  src = src.replace(/(?<!\$)\$(?!\$)([^$\n]+?)(?<!\$)\$(?!\$)/g, (_m, body) => {
    const trimmed = body.trim();
    // Don't mask if it looks like currency (must be ONLY digits, commas, decimals, and optional suffixes)
    // This regex matches the full currency pattern: digits (with commas), optional decimals, optional k/m/b suffix
    // It must match the ENTIRE string, not just the start
    const looksLikeCurrency = /^-?\d{1,3}(?:,\d{3})*(?:\.\d+)?(?:\s?[KMBkmb]|[Kk]ilo|[Mm]illion|[Bb]illion)?$/.test(trimmed);
    if (looksLikeCurrency) return _m;
    
    // Fix: Double-escape backslashes followed by punctuation to prevent Markdown from consuming them
    // e.g. \, -> \\,  and \{ -> \\{
    // We protect any backslash that isn't followed by a letter or digit
    const fixedBody = body.replace(/\\([^A-Za-z0-9])/g, (_match: string, char: string) => {
      if (char === '\\') return '\\\\\\\\';
      return '\\\\' + char;
    });

    const key = `__INLINE_MATH_${i++}__`;
    masks[key] = `$${fixedBody}$`;
    return key;
  });

  return { masked: src, masks };
}

/**
 * Ensure Markdown tables start on their own line even if the LLM placed them
 * immediately after punctuation like ":" without a newline.
 */
function normalizeInlineTables(src: string) {
  const lines = src.split('\n');

  // First pass: handle tables on the same line as preceding text (e.g., "Table: | Col |")
  for (let i = 0; i < lines.length - 1; i++) {
    const line = lines[i];
    const nextLine = lines[i + 1] ?? '';
    if (!line || !nextLine) continue;

    const nextTrim = nextLine.trim();
    const looksLikeSeparator =
      nextTrim.startsWith('|') &&
      nextTrim.includes('-');
    if (!looksLikeSeparator) continue;

    const firstPipe = line.indexOf('|');
    if (firstPipe <= 0) continue; // Already at start or no table detected

    const prefix = line.slice(0, firstPipe);
    if (!prefix || prefix.trim() === '') continue;

    const trimmedPrefix = prefix.trim();
    const prefixWithoutSpaces = trimmedPrefix.replace(/\s+/g, '');
    const isBlockQuotePrefix = prefixWithoutSpaces !== '' && /^[>]+$/.test(prefixWithoutSpaces);
    const isListPrefix = /^[-*+]\s*$/.test(trimmedPrefix);
    const isOrderedListPrefix = /^\d+\.\s*$/.test(trimmedPrefix);
    if (isBlockQuotePrefix || isListPrefix || isOrderedListPrefix) continue;

    const tableHeader = line.slice(firstPipe);
    const pipeCount = (tableHeader.match(/\|/g) || []).length;
    if (pipeCount < 2) continue; // Need at least header + one column separator

    const beforeLine = prefix.replace(/\s+$/, '');
    const normalizedHeader = tableHeader.replace(/^\s+/, '');
    if (!beforeLine) continue;

    lines.splice(i, 1, beforeLine, normalizedHeader);
    i++; // Skip past the newly inserted header line
  }

  // Second pass: ensure blank line before tables that start with | on their own line
  // This handles cases like:
  //   some text
  //   | Header | Header |
  //   |--------|--------|
  // Which need a blank line before the table for GFM to recognize it
  const result: string[] = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lineTrim = line.trim();
    const nextLine = lines[i + 1] ?? '';
    const nextTrim = nextLine.trim();

    // Check if this line is a table header row (starts with |, has multiple |, followed by separator row)
    const isTableHeader =
      lineTrim.startsWith('|') &&
      (lineTrim.match(/\|/g) || []).length >= 2 &&
      nextTrim.startsWith('|') &&
      /^[\s|:-]+$/.test(nextTrim) &&
      nextTrim.includes('-');

    if (isTableHeader && result.length > 0) {
      const prevLine = result[result.length - 1];
      // If previous line is not empty and not already a blank line, insert one
      if (prevLine.trim() !== '') {
        result.push('');
      }
    }

    result.push(line);
  }

  return result.join('\n');
}

const LATEX_ENVIRONMENTS = [
  'aligned',
  'align',
  'align*',
  'array',
  'cases',
  'pmatrix',
  'bmatrix',
  'vmatrix',
  'Vmatrix',
  'matrix',
  'smallmatrix',
  'gather',
  'gather*',
  'multline',
  'multline*',
  'split',
  'flalign',
  'flalign*',
  'eqnarray',
  'equation',
  'equation*',
];

function createMaskPlaceholder(masks: Record<string, string>, prefix: string): string {
  let index = 0;
  let key = `__${prefix}_${index}__`;
  while (Object.prototype.hasOwnProperty.call(masks, key)) {
    index++;
    key = `__${prefix}_${index}__`;
  }
  return key;
}

function wrapLatexEnvironments(src: string, masks: Record<string, string>) {
  if (!LATEX_ENVIRONMENTS.length) return src;
  const envPattern = LATEX_ENVIRONMENTS.join('|');
  const regex = new RegExp(String.raw`\\begin\{(${envPattern})\}([\s\S]*?)\\end\{\1\}`, 'g');

  return src.replace(regex, (match, _env, _body, offset, source) => {
    const before = source.slice(0, offset);
    const after = source.slice(offset + match.length);

    // Check if already wrapped in display math ($$ or \[...\])
    // Case 1: $$ or \[ immediately before (with optional whitespace)
    const hasDisplayStart = /(\$\$|\\\[)\s*$/.test(before);
    const hasDisplayEnd = /^\s*(\$\$|\\\])/.test(after);

    if (hasDisplayStart && hasDisplayEnd) {
      return match;
    }

    // Case 2: Check if we're anywhere inside \[...\] block
    // Find the last \[ and \] before our position
    const lastOpenBracket = before.lastIndexOf('\\[');
    const lastCloseBracket = before.lastIndexOf('\\]');
    const isInsideBracketMath = lastOpenBracket > lastCloseBracket && lastOpenBracket !== -1;

    if (isInsideBracketMath) {
      // Verify there's a closing \] after the environment
      const hasClosingBracket = /\\]/.test(after);
      if (hasClosingBracket) {
        return match;
      }
    }

    // Case 3: Check if inside display math $$...$$ that wasn't at boundary
    // Find matching $$ pairs before our position
    const displayMathPattern = /\$\$/g;
    let displayCount = 0;
    while (displayMathPattern.exec(before) !== null) {
      displayCount++;
    }
    const isInsideDisplayMath = displayCount % 2 === 1;

    if (isInsideDisplayMath) {
      const hasClosingDisplay = /\$\$/.test(after);
      if (hasClosingDisplay) {
        return match;
      }
    }

    // Case 4: Check if inside inline math ($...$)
    // Remove $$ first to avoid double-counting, then count single $
    const beforeWithoutDisplay = before.replace(/\$\$/g, '__DD__');
    // Also remove escaped \$ signs
    const beforeClean = beforeWithoutDisplay.replace(/\\\$/g, '__ES__');
    // Count unescaped single $ signs
    const dollarMatches = beforeClean.match(/\$/g) || [];
    const isInsideInlineMath = dollarMatches.length % 2 === 1;

    if (isInsideInlineMath) {
      const afterWithoutDisplay = after.replace(/\$\$/g, '__DD__');
      const afterClean = afterWithoutDisplay.replace(/\\\$/g, '__ES__');
      const hasClosingDollar = /^[^$]*\$(?!\$)/.test(afterClean);
      if (hasClosingDollar) {
        // Already inside inline math - leave it alone for KaTeX to handle
        return match;
      }
    }

    const placeholder = createMaskPlaceholder(masks, 'LATEX_ENV');
    const block = match.trim();
    masks[placeholder] = `\n$$\n${block}\n$$\n`;
    return placeholder;
  });
}

function unmaskCodeSegments(src: string, masks: Record<string, string>) {
  for (const [k, v] of Object.entries(masks)) {
    const pattern = new RegExp(k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g');
    src = src.replace(pattern, () => v);
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

    // 0a) Unwrap markdown tables that are incorrectly wrapped in code blocks
    //     LLMs sometimes wrap tables in ``` which prevents GFM table rendering
    processed = unwrapTablesFromCodeBlocks(processed);

    // 0b) Mask code blocks/inline code and display math FIRST so we never touch them during preprocessing
    //     This is critical for preserving $ symbols in Mermaid and other code blocks
    const { masked, masks } = maskCodeSegments(processed);
    processed = masked;
    
    // Convert HTML <br> tags into newline characters so they render like real line breaks
    processed = processed.replace(/<br\s*\/?>/gi, '\n');
    
    // LLMs sometimes keep the first table row on the same line as preceding text (e.g. "Table: | Col |")
    // ReactMarkdown expects the table to start on a fresh line, so split those constructs.
    processed = normalizeInlineTables(processed);
    
    // Wrap standalone LaTeX environments (aligned, cases, matrices, etc.) in display math fences
    // so KaTeX can parse them reliably, but skip anything that's already wrapped.
    processed = wrapLatexEnvironments(processed, masks);
    
    // 0.5) Process currency BEFORE masking inline math to avoid conflicts
    //      Temporarily replace currency with placeholders
    const currencyMap = new Map<string, string>();
    let idx = 0;

    // Range helper: replace ranges like $5-$10 or $5–$10 with placeholders for BOTH sides
    // Currency pattern: must be followed by space, punctuation, end of string, or valid suffix (k/m/b)
    // Must NOT be followed by a letter (unless it's a valid suffix)
    const currencyCore = String.raw`-?\$\(?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?(?:\s?(?:[KMBkmb]|[Kk]ilo|[Mm]illion|[Bb]illion))?|\$-?\d+(?:\.\d+)?(?:\s?(?:[KMBkmb]|[Kk]ilo|[Mm]illion|[Bb]illion))?`;
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

    // Single currency amounts - must be followed by space, punctuation, or end of string
    // Use negative lookahead to ensure it's not followed by a letter (unless it's a valid suffix)
    const singleCurrencyRegex = new RegExp(
      String.raw`-?\$\(?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?(?:\s?(?:[KMBkmb]|[Kk]ilo|[Mm]illion|[Bb]illion))?(?!\w)|\$-?\d+(?:\.\d+)?(?:\s?(?:[KMBkmb]|[Kk]ilo|[Mm]illion|[Bb]illion))?(?!\w)`,
      'g'
    );
    processed = processed.replace(singleCurrencyRegex, (match, offset, string) => {
      // Double-check: if followed by a letter (and not a valid suffix), it's not currency
      const afterMatch = string.substring(offset + match.length);
      if (afterMatch.match(/^[a-zA-Z]/) && !match.match(/[KMBkmb]|[Kk]ilo|[Mm]illion|[Bb]illion$/)) {
        return match; // Don't replace, it's probably part of math like $10n$
      }
      const ph = `__CURRENCY_${idx++}__`;
      currencyMap.set(ph, match);
      return ph;
    });

    // Now mask inline math (currency is already protected)
    const { masked: mathMasked, masks: mathMasks } = maskInlineMath(processed);
    processed = mathMasked;
    // Merge math masks into main masks
    Object.assign(masks, mathMasks);
    
    // Auto-detect and wrap common math patterns that might not have delimiters
    // This helps catch expressions like "x^2 + y^2 = z^2" and wrap them properly
    const mathPatterns = [
      // Equations with equals sign and math operators
      /(?:^|\s)([a-zA-Z0-9]+\s*[\^_]\s*[a-zA-Z0-9{}]+(?:\s*[+\-*/]\s*[a-zA-Z0-9]+\s*[\^_]\s*[a-zA-Z0-9{}]+)*\s*=\s*[^$\n]+)(?:\s|$)/g,
      // Fractions not already wrapped
      /(?:^|\s)(\\frac\{[^}]+\}\{[^}]+\})(?:\s|$)/g,
      // Square roots, integrals, sums not already wrapped
      /(?:^|\s)(\\(?:sqrt|int|sum|prod|lim|log|ln|sin|cos|tan|exp)\b[^$\n]{0,50})(?:\s|$)/g,
      // Chemical formulas (e.g., H2O, CO2, Ca(OH)2)
      /(?:^|\s)([A-Z][a-z]?(?:\d+)?(?:\([A-Z][a-z]?(?:\d+)?\))?(?:\d+)?(?:[+-]\d*)?)+(?:\s|$)/g,
    ];
    
    // Wrap detected patterns in $ delimiters if not already wrapped
    mathPatterns.forEach(pattern => {
      processed = processed.replace(pattern, (match, expr) => {
        // Check if already wrapped in $ or $$
        if (match.includes('$')) return match;
        // Avoid wrapping single-letter words like "I" that are not math
        const trimmed = String(expr ?? '').trim();
        if (/^[A-Za-z]$/.test(trimmed)) return match;

        // Heuristics: only auto-wrap if it clearly looks like math or chemistry
        const looksLikeMath = /[\\^_+=<>]|\\b(?:frac|sqrt|sum|int|lim|log|ln|sin|cos|tan|exp)\b/.test(trimmed);
        const hasDigit = /\d/.test(trimmed);
        const hasParens = /[()]/.test(trimmed);
        const uppercaseCount = (trimmed.match(/[A-Z]/g) || []).length;
        const lowercaseCount = (trimmed.match(/[a-z]/g) || []).length;
        const hasTwoElementTokens = uppercaseCount >= 2; // e.g., NaCl, CO2 (with digits handled separately)

        const looksLikeChemistry = hasDigit || hasParens || (hasTwoElementTokens && lowercaseCount > 0);

        if (!looksLikeMath && !looksLikeChemistry) return match;

        return match.replace(expr, `$${expr}$`);
      });
    });

    // 1) Normalize LaTeX delimiters to markdown-math friendly forms
    //    \[...\] -> $$...$$   and   \(...\) -> $...$
    processed = processed.replace(/\\\[([\s\S]*?)\\\]/g, (_m, p1) => `\n$$${p1}$$\n`);
    processed = processed.replace(/\\\(([\s\S]*?)\\\)/g, (_m, p1) => `$${p1}$`);

    // 2) Protect stray $ that aren't math (e.g., isolated dollar signs in prose)
    //    If we see $word$ that doesn't look like math, escape both sides.
    //    Skip if it's already a placeholder (currency or math)
    processed = processed.replace(
      /(?<!\\)\$(?!\$)([^$\n]*?)(?<!\\)\$(?!\$)/g,
      (m, inner) => {
        // Skip if this is already a placeholder
        if (m.includes('__CURRENCY_') || m.includes('__INLINE_MATH_') || m.includes('__DISPLAY_MATH_')) {
          return m;
        }
        
        // Handle empty math blocks - leave them as-is (KaTeX will handle them)
        if (inner.trim() === '') {
          return m;
        }
        
        // Much more aggressive math detection - assume math unless it's clearly currency
        const isLikelyCurrency = /^\d+(?:,\d{3})*(?:\.\d{2})?$/.test(inner.trim());
        const hasBackslash = /\\/.test(inner);
        const hasMathOperators = /[+\-*/=<>^_{}()]/.test(inner);
        const hasLettersAndNumbers = /[a-zA-Z].*\d|\d.*[a-zA-Z]/.test(inner);
        const hasGreekLetters = /\\(?:alpha|beta|gamma|delta|epsilon|theta|lambda|mu|pi|sigma|omega)/.test(inner);
        const hasMathFunctions = /\\(?:frac|sqrt|sum|int|lim|log|ln|sin|cos|tan|exp)/.test(inner);
        const isSingleLetterVariable = /^[A-Za-z]$/.test(inner.trim());
        
        // It's probably math if it has any math-like characteristics
        const isProbablyMath = !isLikelyCurrency && (
          hasBackslash || 
          hasMathOperators || 
          hasLettersAndNumbers || 
          hasGreekLetters || 
          hasMathFunctions ||
          isSingleLetterVariable ||
          inner.length > 1 // Single characters are likely variables unless clearly non-math
        );
        
        if (isProbablyMath) return m;
        return `\\$${inner}\\$`;
      }
    );

    // 2.5) Escape stray double-dollar markers that appear inline with text and have no closing pair
    processed = processed
      .split('\n')
      .map((line) => {
        const firstIndex = line.indexOf('$$');
        if (firstIndex === -1) return line;
        if (line.trim() === '$$') return line; // display math fence on its own line
        const secondIndex = line.indexOf('$$', firstIndex + 2);
        if (secondIndex !== -1) return line; // already has a matching pair on the same line
        return line.replace('$$', '\\$\\$');
      })
      .join('\n');

    // 3) Restore currency placeholders but convert '$' into HTML entities so remark-math never
    //    interprets them as inline math delimiters. Strip any escaping slashes that users provided.
    currencyMap.forEach((original, ph) => {
      const entitySafe = original.replace(/\$/g, '&#36;');
      processed = processed.replace(new RegExp(ph.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), entitySafe);
    });
    processed = processed.replace(/\\&#36;/g, '&#36;');

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
 * Utility: detect likely math without false positives from currency
 */
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
