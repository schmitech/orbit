import { Client } from '@elastic/elasticsearch';
import winston from 'winston';
import 'winston-daily-rotate-file';
import path from 'path';
import { fileURLToPath } from 'node:url';
import { AppConfig } from './types';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * IP address metadata interface
 */
export interface IPMetadata {
  address: string;
  type: 'ipv4' | 'ipv6' | 'local' | 'unknown';
  isLocal: boolean;
  source: 'direct' | 'proxy' | 'unknown';
  originalValue: string;
}

/**
 * Logger service for handling logs to file and Elasticsearch
 */
export class LoggerService {
  private config: AppConfig;
  private esClient: Client | null = null;
  private logger: winston.Logger;
  private verbose: boolean;

  constructor(config: AppConfig) {
    this.config = config;
    this.verbose = config.general?.verbose === 'true';

    // Initialize Winston logger
    this.logger = winston.createLogger({
      level: 'info',
      format: winston.format.combine(
        winston.format.timestamp(),
        winston.format.json()
      ),
      transports: [
        new winston.transports.DailyRotateFile({
          filename: path.join(__dirname, '../logs/chat-%DATE%.log'),
          datePattern: 'YYYY-MM-DD',
          maxSize: '20m',
          maxFiles: '14d'
        })
      ]
    });
  }

  /**
   * Initializes Elasticsearch client
   */
  async initializeElasticsearch(): Promise<void> {
    if (!this.config.elasticsearch.enabled) {
      return;
    }

    if (!process.env.ELASTICSEARCH_USERNAME || !process.env.ELASTICSEARCH_PASSWORD) {
      console.warn('Elasticsearch credentials not found in environment variables');
      this.config.elasticsearch.enabled = false;
      return;
    }

    try {
      this.esClient = new Client({
        node: this.config.elasticsearch.node,
        auth: {
          username: process.env.ELASTICSEARCH_USERNAME,
          password: process.env.ELASTICSEARCH_PASSWORD
        },
        tls: {
          rejectUnauthorized: false
        },
        requestTimeout: 5000, // 5 second timeout
        pingTimeout: 3000    // 3 second ping timeout
      });

      // Test connection with timeout
      const pingPromise = this.esClient.ping();
      const timeoutPromise = new Promise((_, reject) => 
        setTimeout(() => reject(new Error('Elasticsearch connection timeout')), 5000)
      );

      await Promise.race([pingPromise, timeoutPromise]);
      console.log('Successfully connected to Elasticsearch');

      await this.setupElasticsearchIndex();
    } catch (error: any) {
      console.error('Failed to connect to Elasticsearch:', error.message);
      console.log('Continuing without Elasticsearch logging...');
      this.config.elasticsearch.enabled = false;
      this.esClient = null;
    }
  }

  /**
   * Creates Elasticsearch index if it doesn't exist
   */
  private async setupElasticsearchIndex(): Promise<void> {
    if (!this.esClient) return;
    
    try {
      // Check if index exists
      const indexExists = await this.esClient.indices.exists({ 
        index: this.config.elasticsearch.index 
      });
      
      if (!indexExists) {
        // Create index with basic settings
        await this.esClient.indices.create({ 
          index: this.config.elasticsearch.index,
          body: {
            settings: {
              number_of_shards: 1,
              number_of_replicas: 0
            },
            mappings: {
              properties: {
                timestamp: { type: 'date' },
                query: { type: 'text' },
                response: { type: 'text' },
                backend: { type: 'keyword' },
                blocked: { type: 'boolean' },
                ip: { type: 'ip' },  // Main IP field - will store actual IP
                ip_metadata: {  // Additional IP metadata
                  properties: {
                    type: { type: 'keyword' },
                    isLocal: { type: 'boolean' },
                    source: { type: 'keyword' },
                    originalValue: { type: 'keyword' },
                    potentialRisk: { type: 'boolean' }
                  }
                }
              }
            }
          }
        });
        console.log(`Created new Elasticsearch index: ${this.config.elasticsearch.index}`);
      } else {
        console.log(`Using existing Elasticsearch index: ${this.config.elasticsearch.index}`);
      }
    } catch (error) {
      console.error('Failed to setup Elasticsearch index:', error);
      this.config.elasticsearch.enabled = false;
      this.esClient = null;
    }
  }

