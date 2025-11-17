import inquirer from 'inquirer';
import * as fs from 'fs';
import { ApiClient } from '../api/client';
import { ConfigManager } from '../config/manager';
import { Formatter } from '../utils/formatters';
import { validatePromptId, formatDate } from '../utils/validators';

export class PromptCommands {
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
      this.formatter.error('Prompt command requires a subcommand');
      this.formatter.info('Available subcommands: create, list, get, update, delete, associate');
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
      case 'get':
        await this.get(rest);
        break;
      case 'update':
        await this.update(rest);
        break;
      case 'delete':
        await this.delete(rest);
        break;
      case 'associate':
        await this.associate(rest);
        break;
      default:
        this.formatter.error(`Unknown prompt subcommand: ${subcommand}`);
        this.formatter.info('Available subcommands: create, list, get, update, delete, associate');
    }
  }

  async create(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const name = parsed.name as string | undefined;
    const file = parsed.file as string | undefined;
    const version = (parsed.version as string) || '1.0';

    if (!name || !file) {
      this.formatter.error('--name and --file are required');
      return;
    }

    if (!fs.existsSync(file)) {
      this.formatter.error(`File not found: ${file}`);
      return;
    }

    try {
      const promptText = fs.readFileSync(file, 'utf-8');
      const result = await this.apiClient.createPrompt(name, promptText, version);

      this.formatter.success('System prompt created successfully');
      console.log(this.formatter.bold('ID:'), result.id);
      console.log(this.formatter.bold('Name:'), result.name);
      console.log(this.formatter.bold('Version:'), result.version);
    } catch (error: any) {
      this.formatter.error(`Failed to create prompt: ${error.message}`);
    }
  }

  async list(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const outputFormat = parsed.output === 'json' ? 'json' : 'table';
    const nameFilter = parsed['name-filter'] as string | undefined;
    const limit = parsed.limit ? parseInt(parsed.limit as string) : 100;
    const offset = parsed.offset ? parseInt(parsed.offset as string) : 0;

    try {
      const prompts = await this.apiClient.listPrompts({
        name_filter: nameFilter,
        limit,
        offset
      });

      if (outputFormat === 'json') {
        this.formatter.formatJson(prompts);
      } else {
        if (prompts.length === 0) {
          this.formatter.info('No prompts found');
          return;
        }

        const headers = ['ID', 'Name', 'Version', 'Created', 'Updated'];
        const data = prompts.map(prompt => ({
          'ID': prompt.id.substring(0, 12) + '...',
          'Name': prompt.name,
          'Version': prompt.version,
          'Created': formatDate(prompt.created_at),
          'Updated': formatDate(prompt.updated_at)
        }));

        this.formatter.formatTable(data, headers);
        console.log(`\nFound ${prompts.length} prompt(s)`);
      }
    } catch (error: any) {
      this.formatter.error(`Failed to list prompts: ${error.message}`);
    }
  }

  async get(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const outputFormat = parsed.output === 'json' ? 'json' : 'table';
    const promptId = parsed.id as string | undefined;
    const saveFile = parsed.save as string | undefined;

    if (!promptId) {
      this.formatter.error('--id is required');
      return;
    }

    try {
      validatePromptId(promptId);
      const prompt = await this.apiClient.getPrompt(promptId);

      if (saveFile) {
        fs.writeFileSync(saveFile, prompt.prompt, 'utf-8');
        this.formatter.success(`Prompt saved to ${saveFile}`);
      }

      if (outputFormat === 'json') {
        this.formatter.formatJson(prompt);
      } else {
        console.log(this.formatter.bold('ID:'), prompt.id);
        console.log(this.formatter.bold('Name:'), prompt.name);
        console.log(this.formatter.bold('Version:'), prompt.version);
        if (prompt.created_at) {
          console.log(this.formatter.bold('Created:'), formatDate(prompt.created_at));
        }
        if (prompt.updated_at) {
          console.log(this.formatter.bold('Updated:'), formatDate(prompt.updated_at));
        }
        console.log('\n' + this.formatter.bold('Prompt Text:'));
        console.log('─'.repeat(60));
        console.log(prompt.prompt);
        console.log('─'.repeat(60));
      }
    } catch (error: any) {
      this.formatter.error(`Failed to get prompt: ${error.message}`);
    }
  }

  async update(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const promptId = parsed.id as string | undefined;
    const file = parsed.file as string | undefined;
    const version = parsed.version as string | undefined;

    if (!promptId || !file) {
      this.formatter.error('--id and --file are required');
      return;
    }

    if (!fs.existsSync(file)) {
      this.formatter.error(`File not found: ${file}`);
      return;
    }

    try {
      validatePromptId(promptId);
      const promptText = fs.readFileSync(file, 'utf-8');
      await this.apiClient.updatePrompt(promptId, promptText, version);
      this.formatter.success('System prompt updated successfully');
    } catch (error: any) {
      this.formatter.error(`Failed to update prompt: ${error.message}`);
    }
  }

  async delete(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const promptId = parsed.id as string | undefined;
    const force = parsed.force === true;

    if (!promptId) {
      this.formatter.error('--id is required');
      return;
    }

    try {
      validatePromptId(promptId);
    } catch (error: any) {
      this.formatter.error(error.message);
      return;
    }

    if (!force) {
      const answer = await inquirer.prompt([
        {
          type: 'confirm',
          name: 'confirm',
          message: `Are you sure you want to delete prompt ${promptId.substring(0, 12)}...?`,
          default: false
        }
      ]);

      if (!answer.confirm) {
        this.formatter.info('Operation cancelled');
        return;
      }
    }

    try {
      await this.apiClient.deletePrompt(promptId);
      this.formatter.success('System prompt deleted successfully');
    } catch (error: any) {
      this.formatter.error(`Failed to delete prompt: ${error.message}`);
    }
  }

  async associate(args: string[]): Promise<void> {
    const parsed = this.parseArgs(args);
    const apiKey = parsed.key as string | undefined;
    const promptId = parsed['prompt-id'] as string | undefined;

    if (!apiKey || !promptId) {
      this.formatter.error('--key and --prompt-id are required');
      return;
    }

    try {
      await this.apiClient.associatePromptWithApiKey(apiKey, promptId);
      this.formatter.success('System prompt associated with API key successfully');
    } catch (error: any) {
      this.formatter.error(`Failed to associate prompt: ${error.message}`);
    }
  }
}

