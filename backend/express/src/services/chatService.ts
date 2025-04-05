import { RunnableSequence } from '@langchain/core/runnables';
import { Response } from 'express';
import { AppConfig } from '../types';
import { OllamaClient } from '../clients/ollamaClient';
import { VLLMClient } from '../clients/vllmClient';
import { BaseLanguageModelClient } from '../clients/baseClient';
import { LoggerService } from '../logger';
import { AudioService } from './audioService';

/**
 * Type for backend selection
 */
export type Backend = 'ollama' | 'vllm';

export interface ChatResponse {
  response: string;
  audio: string | null;
}

/**
 * Service for handling chat interactions
 */
export class ChatService {
  private config: AppConfig;
  private client: BaseLanguageModelClient;
  private chain!: RunnableSequence;
  private loggerService: LoggerService;
  private audioService: AudioService;
  private verbose: boolean;

  constructor(
    config: AppConfig, 
    client: BaseLanguageModelClient, 
    loggerService: LoggerService,
    audioService: AudioService
  ) {
    this.config = config;
    this.client = client;
    this.loggerService = loggerService;
    this.audioService = audioService;
    this.verbose = config.general?.verbose === 'true';
  }

  /**
   * Initialize the chat service
   */
  async initialize(): Promise<void> {
    this.chain = await this.client.createChain();
  }

  /**
   * Process a chat message and stream the response
   */
  async processChat(
    message: string, 
    voiceEnabled: boolean, 
    ip: string,
    stream: boolean
  ): Promise<ChatResponse | AsyncGenerator<string, void, unknown>> {
    if (stream) {
      return this.processStreamingChat(message, voiceEnabled, ip);
    } else {
      return this.processNormalChat(message, voiceEnabled, ip);
    }
  }

  private async processStreamingChat(
    message: string,
    voiceEnabled: boolean,
    ip: string
  ): Promise<AsyncGenerator<string, void, unknown>> {
    const self = this;
    
    async function* generateResponse() {
      try {
        // Use chain to stream response
        const stream = await self.chain.stream({ query: message });
        
        for await (const chunk of stream) {
          if (chunk) {
            yield chunk;
          }
        }

        // Log the interaction if logger service is available
        if (self.loggerService) {
          const backend = (self.client as any).mockType || 
                         (self.client instanceof OllamaClient ? 'ollama' : 'vllm');
          await self.loggerService.logChatInteraction({
            timestamp: new Date(),
            query: message,
            response: 'STREAMING',
            backend: backend === 'unknown' ? 'vllm' : backend,
            ip: ip
          });
        }
      } catch (error) {
        console.error('Error in streaming chat:', error);
        yield 'Error generating response';
      }
    }

    return generateResponse();
  }

  private async processNormalChat(
    message: string,
    voiceEnabled: boolean,
    ip: string
  ): Promise<ChatResponse> {
    try {
      // Use chain to get complete response
      const response = await this.chain.invoke({ query: message });
      
      // Log conversation if logger service is available
      if (this.loggerService) {
        const backend = (this.client as any).mockType || 
                       (this.client instanceof OllamaClient ? 'ollama' : 'vllm');
        await this.loggerService.logChatInteraction({
          timestamp: new Date(),
          query: message,
          response: response,
          backend: backend === 'unknown' ? 'vllm' : backend,
          ip: ip
        });
      }

      return {
        response: response,
        audio: null // Audio handling can be added later
      };
    } catch (error) {
      console.error('Error in normal chat:', error);
      throw error;
    }
  }

  /**
   * Generate audio for a chunk of text and write to response
   */
  private async generateAudioChunk(text: string, res: Response, isFinal: boolean = false): Promise<void> {
    try {
      const audioBuffer = await this.audioService.generateAudio(text);
      const base64Audio = this.audioService.convertToBase64(audioBuffer);
      
      console.log('Audio generated successfully, length:', base64Audio.length);
  
      res.write(JSON.stringify({
        type: 'audio',
        content: base64Audio,
        isFinal,
      }) + '\n');
    } catch (error) {
      console.error('Audio generation error:', error);
      // We'll continue without audio rather than failing the entire request
    }
  }
}