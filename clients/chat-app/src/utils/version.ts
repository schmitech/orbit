/**
 * Version utilities for displaying package information
 */

import packageJson from '../../package.json';

// Package version from package.json
export const PACKAGE_VERSION = packageJson.version;
export const API_PACKAGE_VERSION = packageJson.dependencies['@schmitech/chatbot-api'] || '^1.0.1';

/**
 * Get the current API package version being used
 * This will attempt to get the actual installed version at runtime
 */
export async function getApiPackageVersion(): Promise<string> {
  try {
    // Try to get the actual installed version from the package
    // Note: This might not work in all environments, so we have a fallback
    const apiPackage = await import('@schmitech/chatbot-api');
    return (apiPackage as any).version || API_PACKAGE_VERSION;
  } catch (error) {
    // Fallback to the version from our package.json
    return API_PACKAGE_VERSION;
  }
}

/**
 * Get version information for display
 */
export async function getVersionInfo() {
  const apiVersion = await getApiPackageVersion();
  return {
    appVersion: PACKAGE_VERSION,
    apiVersion: apiVersion,
    isLocalApi: (import.meta.env as any).VITE_USE_LOCAL_API === 'true'
  };
}
