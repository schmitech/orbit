import { ChromaClient } from 'chromadb';
import { AppConfig } from '../types';
import { OllamaClient } from '../clients/ollamaClient';
import { VLLMClient } from '../clients/vllmClient';
import { AudioService } from './audioService';

/**
 * Service for handling health checks
 */
export class HealthService {
  private config: AppConfig;
  private chromaClient: ChromaClient;
  private llmClient: OllamaClient | VLLMClient;
  private audioService: AudioService;
  
  constructor(
    config: AppConfig, 
    chromaClient: ChromaClient, 
    llmClient: OllamaClient | VLLMClient,
    audioService: AudioService
  ) {
    this.config = config;
    this.chromaClient = chromaClient;
    this.llmClient = llmClient;
    this.audioService = audioService;
  }
  
  /**
   * Get health status of all components
   */
  async getHealthStatus(): Promise<{
    uptime: number;
    timestamp: number;
    services: {
      ollama?: { status: string; statusCode?: number; error?: string };
      vllm?: { status: string; statusCode?: number; error?: string };
      chroma: { status: string; error?: string };
      elevenlabs: { status: string; statusCode?: number; error?: string };
    };
  }> {
    // Check ChromaDB status
    const chromaStatus: { 
      status: string; 
      error?: string 
    } = { status: 'unknown' };
    
    try {
      await this.chromaClient.heartbeat();
      chromaStatus.status = 'healthy';
    } catch (error: any) {
      chromaStatus.status = 'unhealthy';
      chromaStatus.error = error.message;
    }

    // Check ElevenLabs status
    const elevenLabsStatus = await this.audioService.verifyConnection();

    // Create the health object
    const health: {
      uptime: number;
      timestamp: number;
      services: {
        ollama?: { status: string; statusCode?: number; error?: string };
        vllm?: { status: string; statusCode?: number; error?: string };
        chroma: { status: string; error?: string };
        elevenlabs: { status: string; statusCode?: number; error?: string };
      };
    } = {
      uptime: process.uptime(),
      timestamp: Date.now(),
      services: {
        chroma: chromaStatus,
        elevenlabs: elevenLabsStatus
      }
    };

    // Add LLM status based on client type
    if (this.llmClient instanceof OllamaClient) {
      const isConnected = await this.llmClient.verifyConnection();
      health.services.ollama = {
        status: isConnected ? 'healthy' : 'unhealthy',
        error: isConnected ? undefined : 'Connection failed'
      };
    } else if (this.llmClient instanceof VLLMClient) {
      const isConnected = await this.llmClient.verifyConnection();
      health.services.vllm = {
        status: isConnected ? 'healthy' : 'unhealthy',
        error: isConnected ? undefined : 'Connection failed'
      };
    }
    
    return health;
  }
  
  /**
   * Determine if all services are healthy
   */
  isHealthy(healthStatus: ReturnType<typeof this.getHealthStatus> extends Promise<infer T> ? T : never): boolean {
    const { services } = healthStatus;
    
    // Basic service health checks
    const chromaHealthy = services.chroma.status === 'healthy';
    const audioHealthy = services.elevenlabs.status === 'healthy' || services.elevenlabs.status === 'disabled';
    
    // Check LLM service
    const llmHealthy = services.ollama?.status === 'healthy' || services.vllm?.status === 'healthy';
    
    return chromaHealthy && audioHealthy && llmHealthy;
  }
}