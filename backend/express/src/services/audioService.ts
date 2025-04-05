import { AppConfig } from './types';

/**
 * Service for handling text-to-speech conversion
 */
export class AudioService {
  private config: AppConfig;
  private apiKey: string;
  
  constructor(config: AppConfig) {
    this.config = config;
    this.apiKey = process.env.ELEVEN_LABS_API_KEY || config.eleven_labs.api_key;
  }
  
  /**
   * Verifies the ElevenLabs API connection
   */
  async verifyConnection(): Promise<{ status: string, statusCode?: number, error?: string }> {
    try {
      if (!this.apiKey) {
        return { 
          status: 'disabled',
          error: 'No API key provided'
        };
      }
      
      const response = await fetch('https://api.elevenlabs.io/v1/user', {
        headers: {
          'xi-api-key': this.apiKey
        }
      });
      
      return {
        status: response.ok ? 'healthy' : 'unhealthy',
        statusCode: response.status
      };
    } catch (error: any) {
      return {
        status: 'unhealthy',
        error: error.message
      };
    }
  }
  
  /**
   * Generates audio from text using ElevenLabs API
   */
  async generateAudio(text: string): Promise<ArrayBuffer> {
    if (!this.apiKey) {
      throw new Error('ElevenLabs API key is not configured');
    }
    
    console.log('Generating audio for:', text);

    const response = await fetch(
      `https://api.elevenlabs.io/v1/text-to-speech/${this.config.eleven_labs.voice_id}/stream`,
      {
        method: 'POST',
        headers: {
          'Accept': 'audio/mpeg',
          'Content-Type': 'application/json',
          'xi-api-key': this.apiKey,
        },
        body: JSON.stringify({
          text,
          model_id: 'eleven_multilingual_v1',
          voice_settings: {
            stability: 0.5,              // Reduced for more natural variation
            similarity_boost: 0.6,       // Reduced for more expressive speech
            style: 0.35,                 // Increased for more casual style
            speaking_rate: 1.1,          // Slightly faster for conversational feel
            use_speaker_boost: true      // Enhanced clarity for voice calls
          },
        }),
      }
    );

    if (!response.ok) {
      throw new Error(`Audio generation failed: ${response.status} ${response.statusText}`);
    }
    
    return await response.arrayBuffer();
  }
  
  /**
   * Converts ArrayBuffer to base64 string
   */
  convertToBase64(buffer: ArrayBuffer): string {
    return Buffer.from(buffer).toString('base64');
  }
}