  /**
   * Formats raw IP address into metadata
   */
  private formatIPAddress(ip: string | string[] | undefined): IPMetadata {
    // Default metadata
    const metadata: IPMetadata = {
      address: 'unknown',
      type: 'unknown',
      isLocal: false,
      source: 'unknown',
      originalValue: Array.isArray(ip) ? ip.join(', ') : (ip || 'unknown')
    };

    // Handle array from X-Forwarded-For
    const ipToProcess = Array.isArray(ip) ? ip[0] : ip;

    if (!ipToProcess) {
      return metadata;
    }

    // Clean the IP address
    let cleanIP = ipToProcess.trim();

    // Detect and format IPv6 localhost
    if (cleanIP === '::1' || cleanIP === '::ffff:127.0.0.1') {
      return {
        address: 'localhost',
        type: 'local',
        isLocal: true,
        source: 'direct',
        originalValue: cleanIP
      };
    }

    // Detect and format IPv4 localhost
    if (cleanIP === '127.0.0.1' || cleanIP.startsWith('::ffff:127.')) {
      return {
        address: 'localhost',
        type: 'local',
        isLocal: true,
        source: 'direct',
        originalValue: cleanIP
      };
    }

    // Handle IPv4-mapped IPv6 addresses
    if (cleanIP.startsWith('::ffff:')) {
      cleanIP = cleanIP.substring(7);
      metadata.type = 'ipv4';
    } else if (cleanIP.includes(':')) {
      metadata.type = 'ipv6';
    } else {
      metadata.type = 'ipv4';
    }

    metadata.address = cleanIP;
    metadata.isLocal = this.isLocalIP(cleanIP);
    metadata.source = Array.isArray(ip) ? 'proxy' : 'direct';

    return metadata;
  }

  /**
   * Determines if an IP address is local/private
   */
  private isLocalIP(ip: string): boolean {
    return ip.startsWith('10.') || 
          ip.startsWith('172.16.') || 
          ip.startsWith('192.168.') || 
          ip === '127.0.0.1' || 
          ip === '::1' ||
          ip.startsWith('fc00:') ||
          ip.startsWith('fd') ||
          ip.toLowerCase().startsWith('fe80:');
  }

  /**
   * Logs chat interaction to file and Elasticsearch
   */
  async logChatInteraction(data: {
    timestamp: Date;
    query: string;
    response: string;
    backend: 'ollama' | 'vllm';
    blocked?: boolean;
    ip?: string | string[];
  }): Promise<void> {
    const ipMetadata = this.formatIPAddress(data.ip);
    
    // Always log to file with full data
    this.logger.info('Chat Interaction', {
      timestamp: data.timestamp.toISOString(),
      query: data.query,
      response: data.response,
      backend: data.backend,
      blocked: data.blocked || false,
      ip: {
        ...ipMetadata,
        potentialRisk: data.blocked && !ipMetadata.isLocal,
        timestamp: data.timestamp.toISOString()
      },
      elasticsearch_status: this.config.elasticsearch.enabled ? 'enabled' : 'disabled'
    });

    // Log to Elasticsearch if enabled and available
    if (this.config.elasticsearch.enabled && this.esClient) {
      try {
        if (this.verbose) {
          console.log('\n=== Elasticsearch Logging ===');
          console.log('Attempting to index document to:', this.config.elasticsearch.index);
        }

        // Convert localhost/friendly names to actual IP for Elasticsearch storage
        const ipForElastic = ipMetadata.type === 'local' ? '127.0.0.1' : ipMetadata.address;

        const document = {
          timestamp: data.timestamp.toISOString(),
          query: data.query,
          response: data.response,
          backend: data.backend,
          blocked: data.blocked || false,
          ip: ipForElastic, // Store actual IP address
          ip_metadata: {
            type: ipMetadata.type,
            isLocal: ipMetadata.isLocal,
            source: ipMetadata.source,
            originalValue: ipMetadata.originalValue,
            potentialRisk: data.blocked && !ipMetadata.isLocal
          }
        };

        if (this.verbose) {
          console.log('Document to index:', JSON.stringify(document, null, 2));
        }

        const indexResult = await this.esClient.index({
          index: this.config.elasticsearch.index,
          document: document,
          refresh: true // This ensures the document is immediately searchable
        });

        if (this.verbose) {
          console.log('Elasticsearch indexing result:', indexResult);
          
          // Verify document exists
          const verifyDoc = await this.esClient.get({
            index: this.config.elasticsearch.index,
            id: indexResult._id
          });
          console.log('Document verification:', verifyDoc);
        }
      } catch (error: any) {
        console.error('Failed to log to Elasticsearch:', { 
          error: error.message,
          stack: error.stack,
          meta: error.meta,
          statusCode: error.statusCode,
          name: error.name
        });
        
        // Try to diagnose the issue
        try {
          if (this.esClient) {
            const indexExists = await this.esClient.indices.exists({
              index: this.config.elasticsearch.index
            });
            
            console.log('Index exists check:', {
              index: this.config.elasticsearch.index,
              exists: indexExists
            });

            if (!indexExists) {
              console.error('Index does not exist! This should not happen as we create it at startup.');
            }

            const indexSettings = await this.esClient.indices.get({
              index: this.config.elasticsearch.index
            });
            
            console.log('Index settings:', indexSettings);
          }
        } catch (diagError: any) {
          console.error('Error during diagnostics:', diagError.message);
        }
      }
    } else if (this.verbose) {
      console.log('\n=== Elasticsearch Logging Skipped ===');
      console.log('Elasticsearch enabled:', this.config.elasticsearch.enabled);
      console.log('Elasticsearch client available:', !!this.esClient);
    }
  }
}