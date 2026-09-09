import type { ParsedArgs } from './args.js';
import { ask, askSecret } from './prompt.js';

export interface Connection {
  url: string;
  apiKey: string;
}

export class ConfigError extends Error {}

/**
 * Resolve the server URL and API key.
 *
 * Order: CLI flags -> env vars -> interactive prompt (TTY only).
 * Nothing is persisted to disk — each run resolves its own connection.
 */
export async function resolveConnection(args: ParsedArgs): Promise<Connection> {
  let url = args.url ?? process.env.ORBIT_URL;
  let apiKey = args.key ?? process.env.ORBIT_API_KEY;

  if (!url) {
    if (!process.stdin.isTTY) {
      throw new ConfigError(
        'Missing server URL. Pass --url <url> or set ORBIT_URL.'
      );
    }
    url = await ask('ORBIT server URL: ');
  }

  if (!apiKey) {
    if (!process.stdin.isTTY) {
      throw new ConfigError(
        'Missing API key. Pass --key <key> or set ORBIT_API_KEY (preferred over --key, which lands in shell history).'
      );
    }
    apiKey = await askSecret('ORBIT API key: ');
  }

  url = url.trim().replace(/\/+$/, '');
  if (!url) {
    throw new ConfigError('Server URL cannot be empty.');
  }
  if (!apiKey.trim()) {
    throw new ConfigError('API key cannot be empty.');
  }

  return { url, apiKey: apiKey.trim() };
}
