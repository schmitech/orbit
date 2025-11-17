import { ApiClient } from '../api/client';
import { ConfigManager } from '../config/manager';
import { Formatter } from '../utils/formatters';
import ora from 'ora';

export class AdminCommands {
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
      this.formatter.error('Admin command requires a subcommand');
      this.formatter.info('Available subcommands: reload-adapters');
      return;
    }

    const subcommand = args[0].toLowerCase();
    const rest = args.slice(1);

    switch (subcommand) {
      case 'reload-adapters':
        await this.reloadAdapters(rest);
        break;
      default:
        this.formatter.error(`Unknown admin subcommand: ${subcommand}`);
        this.formatter.info('Available subcommands: reload-adapters');
    }
  }

  async reloadAdapters(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const outputFormat = parsed.output === 'json' ? 'json' : 'table';
    const adapterName = parsed.adapter as string | undefined;
    const verbose = parsed.verbose === true;

    const spinner = ora('Reloading adapters...').start();

    try {
      const result = await this.apiClient.reloadAdapters(adapterName);

      spinner.succeed(result.message);

      if (outputFormat === 'json') {
        this.formatter.formatJson(result);
      } else {
        if (adapterName) {
          // Single adapter reload
          const action = result.summary?.action || 'reloaded';
          console.log(this.formatter.bold('Adapter:'), result.summary?.adapter_name || adapterName);
          
          if (action === 'disabled') {
            console.log(this.formatter.bold('Action:'), this.formatter.red(action), '(adapter removed from active pool)');
          } else if (action === 'enabled' || action === 'added') {
            console.log(this.formatter.bold('Action:'), this.formatter.green(action));
          } else if (action === 'updated') {
            console.log(this.formatter.bold('Action:'), this.formatter.yellow(action));
          } else {
            console.log(this.formatter.bold('Action:'), action);
          }
        } else {
          // Multiple adapters reload
          const summary = result.summary || {};
          console.log('\n' + this.formatter.bold('Adapter Reload Summary:'));
          console.log(`  Added: ${summary.added || 0}`);
          console.log(`  Removed: ${summary.removed || 0}`);
          console.log(`  Updated: ${summary.updated || 0}`);
          console.log(`  Unchanged: ${summary.unchanged || 0}`);
          console.log(`  Total: ${summary.total || 0}`);

          if (verbose) {
            if (summary.added_names && summary.added_names.length > 0) {
              console.log(this.formatter.green('\nAdded:'), summary.added_names.join(', '));
            }
            if (summary.removed_names && summary.removed_names.length > 0) {
              console.log(this.formatter.red('Removed:'), summary.removed_names.join(', '));
            }
            if (summary.updated_names && summary.updated_names.length > 0) {
              console.log(this.formatter.yellow('Updated:'), summary.updated_names.join(', '));
            }
          }
        }
      }
    } catch (error: any) {
      spinner.fail('Failed to reload adapters');
      this.formatter.error(error.message);
    }
  }
}

