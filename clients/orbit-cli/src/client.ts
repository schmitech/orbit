import { ApiClient, type StreamResponse } from '@schmitech/chatbot-api';
import type { Connection } from './connection.js';

export function createClient(connection: Connection, sessionId?: string): ApiClient {
  return new ApiClient({
    apiUrl: connection.url,
    apiKey: connection.apiKey,
    sessionId: sessionId ?? null,
  });
}

export interface ChatOptions {
  stream?: boolean;
  fileIds?: string[];
  threadId?: string;
  abortSignal?: AbortSignal;
  model?: string;
  skill?: string;
}

/**
 * Named-options wrapper around ApiClient.streamChat's 15-argument positional
 * signature. This is the only place the CLI touches that signature directly —
 * every caller elsewhere in the CLI goes through this function.
 */
export function streamChat(
  client: ApiClient,
  message: string,
  options: ChatOptions = {}
): AsyncGenerator<StreamResponse> {
  return client.streamChat(
    message,
    options.stream ?? true,
    options.fileIds,
    options.threadId,
    undefined, // audioInput
    undefined, // audioFormat
    undefined, // language
    undefined, // returnAudio
    undefined, // ttsVoice
    undefined, // sourceLanguage
    undefined, // targetLanguage
    options.abortSignal,
    options.model,
    options.skill,
    undefined // regenerateOfMessageId
  );
}
