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
  async processChat(message: string, voiceEnabled: boolean, ip: string | string[], res: Response): Promise<void> {
    const backend = (this.client as any).mockType || (this.client instanceof OllamaClient ? 'ollama' : 'vllm');
    
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');

    try {
      let textBuffer = '';
      let isFirstChunk = true;
      let fullResponse = '';
      
      const stream = await this.chain.stream({ query: message });
      
      for await (const chunk of stream) {
        if (chunk) {
          fullResponse += chunk;
          textBuffer += chunk;
          res.write(JSON.stringify({ type: 'text', content: chunk }) + '\n');

          // Start voice generation earlier with smaller first chunk
          if (voiceEnabled && isFirstChunk && textBuffer.length >= 50) {  // Reduced from 100 to 50
            const currentText = textBuffer;
            textBuffer = '';
            isFirstChunk = false;

            // Reduced initial delay
            await new Promise(resolve => setTimeout(resolve, 300));  // Reduced from 1000 to 300
            try {
              await this.generateAudioChunk(currentText, res);
            } catch (error) {
              console.error('First chunk audio generation failed:', error);
            }
          }
          // Process subsequent chunks more frequently
          else if (voiceEnabled && !isFirstChunk && (
            (textBuffer.match(/[.!?]\s*$/) && textBuffer.length >= 30) ||  // Reduced from 50 to 30
            textBuffer.length >= 100  // Reduced from 150 to 100
          )) {
            const currentText = textBuffer;
            textBuffer = '';

            // Reduced delay between chunks
            await new Promise(resolve => setTimeout(resolve, 200));  // Reduced from 800 to 200
            try {
              await this.generateAudioChunk(currentText, res);
            } catch (error) {
              console.error('Audio generation failed:', error);
            }
          }
        }
      }
      
      // Handle any remaining text with minimal delay
      if (voiceEnabled && textBuffer.trim()) {
        await new Promise(resolve => setTimeout(resolve, 100));  // Reduced from 800 to 100
        try {
          await this.generateAudioChunk(textBuffer.trim(), res, true);
        } catch (error) {
          console.error('Final chunk audio generation failed:', error);
        }
      }
      
      // Log the interaction with IP
      await this.loggerService.logChatInteraction({
        timestamp: new Date(),
        query: message,
        response: fullResponse,
        backend: backend === 'unknown' ? 'vllm' : backend, // Default to vllm if unknown
        ip: typeof ip === 'string' ? ip : ip[0]  // Handle potential array from x-forwarded-for
      });

      res.end();
    } catch (error) {
      console.error('Error:', error);
      
      // Log errors too with IP
      await this.loggerService.logChatInteraction({
        timestamp: new Date(),
        query: message,
        response: 'ERROR',
        backend: backend === 'unknown' ? 'vllm' : backend, // Default to vllm if unknown
        ip: typeof ip === 'string' ? ip : ip[0]  // Handle potential array from x-forwarded-for
      });

      res.write(JSON.stringify({ type: 'text', content: 'An error occurred while processing your request.' }) + '\n');
      res.end();
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