import type { ApiClient } from '@schmitech/chatbot-api';
import { streamChat, type ChatOptions } from './client.js';
import { classifyError } from './errors.js';
import { EXIT_CANCELLED, EXIT_OK } from './exit-codes.js';

/**
 * Send one turn and stream the reply to stdout as plain text — no ANSI, no
 * progress noise. stdout carries the response only; errors go to stderr.
 * Returns the process exit code; callers are responsible for process.exit.
 */
export async function runOneShot(
  client: ApiClient,
  message: string,
  options: ChatOptions & { signal?: AbortSignal }
): Promise<number> {
  try {
    for await (const chunk of streamChat(client, message, { ...options, abortSignal: options.signal })) {
      if (chunk.text) {
        process.stdout.write(chunk.text);
      }
    }
    process.stdout.write('\n');
    return EXIT_OK;
  } catch (error) {
    if (options.signal?.aborted) {
      return EXIT_CANCELLED;
    }
    const { code, message: errorMessage } = classifyError(error);
    process.stderr.write(`${errorMessage}\n`);
    return code;
  }
}
