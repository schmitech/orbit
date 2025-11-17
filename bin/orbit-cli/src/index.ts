#!/usr/bin/env node

import * as readline from 'readline';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { ConfigManager } from './config/manager';
import { ApiClient } from './api/client';
import { Formatter } from './utils/formatters';
import { CommandRegistry } from './commands/registry';

const HISTORY_FILE = path.join(os.homedir(), '.orbit', '.cli_history');

export class REPL {
  private rl: readline.Interface;
  private configManager: ConfigManager;
  private apiClient: ApiClient;
  private formatter: Formatter;
  private commandRegistry: CommandRegistry;
  private history: string[] = [];
  private shouldExit = false;

  constructor() {
    this.configManager = new ConfigManager();
    this.apiClient = new ApiClient(this.configManager);
    this.formatter = new Formatter();
    this.commandRegistry = new CommandRegistry(this.apiClient, this.configManager, this.formatter);

    this.rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
      prompt: 'orbit> ',
      completer: this.completer.bind(this)
    });

    this.loadHistory();
    this.setupEventHandlers();
  }

  private setupEventHandlers(): void {
    this.rl.on('line', (line: string) => {
      const trimmed = line.trim();
      
      if (trimmed) {
        this.addToHistory(trimmed);
        this.processCommand(trimmed);
      }
      
      if (!this.shouldExit) {
        this.rl.prompt();
      }
    });

    this.rl.on('close', () => {
      this.saveHistory();
      process.exit(0);
    });

    // Handle Ctrl+C gracefully
    process.on('SIGINT', () => {
      console.log('\nUse "exit" or "quit" to exit, or Ctrl+D');
      this.rl.prompt();
    });
  }

  private async processCommand(line: string): Promise<void> {
    const args = this.parseCommand(line);
    if (args.length === 0) {
      return;
    }

    const command = args[0].toLowerCase();
    const rest = args.slice(1);

    // Handle special commands
    if (command === 'exit' || command === 'quit') {
      this.shouldExit = true;
      this.saveHistory();
      this.rl.close();
      return;
    }

    if (command === 'help' || command === '?') {
      if (rest.length > 0) {
        this.showCommandHelp(rest[0]);
      } else {
        this.showHelp();
      }
      return;
    }

    if (command === 'clear' || command === 'cls') {
      console.clear();
      return;
    }

    // Route to command handler
    try {
      await this.commandRegistry.execute(command, rest);
    } catch (error: any) {
      if (error.name === 'OrbitError' || error.name === 'AuthenticationError' || error.name === 'NetworkError') {
        this.formatter.error(error.message);
      } else {
        this.formatter.error(`Unexpected error: ${error.message}`);
        if (process.env.DEBUG) {
          console.error(error);
        }
      }
    }
  }

  private parseCommand(line: string): string[] {
    const args: string[] = [];
    let current = '';
    let inQuotes = false;
    let quoteChar = '';

    for (let i = 0; i < line.length; i++) {
      const char = line[i];

      if ((char === '"' || char === "'") && (i === 0 || line[i - 1] !== '\\')) {
        if (!inQuotes) {
          inQuotes = true;
          quoteChar = char;
        } else if (char === quoteChar) {
          inQuotes = false;
          quoteChar = '';
        } else {
          current += char;
        }
      } else if (char === ' ' && !inQuotes) {
        if (current) {
          args.push(current);
          current = '';
        }
      } else {
        current += char;
      }
    }

    if (current) {
      args.push(current);
    }

    return args;
  }

  private completer(line: string): [string[], string] {
    const commands = this.commandRegistry.getCommands();
    const hits = commands.filter(c => c.startsWith(line));
    return [hits.length ? hits : commands, line];
  }

  private loadHistory(): void {
    try {
      if (fs.existsSync(HISTORY_FILE)) {
        const data = fs.readFileSync(HISTORY_FILE, 'utf-8');
        this.history = data.split('\n').filter(line => line.trim());
        // Limit history to last 1000 lines
        if (this.history.length > 1000) {
          this.history = this.history.slice(-1000);
        }
      }
    } catch (error) {
      // Ignore history load errors
    }
  }

  private saveHistory(): void {
    try {
      const dir = path.dirname(HISTORY_FILE);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
      }
      fs.writeFileSync(HISTORY_FILE, this.history.join('\n'), { mode: 0o600 });
    } catch (error) {
      // Ignore history save errors
    }
  }

  private addToHistory(line: string): void {
    this.history.push(line);
    if (this.history.length > 1000) {
      this.history = this.history.slice(-1000);
    }
  }

  private showHelp(): void {
    console.log(`
Available commands:

Authentication:
  login [--username] [--password]    Login to the server
  logout                             Logout and clear token
  register --username --password     Register a new user (admin only)
  me                                 Show current user information
  auth-status                        Check authentication status

User Management:
  user list [--role] [--active-only]     List users
  user reset-password --user-id|--username [--password]  Reset user password
  user change-password                   Change your password
  user activate --user-id                 Activate a user
  user deactivate --user-id               Deactivate a user
  user delete --user-id [--force]        Delete a user

API Keys:
  key create --adapter --name [--notes] [--prompt-id|--prompt-file]  Create API key
  key list [--active-only]                List API keys
  key status --key                         Get API key status
  key test --key                           Test an API key
  key rename --old-key --new-key           Rename an API key
  key deactivate --key                     Deactivate an API key
  key delete --key [--force]               Delete an API key
  key list-adapters                        List available adapters

System Prompts:
  prompt create --name --file [--version]  Create a system prompt
  prompt list [--name-filter]              List prompts
  prompt get --id [--save]                 Get a prompt
  prompt update --id --file [--version]    Update a prompt
  prompt delete --id [--force]             Delete a prompt
  prompt associate --key --prompt-id       Associate prompt with API key

Admin:
  admin reload-adapters [--adapter]        Reload adapter configurations

Server:
  status [--watch]                         Check server status

Configuration:
  config show [--key]                      Show configuration
  config set <key> <value>                 Set configuration value
  config reset [--force]                   Reset configuration

Other:
  help [command]                          Show help
  exit, quit                              Exit the CLI
  clear, cls                              Clear screen

Use --output json for JSON output format.
Use --no-color to disable colored output.
    `);
  }

  private showCommandHelp(command: string): void {
    // Simple help for now - can be enhanced
    this.formatter.info(`Help for command: ${command}`);
    this.formatter.info('Use "help" to see all commands');
  }

  public start(): void {
    console.log('ORBIT CLI - Interactive Mode');
    console.log('Type "help" for available commands, "exit" to quit\n');
    this.rl.prompt();
  }

  public async runCommand(args: string[]): Promise<void> {
    // For non-interactive mode (direct command execution)
    if (args.length === 0) {
      this.start();
      return;
    }

    const command = args[0].toLowerCase();
    const rest = args.slice(1);

    try {
      await this.commandRegistry.execute(command, rest);
    } catch (error: any) {
      if (error.name === 'OrbitError' || error.name === 'AuthenticationError' || error.name === 'NetworkError') {
        this.formatter.error(error.message);
      } else {
        this.formatter.error(`Unexpected error: ${error.message}`);
        if (process.env.DEBUG) {
          console.error(error);
        }
      }
      process.exit(1);
    }
  }
}

// Main entry point
if (require.main === module) {
  const repl = new REPL();
  
  // Check if running in non-interactive mode (command passed as args)
  const args = process.argv.slice(2);
  
  if (args.length > 0) {
    // Non-interactive mode
    repl.runCommand(args).then(() => {
      process.exit(0);
    }).catch((error) => {
      console.error(error);
      process.exit(1);
    });
  } else {
    // Interactive REPL mode
    repl.start();
  }
}

