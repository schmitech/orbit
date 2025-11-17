import inquirer from 'inquirer';
import { ApiClient } from '../api/client';
import { ConfigManager } from '../config/manager';
import { Formatter } from '../utils/formatters';
import { validateUserId, formatDate } from '../utils/validators';
import * as readline from 'readline';
import * as crypto from 'crypto';

export class UserCommands {
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

  async handle(args: string[]): Promise<void> {
    if (args.length === 0) {
      this.formatter.error('User command requires a subcommand');
      this.formatter.info('Available subcommands: list, reset-password, change-password, activate, deactivate, delete');
      return;
    }

    const subcommand = args[0].toLowerCase();
    const rest = args.slice(1);

    switch (subcommand) {
      case 'list':
        await this.list(rest);
        break;
      case 'reset-password':
        await this.resetPassword(rest);
        break;
      case 'change-password':
        await this.changePassword(rest);
        break;
      case 'activate':
        await this.activate(rest);
        break;
      case 'deactivate':
        await this.deactivate(rest);
        break;
      case 'delete':
        await this.delete(rest);
        break;
      default:
        this.formatter.error(`Unknown user subcommand: ${subcommand}`);
        this.formatter.info('Available subcommands: list, reset-password, change-password, activate, deactivate, delete');
    }
  }

  async list(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const outputFormat = parsed.output === 'json' ? 'json' : 'table';
    const role = parsed.role as string | undefined;
    const activeOnly = parsed['active-only'] === true;
    const limit = parsed.limit ? parseInt(parsed.limit as string) : 100;
    const offset = parsed.offset ? parseInt(parsed.offset as string) : 0;

    try {
      const users = await this.apiClient.listUsers({
        role,
        active_only: activeOnly,
        limit,
        offset
      });

      if (outputFormat === 'json') {
        this.formatter.formatJson(users);
      } else {
        if (users.length === 0) {
          this.formatter.info('No users found');
          return;
        }

        const headers = ['ID', 'Username', 'Role', 'Active', 'Created'];
        const data = users.map(user => ({
          'ID': user.id.substring(0, 12) + '...',
          'Username': user.username,
          'Role': user.role,
          'Active': user.active ? '✓' : '✗',
          'Created': formatDate(user.created_at)
        }));

        this.formatter.formatTable(data, headers);
        console.log(`\nFound ${users.length} user(s)`);
      }
    } catch (error: any) {
      this.formatter.error(`Failed to list users: ${error.message}`);
    }
  }

  async resetPassword(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    let userId = parsed['user-id'] as string | undefined;
    const username = parsed.username as string | undefined;
    let password = parsed.password as string | undefined;

    if (!userId && !username) {
      this.formatter.error('Either --user-id or --username is required');
      return;
    }

    // Resolve user ID from username if needed
    if (!userId && username) {
      try {
        const user = await this.apiClient.getUserByUsername(username);
        userId = user.id;
      } catch (error: any) {
        this.formatter.error(`User not found: ${username}`);
        return;
      }
    }

    if (!password) {
      // Generate a random password
      password = crypto.randomBytes(16).toString('base64').slice(0, 16);
      console.log(this.formatter.bold('Generated password:'), password);
    }

    try {
      await this.apiClient.resetUserPassword(userId!, password);
      this.formatter.success('User password reset successfully');
    } catch (error: any) {
      this.formatter.error(`Failed to reset password: ${error.message}`);
    }
  }

  async changePassword(args: string[]): Promise<void> {
    let currentPassword: string;
    let newPassword: string;

    currentPassword = await this.promptPassword('Current password: ');
    newPassword = await this.promptPassword('New password: ');
    const confirm = await this.promptPassword('Confirm new password: ');

    if (newPassword !== confirm) {
      this.formatter.error('New passwords do not match');
      return;
    }

    try {
      await this.apiClient.changePassword(currentPassword, newPassword);
      this.configManager.clearToken(); // Clear token since password changed
      this.formatter.success('Password changed successfully');
      this.formatter.warning('All sessions have been invalidated. Please login again.');
    } catch (error: any) {
      this.formatter.error(`Failed to change password: ${error.message}`);
    }
  }

  async activate(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const userId = parsed['user-id'] as string | undefined;
    const force = parsed.force === true;

    if (!userId) {
      this.formatter.error('--user-id is required');
      return;
    }

    try {
      validateUserId(userId);
    } catch (error: any) {
      this.formatter.error(error.message);
      return;
    }

    if (!force) {
      const answer = await inquirer.prompt([
        {
          type: 'confirm',
          name: 'confirm',
          message: `Are you sure you want to activate user ${userId.substring(0, 12)}...?`,
          default: false
        }
      ]);

      if (!answer.confirm) {
        this.formatter.info('Operation cancelled');
        return;
      }
    }

    try {
      await this.apiClient.activateUser(userId);
      this.formatter.success('User activated successfully');
    } catch (error: any) {
      this.formatter.error(`Failed to activate user: ${error.message}`);
    }
  }

  async deactivate(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const userId = parsed['user-id'] as string | undefined;
    const force = parsed.force === true;

    if (!userId) {
      this.formatter.error('--user-id is required');
      return;
    }

    try {
      validateUserId(userId);
    } catch (error: any) {
      this.formatter.error(error.message);
      return;
    }

    if (!force) {
      const answer = await inquirer.prompt([
        {
          type: 'confirm',
          name: 'confirm',
          message: `Are you sure you want to deactivate user ${userId.substring(0, 12)}...?`,
          default: false
        }
      ]);

      if (!answer.confirm) {
        this.formatter.info('Operation cancelled');
        return;
      }
    }

    try {
      await this.apiClient.deactivateUser(userId);
      this.formatter.success('User deactivated successfully');
    } catch (error: any) {
      this.formatter.error(`Failed to deactivate user: ${error.message}`);
    }
  }

  async delete(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const userId = parsed['user-id'] as string | undefined;
    const force = parsed.force === true;

    if (!userId) {
      this.formatter.error('--user-id is required');
      return;
    }

    try {
      validateUserId(userId);
    } catch (error: any) {
      this.formatter.error(error.message);
      return;
    }

    if (!force) {
      const answer = await inquirer.prompt([
        {
          type: 'confirm',
          name: 'confirm',
          message: `Are you sure you want to delete user ${userId.substring(0, 12)}...?`,
          default: false
        }
      ]);

      if (!answer.confirm) {
        this.formatter.info('Operation cancelled');
        return;
      }
    }

    try {
      await this.apiClient.deleteUser(userId);
      this.formatter.success('User deleted successfully');
    } catch (error: any) {
      this.formatter.error(`Failed to delete user: ${error.message}`);
    }
  }
}

