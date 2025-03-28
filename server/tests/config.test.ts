import * as fs from 'fs/promises';
import * as yaml from 'js-yaml';
import { loadConfig, validateConfig } from '../src/config';
import { AppConfig } from '../src/types';

// Mock dependencies
jest.mock('fs/promises');
jest.mock('js-yaml');
jest.mock('node:url', () => ({
  fileURLToPath: jest.fn(() => '/fake/path/file.js'),
}));
jest.mock('path', () => ({
  dirname: jest.fn(() => '/fake/path'),
  resolve: jest.fn(() => '/fake/path/config.yaml'),
}));

describe('Config Module', () => {
  // Mock environment variables and console
  const originalEnv = process.env;
  const mockExit = process.exit as unknown as jest.Mock;
  const mockConsoleError = jest.spyOn(console, 'error').mockImplementation();
  const mockConsoleLog = jest.spyOn(console, 'log').mockImplementation();

  beforeEach(() => {
    // Reset mocks
    jest.clearAllMocks();
    process.env = { ...originalEnv };
    (fs.readFile as jest.Mock).mockResolvedValue('mockYamlContent');
    (yaml.load as jest.Mock).mockReturnValue({
      system: {
        prompt: 'test prompt'
      },
      elasticsearch: {},
      eleven_labs: {},
      general: {
        verbose: 'false'
      }
    });
  });

  afterAll(() => {
    process.env = originalEnv;
    mockConsoleError.mockRestore();
    mockConsoleLog.mockRestore();
  });

  describe('loadConfig', () => {
    it('should load config from yaml file', async () => {
      const config = await loadConfig();
      
      expect(fs.readFile).toHaveBeenCalledWith('/fake/path/config.yaml', 'utf-8');
      expect(yaml.load).toHaveBeenCalledWith('mockYamlContent');
      expect(config).toHaveProperty('system.prompt', 'test prompt');
    });

    it('should override config with environment variables', async () => {
      // Setup env vars
      process.env.ELASTICSEARCH_USERNAME = 'testuser';
      process.env.ELASTICSEARCH_PASSWORD = 'testpass';
      process.env.ELEVEN_LABS_API_KEY = 'testapikey';

      const config = await loadConfig();
      
      expect(config.elasticsearch.auth).toEqual({
        username: 'testuser',
        password: 'testpass'
      });
      expect(config.eleven_labs.api_key).toBe('testapikey');
    });

    it('should exit if file reading fails', async () => {
      (fs.readFile as jest.Mock).mockRejectedValue(new Error('File not found'));
      
      await loadConfig();
      
      expect(mockConsoleError).toHaveBeenCalledWith(
        'Error reading config file:',
        expect.any(Error)
      );
      expect(mockExit).toHaveBeenCalledWith(1);
    });
  });

  describe('validateConfig', () => {
    it('should validate system prompt exists', () => {
      const config = {
        system: { prompt: 'test prompt' },
        general: { verbose: 'false' }
      } as unknown as AppConfig;

      expect(() => validateConfig(config)).not.toThrow();
    });

    it('should exit if system prompt is missing', () => {
      const config = {
        system: {},
        general: { verbose: 'false' }
      } as unknown as AppConfig;

      validateConfig(config);
      
      expect(mockConsoleError).toHaveBeenCalledWith(
        'No system prompt found in config.yaml. Exiting...'
      );
      expect(mockExit).toHaveBeenCalledWith(1);
    });

    it('should log prompt info if verbose is true', () => {
      const config = {
        system: { prompt: 'a very long test prompt that should be truncated in logs' },
        general: { verbose: 'true' }
      } as unknown as AppConfig;

      validateConfig(config);
      
      expect(mockConsoleLog).toHaveBeenCalledTimes(3);
      expect(mockConsoleLog).toHaveBeenCalledWith('Using system prompt from config.yaml:');
    });
  });
});