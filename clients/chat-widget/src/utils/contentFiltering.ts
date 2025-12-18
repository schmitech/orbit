/**
 * Utilities to keep streamed markdown content clean by stripping very large
 * base64 audio blobs and limiting runaway responses.
 */
const MARKDOWN_CHARACTERS = ['#', '*', '`', '[', ']', '(', ')', '{', '}', '|', '<', '>'];

const containsMarkdownSyntax = (value: string): boolean =>
  MARKDOWN_CHARACTERS.some(character => value.includes(character));

/**
 * Detects if text is likely base64-encoded audio.
 */
export function isBase64AudioData(text: string): boolean {
  if (!text || text.length < 1000) {
    return false;
  }

  const cleaned = text.replace(/\s+/g, '');
  const base64Pattern = /^[A-Za-z0-9+/=]+$/;

  if (cleaned.length > 10000 && base64Pattern.test(cleaned)) {
    const hasTextPatterns = /\b(the|and|for|are|but|not|you|all|can|function|const|let|var|class|return|import|export|async|await|if|else|while|true|false|null|undefined|http|https|www|error|data|response|request|api|json|xml|html|css|js|py|java|cpp|def|print|console|log)\b/i.test(
      text
    );
    const hasMarkdown = containsMarkdownSyntax(text);
    const hasPunctuation = /[.,;:!?'"()-]/.test(text);
    if (!hasTextPatterns && !hasMarkdown && !hasPunctuation) {
      return true;
    }
  }

  if (cleaned.length > 50000 && base64Pattern.test(cleaned)) {
    const nonBase64Chars = text.replace(/[A-Za-z0-9+/=\s]/g, '').length;
    if (nonBase64Chars < 10) {
      return true;
    }
  }

  return false;
}

/**
 * Removes base64 audio data from streamed markdown content.
 */
export function sanitizeMessageContent(content: string): string {
  if (!content) return content;

  if (isBase64AudioData(content)) {
    return '';
  }

  const base64BlockPattern = /([A-Za-z0-9+/=]{10000,})/g;
  return content.replace(base64BlockPattern, match => {
    const cleaned = match.replace(/\s+/g, '');

    if (cleaned.length > 10000 && /^[A-Za-z0-9+/=]+$/.test(cleaned)) {
      const hasTextPatterns = /\b(function|const|let|var|class|return|import|export|if|else|while|for|true|false|null|def|print)\b/i.test(
        match
      );
      const hasMarkdown = containsMarkdownSyntax(match);
      const hasPunctuation = /[.,;:!?'"()-]/.test(match);

      if (!hasTextPatterns && !hasMarkdown && !hasPunctuation) {
        return '';
      }
    }

    return match;
  });
}

/**
 * Truncate ultra long responses to keep the widget responsive.
 */
export function truncateLongContent(content: string, maxLength = 50000): string {
  if (!content || content.length <= maxLength) {
    return content;
  }

  if (isBase64AudioData(content)) {
    return '';
  }

  return `${content.substring(0, maxLength)}\n\n... (content truncated due to length)`;
}
