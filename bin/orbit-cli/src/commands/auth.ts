import inquirer from 'inquirer';
import * as readline from 'readline';
import { ApiClient, AuthenticationError } from '../api/client';
import { ConfigManager } from '../config/manager';
import { Formatter } from '../utils/formatters';
import { validateUsername, validatePassword } from '../utils/validators';

export class AuthCommands {
  constructor(
    private apiClient: ApiClient,
    private configManager: ConfigManager,
    private formatter: Formatter
  ) {}

  private parseArgs(args: string[]): Record<string, string> {
    const parsed: Record<string, string> = {};
    for (let i = 0; i < args.length; i++) {
      if (args[i].startsWith('--')) {
        const key = args[i].slice(2);
        const value = args[i + 1];
        if (value && !value.startsWith('--')) {
          parsed[key] = value;
          i++;
        } else {
          parsed[key] = 'true';
        }
      }
    }
    return parsed;
  }

  private async promptPassword(message: string = 'Password: '): Promise<string> {
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout
    });

    return new Promise((resolve) => {
      process.stdin.setRawMode(true);
      process.stdin.resume();
      process.stdin.setEncoding('utf8');

      let password = '';
      process.stdout.write(message);

      const onData = (char: string) => {
        if (char === '\n' || char === '\r') {
          process.stdin.setRawMode(false);
          process.stdin.pause();
          process.stdin.removeListener('data', onData);
          rl.close();
          process.stdout.write('\n');
          resolve(password);
        } else if (char === '\u0003') {
          process.exit(0);
        } else if (char === '\u007f' || char === '\b') {
          if (password.length > 0) {
            password = password.slice(0, -1);
            process.stdout.write('\b \b');
          }
        } else {
          password += char;
          process.stdout.write('*');
        }
      };

      process.stdin.on('data', onData);
    });
  }

  async login(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    let username = parsed.username;
    let password = parsed.password;

    // Check if already authenticated
    try {
      const user = await this.apiClient.getCurrentUser();
      this.formatter.warning(`Already logged in as ${user.username}`);
      this.formatter.info('Please logout first if you want to login with a different account');
      return;
    } catch (error) {
      // Not authenticated, continue
    }

    // Prompt for username if not provided
    if (!username) {
      const answer = await inquirer.prompt([
        {
          type: 'input',
          name: 'username',
          message: 'Username:',
          validate: (input) => {
            try {
              validateUsername(input);
              return true;
            } catch (error: any) {
              return error.message;
            }
          }
        }
      ]);
      username = answer.username;
    } else {
      try {
        validateUsername(username);
      } catch (error: any) {
        this.formatter.error(error.message);
        return;
      }
    }

    // Prompt for password if not provided
    if (!password) {
      password = await this.promptPassword();
    }

    try {
      validatePassword(password);
    } catch (error: any) {
      this.formatter.error(error.message);
      return;
    }

    try {
      const result = await this.apiClient.login(username, password);
      this.configManager.setAuthToken(result.token);
      this.formatter.success(`Logged in as ${result.user.username}`);
    } catch (error: any) {
      if (error instanceof AuthenticationError) {
        this.formatter.error('Invalid username or password');
      } else {
        this.formatter.error(`Login failed: ${error.message}`);
      }
    }
  }

  async logout(args: string[]): Promise<void> {
    try {
      await this.apiClient.logout();
      this.configManager.clearToken();
      this.formatter.success('Logged out successfully');
    } catch (error: any) {
      // Clear token anyway even if server logout fails
      this.configManager.clearToken();
      this.formatter.info('Logged out locally');
    }
  }

  async register(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    let username = parsed.username;
    let password = parsed.password;
    const role = parsed.role || 'user';

    if (!username) {
      const answer = await inquirer.prompt([
        {
          type: 'input',
          name: 'username',
          message: 'Username:',
          validate: (input) => {
            try {
              validateUsername(input);
              return true;
            } catch (error: any) {
              return error.message;
            }
          }
        }
      ]);
      username = answer.username;
    }

    if (!password) {
      password = await this.promptPassword('Password for new user: ');
      const confirm = await this.promptPassword('Confirm password: ');
      if (password !== confirm) {
        this.formatter.error('Passwords do not match');
        return;
      }
    }

    try {
      const result = await this.apiClient.registerUser(username, password, role);
      this.formatter.success(`User '${result.username}' registered successfully`);
    } catch (error: any) {
      this.formatter.error(`Registration failed: ${error.message}`);
    }
  }

  async me(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const outputFormat = parsed.output === 'json' ? 'json' : 'table';

    try {
      const user = await this.apiClient.getCurrentUser();
      
      if (outputFormat === 'json') {
        this.formatter.formatJson(user);
      } else {
        console.log(this.formatter.bold('Username:'), user.username);
        console.log(this.formatter.bold('Role:'), user.role);
        console.log(this.formatter.bold('ID:'), user.id);
        if (user.created_at) {
          console.log(this.formatter.bold('Created:'), user.created_at);
        }
        if (user.last_login) {
          console.log(this.formatter.bold('Last Login:'), user.last_login);
        }
      }
    } catch (error: any) {
      if (error instanceof AuthenticationError) {
        this.formatter.error('Not authenticated. Please run "login" first.');
      } else {
        this.formatter.error(`Failed to get user info: ${error.message}`);
      }
    }
  }

  async authStatus(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const outputFormat = parsed.output === 'json' ? 'json' : 'table';

    const token = this.configManager.getAuthToken();
    const serverUrl = this.configManager.getServerUrl();

    if (!token) {
      const status = {
        authenticated: false,
        message: 'Not authenticated',
        server_url: serverUrl
      };
      
      if (outputFormat === 'json') {
        this.formatter.formatJson(status);
      } else {
        this.formatter.warning('Not authenticated');
        console.log(this.formatter.bold('Server URL:'), serverUrl);
        this.formatter.info('Run "login" to authenticate');
      }
      return;
    }

    try {
      const user = await this.apiClient.getCurrentUser();
      const status = {
        authenticated: true,
        user: user,
        server_url: serverUrl
      };

      if (outputFormat === 'json') {
        this.formatter.formatJson(status);
      } else {
        this.formatter.success('Authenticated');
        console.log(this.formatter.bold('Username:'), user.username);
        console.log(this.formatter.bold('Role:'), user.role);
        console.log(this.formatter.bold('Server URL:'), serverUrl);
      }
    } catch (error: any) {
      const status = {
        authenticated: false,
        message: 'Token expired or invalid',
        server_url: serverUrl
      };

      if (outputFormat === 'json') {
        this.formatter.formatJson(status);
      } else {
        this.formatter.warning('Token expired or invalid');
        this.formatter.info('Run "login" to authenticate');
      }
    }
  }
}

