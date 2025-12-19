/**
 * Configuration Types for Middleware Proxy
 */

export interface AdapterConfig {
  name: string;
  apiKey: string;
  apiUrl: string;
}

export interface CorsConfig {
  allowedOrigins: string[];
  allowCredentials: boolean;
  allowedMethods: string[];
  allowedHeaders: string[];
  exposeHeaders: string[];
  maxAge: number;
}

export interface RateLimitConfig {
  windowMs: number;
  maxRequests: number;
  perAdapter: boolean;
}

export interface LoggingConfig {
  level: 'debug' | 'info' | 'warn' | 'error';
  format: 'json' | 'pretty';
  logRequests: boolean;
}

export interface ServerConfig {
  port: number;
  host: string;
}

export interface ProxyConfig {
  server: ServerConfig;
  adapters: AdapterConfig[];
  cors: CorsConfig;
  rateLimit: RateLimitConfig;
  logging: LoggingConfig;
}
