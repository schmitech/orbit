import { HealthService } from '../../src/services/healthService';
import { OllamaClient } from '../../src/clients/ollamaClient';
import { VLLMClient } from '../../src/clients/vllmClient';
import { ChromaClient } from 'chromadb';
import { AudioService } from '../../src/services/audioService';

// Mock dependencies
jest.mock('chromadb');
jest.mock('../../src/clients/ollamaClient');
jest.mock('../../src/clients/vllmClient');
jest.mock('../../src/services/audioService');

describe('HealthService', () => {
  let healthService: HealthService;
  let mockConfig: any;
  let mockChromaClient: jest.Mocked<ChromaClient>;
  let mockLlmClient: jest.Mocked<OllamaClient | VLLMClient>;
  let mockAudioService: jest.Mocked<AudioService>;
  
  beforeEach(() => {
    jest.clearAllMocks();
    
    mockConfig = {};
    
    mockChromaClient = {
      heartbeat: jest.fn().mockResolvedValue({}),
    } as unknown as jest.Mocked<ChromaClient>;
    
    mockLlmClient = {
      verifyConnection: jest.fn().mockResolvedValue(true),
    } as unknown as jest.Mocked<OllamaClient>;
    
    mockAudioService = {
      verifyConnection: jest.fn().mockResolvedValue({
        status: 'healthy',
        statusCode: 200
      }),
    } as unknown as jest.Mocked<AudioService>;
    
    healthService = new HealthService(
      mockConfig,
      mockChromaClient,
      mockLlmClient,
      mockAudioService
    );
  });

  describe('getHealthStatus', () => {
    it('should return healthy status for all components when everything is working', async () => {
      Object.defineProperty(mockLlmClient, 'constructor', { value: OllamaClient });
      
      const healthStatus = await healthService.getHealthStatus();
      
      expect(healthStatus).toEqual({
        uptime: expect.any(Number),
        timestamp: expect.any(Number),
        services: {
          ollama: {
            status: 'healthy'
          },
          chroma: {
            status: 'healthy'
          },
          elevenlabs: {
            status: 'healthy',
            statusCode: 200
          }
        }
      });
    });

    it('should report unhealthy Chroma status when heartbeat fails', async () => {
      mockChromaClient.heartbeat.mockRejectedValueOnce(new Error('Connection failed'));
      
      const healthStatus = await healthService.getHealthStatus();
      
      expect(healthStatus.services.chroma).toEqual({
        status: 'unhealthy',
        error: 'Connection failed'
      });
    });

    it('should report unhealthy Ollama status when connection fails', async () => {
      Object.defineProperty(mockLlmClient, 'constructor', { value: OllamaClient });
      mockLlmClient.verifyConnection.mockResolvedValueOnce(false);
      
      const healthStatus = await healthService.getHealthStatus();
      
      expect(healthStatus.services.ollama).toEqual({
        status: 'unhealthy',
        error: 'Connection failed'
      });
    });

    it('should report vLLM status when using vLLM client', async () => {
      Object.defineProperty(mockLlmClient, 'constructor', { value: VLLMClient });
      mockLlmClient.verifyConnection.mockResolvedValueOnce(true);
      
      const healthStatus = await healthService.getHealthStatus();
      
      expect(healthStatus.services.vllm).toEqual({
        status: 'healthy'
      });
      expect(healthStatus.services.ollama).toBeUndefined();
    });

    it('should report disabled status for elevenlabs when disabled', async () => {
      mockAudioService.verifyConnection.mockResolvedValueOnce({
        status: 'disabled',
        error: 'No API key provided'
      });
      
      const healthStatus = await healthService.getHealthStatus();
      
      expect(healthStatus.services.elevenlabs).toEqual({
        status: 'disabled',
        error: 'No API key provided'
      });
    });
  });

  describe('isHealthy', () => {
    it('should return true when all services are healthy', async () => {
      const healthStatus = await healthService.getHealthStatus();
      
      const result = healthService.isHealthy(healthStatus);
      
      expect(result).toBe(true);
    });

    it('should return false when Chroma is unhealthy', async () => {
      mockChromaClient.heartbeat.mockRejectedValueOnce(new Error('Connection failed'));
      
      const healthStatus = await healthService.getHealthStatus();
      const result = healthService.isHealthy(healthStatus);
      
      expect(result).toBe(false);
    });

    it('should return false when LLM client is unhealthy', async () => {
      mockLlmClient.verifyConnection.mockResolvedValueOnce(false);
      
      const healthStatus = await healthService.getHealthStatus();
      const result = healthService.isHealthy(healthStatus);
      
      expect(result).toBe(false);
    });

    it('should return true when ElevenLabs is disabled but everything else is healthy', async () => {
      mockAudioService.verifyConnection.mockResolvedValueOnce({
        status: 'disabled',
        error: 'No API key provided'
      });
      
      const healthStatus = await healthService.getHealthStatus();
      const result = healthService.isHealthy(healthStatus);
      
      expect(result).toBe(true);
    });

    it('should return false when ElevenLabs is unhealthy', async () => {
      mockAudioService.verifyConnection.mockResolvedValueOnce({
        status: 'unhealthy',
        error: 'API error'
      });
      
      const healthStatus = await healthService.getHealthStatus();
      const result = healthService.isHealthy(healthStatus);
      
      expect(result).toBe(false);
    });
  });
});