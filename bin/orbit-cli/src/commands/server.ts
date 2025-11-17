import { ApiClient } from '../api/client';
import { ConfigManager } from '../config/manager';
import { Formatter } from '../utils/formatters';

export class ServerCommands {
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

  async status(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const outputFormat = parsed.output === 'json' ? 'json' : 'table';
    const watch = parsed.watch === true;
    const interval = parsed.interval ? parseInt(parsed.interval as string) : 5;

    if (watch) {
      await this.watchStatus(interval, outputFormat);
    } else {
      await this.showStatus(outputFormat);
    }
  }

  private async showStatus(outputFormat: 'table' | 'json'): Promise<void> {
    try {
      const [health, systemStatus] = await Promise.all([
        this.apiClient.getHealth().catch(() => null),
        this.apiClient.getSystemStatus().catch(() => null)
      ]);

      if (!health && !systemStatus) {
        this.formatter.error('Server is not responding');
        return;
      }

      if (outputFormat === 'json') {
        this.formatter.formatJson({
          health,
          system: systemStatus
        });
      } else {
        if (health) {
          if (health.status === 'ok' || health.status === 'healthy') {
            this.formatter.success('Server is healthy');
          } else {
            this.formatter.warning(`Server status: ${health.status}`);
          }
        }

        if (systemStatus) {
          console.log(this.formatter.bold('Fault Tolerance:'), 
            systemStatus.fault_tolerance?.enabled ? this.formatter.green('Enabled') : this.formatter.yellow('Disabled'));
          
          if (systemStatus.fault_tolerance?.adapters) {
            const adapters = systemStatus.fault_tolerance.adapters;
            const adapterCount = Object.keys(adapters).length;
            console.log(this.formatter.bold('Adapters:'), adapterCount);
          }
        }
      }
    } catch (error: any) {
      this.formatter.error(`Failed to get server status: ${error.message}`);
    }
  }

  private async watchStatus(interval: number, outputFormat: 'table' | 'json'): Promise<void> {
    const updateStatus = async () => {
      // Clear screen
      process.stdout.write('\x1B[2J\x1B[0f');
      
      console.log('ORBIT Server Status (Press Ctrl+C to stop)\n');
      console.log(`Last updated: ${new Date().toLocaleString()}\n`);
      
      await this.showStatus(outputFormat);
      
      console.log(`\nRefreshing every ${interval} seconds...`);
    };

    // Initial update
    await updateStatus();

    // Set up interval
    const intervalId = setInterval(updateStatus, interval * 1000);

    // Handle Ctrl+C
    process.on('SIGINT', () => {
      clearInterval(intervalId);
      console.log('\nStatus monitoring stopped');
      process.exit(0);
    });
  }
}

