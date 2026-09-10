import type { ApiClient } from '@schmitech/chatbot-api';
import { AttachmentError, extractAttachments } from './attachments.js';
import { saveArtifacts } from './artifacts.js';
import { streamChat, type ChatOptions } from './client.js';
import { classifyError } from './errors.js';
import { EXIT_CANCELLED, EXIT_OK, EXIT_USAGE } from './exit-codes.js';

/**
 * Send one turn and stream the reply to stdout as plain text — no ANSI, no
 * progress noise. stdout carries the response only; errors, artifact
 * notices, and progress go to stderr. Returns the process exit code;
 * callers are responsible for process.exit.
 */
export async function runOneShot(
  client: ApiClient,
  rawMessage: string,
  options: ChatOptions & { signal?: AbortSignal }
): Promise<number> {
  let message: string;
  let fileIds: string[];
  try {
    ({ text: message, fileIds } = await extractAttachments(client, rawMessage));
  } catch (error) {
    if (error instanceof AttachmentError) {
      process.stderr.write(`${error.message}\n`);
      return EXIT_USAGE;
    }
    const { code, message: errorMessage } = classifyError(error);
    process.stderr.write(`${errorMessage}\n`);
    return code;
  }

  try {
    for await (const chunk of streamChat(client, message, {
      ...options,
      fileIds,
      abortSignal: options.signal,
    })) {
      if (chunk.text) {
        process.stdout.write(chunk.text);
      }
      for (const path of await saveArtifacts(client, chunk)) {
        process.stderr.write(`Saved artifact: ${path}\n`);
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
