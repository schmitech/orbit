import { OllamaClient } from '../src/clients/ollamaClient';
import { Ollama } from '@langchain/community/llms/ollama';
import { AppConfig } from '../src/types';

// Mock dependencies
jest.mock('@langchain/community/llms/ollama', () => {
  return {
    Ollama: jest.fn().mockImplementation(() => {
      return {
        invoke: jest.fn().mockResolvedValue('mocked response')
      };
    })
  };
});

// Mock global fetch
global.fetch = jest.fn() as jest.MockedFunction<typeof fetch>;

describe('OllamaClient', () => {
  let client: OllamaClient;
  let mockConfig: Partial<AppConfig>;
  const mockRetriever = {
    getRelevantDocuments: jest.fn().mockResolvedValue([])
  };

  beforeEach(() => {
    jest.clearAllMocks();
    
    mockConfig = {
      ollama: {
        base_url: 'http://localhost:11434',
        model: 'llama2',
        temperature: 0.7,
        top_p: 0.9,
        top_k: 40,
        repeat_penalty: 1.1,
        num_predict: 100,
        num_ctx: 2048,
        num_threads: 4,
        embed_model: 'embed-model'
      },
      system: {
        prompt: 'You are a helpful assistant',
      },
      general: {
        verbose: 'false',
        port: 3000
      }
    };
    
    client = new OllamaClient(mockConfig as AppConfig, mockRetriever as any);
    (fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: jest.fn().mockResolvedValue({ response: 'mocked response' })
    });
  });

  describe('constructor', () => {
    it('should initialize with correct parameters', () => {
      expect(Ollama).toHaveBeenCalledWith(expect.objectContaining({
        baseUrl: 'http://localhost:11434',
        model: 'llama2',
        temperature: 0.7,
        system: 'You are a helpful assistant'
      }));
    });
  });

  describe('verifyConnection', () => {
    it('should return true if connection is successful', async () => {
      (fetch as jest.Mock).mockResolvedValueOnce({
        ok: true
      });
      
      const result = await client.verifyConnection();
      
      expect(result).toBe(true);
      expect(fetch).toHaveBeenCalledWith('http://localhost:11434/api/tags');
    });

    it('should return false if connection fails', async () => {
      (fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 500
      });
      
      const result = await client.verifyConnection();
      
      expect(result).toBe(false);
    });

    it('should return false if connection throws', async () => {
      (fetch as jest.Mock).mockRejectedValueOnce(new Error('Network error'));
      
      const result = await client.verifyConnection();
      
      expect(result).toBe(false);
    });
  });

  describe('createChain', () => {
    it('should create a runnable sequence', async () => {
      const chain = await client.createChain();
      
      expect(chain).toBeDefined();
      expect(typeof chain.stream).toBe('function');
    });
  });
});