import { ChatService } from '../../src/services/chatService';
import { BaseLanguageModelClient } from '../../src/clients/baseClient';
import { LoggerService } from '../../src/logger';
import { AudioService } from '../../src/services/audioService';
import { Response } from 'express';
import { AppConfig } from '../../src/types';

// Mock implementation of BaseLanguageModelClient for testing
class MockLanguageModelClient extends BaseLanguageModelClient {
  constructor(config: AppConfig, retriever: any, public mockType: 'ollama' | 'vllm' | 'unknown' = 'ollama') {
    super(config, retriever);
  }

  async createChain(): Promise<any> {
    return {
      stream: jest.fn().mockImplementation(() => {
        return {
          [Symbol.asyncIterator]: () => {
            let count = 0;
            return {
              next: async () => {
                if (count < 3) {
                  count++;
                  return { value: `chunk ${count}`, done: false };
                }
                return { done: true };
              }
            };
          }
        };
      })
    };
  }

  async checkGuardrail(query: string): Promise<{ safe: boolean }> {
    return { safe: !query.includes('unsafe') };
  }
}

// For type checking in ChatService
jest.mock('../../src/clients/ollamaClient');
jest.mock('../../src/clients/vllmClient');

describe('ChatService', () => {
  let chatService: ChatService;
  let mockClient: MockLanguageModelClient;
  let mockLoggerService: Partial<LoggerService>;
  let mockAudioService: Partial<AudioService>;
  let mockConfig: any;
  let mockResponse: Partial<Response>;
  
  beforeEach(() => {
    jest.clearAllMocks();
    
    mockConfig = {
      general: { verbose: 'false' }
    };
    
    mockLoggerService = {
      logChatInteraction: jest.fn().mockResolvedValue(undefined)
    };
    
    mockAudioService = {
      generateAudio: jest.fn().mockResolvedValue(Buffer.from('test-audio')),
      convertToBase64: jest.fn().mockReturnValue('base64-audio-data')
    };
    
    mockClient = new MockLanguageModelClient(mockConfig, {});
    
    // Mock response object
    mockResponse = {
      setHeader: jest.fn(),
      write: jest.fn(),
      end: jest.fn()
    };

    // Type assertions to make TypeScript happy with our mocks
    chatService = new ChatService(
      mockConfig as AppConfig,
      mockClient as unknown as BaseLanguageModelClient,
      mockLoggerService as LoggerService,
      mockAudioService as AudioService
    );
  });

  describe('initialize', () => {
    it('should initialize the chain', async () => {
      const createChainSpy = jest.spyOn(mockClient, 'createChain');
      
      await chatService.initialize();
      
      expect(createChainSpy).toHaveBeenCalled();
    });
  });

  describe('checkGuardrail', () => {
    it('should call client.checkGuardrail', async () => {
      const checkGuardrailSpy = jest.spyOn(mockClient, 'checkGuardrail');
      
      await chatService.checkGuardrail('test query');
      
      expect(checkGuardrailSpy).toHaveBeenCalledWith('test query');
    });
  });

  describe('processChat', () => {
    beforeEach(async () => {
      await chatService.initialize();
    });

    it('should detect Ollama client correctly', async () => {
      mockClient.mockType = 'ollama';
      
      await chatService.processChat('test message', false, '127.0.0.1', mockResponse as Response);
      
      expect(mockLoggerService.logChatInteraction).toHaveBeenCalledWith(
        expect.objectContaining({
          backend: 'ollama'
        })
      );
    });

    it('should detect VLLM client correctly', async () => {
      mockClient.mockType = 'vllm';
      
      await chatService.processChat('test message', false, '127.0.0.1', mockResponse as Response);
      
      expect(mockLoggerService.logChatInteraction).toHaveBeenCalledWith(
        expect.objectContaining({
          backend: 'vllm'
        })
      );
    });

    it('should block unsafe messages', async () => {
      await chatService.processChat('unsafe message', false, '127.0.0.1', mockResponse as Response);
      
      expect(mockResponse.write).toHaveBeenCalledWith(
        expect.stringContaining('Sorry but I cannot help you with that')
      );
      expect(mockLoggerService.logChatInteraction).toHaveBeenCalledWith(
        expect.objectContaining({
          response: 'BLOCKED: Failed guardrail check',
          blocked: true
        })
      );
      expect(mockResponse.end).toHaveBeenCalled();
    });

    it('should process safe messages and stream text', async () => {
      await chatService.processChat('safe message', false, '127.0.0.1', mockResponse as Response);
      
      // Should set correct headers
      expect(mockResponse.setHeader).toHaveBeenCalledWith('Content-Type', 'text/event-stream');
      
      // Should write 3 chunks
      expect(mockResponse.write).toHaveBeenCalledTimes(3);
      expect(mockResponse.write).toHaveBeenCalledWith(
        JSON.stringify({ type: 'text', content: 'chunk 1' }) + '\n'
      );
      
      // Should log the complete message
      expect(mockLoggerService.logChatInteraction).toHaveBeenCalledWith(
        expect.objectContaining({
          query: 'safe message',
          response: 'chunk 1chunk 2chunk 3'
        })
      );
      
      expect(mockResponse.end).toHaveBeenCalled();
    });

    it('should generate audio for voice-enabled messages', async () => {
      await chatService.processChat('voice message', true, '127.0.0.1', mockResponse as Response);
      
      // Should have generated audio
      expect(mockAudioService.generateAudio).toHaveBeenCalled();
      expect(mockAudioService.convertToBase64).toHaveBeenCalled();
      
      // Should have written audio response
      expect(mockResponse.write).toHaveBeenCalledWith(
        expect.stringContaining('audio')
      );
    });

    it('should handle errors gracefully', async () => {
      // Force an error during processing
      const mockError = new Error('Test error');
      mockClient.createChain = jest.fn().mockImplementation(() => {
        return {
          stream: jest.fn().mockImplementation(() => {
            throw mockError;
          })
        };
      });
      
      await chatService.initialize();
      await chatService.processChat('error message', false, '127.0.0.1', mockResponse as Response);
      
      // Should log error
      expect(mockLoggerService.logChatInteraction).toHaveBeenCalledWith(
        expect.objectContaining({
          response: 'ERROR'
        })
      );
      
      // Should send error response
      expect(mockResponse.write).toHaveBeenCalledWith(
        expect.stringContaining('An error occurred')
      );
      
      expect(mockResponse.end).toHaveBeenCalled();
    });
  });
});