import { ChromaClient } from 'chromadb';
import { AppConfig } from '../types';
import { OllamaClient } from '../clients/ollamaClient';
import { VLLMClient } from '../clients/vllmClient';
import { AudioService } from './audioService';

export interface HealthStatus {
  status: string;
  components: {
    [key: string]: {
      status: string;
      error?: string;
    };
  };
}

/**
 * Service for handling health checks
 */
export class HealthService {
  private config: AppConfig;
  private chromaClient: ChromaClient;
  private llmClient: OllamaClient | VLLMClient;
  private audioService: AudioService;
  private lastStatus: HealthStatus | null = null;
  private lastCheckTime = 0;
  private readonly cacheTtl = 30; // Cache health status for 30 seconds
  
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
  async getHealthStatus(useCache: boolean = true): Promise<HealthStatus> {
    const currentTime = Date.now() / 1000;

    // Return cached status if available and not expired
    if (useCache && this.lastStatus && (currentTime - this.lastCheckTime) < this.cacheTtl) {
      return this.lastStatus;
    }

    const status: HealthStatus = {
      status: 'ok',
      components: {
        server: {
          status: 'ok'
        },
        chroma: {
          status: 'unknown'
        },
        llm: {
          status: 'unknown'
        }
      }
    };

    // Check Chroma
    try {
      await this.chromaClient.heartbeat();
      status.components.chroma.status = 'ok';
    } catch (error: any) {
      status.components.chroma.status = 'error';
      status.components.chroma.error = error.message;
    }

    // Check LLM (Ollama/vLLM)
    try {
      const llmOk = await this.llmClient.verifyConnection();
      status.components.llm.status = llmOk ? 'ok' : 'error';
      if (!llmOk) {
        status.components.llm.error = 'Failed to connect to LLM service';
      }
    } catch (error: any) {
      status.components.llm.status = 'error';
      status.components.llm.error = error.message;
    }

    // Overall status
    if (Object.values(status.components).some(component => component.status !== 'ok')) {
      status.status = 'error';
    }

    // Cache the result
    this.lastStatus = status;
    this.lastCheckTime = currentTime;

    return status;
  }
  
  /**
   * Determine if all services are healthy
   */
  isHealthy(health: HealthStatus): boolean {
    return health.status === 'ok';
  }
}