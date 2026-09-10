import { readFile } from 'node:fs/promises';
import { basename, extname } from 'node:path';
import type { ApiClient } from '@schmitech/chatbot-api';

const MIME_TYPES: Record<string, string> = {
  '.txt': 'text/plain',
  '.md': 'text/markdown',
  '.json': 'application/json',
  '.csv': 'text/csv',
  '.pdf': 'application/pdf',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
};

function mimeTypeFor(path: string): string {
  return MIME_TYPES[extname(path).toLowerCase()] ?? 'application/octet-stream';
}

/** Matches an `@path` token: `@` followed by non-whitespace. */
const ATTACHMENT_PATTERN = /@(\S+)/g;

export class AttachmentError extends Error {}

/**
 * Extract `@path` tokens from a message, upload each file, and return the
 * message with those tokens stripped plus the resulting file ids.
 *
 * Attachments are per-turn: the caller passes the returned file ids as this
 * turn's fileIds only, so they don't silently persist onto later turns.
 */
export async function extractAttachments(
  client: ApiClient,
  message: string
): Promise<{ text: string; fileIds: string[] }> {
  const paths = [...message.matchAll(ATTACHMENT_PATTERN)].map((match) => match[1]);
  if (paths.length === 0) {
    return { text: message, fileIds: [] };
  }

  const fileIds: string[] = [];
  for (const path of paths) {
    let bytes: Buffer;
    try {
      bytes = await readFile(path);
    } catch {
      throw new AttachmentError(`Attachment not found: ${path}`);
    }
    const file = new File([bytes], basename(path), { type: mimeTypeFor(path) });
    const uploaded = await client.uploadFile(file);
    fileIds.push(uploaded.file_id);
  }

  const text = message.replace(ATTACHMENT_PATTERN, '').replace(/\s+/g, ' ').trim();
  return { text: text || 'Please review the attached file(s).', fileIds };
}
