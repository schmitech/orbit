import express from 'express';
import cors from 'cors';
import { ChromaClient } from 'chromadb';
import { ChromaRetriever } from './chromaRetriever';
import { OllamaEmbeddings } from '@langchain/community/embeddings/ollama';
import { OllamaEmbeddingWrapper } from './ollamaEmbeddingWrapper';
import { loadConfig } from './config';
import { OllamaClient } from './clients/ollamaClient';
import { VLLMClient } from './clients/vllmClient';
import { LoggerService } from './logger';
import { AudioService } from './services/audioService';
import { ChatService, Backend } from './services/chatService';
import { HealthService } from './services/healthService';
import https from 'https';
import fs from 'fs/promises';

/**
 * Main application class
 */
class Application {
  private config!: Awaited<ReturnType<typeof loadConfig>>;
  private app = express();
  private server!: https.Server | ReturnType<typeof this.app.listen>;
  private chromaClient!: ChromaClient;
  private llmClient!: OllamaClient | VLLMClient;
  private loggerService!: LoggerService;
  private audioService!: AudioService;
  private chatService!: ChatService;
  private healthService!: HealthService;
  private backend!: Backend;

  /**
   * Initialize the application
   */
  async initialize(): Promise<void> {
    try {
      // Parse command line arguments
      this.backend = process.argv[2] as Backend || 'ollama';
      if (!['ollama', 'vllm'].includes(this.backend)) {
        console.error('Invalid backend specified. Use either "ollama" or "vllm"');
        process.exit(1);
      }

      // Load configuration
      this.config = await loadConfig();
      
      if (this.config.general?.verbose === 'true') {
        console.log(`Using ${this.backend} backend`);
      }
      
      // Set up middleware
      this.app.use(cors());
      this.app.use(express.json());

      // Initialize services
      await this.initializeServices();
      
      // Set up routes
      this.setupRoutes();
      
      // Start server
      await this.startServer();
      
      // Setup graceful shutdown
      this.setupGracefulShutdown();
    } catch (error) {
      console.error('Application initialization error:', error);
      process.exit(1);
    }
  }

  /**
   * Initialize all services
   */
  private async initializeServices(): Promise<void> {
    try {
      // Initialize ChromaDB client
      this.chromaClient = new ChromaClient({
        path: `http://${this.config.chroma.host}:${this.config.chroma.port}`
      });

      // Initialize Ollama embeddings with config
      const embeddings = new OllamaEmbeddings({
        baseUrl: this.config.ollama.base_url,
        model: this.config.ollama.embed_model,
      });

      // Create the wrapper instance
      const embeddingWrapper = new OllamaEmbeddingWrapper(embeddings);

      // Initialize Chroma collection
      let collection;
      try {
        collection = await this.chromaClient.getCollection({
          name: this.config.chroma.collection || 'qa-chatbot',
          embeddingFunction: embeddingWrapper
        });
        
        console.log('Successfully connected to existing Chroma collection: ' + this.config.chroma.collection);
      } catch (error) {
        console.error('Failed to get Chroma collection:', error);
        process.exit(1);
      }

      // Initialize the retriever
      const retriever = new ChromaRetriever(collection, embeddingWrapper);

      // Initialize the LLM client based on backend
      if (this.backend === 'ollama') {
        this.llmClient = new OllamaClient(this.config, retriever);
        
        // Verify connection
        if (!await this.llmClient.verifyConnection()) {
          console.error('Failed to connect to Ollama. Exiting...');
          process.exit(1);
        }
      } else {
        this.llmClient = new VLLMClient(this.config, retriever);
      }

      // Initialize the logger service
      this.loggerService = new LoggerService(this.config);
      await this.loggerService.initializeElasticsearch();
      
      // Initialize audio service
      this.audioService = new AudioService(this.config);
      
      // Initialize chat service
      this.chatService = new ChatService(
        this.config,
        this.llmClient,
        this.loggerService,
        this.audioService
      );
      await this.chatService.initialize();
      
      // Initialize health service
      this.healthService = new HealthService(
        this.config,
        this.chromaClient,
        this.llmClient,
        this.audioService
      );
    } catch (error) {
      console.error('Failed to initialize services:', error);
      process.exit(1);
    }
  }

  /**
   * Set up application routes
   */
  private setupRoutes(): void {
    // Chat endpoint
    this.app.post('/chat', async (req, res) => {
      const { message, voiceEnabled } = req.body;
      
      // Get client IP address
      const ip = req.headers['x-forwarded-for'] || 
                req.socket.remoteAddress || 
                'unknown';
                
      await this.chatService.processChat(message, voiceEnabled, ip, res);
    });

    // Health check endpoint
    this.app.get('/health', async (req, res) => {
      try {
        const health = await this.healthService.getHealthStatus();
        const status = this.healthService.isHealthy(health) ? 200 : 503;
        res.status(status).json(health);
      } catch (error: any) {
        res.status(500).json({
          status: 'error',
          error: error.message
        });
      }
    });
  }

  /**
   * Start the server with HTTP or HTTPS
   */
  private async startServer(): Promise<void> {
    const port = this.config.general?.port || 3000;
    
    if (this.config.general?.https?.enabled) {
      try {
        const httpsOptions = {
          key: await fs.readFile(this.config.general.https.key_file),
          cert: await fs.readFile(this.config.general.https.cert_file)
        };
        
        this.server = https.createServer(httpsOptions, this.app);
        const httpsPort = this.config.general.https.port || 3443;
        
        this.server.listen(httpsPort, () => {
          console.log(`HTTPS Server running at https://localhost:${httpsPort}`);
        });
      } catch (error) {
        console.error('Failed to start HTTPS server:', error);
        process.exit(1);
      }
    } else {
      this.server = this.app.listen(port, () => {
        console.log(`HTTP Server running at http://localhost:${port}`);
      });
    }
  }

  /**
   * Set up graceful shutdown handlers
   */
  private setupGracefulShutdown(): void {
    // Implement graceful shutdown
    process.on('SIGTERM', () => this.gracefulShutdown());
    process.on('SIGINT', () => this.gracefulShutdown());
  }

  /**
   * Handle graceful shutdown of the application
   */
  private async gracefulShutdown(): Promise<void> {
    console.log('Shutdown signal received, closing server gracefully');
    
    // Stop accepting new requests
    this.server.close(() => {
      console.log('HTTP/HTTPS server closed');
    });
    
    // Wait for existing requests to complete (with timeout)
    const timeout = setTimeout(() => {
      console.log('Forcing shutdown after timeout');
      process.exit(1);
    }, 30000);
    
    try {
      // Clean up resources
      console.log('Cleaning up resources...');
      
      // Close any open connections or resources
      // This is where you would close database connections, etc.
      
      clearTimeout(timeout);
      console.log('Graceful shutdown completed');
      process.exit(0);
    } catch (err) {
      console.error('Error during shutdown:', err);
      process.exit(1);
    }
  }
}

// Start the application
const app = new Application();
app.initialize().catch(error => {
  console.error('Failed to start application:', error);
  process.exit(1);
});