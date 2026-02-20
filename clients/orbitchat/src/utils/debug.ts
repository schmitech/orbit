/**
 * Debug utility to conditionally log based on consoleDebug config
 */

import { runtimeConfig } from './runtimeConfig';

const isDebugEnabled = (): boolean => runtimeConfig.consoleDebug;

/**
 * Conditionally log to console.log if debug is enabled
 */
export const debugLog = (...args: unknown[]): void => {
  if (isDebugEnabled()) {
    console.log(...args);
  }
};

/**
 * Conditionally log to console.warn if debug is enabled
 */
export const debugWarn = (...args: unknown[]): void => {
  if (isDebugEnabled()) {
    console.warn(...args);
  }
};

/**
 * Conditionally log to console.error if debug is enabled
 */
export const debugError = (...args: unknown[]): void => {
  if (isDebugEnabled()) {
    console.error(...args);
  }
};

/**
 * Always log errors (even when debug is disabled) - use for critical errors
 */
export const logError = (...args: unknown[]): void => {
  console.error(...args);
};
