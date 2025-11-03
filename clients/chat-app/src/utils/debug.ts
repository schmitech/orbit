/**
 * Debug utility to conditionally log based on VITE_CONSOLE_DEBUG environment variable
 */

const isDebugEnabled = (): boolean => {
  return (import.meta.env as any).VITE_CONSOLE_DEBUG === 'true';
};

/**
 * Conditionally log to console.log if debug is enabled
 */
export const debugLog = (...args: any[]): void => {
  if (isDebugEnabled()) {
    console.log(...args);
  }
};

/**
 * Conditionally log to console.warn if debug is enabled
 */
export const debugWarn = (...args: any[]): void => {
  if (isDebugEnabled()) {
    console.warn(...args);
  }
};

/**
 * Conditionally log to console.error if debug is enabled
 */
export const debugError = (...args: any[]): void => {
  if (isDebugEnabled()) {
    console.error(...args);
  }
};

/**
 * Always log errors (even when debug is disabled) - use for critical errors
 */
export const logError = (...args: any[]): void => {
  console.error(...args);
};

