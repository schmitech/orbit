import { EXIT_AUTH, EXIT_NETWORK, EXIT_SERVER_ERROR } from './exit-codes.js';

/**
 * Classify an error thrown by the SDK into one of the CLI's exit codes.
 *
 * The SDK (clients/node-api) wraps most failures in a plain Error whose
 * message embeds the HTTP status code, and its network-error detection
 * ("Failed to fetch") is written for browser fetch — Node's undici throws a
 * differently worded TypeError, so it is matched separately here.
 */
export function classifyError(error: unknown): { code: number; message: string } {
  const message = error instanceof Error ? error.message : String(error);

  if (/ECONNREFUSED|ENOTFOUND|EAI_AGAIN|fetch failed|Could not connect to the server/i.test(message)) {
    return { code: EXIT_NETWORK, message: 'Could not connect to the server. Check the URL and that it is running.' };
  }

  if (/:\s*401\b/.test(message) || /invalid|disabled|no associated adapter/i.test(message)) {
    return { code: EXIT_AUTH, message: 'API key is invalid, disabled, or lacks an adapter.' };
  }

  return { code: EXIT_SERVER_ERROR, message };
}
