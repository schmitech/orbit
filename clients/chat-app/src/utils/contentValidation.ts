/**
 * Content validation utilities to prevent base64 audio data from being displayed as text
 */

const MARKDOWN_CHARACTERS = ['#', '*', '`', '[', ']', '(', ')', '{', '}', '|', '<', '>'];

const containsMarkdownSyntax = (value: string): boolean =>
  MARKDOWN_CHARACTERS.some((character) => value.includes(character));

/**
 * Detects if a string contains base64-encoded audio data
 * Base64 audio strings are typically very long and contain only base64 characters
 */
export function isBase64AudioData(text: string): boolean {
  if (!text || text.length < 1000) {
    return false; // Too short to be audio data (audio is typically >10KB when base64 encoded)
  }

  // Base64 characters: A-Z, a-z, 0-9, +, /, = (for padding)
  const base64Pattern = /^[A-Za-z0-9+/=]+$/;

  // Check if the text is mostly base64 characters
  // Remove whitespace and newlines first
  const cleaned = text.replace(/\s+/g, '');

  // Only detect as audio if:
  // 1. It's very long (>10000 chars = ~7.5KB) - typical audio is much larger
  // 2. It's pure base64 (no punctuation, no markdown, no code)
  // 3. It has no common text patterns
  if (cleaned.length > 10000 && base64Pattern.test(cleaned)) {
    // Check for common text patterns that would indicate legitimate content
    // Include programming keywords, markdown syntax, URLs, etc.
    const hasTextPatterns = /\b(the|and|for|are|but|not|you|all|can|function|const|let|var|class|return|import|export|async|await|if|else|while|true|false|null|undefined|http|https|www|error|data|response|request|api|json|xml|html|css|js|py|java|cpp|def|print|console|log)\b/i.test(text);
    const hasMarkdown = containsMarkdownSyntax(text);
    const hasPunctuation = /[.,;:!?'"()-]/.test(text);

    // If no text patterns, no markdown, and no punctuation - it's likely audio
    if (!hasTextPatterns && !hasMarkdown && !hasPunctuation) {
      return true;
    }
  }

  // Check for extremely long pure base64 (>50KB encoded = ~37.5KB raw audio)
  // At this size, it's almost certainly audio data
  if (cleaned.length > 50000 && base64Pattern.test(cleaned)) {
    // Even with some patterns, if it's this long and mostly base64, it's audio
    const nonBase64Chars = text.replace(/[A-Za-z0-9+/=\s]/g, '').length;
    if (nonBase64Chars < 10) {
      return true;
    }
  }

  return false;
}

/**
 * Sanitizes message content by removing base64 audio data
 */
export function sanitizeMessageContent(content: string): string {
  if (!content) return content;

  // Check if the entire content is base64 audio
  if (isBase64AudioData(content)) {
    return ''; // Remove it entirely
  }

  // Check for base64 audio embedded in the content
  // Only look for very long base64-like strings (>10KB encoded)
  // This threshold is high enough to avoid false positives with legitimate base64 in code
  const base64BlockPattern = /([A-Za-z0-9+/=]{10000,})/g;
  const sanitized = content.replace(base64BlockPattern, (match) => {
    // Remove whitespace to check the actual base64 content
    const cleaned = match.replace(/\s+/g, '');

    // Only remove if it's pure base64 with no text patterns
    if (cleaned.length > 10000 && /^[A-Za-z0-9+/=]+$/.test(cleaned)) {
      // Check for text patterns that would indicate legitimate content
      const hasTextPatterns = /\b(function|const|let|var|class|return|import|export|if|else|while|for|true|false|null|def|print)\b/i.test(match);
      const hasMarkdown = containsMarkdownSyntax(match);
      const hasPunctuation = /[.,;:!?'"()-]/.test(match);

      // If pure base64 with no text patterns, remove it
      if (!hasTextPatterns && !hasMarkdown && !hasPunctuation) {
        return ''; // Remove it
      }
    }
    return match; // Keep it if it might be legitimate
  });

  return sanitized.trim();
}

/**
 * Truncates extremely long content to prevent UI issues
 */
export function truncateLongContent(content: string, maxLength: number = 50000): string {
  if (!content || content.length <= maxLength) {
    return content;
  }
  
  // Before truncating, check if it's base64 audio - if so, remove it entirely
  if (isBase64AudioData(content)) {
    return '';
  }
  
  return content.substring(0, maxLength) + '\n\n... (content truncated due to length)';
}
