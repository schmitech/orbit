import path from 'path';
import { fileURLToPath } from 'node:url';
import fs from 'fs/promises';
import yaml from 'js-yaml';
import { AppConfig } from './types';
import dotenv from 'dotenv';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * Loads and validates the application configuration
 */
export async function loadConfig(): Promise<AppConfig> {
  // Load .env file
  dotenv.config();

  try {
    const configPath = path.resolve(__dirname, '../../config/config.yaml');
    console.log('Loading config from:', configPath);
    
    const configFile = await fs.readFile(configPath, 'utf-8');
    const config = yaml.load(configFile) as AppConfig;
    
    // Update config with environment variables
    if (process.env.ELASTICSEARCH_USERNAME && process.env.ELASTICSEARCH_PASSWORD) {
      config.elasticsearch.auth = {
        username: process.env.ELASTICSEARCH_USERNAME,
        password: process.env.ELASTICSEARCH_PASSWORD
      };
    }
    
    if (process.env.ELEVEN_LABS_API_KEY) {
      config.eleven_labs.api_key = process.env.ELEVEN_LABS_API_KEY;
    }

    return config;
  } catch (error) {
    console.error('Error reading config file:', error);
    process.exit(1);
  }
}