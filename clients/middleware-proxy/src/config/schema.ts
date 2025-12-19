/**
 * Configuration Schema using Zod
 */

import { z } from 'zod';

export const AdapterConfigSchema = z.object({
  name: z.string().min(1, 'Adapter name is required'),
  apiKey: z.string().min(1, 'API key is required'),
  apiUrl: z.string().url('API URL must be a valid URL'),
});

export const CorsConfigSchema = z.object({
  allowedOrigins: z.array(z.string()).default(['*']),
  allowCredentials: z.boolean().default(false),
  allowedMethods: z.array(z.string()).default(['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']),
  allowedHeaders: z.array(z.string()).default([
    'Content-Type',
    'X-API-Key',
    'X-Session-ID',
    'X-Thread-ID',
    'X-Adapter-Name',
    'Accept',
  ]),
  exposeHeaders: z.array(z.string()).default([
    'X-RateLimit-Limit',
    'X-RateLimit-Remaining',
    'X-RateLimit-Reset',
  ]),
  maxAge: z.number().default(600),
});

export const RateLimitConfigSchema = z.object({
  windowMs: z.number().positive().default(60000),
  maxRequests: z.number().positive().default(100),
  perAdapter: z.boolean().default(true),
});

export const LoggingConfigSchema = z.object({
  level: z.enum(['debug', 'info', 'warn', 'error']).default('info'),
  format: z.enum(['json', 'pretty']).default('json'),
  logRequests: z.boolean().default(true),
});

export const ServerConfigSchema = z.object({
  port: z.number().int().positive().default(3001),
  host: z.string().default('0.0.0.0'),
});

export const ProxyConfigSchema = z.object({
  server: ServerConfigSchema.default({}),
  adapters: z.array(AdapterConfigSchema).min(1, 'At least one adapter is required'),
  cors: CorsConfigSchema.default({}),
  rateLimit: RateLimitConfigSchema.default({}),
  logging: LoggingConfigSchema.default({}),
});

export type ValidatedProxyConfig = z.infer<typeof ProxyConfigSchema>;
