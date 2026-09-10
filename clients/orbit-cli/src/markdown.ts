import { highlight, supportsLanguage } from 'cli-highlight';
import { ansiEnabled } from './tty.js';

const RESET = '\x1b[0m';
const BOLD = '\x1b[1m';
const DIM = '\x1b[2m';
const ITALIC = '\x1b[3m';
const HEADING = '\x1b[1;36m';

function styleLine(line: string): string {
  const heading = /^(#{1,6})\s+(.*)$/.exec(line);
  if (heading) {
    return `${HEADING}${heading[2]}${RESET}`;
  }

  let out = line;
  out = out.replace(/\*\*(.+?)\*\*/g, `${BOLD}$1${RESET}`);
  out = out.replace(/__(.+?)__/g, `${BOLD}$1${RESET}`);
  out = out.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, `${ITALIC}$1${RESET}`);
  out = out.replace(/`([^`]+)`/g, `${DIM}$1${RESET}`);
  out = out.replace(/^(\s*)[-*+]\s+/, '$1• ');
  out = out.replace(/^(\s*>)\s?/, `${DIM}│${RESET} `);
  return out;
}

function stripLine(line: string): string {
  return line
    .replace(/^#{1,6}\s+/, '')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/__(.+?)__/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/^(\s*)[-*+]\s+/, '$1- ');
}

/**
 * Line-buffered markdown -> ANSI renderer for the REPL's streaming
 * transcript: headings, emphasis, inline code, list markers, and a dimmed
 * treatment for fenced code blocks. Deliberately line-buffered rather than
 * block-buffered with a retroactive tail re-render — a completed line is
 * final and is never rewritten, which is simpler and avoids the cursor
 * bookkeeping a live-redraw renderer needs, at the cost of not syntax
 * highlighting code by language and not reflowing tables. Respects
 * `NO_COLOR` and non-TTY by falling back to the markdown stripped of its
 * syntax rather than raw asterisks/hashes.
 */
export class MarkdownRenderer {
  private buffer = '';
  private inFence = false;
  private fenceLang: string | undefined;

  push(text: string): void {
    this.buffer += text;
    let newlineIndex: number;
    while ((newlineIndex = this.buffer.indexOf('\n')) !== -1) {
      const line = this.buffer.slice(0, newlineIndex);
      this.buffer = this.buffer.slice(newlineIndex + 1);
      this.emitLine(line);
    }
  }

  /** Flush any trailing partial line (the model's reply need not end in \n). */
  flush(): void {
    if (this.buffer.length > 0) {
      this.emitLine(this.buffer);
      this.buffer = '';
    }
  }

  private emitLine(line: string): void {
    const color = ansiEnabled();

    const fenceMatch = /^```\s*(\S*)/.exec(line.trim());
    if (fenceMatch) {
      this.inFence = !this.inFence;
      this.fenceLang = this.inFence ? fenceMatch[1] || undefined : undefined;
      if (color) {
        process.stdout.write(`${DIM}${line}${RESET}\n`);
      }
      // Plain-text fallback strips markdown syntax; the fence delimiter
      // itself carries no content, so it is dropped rather than printed.
      return;
    }

    if (this.inFence) {
      if (!color) {
        process.stdout.write(`${line}\n`);
        return;
      }
      if (this.fenceLang && supportsLanguage(this.fenceLang)) {
        try {
          process.stdout.write(`${highlight(line, { language: this.fenceLang, ignoreIllegals: true })}\n`);
          return;
        } catch {
          // Fall through to the flat dim treatment below.
        }
      }
      process.stdout.write(`${DIM}${line}${RESET}\n`);
      return;
    }

    process.stdout.write(`${color ? styleLine(line) : stripLine(line)}\n`);
  }
}
