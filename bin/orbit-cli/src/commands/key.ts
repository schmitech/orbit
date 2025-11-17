import inquirer from 'inquirer';
import * as fs from 'fs';
import { ApiClient } from '../api/client';
import { ConfigManager } from '../config/manager';
import { Formatter } from '../utils/formatters';
import { validateApiKey, maskApiKey, formatDate } from '../utils/validators';

export class KeyCommands {
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
      this.formatter.error('Key command requires a subcommand');
      this.formatter.info('Available subcommands: create, list, status, test, rename, deactivate, delete, list-adapters');
      return;
    }

    const subcommand = args[0].toLowerCase();
    const rest = args.slice(1);

    switch (subcommand) {
      case 'create':
        await this.create(rest);
        break;
      case 'list':
        await this.list(rest);
        break;
      case 'status':
        await this.status(rest);
        break;
      case 'test':
        await this.test(rest);
        break;
      case 'rename':
        await this.rename(rest);
        break;
      case 'deactivate':
        await this.deactivate(rest);
        break;
      case 'delete':
        await this.delete(rest);
        break;
      case 'list-adapters':
        await this.listAdapters(rest);
        break;
      default:
        this.formatter.error(`Unknown key subcommand: ${subcommand}`);
        this.formatter.info('Available subcommands: create, list, status, test, rename, deactivate, delete, list-adapters');
    }
  }

  async create(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const adapter = parsed.adapter as string | undefined;
    const name = parsed.name as string | undefined;
    const notes = parsed.notes as string | undefined;
    const promptId = parsed['prompt-id'] as string | undefined;
    const promptFile = parsed['prompt-file'] as string | undefined;
    const promptName = parsed['prompt-name'] as string | undefined;

    if (!adapter || !name) {
      this.formatter.error('--adapter and --name are required');
      return;
    }

    try {
      let finalPromptId = promptId;

      // Handle prompt file if provided
      if (promptFile) {
        if (!fs.existsSync(promptFile)) {
          this.formatter.error(`File not found: ${promptFile}`);
          return;
        }

        const promptText = fs.readFileSync(promptFile, 'utf-8');
        
        if (promptId) {
          // Update existing prompt
          await this.apiClient.updatePrompt(promptId, promptText);
          finalPromptId = promptId;
        } else if (promptName) {
          // Create new prompt
          const prompt = await this.apiClient.createPrompt(promptName, promptText);
          finalPromptId = prompt.id;
        } else {
          this.formatter.error('Either --prompt-id or --prompt-name is required when using --prompt-file');
          return;
        }
      }

      const data: any = {
        client_name: name,
        adapter_name: adapter
      };

      if (notes) {
        data.notes = notes;
      }

      if (finalPromptId) {
        data.system_prompt_id = finalPromptId;
      }

      const result = await this.apiClient.createApiKey(data);

      // Associate prompt if we created/updated one
      if (finalPromptId && result.api_key) {
        try {
          await this.apiClient.associatePromptWithApiKey(result.api_key, finalPromptId);
        } catch (error) {
          // Ignore association errors, key was still created
        }
      }

      this.formatter.success('API key created successfully');
      console.log(this.formatter.bold('API Key:'), result.api_key);
      console.log(this.formatter.bold('Client:'), result.client_name);
      if (result.adapter_name) {
        console.log(this.formatter.bold('Adapter:'), result.adapter_name);
      }
      if (finalPromptId) {
        console.log(this.formatter.bold('Prompt ID:'), finalPromptId);
      }
    } catch (error: any) {
      this.formatter.error(`Failed to create API key: ${error.message}`);
    }
  }

  async list(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const outputFormat = parsed.output === 'json' ? 'json' : 'table';
    const activeOnly = parsed['active-only'] === true;
    const limit = parsed.limit ? parseInt(parsed.limit as string) : 100;
    const offset = parsed.offset ? parseInt(parsed.offset as string) : 0;

    try {
      const keys = await this.apiClient.listApiKeys({
        active_only: activeOnly,
        limit,
        offset
      });

      if (outputFormat === 'json') {
        this.formatter.formatJson(keys);
      } else {
        if (keys.length === 0) {
          this.formatter.info('No API keys found');
          return;
        }

        const headers = ['API Key', 'Client', 'Adapter', 'Active', 'Created'];
        const data = keys.map(key => ({
          'API Key': maskApiKey(key.api_key),
          'Client': key.client_name,
          'Adapter': key.adapter_name || 'N/A',
          'Active': key.active ? '✓' : '✗',
          'Created': formatDate(key.created_at)
        }));

        this.formatter.formatTable(data, headers);
        console.log(`\nFound ${keys.length} API key(s)`);
      }
    } catch (error: any) {
      this.formatter.error(`Failed to list API keys: ${error.message}`);
    }
  }

  async status(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const outputFormat = parsed.output === 'json' ? 'json' : 'table';
    const apiKey = parsed.key as string | undefined;

    if (!apiKey) {
      this.formatter.error('--key is required');
      return;
    }

    try {
      validateApiKey(apiKey);
      const status = await this.apiClient.getApiKeyStatus(apiKey);

      if (outputFormat === 'json') {
        this.formatter.formatJson(status);
      } else {
        if (status.active) {
          this.formatter.success('API key is active');
        } else {
          this.formatter.warning('API key is inactive');
        }

        console.log(this.formatter.bold('Client:'), status.client_name);
        if (status.adapter_name) {
          console.log(this.formatter.bold('Adapter:'), status.adapter_name);
        }
        if (status.created_at) {
          console.log(this.formatter.bold('Created:'), formatDate(status.created_at));
        }
        if (status.last_used) {
          console.log(this.formatter.bold('Last Used:'), status.last_used);
        }
        if (status.system_prompt_id) {
          console.log(this.formatter.bold('System Prompt:'), status.system_prompt_id);
        }
      }
    } catch (error: any) {
      this.formatter.error(`Failed to get API key status: ${error.message}`);
    }
  }

  async test(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const apiKey = parsed.key as string | undefined;

    if (!apiKey) {
      this.formatter.error('--key is required');
      return;
    }

    try {
      validateApiKey(apiKey);
      const result = await this.apiClient.testApiKey(apiKey);

      if (result.status === 'error') {
        this.formatter.error(`API key test failed: ${result.error}`);
      } else {
        this.formatter.success('API key is valid and active');
      }
    } catch (error: any) {
      this.formatter.error(`Failed to test API key: ${error.message}`);
    }
  }

  async rename(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const oldKey = parsed['old-key'] as string | undefined;
    const newKey = parsed['new-key'] as string | undefined;

    if (!oldKey || !newKey) {
      this.formatter.error('--old-key and --new-key are required');
      return;
    }

    try {
      validateApiKey(oldKey);
      validateApiKey(newKey);
      await this.apiClient.renameApiKey(oldKey, newKey);
      this.formatter.success('API key renamed successfully');
      console.log(this.formatter.bold('Old key:'), maskApiKey(oldKey));
      console.log(this.formatter.bold('New key:'), maskApiKey(newKey));
    } catch (error: any) {
      this.formatter.error(`Failed to rename API key: ${error.message}`);
    }
  }

  async deactivate(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const apiKey = parsed.key as string | undefined;

    if (!apiKey) {
      this.formatter.error('--key is required');
      return;
    }

    try {
      validateApiKey(apiKey);
      await this.apiClient.deactivateApiKey(apiKey);
      this.formatter.success('API key deactivated successfully');
    } catch (error: any) {
      this.formatter.error(`Failed to deactivate API key: ${error.message}`);
    }
  }

  async delete(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const apiKey = parsed.key as string | undefined;
    const force = parsed.force === true;

    if (!apiKey) {
      this.formatter.error('--key is required');
      return;
    }

    try {
      validateApiKey(apiKey);
    } catch (error: any) {
      this.formatter.error(error.message);
      return;
    }

    if (!force) {
      const answer = await inquirer.prompt([
        {
          type: 'confirm',
          name: 'confirm',
          message: `Are you sure you want to delete API key ${maskApiKey(apiKey)}?`,
          default: false
        }
      ]);

      if (!answer.confirm) {
        this.formatter.info('Operation cancelled');
        return;
      }
    }

    try {
      await this.apiClient.deleteApiKey(apiKey);
      this.formatter.success('API key deleted successfully');
    } catch (error: any) {
      this.formatter.error(`Failed to delete API key: ${error.message}`);
    }
  }

  async listAdapters(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const outputFormat = parsed.output === 'json' ? 'json' : 'table';

    // Note: There's no API endpoint for listing adapters, so we show a message
    // In the future, this could be added to the server API
    this.formatter.info('Adapter list is not available via API');
    this.formatter.info('Check config/adapters.yaml on the server for adapter configuration');
    this.formatter.info('Use "key create --adapter <name>" to create keys for specific adapters');
  }
}

