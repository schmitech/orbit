import chalk from 'chalk';
import { table } from 'table';

export type OutputFormat = 'table' | 'json';

export class Formatter {
  private format: OutputFormat;
  private useColor: boolean;

  constructor(format: OutputFormat = 'table', useColor: boolean = true) {
    this.format = format;
    this.useColor = useColor;
  }

  setFormat(format: OutputFormat): void {
    this.format = format;
  }

  setColor(useColor: boolean): void {
    this.useColor = useColor;
  }

  success(message: string): void {
    if (this.useColor) {
      console.log(chalk.green('✓'), message);
    } else {
      console.log('✓', message);
    }
  }

  error(message: string): void {
    if (this.useColor) {
      console.error(chalk.red('✗'), message);
    } else {
      console.error('✗', message);
    }
  }

  warning(message: string): void {
    if (this.useColor) {
      console.log(chalk.yellow('⚠'), message);
    } else {
      console.log('⚠', message);
    }
  }

  info(message: string): void {
    if (this.useColor) {
      console.log(chalk.blue('ℹ'), message);
    } else {
      console.log('ℹ', message);
    }
  }

  formatTable(data: any[], headers: string[]): void {
    if (this.format === 'json') {
      this.formatJson(data);
      return;
    }

    const rows = data.map(row => headers.map(header => {
      const value = row[header];
      if (value === undefined || value === null) {
        return 'N/A';
      }
      return String(value);
    }));

    const tableData = [headers, ...rows];
    const output = table(tableData, {
      border: {
        topBody: '─',
        topJoin: '┬',
        topLeft: '┌',
        topRight: '┐',
        bottomBody: '─',
        bottomJoin: '┴',
        bottomLeft: '└',
        bottomRight: '┘',
        bodyLeft: '│',
        bodyRight: '│',
        bodyJoin: '│',
        joinBody: '─',
        joinLeft: '├',
        joinRight: '┤',
        joinJoin: '┼'
      }
    });

    console.log(output);
  }

  formatJson(data: any): void {
    console.log(JSON.stringify(data, null, 2));
  }

  formatOutput(data: any, headers?: string[]): void {
    if (this.format === 'json') {
      this.formatJson(data);
    } else if (Array.isArray(data) && headers) {
      this.formatTable(data, headers);
    } else {
      this.formatJson(data);
    }
  }

  bold(text: string): string {
    if (this.useColor) {
      return chalk.bold(text);
    }
    return text;
  }

  dim(text: string): string {
    if (this.useColor) {
      return chalk.dim(text);
    }
    return text;
  }

  green(text: string): string {
    if (this.useColor) {
      return chalk.green(text);
    }
    return text;
  }

  red(text: string): string {
    if (this.useColor) {
      return chalk.red(text);
    }
    return text;
  }

  yellow(text: string): string {
    if (this.useColor) {
      return chalk.yellow(text);
    }
    return text;
  }

  blue(text: string): string {
    if (this.useColor) {
      return chalk.blue(text);
    }
    return text;
  }
}

