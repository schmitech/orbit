let counter = 0;

export function generateSessionId(): string {
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).substring(2, 8);
  return `mobile-${timestamp}-${random}`;
}

export function generateMessageId(prefix: string): string {
  counter += 1;
  const timestamp = Date.now().toString(36);
  return `${prefix}-${timestamp}-${counter}`;
}
