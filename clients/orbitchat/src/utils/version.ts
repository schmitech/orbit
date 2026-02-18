/**
 * Version utilities for displaying package information
 */

import packageJson from '../../package.json';

// Package version from package.json
export const PACKAGE_VERSION = packageJson.version;

/**
 * Get version information for display
 */
export function getVersionInfo(): {
  appVersion: string;
} {
  return {
    appVersion: PACKAGE_VERSION,
  };
}
