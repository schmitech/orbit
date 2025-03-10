import {StreamResponse } from './types';

export class ChatbotClient {
  constructor(private baseUrl: string) {}

  async *streamChat({ message, voiceEnabled }: { message: string; voiceEnabled: boolean }): AsyncGenerator<StreamResponse> {
    const response = await fetch(`${this.baseUrl}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, voiceEnabled })
    });

    const reader = response.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      const chunk = decoder.decode(value);
      const lines = chunk.split('\n').filter(Boolean);
      for (const line of lines) {
        yield JSON.parse(line);
      }
    }
  }
} 