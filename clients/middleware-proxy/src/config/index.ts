/**
 * Configuration Loader
 *
 * Priority (highest to lowest):
 * 1. Environment variables
 * 2. Config file (if specified)
 * 3. Default values
 */

import fs from 'fs';
import { ProxyConfigSchema, ValidatedProxyConfig } from './schema.js';
import type { AdapterConfig, ProxyConfig } from './types.js';

/**
 * Parse adapters from environment variable
 * Format: JSON array of adapter objects
 * Example: '[{"name":"Chat","apiKey":"key1","apiUrl":"https://api.example.com"}]'
 */
function parseAdaptersFromEnv(): AdapterConfig[] | null {
  const envValue = process.env.ORBIT_ADAPTERS || process.env.VITE_ADAPTERS;
  if (!envValue) {
    return null;
  }

  try {
    const parsed = JSON.parse(envValue);
    if (!Array.isArray(parsed)) {
      console.warn('Warning: ORBIT_ADAPTERS must be a JSON array');
      return null;
    }
    return parsed as AdapterConfig[];
  } catch (error) {
    console.warn('Warning: Could not parse ORBIT_ADAPTERS:', (error as Error).message);
    return null;
  }
}

/**
 * Parse allowed origins from environment variable
 * Format: Comma-separated list
 * Example: 'https://app.example.com,https://widget.example.com'
 */
function parseAllowedOrigins(): string[] | undefined {
  const envValue = process.env.ALLOWED_ORIGINS;
  if (!envValue) {
    return undefined;
  }
  return envValue.split(',').map(origin => origin.trim()).filter(Boolean);
}

/**
 * Load configuration from file
 */
function loadConfigFile(filePath: string): Partial<ProxyConfig> | null {
  try {
    if (fs.existsSync(filePath)) {
      const content = fs.readFileSync(filePath, 'utf8');
      return JSON.parse(content);
    }
  } catch (error) {
    console.warn(`Warning: Could not load config file ${filePath}:`, (error as Error).message);
  }
  return null;
}

/**
 * Load configuration from environment variables
 */
function loadConfigFromEnv(): Partial<ProxyConfig> {
  const config: Partial<ProxyConfig> = {};

  // Server config
  const port = process.env.PORT;
  const host = process.env.HOST;
  if (port || host) {
    config.server = {
      port: port ? parseInt(port, 10) : 3001,
      host: host || '0.0.0.0',
    };
  }

  // Adapters
  const adapters = parseAdaptersFromEnv();
  if (adapters) {
    config.adapters = adapters;
  }

  // CORS config
  const allowedOrigins = parseAllowedOrigins();
  if (allowedOrigins) {
    config.cors = {
      allowedOrigins,
      allowCredentials: false,
      allowedMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
      allowedHeaders: ['Content-Type', 'X-API-Key', 'X-Session-ID', 'X-Thread-ID', 'X-Adapter-Name', 'Accept'],
      exposeHeaders: ['X-RateLimit-Limit', 'X-RateLimit-Remaining', 'X-RateLimit-Reset'],
      maxAge: 600,
    };
  }

  // Rate limit config
  const windowMs = process.env.RATE_LIMIT_WINDOW_MS;
  const maxRequests = process.env.RATE_LIMIT_MAX_REQUESTS;
  if (windowMs || maxRequests) {
    config.rateLimit = {
      windowMs: windowMs ? parseInt(windowMs, 10) : 60000,
      maxRequests: maxRequests ? parseInt(maxRequests, 10) : 100,
      perAdapter: true,
    };
  }

  // Logging config
  const logLevel = process.env.LOG_LEVEL as 'debug' | 'info' | 'warn' | 'error' | undefined;
  const logFormat = process.env.LOG_FORMAT as 'json' | 'pretty' | undefined;
  const logRequests = process.env.LOG_REQUESTS;
  if (logLevel || logFormat || logRequests) {
    config.logging = {
      level: logLevel || 'info',
      format: logFormat || 'json',
      logRequests: logRequests !== 'false',
    };
  }

  return config;
}

/**
 * Deep merge two configuration objects
 */
function deepMerge<T extends Record<string, unknown>>(target: T, source: Partial<T>): T {
  const result = { ...target };
  for (const key of Object.keys(source) as Array<keyof T>) {
    const sourceValue = source[key];
    if (sourceValue !== undefined) {
      if (
        typeof sourceValue === 'object' &&
        sourceValue !== null &&
        !Array.isArray(sourceValue) &&
        typeof result[key] === 'object' &&
        result[key] !== null &&
        !Array.isArray(result[key])
      ) {
        result[key] = deepMerge(
          result[key] as Record<string, unknown>,
          sourceValue as Record<string, unknown>
        ) as T[keyof T];
      } else {
        result[key] = sourceValue as T[keyof T];
      }
    }
  }
  return result;
}

/**
 * Load and validate the complete configuration
 */
export function loadConfig(): ValidatedProxyConfig {
  // Start with empty config
  let config: Partial<ProxyConfig> = {};

  // Load from config file if specified
  const configFile = process.env.CONFIG_FILE;
  if (configFile) {
    const fileConfig = loadConfigFile(configFile);
    if (fileConfig) {
      config = deepMerge(config as Record<string, unknown>, fileConfig as Record<string, unknown>) as Partial<ProxyConfig>;
    }
  }

  // Load from environment variables (overrides file config)
  const envConfig = loadConfigFromEnv();
  config = deepMerge(config as Record<string, unknown>, envConfig as Record<string, unknown>) as Partial<ProxyConfig>;

  // Validate configuration
  const result = ProxyConfigSchema.safeParse(config);
  if (!result.success) {
    const errors = result.error.errors.map(e => `${e.path.join('.')}: ${e.message}`).join(', ');
    throw new Error(`Configuration validation failed: ${errors}`);
  }

  return result.data;
}

export * from './types.js';
export * from './schema.js';
