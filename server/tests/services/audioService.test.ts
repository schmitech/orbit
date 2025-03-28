import { AudioService } from '../../src/services/audioService';
import { AppConfig } from '../../src/types';

// Mock global fetch
global.fetch = jest.fn() as jest.MockedFunction<typeof fetch>;

describe('AudioService', () => {
  let audioService: AudioService;
  let mockConfig: Partial<AppConfig>;
  
  beforeEach(() => {
    jest.clearAllMocks();
    
    mockConfig = {
      eleven_labs: {
        api_key: 'test-api-key',
        voice_id: 'voice-id-123'
      }
    };
    
    // Reset process.env
    process.env.ELEVEN_LABS_API_KEY = undefined;
    
    audioService = new AudioService(mockConfig as AppConfig);
    
    // Default mock implementation for fetch
    (fetch as jest.Mock).mockResolvedValue({
      ok: true,
      arrayBuffer: jest.fn().mockResolvedValue(new ArrayBuffer(10))
    });
  });

  describe('verifyConnection', () => {
    it('should return disabled status when no API key is provided', async () => {
      // Clear API key
      mockConfig.eleven_labs!.api_key = '';
      audioService = new AudioService(mockConfig as AppConfig);
      
      const result = await audioService.verifyConnection();
      
      expect(result).toEqual({
        status: 'disabled',
        error: 'No API key provided'
      });
      expect(fetch).not.toHaveBeenCalled();
    });

    it('should return healthy status on successful connection', async () => {
      (fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200
      });
      
      const result = await audioService.verifyConnection();
      
      expect(result).toEqual({
        status: 'healthy',
        statusCode: 200
      });
      expect(fetch).toHaveBeenCalledWith(
        'https://api.elevenlabs.io/v1/user',
        expect.objectContaining({
          headers: {
            'xi-api-key': 'test-api-key'
          }
        })
      );
    });

    it('should return unhealthy status on API error', async () => {
      (fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 401
      });
      
      const result = await audioService.verifyConnection();
      
      expect(result).toEqual({
        status: 'unhealthy',
        statusCode: 401
      });
    });

    it('should return unhealthy status on network error', async () => {
      (fetch as jest.Mock).mockRejectedValueOnce(new Error('Network error'));
      
      const result = await audioService.verifyConnection();
      
      expect(result).toEqual({
        status: 'unhealthy',
        error: 'Network error'
      });
    });

    it('should use environment variable API key if available', async () => {
      process.env.ELEVEN_LABS_API_KEY = 'env-api-key';
      audioService = new AudioService(mockConfig as AppConfig);
      
      (fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        status: 200
      });
      
      await audioService.verifyConnection();
      
      expect(fetch).toHaveBeenCalledWith(
        'https://api.elevenlabs.io/v1/user',
        expect.objectContaining({
          headers: {
            'xi-api-key': 'env-api-key'
          }
        })
      );
    });
  });

  describe('generateAudio', () => {
    it('should throw error when no API key is provided', async () => {
      // Clear API key
      mockConfig.eleven_labs!.api_key = '';
      audioService = new AudioService(mockConfig as AppConfig);
      
      await expect(audioService.generateAudio('Test text')).rejects.toThrow(
        'ElevenLabs API key is not configured'
      );
    });

    it('should call ElevenLabs API with correct parameters', async () => {
      await audioService.generateAudio('Test text');
      
      expect(fetch).toHaveBeenCalledWith(
        `https://api.elevenlabs.io/v1/text-to-speech/voice-id-123/stream`,
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Accept': 'audio/mpeg',
            'Content-Type': 'application/json',
            'xi-api-key': 'test-api-key'
          }),
          body: expect.any(String)
        })
      );
      
      // Check payload
      const payload = JSON.parse((fetch as jest.Mock).mock.calls[0][1].body);
      expect(payload).toEqual({
        text: 'Test text',
        model_id: 'eleven_multilingual_v1',
        voice_settings: expect.objectContaining({
          stability: 0.5,
          similarity_boost: 0.6,
          style: 0.35,
          speaking_rate: 1.1,
          use_speaker_boost: true
        })
      });
    });

    it('should return arrayBuffer from API response', async () => {
      const mockBuffer = new ArrayBuffer(10);
      (fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        arrayBuffer: jest.fn().mockResolvedValueOnce(mockBuffer)
      });
      
      const result = await audioService.generateAudio('Test text');
      
      expect(result).toBe(mockBuffer);
    });

    it('should throw error on API failure', async () => {
      (fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request'
      });
      
      await expect(audioService.generateAudio('Test text')).rejects.toThrow(
        'Audio generation failed: 400 Bad Request'
      );
    });
  });

  describe('convertToBase64', () => {
    it('should convert ArrayBuffer to base64 string', () => {
      const buffer = new Uint8Array([0, 1, 2, 3, 4]).buffer;
      
      const result = audioService.convertToBase64(buffer);
      
      // Uint8Array([0, 1, 2, 3, 4]) in base64 is 'AAECAwQ='
      expect(result).toBe('AAECAwQ=');
    });
  });
});