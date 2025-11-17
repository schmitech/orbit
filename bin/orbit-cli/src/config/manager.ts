import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';

export interface Config {
  serverUrl: string;
  authToken?: string;
}

const DEFAULT_CONFIG_DIR = path.join(os.homedir(), '.orbit');
const DEFAULT_CONFIG_FILE = path.join(DEFAULT_CONFIG_DIR, 'config.json');
const DEFAULT_SERVER_URL = 'http://localhost:3000';

export class ConfigManager {
  private config: Config | null = null;
  private configFile: string;

  constructor(configFile: string = DEFAULT_CONFIG_FILE) {
    this.configFile = configFile;
    this.ensureConfigDir();
  }

  private ensureConfigDir(): void {
    const configDir = path.dirname(this.configFile);
    if (!fs.existsSync(configDir)) {
      fs.mkdirSync(configDir, { mode: 0o700, recursive: true });
    }
  }

  load(): Config {
    if (this.config) {
      return this.config;
    }

    let loadedConfig: Config;

    if (!fs.existsSync(this.configFile)) {
      loadedConfig = {
        serverUrl: DEFAULT_SERVER_URL,
      };
    } else {
      try {
        const data = fs.readFileSync(this.configFile, 'utf-8');
        const parsed = JSON.parse(data);

        if (parsed && typeof parsed === 'object') {
          loadedConfig = {
            serverUrl: DEFAULT_SERVER_URL,
            ...parsed,
          };
        } else {
          loadedConfig = { serverUrl: DEFAULT_SERVER_URL };
        }
      } catch (error) {
        // If config file is corrupted, use defaults
        loadedConfig = {
          serverUrl: DEFAULT_SERVER_URL,
        };
      }
    }

    this.config = loadedConfig;
    return this.config;
  }

  save(config: Config): void {
    this.ensureConfigDir();
    
    // Ensure serverUrl is set
    if (!config.serverUrl) {
      config.serverUrl = DEFAULT_SERVER_URL;
    }

    const data = JSON.stringify(config, null, 2);
    fs.writeFileSync(this.configFile, data, { mode: 0o600 });
    this.config = config;
  }

  get(key: keyof Config): string | undefined {
    const config = this.load();
    return config[key];
  }

  set(key: keyof Config, value: string): void {
    const config = this.load();
    (config as any)[key] = value;
    this.save(config);
  }

  clearToken(): void {
    const config = this.load();
    delete config.authToken;
    this.save(config);
  }

  getServerUrl(): string {
    return this.get('serverUrl') || DEFAULT_SERVER_URL;
  }

  getAuthToken(): string | undefined {
    return this.get('authToken');
  }

  setAuthToken(token: string): void {
    this.set('authToken', token);
  }

  setServerUrl(url: string): void {
    this.set('serverUrl', url);
  }

  reset(): void {
    this.config = {
      serverUrl: DEFAULT_SERVER_URL
    };
    this.save(this.config);
  }
}

