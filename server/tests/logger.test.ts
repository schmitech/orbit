import { LoggerService, IPMetadata } from '../src/logger';
import { Client } from '@elastic/elasticsearch';
import winston from 'winston';

// Mock dependencies
jest.mock('@elastic/elasticsearch');
jest.mock('winston', () => {
  const mLogger = {
    info: jest.fn(),
    error: jest.fn()
  };
  return {
    format: {
      combine: jest.fn(),
      timestamp: jest.fn(),
      json: jest.fn()
    },
    createLogger: jest.fn().mockReturnValue(mLogger),
    transports: {
      DailyRotateFile: jest.fn()
    }
  };
});

describe('LoggerService', () => {
  let loggerService: LoggerService;
  let mockConfig: any;
  let mockConsoleLog: jest.SpyInstance;
  let mockConsoleWarn: jest.SpyInstance;
  let mockConsoleError: jest.SpyInstance;
  let mockElasticClient: any;
  
  beforeEach(() => {
    jest.clearAllMocks();
    
    // Setup console mocks
    mockConsoleLog = jest.spyOn(console, 'log').mockImplementation();
    mockConsoleWarn = jest.spyOn(console, 'warn').mockImplementation();
    mockConsoleError = jest.spyOn(console, 'error').mockImplementation();
    
    // Setup elasticsearch client mock
    mockElasticClient = {
      ping: jest.fn().mockResolvedValue({}),
      indices: {
        exists: jest.fn().mockResolvedValue(true),
        create: jest.fn().mockResolvedValue({}),
        get: jest.fn().mockResolvedValue({})
      },
      index: jest.fn().mockResolvedValue({ _id: 'test-id' }),
      get: jest.fn().mockResolvedValue({})
    };
    (Client as jest.Mock).mockImplementation(() => mockElasticClient);
    
    // Setup config
    mockConfig = {
      elasticsearch: {
        enabled: true,
        node: 'http://localhost:9200',
        index: 'chat-logs'
      },
      general: {
        verbose: 'false'
      }
    };
    
    // Original environment
    process.env.ELASTICSEARCH_USERNAME = 'testuser';
    process.env.ELASTICSEARCH_PASSWORD = 'testpass';
    
    loggerService = new LoggerService(mockConfig);
  });

  afterEach(() => {
    mockConsoleLog.mockRestore();
    mockConsoleWarn.mockRestore();
    mockConsoleError.mockRestore();
  });

  describe('initializeElasticsearch', () => {
    it('should initialize elasticsearch client when enabled', async () => {
      await loggerService.initializeElasticsearch();
      
      expect(Client).toHaveBeenCalledWith(expect.objectContaining({
        node: 'http://localhost:9200',
        auth: {
          username: 'testuser',
          password: 'testpass'
        }
      }));
      expect(mockElasticClient.ping).toHaveBeenCalled();
    });

    it('should handle missing credentials', async () => {
      delete process.env.ELASTICSEARCH_USERNAME;
      delete process.env.ELASTICSEARCH_PASSWORD;
      
      await loggerService.initializeElasticsearch();
      
      expect(mockConsoleWarn).toHaveBeenCalledWith(
        'Elasticsearch credentials not found in environment variables'
      );
      expect(Client).not.toHaveBeenCalled();
    });

    it('should handle failed connections', async () => {
      mockElasticClient.ping.mockRejectedValueOnce(new Error('Connection refused'));
      
      await loggerService.initializeElasticsearch();
      
      expect(mockConsoleError).toHaveBeenCalledWith(
        'Failed to connect to Elasticsearch:',
        'Connection refused'
      );
      expect(mockConsoleLog).toHaveBeenCalledWith(
        'Continuing without Elasticsearch logging...'
      );
    });

    it('should create index if it doesn\'t exist', async () => {
      mockElasticClient.indices.exists.mockResolvedValueOnce(false);
      
      await loggerService.initializeElasticsearch();
      
      expect(mockElasticClient.indices.create).toHaveBeenCalledWith(
        expect.objectContaining({
          index: 'chat-logs'
        })
      );
      expect(mockConsoleLog).toHaveBeenCalledWith(
        'Created new Elasticsearch index: chat-logs'
      );
    });
  });

  describe('logChatInteraction', () => {
    beforeEach(async () => {
      await loggerService.initializeElasticsearch();
    });

    it('should log chat interaction to file', async () => {
      const data = {
        timestamp: new Date(),
        query: 'test query',
        response: 'test response',
        backend: 'ollama' as const,
        ip: '127.0.0.1'
      };
      
      await loggerService.logChatInteraction(data);
      
      // Check that the Winston logger was called
      expect(winston.createLogger().info).toHaveBeenCalledWith(
        'Chat Interaction',
        expect.objectContaining({
          query: 'test query',
          response: 'test response',
          backend: 'ollama'
        })
      );
    });

    it('should log chat interaction to elasticsearch when enabled', async () => {
      const data = {
        timestamp: new Date(),
        query: 'test query',
        response: 'test response',
        backend: 'ollama' as const,
        ip: '8.8.8.8'
      };
      
      await loggerService.logChatInteraction(data);
      
      // Check that elasticsearch index was called
      expect(mockElasticClient.index).toHaveBeenCalledWith(
        expect.objectContaining({
          index: 'chat-logs',
          document: expect.objectContaining({
            query: 'test query',
            response: 'test response',
            backend: 'ollama',
            ip: '8.8.8.8'
          }),
          refresh: true
        })
      );
    });

    it('should handle elasticsearch errors gracefully', async () => {
      mockElasticClient.index.mockRejectedValueOnce(new Error('Index error'));
      
      const data = {
        timestamp: new Date(),
        query: 'test query',
        response: 'test response',
        backend: 'ollama' as const,
        ip: '127.0.0.1'
      };
      
      await loggerService.logChatInteraction(data);
      
      // Should log error but not fail
      expect(mockConsoleError).toHaveBeenCalledWith(
        'Failed to log to Elasticsearch:',
        expect.any(Object)
      );
      
      // Should still log to Winston
      expect(winston.createLogger().info).toHaveBeenCalled();
    });

    it('should handle different IP formats', async () => {
      // Test with array of IPs (like X-Forwarded-For)
      const data = {
        timestamp: new Date(),
        query: 'test query',
        response: 'test response',
        backend: 'ollama' as const,
        ip: ['8.8.8.8', '192.168.1.1']
      };
      
      await loggerService.logChatInteraction(data);
      
      // Should use the first IP in the array
      expect(mockElasticClient.index).toHaveBeenCalledWith(
        expect.objectContaining({
          document: expect.objectContaining({
            ip: '8.8.8.8'
          })
        })
      );
    });

    it('should correctly identify local IPs', async () => {
      const data = {
        timestamp: new Date(),
        query: 'test query',
        response: 'test response',
        backend: 'ollama' as const,
        ip: '192.168.1.1'
      };
      
      await loggerService.logChatInteraction(data);
      
      // Should identify as local IP
      expect(winston.createLogger().info).toHaveBeenCalledWith(
        'Chat Interaction',
        expect.objectContaining({
          ip: expect.objectContaining({
            isLocal: true
          })
        })
      );
    });
  });
});