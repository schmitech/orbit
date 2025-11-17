import { ApiClient } from '../api/client';
import { ConfigManager } from '../config/manager';
import { Formatter } from '../utils/formatters';
import { AuthCommands } from './auth';
import { UserCommands } from './user';
import { KeyCommands } from './key';
import { PromptCommands } from './prompt';
import { AdminCommands } from './admin';
import { ServerCommands } from './server';
import { ConfigCommands } from './config';

export class CommandRegistry {
  private commands: Map<string, (args: string[]) => Promise<void>>;
  private apiClient: ApiClient;
  private configManager: ConfigManager;
  private formatter: Formatter;

  constructor(apiClient: ApiClient, configManager: ConfigManager, formatter: Formatter) {
    this.apiClient = apiClient;
    this.configManager = configManager;
    this.formatter = formatter;
    this.commands = new Map();

    this.registerCommands();
  }

  private registerCommands(): void {
    const auth = new AuthCommands(this.apiClient, this.configManager, this.formatter);
    const user = new UserCommands(this.apiClient, this.configManager, this.formatter);
    const key = new KeyCommands(this.apiClient, this.configManager, this.formatter);
    const prompt = new PromptCommands(this.apiClient, this.configManager, this.formatter);
    const admin = new AdminCommands(this.apiClient, this.configManager, this.formatter);
    const server = new ServerCommands(this.apiClient, this.configManager, this.formatter);
    const config = new ConfigCommands(this.apiClient, this.configManager, this.formatter);

    // Authentication
    this.commands.set('login', (args) => auth.login(args));
    this.commands.set('logout', (args) => auth.logout(args));
    this.commands.set('register', (args) => auth.register(args));
    this.commands.set('me', (args) => auth.me(args));
    this.commands.set('auth-status', (args) => auth.authStatus(args));

    // User management
    this.commands.set('user', (args) => user.handle(args));

    // API keys
    this.commands.set('key', (args) => key.handle(args));

    // Prompts
    this.commands.set('prompt', (args) => prompt.handle(args));

    // Admin
    this.commands.set('admin', (args) => admin.handle(args));

    // Server
    this.commands.set('status', (args) => server.status(args));

    // Config
    this.commands.set('config', (args) => config.handle(args));
  }

  public async execute(command: string, args: string[]): Promise<void> {
    const handler = this.commands.get(command);
    if (!handler) {
      this.formatter.error(`Unknown command: ${command}`);
      this.formatter.info('Type "help" for available commands');
      return;
    }

    await handler(args);
  }

  public getCommands(): string[] {
    return Array.from(this.commands.keys());
  }
}

