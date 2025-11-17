import inquirer from 'inquirer';
import { ApiClient } from '../api/client';
import { ConfigManager } from '../config/manager';
import { Formatter } from '../utils/formatters';

export class ConfigCommands {
  constructor(
    private apiClient: ApiClient,
    private configManager: ConfigManager,
    private formatter: Formatter
  ) {}

  private parseArgs(args: string[]): Record<string, string | boolean> {
    const parsed: Record<string, string | boolean> = {};
    for (let i = 0; i < args.length; i++) {
      if (args[i].startsWith('--')) {
        const key = args[i].slice(2);
        const value = args[i + 1];
        if (value && !value.startsWith('--')) {
          parsed[key] = value;
          i++;
        } else {
          parsed[key] = true;
        }
      }
    }
    return parsed;
  }

  async handle(args: string[]): Promise<void> {
    if (args.length === 0) {
      this.formatter.error('Config command requires a subcommand');
      this.formatter.info('Available subcommands: show, set, reset');
      return;
    }

    const subcommand = args[0].toLowerCase();
    const rest = args.slice(1);

    switch (subcommand) {
      case 'show':
        await this.show(rest);
        break;
      case 'set':
        await this.set(rest);
        break;
      case 'reset':
        await this.reset(rest);
        break;
      default:
        this.formatter.error(`Unknown config subcommand: ${subcommand}`);
        this.formatter.info('Available subcommands: show, set, reset');
    }
  }

  async show(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const outputFormat = parsed.output === 'json' ? 'json' : 'table';
    const key = parsed.key as string | undefined;

    const config = this.configManager.load();

    if (key) {
      const value = (config as any)[key];
      if (value === undefined) {
        // Try nested key (e.g., "server.url")
        const keys = key.split('.');
        let current: any = config;
        for (const k of keys) {
          if (current && typeof current === 'object' && k in current) {
            current = current[k];
          } else {
            this.formatter.error(`Configuration key '${key}' not found`);
            return;
          }
        }
        
        if (outputFormat === 'json') {
          this.formatter.formatJson({ [key]: current });
        } else {
          console.log(`${key}: ${current}`);
        }
      } else {
        if (outputFormat === 'json') {
          this.formatter.formatJson({ [key]: value });
        } else {
          console.log(`${key}: ${value}`);
        }
      }
    } else {
      if (outputFormat === 'json') {
        this.formatter.formatJson(config);
      } else {
        console.log(this.formatter.bold('CLI Configuration:'));
        console.log(`  serverUrl: ${config.serverUrl}`);
        if (config.authToken) {
          console.log(`  authToken: ${'*'.repeat(20)}`);
        } else {
          console.log(`  authToken: (not set)`);
        }
      }
    }
  }

  async set(args: string[]): Promise<void> {
    if (args.length < 2) {
      this.formatter.error('Usage: config set <key> <value>');
      return;
    }

    const key = args[0];
    const value = args[1];

    if (key === 'serverUrl' || key === 'server.url') {
      this.configManager.setServerUrl(value);
      this.formatter.success(`Configuration updated: ${key} = ${value}`);
    } else if (key === 'authToken' || key === 'auth.token') {
      this.configManager.setAuthToken(value);
      this.formatter.success(`Configuration updated: ${key} = ${'*'.repeat(20)}`);
    } else {
      this.formatter.error(`Unknown configuration key: ${key}`);
      this.formatter.info('Available keys: serverUrl, authToken');
    }
  }

  async reset(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const force = parsed.force === true;

    if (!force) {
      const answer = await inquirer.prompt([
        {
          type: 'confirm',
          name: 'confirm',
          message: 'Are you sure you want to reset configuration to defaults?',
          default: false
        }
      ]);

      if (!answer.confirm) {
        this.formatter.info('Operation cancelled');
        return;
      }
    }

    this.configManager.reset();
    this.formatter.success('Configuration reset to defaults');
  }
}

