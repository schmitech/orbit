import { mkdir, writeFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import type { ApiClient, StreamResponse } from '@schmitech/chatbot-api';

const OUT_DIR = './.orbit-out';

// The two shapes the SDK returns for generated media: inline base64 (with a
// *_format field) and a persistent server-side URL that needs an
// authenticated download via ApiClient.downloadArtifact().
const INLINE_FIELDS = [
  { data: 'image', format: 'image_format', kind: 'image' },
  { data: 'video', format: 'video_format', kind: 'video' },
  { data: 'document', format: 'document_format', kind: 'document' },
] as const;

const URL_FIELDS = [
  { url: 'image_url', kind: 'image' },
  { url: 'video_url', kind: 'video' },
  { url: 'document_url', kind: 'document' },
  { url: 'generated_audio_url', kind: 'audio' },
] as const;

async function writeArtifact(kind: string, format: string | undefined, bytes: Buffer): Promise<string> {
  await mkdir(OUT_DIR, { recursive: true });
  const ext = format ? `.${format}` : '';
  const path = `${OUT_DIR}/${kind}-${randomUUID()}${ext}`;
  await writeFile(path, bytes);
  return path;
}

function extFromContentType(contentType: string | null): string {
  if (!contentType) return '';
  const subtype = contentType.split('/')[1]?.split(';')[0];
  return subtype ? `.${subtype}` : '';
}

/**
 * Save any artifacts present on a stream chunk to ./.orbit-out/ and return
 * the paths written. Most chunks carry none of these fields; this is a
 * cheap no-op check for the common case.
 */
export async function saveArtifacts(client: ApiClient, chunk: StreamResponse): Promise<string[]> {
  const paths: string[] = [];
  const record = chunk as unknown as Record<string, string | undefined>;
  const savedKinds = new Set<string>();

  for (const { data, format, kind } of INLINE_FIELDS) {
    const base64 = record[data];
    if (base64) {
      paths.push(await writeArtifact(kind, record[format], Buffer.from(base64, 'base64')));
      savedKinds.add(kind);
    }
  }

  // The server can persist both an inline copy and a refreshable URL for the
  // same generated media on one chunk — save it once, preferring the inline
  // copy already handled above since it needs no extra download round-trip.
  for (const { url, kind } of URL_FIELDS) {
    if (savedKinds.has(kind)) continue;
    const value = record[url];
    if (value) {
      const { data, contentType } = await client.downloadArtifact(value);
      paths.push(await writeArtifact(kind, extFromContentType(contentType).replace(/^\./, '') || undefined, Buffer.from(data)));
    }
  }

  return paths;
}
