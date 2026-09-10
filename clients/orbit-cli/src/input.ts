import * as readline from 'node:readline';
import { ansiEnabled } from './tty.js';

const RESET = '\x1b[0m';
const DIM = '\x1b[2m';
const INVERT = '\x1b[7m';
const CTRL_C = '\x03';

export interface CommandSpec {
  name: string;
  usage: string;
  description: string;
}

type Completer = (line: string) => [string[], string];

export interface LineReaderOptions {
  prompt: string;
  commands: CommandSpec[];
  completer: Completer;
  /** Called on Ctrl+C outside of reverse-search; caller decides abort-turn vs. exit-REPL. */
  onSigint: () => void;
}

// eslint-disable-next-line no-control-regex -- matches the ANSI escape byte itself, to strip color codes before measuring display width.
const ANSI_PATTERN = /\x1b\[[0-9;]*m/g;

function isWideCodePoint(cp: number): boolean {
  return (
    (cp >= 0x1100 && cp <= 0x115f) || // Hangul Jamo
    cp === 0x2329 ||
    cp === 0x232a ||
    (cp >= 0x2e80 && cp <= 0x303e) || // CJK Radicals..CJK Symbols
    (cp >= 0x3041 && cp <= 0x33ff) || // Hiragana..CJK Compatibility
    (cp >= 0x3400 && cp <= 0x4dbf) || // CJK Extension A
    (cp >= 0x4e00 && cp <= 0x9fff) || // CJK Unified Ideographs
    (cp >= 0xa000 && cp <= 0xa4cf) || // Yi
    (cp >= 0xac00 && cp <= 0xd7a3) || // Hangul Syllables
    (cp >= 0xf900 && cp <= 0xfaff) || // CJK Compatibility Ideographs
    (cp >= 0xfe30 && cp <= 0xfe4f) || // CJK Compatibility Forms
    (cp >= 0xff00 && cp <= 0xff60) || // Fullwidth Forms
    (cp >= 0xffe0 && cp <= 0xffe6) ||
    (cp >= 0x1f300 && cp <= 0x1faff) || // emoji blocks (approximate)
    (cp >= 0x20000 && cp <= 0x3fffd) // CJK Extension B and beyond
  );
}

function isZeroWidthCodePoint(cp: number): boolean {
  return (
    cp === 0x200b || // zero width space
    cp === 0x200c ||
    cp === 0x200d || // zero width joiner
    cp === 0xfeff ||
    (cp >= 0x0300 && cp <= 0x036f) || // combining diacritics
    (cp >= 0x1ab0 && cp <= 0x1aff) ||
    (cp >= 0x1dc0 && cp <= 0x1dff) ||
    (cp >= 0x20d0 && cp <= 0x20ff) ||
    (cp >= 0xfe00 && cp <= 0xfe0f) // variation selectors
  );
}

/** Terminal column width of a string: strips ANSI escapes, counts wide/full-width code points as 2 columns and zero-width marks as 0. */
function displayWidth(str: string): number {
  const clean = str.replace(ANSI_PATTERN, '');
  let width = 0;
  for (const ch of clean) {
    const cp = ch.codePointAt(0) ?? 0;
    if (isZeroWidthCodePoint(cp)) continue;
    width += isWideCodePoint(cp) ? 2 : 1;
  }
  return width;
}

/** Terminal rows a string wraps into at the given column width. */
function rowsFor(text: string, width: number): number {
  return Math.max(1, Math.ceil(displayWidth(text) / width) || 1);
}

const graphemeSegmenter =
  typeof Intl !== 'undefined' && 'Segmenter' in Intl ? new Intl.Segmenter(undefined, { granularity: 'grapheme' }) : null;

/** Split a string into grapheme clusters (falling back to code points) so cursor movement never lands inside a surrogate pair or a combined emoji. */
function graphemes(str: string): string[] {
  if (graphemeSegmenter) {
    return Array.from(graphemeSegmenter.segment(str), (s) => s.segment);
  }
  return Array.from(str);
}

function commonPrefix(strings: string[]): string {
  if (strings.length === 0) return '';
  let prefix = strings[0];
  for (const s of strings.slice(1)) {
    let i = 0;
    while (i < prefix.length && i < s.length && prefix[i] === s[i]) i++;
    prefix = prefix.slice(0, i);
  }
  return prefix;
}

/**
 * Hand-rolled raw-mode line editor, replacing `node:readline`'s line editing
 * so the REPL can render UI that readline has no hook for: a live `/`
 * command dropdown and a Ctrl+R reverse-search overlay. Modeled on the
 * masked-input loop `prompt.ts::askSecret()` already uses, extended with
 * cursor movement, in-memory history, and the two overlays above.
 */
export class LineReader {
  private readonly prompt: string;
  private readonly commands: CommandSpec[];
  private readonly completer: Completer;
  private readonly onSigint: () => void;
  private readonly stdin = process.stdin;
  private readonly history: string[] = [];

  private buffer = '';
  private cursor = 0;
  private historyIndex = 0;

  private menuVisible = false;
  private menuIndex = 0;
  private menuItems: CommandSpec[] = [];

  private searchMode = false;
  private searchQuery = '';
  private searchMatch: string | undefined;
  private searchScanIndex = 0;

  private secretMode = false;
  private secretPrompt = '';
  private secretBuffer = '';
  private resolveSecret: ((value: string | null) => void) | null = null;

  private listMode = false;
  private listPrompt = '';
  private listQuery = '';
  private listAllItems: string[] = [];
  private listFiltered: number[] = [];
  private listIndex = 0;
  private resolveList: ((index: number | null) => void) | null = null;

  private resolveLine: ((line: string | null) => void) | null = null;
  private closed = false;
  private wasRaw = false;
  /** Row offset (relative to the input's first row) the cursor was left on by the last render, for wrapped-line redraw bookkeeping. */
  private lastCursorRow = 0;

  constructor(options: LineReaderOptions) {
    this.prompt = options.prompt;
    this.commands = options.commands;
    this.completer = options.completer;
    this.onSigint = options.onSigint;

    if (this.stdin.isTTY) {
      readline.emitKeypressEvents(this.stdin);
      this.wasRaw = this.stdin.isRaw;
      this.stdin.setRawMode(true);
    }
    this.stdin.resume();
    this.stdin.setEncoding('utf8');
    this.stdin.on('keypress', this.onKeypress);
  }

  async *[Symbol.asyncIterator](): AsyncGenerator<string> {
    while (!this.closed) {
      const line = await this.readLine();
      if (line === null) {
        return;
      }
      yield line;
    }
  }

  close(): void {
    if (this.closed) return;
    this.closed = true;
    this.stdin.removeListener('keypress', this.onKeypress);
    if (this.stdin.isTTY) {
      this.stdin.setRawMode(this.wasRaw);
    }
    // The constructor calls stdin.resume() to receive keypress events; a
    // resumed, flowing stdin keeps the event loop alive on its own, so
    // without pausing it here the process never exits after /exit or Ctrl+D.
    this.stdin.pause();
  }

  /**
   * `cursor` counts grapheme clusters, not UTF-16 code units — a `cursor--`
   * next to an emoji or a surrogate-pair character must skip the whole
   * cluster, not land inside it. This converts that cluster count to the
   * actual string offset needed for `buffer.slice(...)`.
   */
  private cursorStringIndex(): number {
    return graphemes(this.buffer).slice(0, this.cursor).join('').length;
  }

  /**
   * Insert `text` at string offset `idx` and recompute the cursor by
   * re-segmenting the resulting prefix, rather than adding `graphemes(text)`
   * to the old cursor. The terminal delivers a multi-codepoint emoji (e.g. a
   * ZWJ family sequence) as separate keypress events one codepoint at a
   * time; segmented alone, a joiner counts as its own cluster, but Unicode's
   * grapheme rules attach it to whatever already precedes it in the buffer.
   * Re-segmenting the real prefix after each keystroke keeps the cursor's
   * cluster count correct instead of drifting ahead of the buffer's actual
   * cluster count (which crashes the next backspace/delete on an
   * out-of-range index).
   */
  private insertAt(idx: number, text: string): void {
    this.buffer = this.buffer.slice(0, idx) + text + this.buffer.slice(idx);
    this.cursor = graphemes(this.buffer.slice(0, idx + text.length)).length;
  }

  /**
   * Read one line of masked input (e.g. an API key) without it ever being
   * echoed, written to terminal scrollback, or added to line history — only
   * a `*` per typed character is shown, same masking `prompt.ts::askSecret()`
   * uses for the initial connection prompt. Ctrl+C cancels and resolves
   * `null` instead of exiting the process, since a REPL command is in
   * progress rather than startup.
   */
  readSecret(promptText: string): Promise<string | null> {
    this.secretMode = true;
    this.secretPrompt = promptText;
    this.secretBuffer = '';
    this.lastCursorRow = 0;
    this.renderSecret();
    return new Promise((resolve) => {
      this.resolveSecret = resolve;
    });
  }

  /**
   * Present `items` as an arrow-key-navigable list (type to filter, like the
   * `/` command menu) and resolve the chosen index, or `null` on Esc/Ctrl+C.
   * Used for `/agents` and `/models` so picking one doesn't require typing
   * its number or name.
   */
  selectFromList(promptText: string, items: string[]): Promise<number | null> {
    this.listMode = true;
    this.listPrompt = promptText;
    this.listQuery = '';
    this.listAllItems = items;
    this.listFiltered = items.map((_, i) => i);
    this.listIndex = 0;
    this.lastCursorRow = 0;
    this.renderList();
    return new Promise((resolve) => {
      this.resolveList = resolve;
    });
  }

  private readLine(): Promise<string | null> {
    this.buffer = '';
    this.cursor = 0;
    this.historyIndex = this.history.length;
    this.menuVisible = false;
    this.searchMode = false;
    this.secretMode = false;
    this.listMode = false;
    this.lastCursorRow = 0;
    this.render();
    return new Promise((resolve) => {
      this.resolveLine = resolve;
    });
  }

  private onKeypress = (str: string | undefined, key: readline.Key): void => {
    if (this.closed) return;

    const isCtrlC = key.sequence === CTRL_C || (key.ctrl && key.name === 'c');
    if (isCtrlC) {
      if (this.secretMode) {
        this.finishSecret(null);
        return;
      }
      if (this.listMode) {
        this.finishList(null);
        return;
      }
      if (this.searchMode) {
        this.exitSearch();
        this.render();
        return;
      }
      this.onSigint();
      return;
    }

    if (this.secretMode) {
      this.handleSecretKey(str, key);
      return;
    }

    if (this.listMode) {
      this.handleListKey(str, key);
      return;
    }

    // Between finish() clearing resolveLine and the next readLine() call (e.g.
    // while a chat turn is streaming), there is no buffer to edit — only
    // cancellation (handled above) is meaningful here. Anything else would
    // corrupt the streamed output and be silently discarded on the next read.
    if (!this.resolveLine) {
      return;
    }

    if (this.searchMode) {
      this.handleSearchKey(str, key);
      return;
    }

    if (key.ctrl && key.name === 'r') {
      this.searchMode = true;
      this.searchQuery = '';
      this.searchMatch = undefined;
      this.searchScanIndex = this.history.length;
      this.render();
      return;
    }

    if (key.ctrl && key.name === 'd') {
      if (this.buffer.length === 0) {
        this.finish(null);
      }
      return;
    }

    switch (key.name) {
      case 'return':
        if (this.menuVisible && this.menuItems.length > 0) {
          this.selectMenuItemOnEnter();
          return;
        }
        this.submit();
        return;
      case 'backspace': {
        if (this.cursor > 0) {
          const segs = graphemes(this.buffer);
          const idx = segs.slice(0, this.cursor - 1).join('').length;
          const removed = segs[this.cursor - 1];
          this.buffer = this.buffer.slice(0, idx) + this.buffer.slice(idx + removed.length);
          this.cursor--;
        }
        break;
      }
      case 'delete': {
        const segs = graphemes(this.buffer);
        if (this.cursor < segs.length) {
          const idx = segs.slice(0, this.cursor).join('').length;
          const removed = segs[this.cursor];
          this.buffer = this.buffer.slice(0, idx) + this.buffer.slice(idx + removed.length);
        }
        break;
      }
      case 'left':
        if (this.cursor > 0) this.cursor--;
        break;
      case 'right':
        if (this.cursor < graphemes(this.buffer).length) this.cursor++;
        break;
      case 'up':
        if (this.menuVisible && this.menuItems.length > 0) {
          this.menuIndex = (this.menuIndex - 1 + this.menuItems.length) % this.menuItems.length;
        } else {
          this.historyUp();
        }
        break;
      case 'down':
        if (this.menuVisible && this.menuItems.length > 0) {
          this.menuIndex = (this.menuIndex + 1) % this.menuItems.length;
        } else {
          this.historyDown();
        }
        break;
      case 'tab':
        if (this.menuVisible && this.menuItems.length > 0) {
          this.acceptMenuSelection();
        } else {
          this.applyCompletion();
        }
        break;
      case 'escape':
        // Dismiss without calling updateMenu() below — the buffer is
        // unchanged by Esc, so it would still match `/...` and immediately
        // reopen the menu it was just told to close.
        this.menuVisible = false;
        this.render();
        return;
      default:
        if (str && !key.ctrl && !key.meta && str >= ' ') {
          this.insertAt(this.cursorStringIndex(), str);
        }
    }

    this.updateMenu();
    this.render();
  };

  private historyUp(): void {
    if (this.historyIndex > 0) {
      this.historyIndex--;
      this.buffer = this.history[this.historyIndex];
      this.cursor = graphemes(this.buffer).length;
    }
  }

  private historyDown(): void {
    if (this.historyIndex < this.history.length - 1) {
      this.historyIndex++;
      this.buffer = this.history[this.historyIndex];
      this.cursor = graphemes(this.buffer).length;
    } else {
      this.historyIndex = this.history.length;
      this.buffer = '';
      this.cursor = 0;
    }
  }

  private updateMenu(): void {
    const match = /^\/(\S*)$/.exec(this.buffer);
    if (!match) {
      this.menuVisible = false;
      return;
    }
    const query = match[1].toLowerCase();
    const items = this.commands.filter((c) => c.name.slice(1).toLowerCase().startsWith(query));
    if (items.length === 0) {
      this.menuVisible = false;
      return;
    }
    this.menuItems = items;
    if (this.menuIndex >= items.length) {
      this.menuIndex = 0;
    }
    this.menuVisible = true;
  }

  private acceptMenuSelection(): void {
    const item = this.menuItems[this.menuIndex];
    if (!item) return;
    this.buffer = `${item.name} `;
    this.cursor = graphemes(this.buffer).length;
    this.menuVisible = false;
  }

  /**
   * Enter on a visible menu runs the highlighted command immediately —
   * whether or not it takes an optional argument (e.g. `/agents
   * <name|number>` with no argument opens its own interactive picker; there
   * is no dedicated "no-argument" case to special-case around). A command
   * that does take an argument can still be filled into the buffer without
   * running it via Tab, for typing that argument manually before Enter.
   */
  private selectMenuItemOnEnter(): void {
    const item = this.menuItems[this.menuIndex];
    if (!item) return;
    this.menuVisible = false;
    this.buffer = item.name;
    this.cursor = graphemes(this.buffer).length;
    this.submit();
  }

  private applyCompletion(): void {
    const idx = this.cursorStringIndex();
    const [hits, partial] = this.completer(this.buffer.slice(0, idx));
    if (hits.length === 1) {
      this.insertAt(idx, hits[0].slice(partial.length));
    } else if (hits.length > 1) {
      const common = commonPrefix(hits);
      if (common.length > partial.length) {
        this.insertAt(idx, common.slice(partial.length));
      }
    }
  }

  private handleSearchKey(str: string | undefined, key: readline.Key): void {
    if (key.name === 'return') {
      this.buffer = this.searchMatch ?? this.searchQuery;
      this.cursor = graphemes(this.buffer).length;
      this.exitSearch();
      this.submit();
      return;
    }
    if (key.name === 'escape' || (key.ctrl && key.name === 'g')) {
      this.exitSearch();
      this.render();
      return;
    }
    if (key.ctrl && key.name === 'r') {
      this.findSearchMatch(true);
      this.render();
      return;
    }
    if (key.name === 'backspace') {
      this.searchQuery = graphemes(this.searchQuery).slice(0, -1).join('');
      this.searchScanIndex = this.history.length;
      this.findSearchMatch(false);
      this.render();
      return;
    }
    if (str && !key.ctrl && !key.meta && str >= ' ') {
      this.searchQuery += str;
      this.searchScanIndex = this.history.length;
      this.findSearchMatch(false);
    }
    this.render();
  }

  private handleSecretKey(str: string | undefined, key: readline.Key): void {
    if (key.name === 'return') {
      this.finishSecret(this.secretBuffer);
      return;
    }
    if (key.name === 'backspace') {
      this.secretBuffer = graphemes(this.secretBuffer).slice(0, -1).join('');
      this.renderSecret();
      return;
    }
    if (key.name === 'escape') {
      this.finishSecret(null);
      return;
    }
    if (str && !key.ctrl && !key.meta && str >= ' ') {
      this.secretBuffer += str;
      this.renderSecret();
    }
  }

  private renderSecret(): void {
    if (this.lastCursorRow > 0) {
      readline.moveCursor(process.stdout, 0, -this.lastCursorRow);
    }
    readline.cursorTo(process.stdout, 0);
    readline.clearScreenDown(process.stdout);
    const masked = '*'.repeat(graphemes(this.secretBuffer).length);
    const text = this.secretPrompt + masked;
    process.stdout.write(text);
    const width = process.stdout.columns || 80;
    this.lastCursorRow = rowsFor(text, width) - 1;
  }

  private finishSecret(value: string | null): void {
    this.secretMode = false;
    if (this.lastCursorRow > 0) {
      readline.moveCursor(process.stdout, 0, -this.lastCursorRow);
    }
    readline.cursorTo(process.stdout, 0);
    readline.clearScreenDown(process.stdout);
    process.stdout.write('\n');
    this.lastCursorRow = 0;
    const resolve = this.resolveSecret;
    this.resolveSecret = null;
    this.secretBuffer = '';
    resolve?.(value);
  }

  private handleListKey(str: string | undefined, key: readline.Key): void {
    if (key.name === 'return') {
      const idx = this.listFiltered[this.listIndex];
      this.finishList(idx === undefined ? null : idx);
      return;
    }
    if (key.name === 'escape') {
      this.finishList(null);
      return;
    }
    if (key.name === 'up') {
      if (this.listFiltered.length > 0) {
        this.listIndex = (this.listIndex - 1 + this.listFiltered.length) % this.listFiltered.length;
      }
      this.renderList();
      return;
    }
    if (key.name === 'down') {
      if (this.listFiltered.length > 0) {
        this.listIndex = (this.listIndex + 1) % this.listFiltered.length;
      }
      this.renderList();
      return;
    }
    if (key.name === 'backspace') {
      this.listQuery = graphemes(this.listQuery).slice(0, -1).join('');
      this.updateListFilter();
      this.renderList();
      return;
    }
    if (str && !key.ctrl && !key.meta && str >= ' ') {
      this.listQuery += str;
      this.updateListFilter();
    }
    this.renderList();
  }

  private updateListFilter(): void {
    const query = this.listQuery.toLowerCase();
    this.listFiltered = this.listAllItems
      .map((label, i) => ({ label, i }))
      .filter(({ label }) => label.toLowerCase().includes(query))
      .map(({ i }) => i);
    if (this.listIndex >= this.listFiltered.length) {
      this.listIndex = 0;
    }
  }

  private renderList(): void {
    const width = process.stdout.columns || 80;
    if (this.lastCursorRow > 0) {
      readline.moveCursor(process.stdout, 0, -this.lastCursorRow);
    }
    readline.cursorTo(process.stdout, 0);
    readline.clearScreenDown(process.stdout);
    const color = ansiEnabled();

    const headerText = `${this.listPrompt}${this.listQuery}`;
    process.stdout.write(headerText);

    let listRows = 0;
    if (this.listFiltered.length === 0) {
      const text = `${color ? DIM : ''}  (no matches)${color ? RESET : ''}`;
      process.stdout.write(`\n${text}`);
      listRows += rowsFor(text, width);
    } else {
      for (const [pos, idx] of this.listFiltered.entries()) {
        const selected = pos === this.listIndex;
        const marker = selected ? '›' : ' ';
        const text = `${marker} ${this.listAllItems[idx]}`;
        const rendered = `${selected && color ? INVERT : ''}${text}${selected && color ? RESET : ''}`;
        process.stdout.write(`\n${rendered}`);
        listRows += rowsFor(rendered, width);
      }
    }

    // Same wrapped-row bookkeeping as the main render(): walk back up to the
    // header's first row, then back down to where the header text (which can
    // itself wrap) actually leaves the cursor.
    const headerRows = rowsFor(headerText, width);
    const rowsBelowFirst = headerRows - 1 + listRows;
    if (rowsBelowFirst > 0) {
      readline.moveCursor(process.stdout, 0, -rowsBelowFirst);
    }

    const cursorAbsolute = displayWidth(headerText);
    const cursorRow = Math.floor(cursorAbsolute / width);
    const cursorCol = cursorAbsolute % width;
    if (cursorRow > 0) {
      readline.moveCursor(process.stdout, 0, cursorRow);
    }
    readline.cursorTo(process.stdout, cursorCol);
    this.lastCursorRow = cursorRow;
  }

  private finishList(index: number | null): void {
    this.listMode = false;
    if (this.lastCursorRow > 0) {
      readline.moveCursor(process.stdout, 0, -this.lastCursorRow);
    }
    readline.cursorTo(process.stdout, 0);
    readline.clearScreenDown(process.stdout);
    this.lastCursorRow = 0;
    const resolve = this.resolveList;
    this.resolveList = null;
    resolve?.(index);
  }

  private findSearchMatch(next: boolean): void {
    if (!this.searchQuery) {
      this.searchMatch = undefined;
      return;
    }
    const start = next ? this.searchScanIndex - 1 : this.history.length - 1;
    for (let i = start; i >= 0; i--) {
      if (this.history[i].includes(this.searchQuery)) {
        this.searchMatch = this.history[i];
        this.searchScanIndex = i;
        return;
      }
    }
    this.searchMatch = undefined;
  }

  private exitSearch(): void {
    this.searchMode = false;
    this.searchQuery = '';
    this.searchMatch = undefined;
  }

  private submit(): void {
    const line = this.buffer;
    if (line.trim().length > 0) {
      this.history.push(line);
    }
    this.finish(line);
  }

  private finish(line: string | null): void {
    this.menuVisible = false;
    if (this.lastCursorRow > 0) {
      readline.moveCursor(process.stdout, 0, -this.lastCursorRow);
    }
    readline.cursorTo(process.stdout, 0);
    readline.clearScreenDown(process.stdout);
    process.stdout.write(line !== null ? `${this.prompt}${line}\n` : '\n');
    this.lastCursorRow = 0;
    const resolve = this.resolveLine;
    this.resolveLine = null;
    if (line === null) {
      this.close();
    }
    resolve?.(line);
  }

  /** Force the in-flight read to end as EOF, e.g. on an idle Ctrl+C. */
  requestExit(): void {
    if (this.searchMode) {
      this.exitSearch();
    }
    this.finish(null);
  }

  private render(): void {
    const width = process.stdout.columns || 80;

    // The previous render left the cursor `lastCursorRow` rows below the
    // input's first row (input can wrap past one terminal row). Walk back up
    // to that first row before clearing, or a long line's earlier rows are
    // left stale on screen.
    if (this.lastCursorRow > 0) {
      readline.moveCursor(process.stdout, 0, -this.lastCursorRow);
    }
    readline.cursorTo(process.stdout, 0);
    readline.clearScreenDown(process.stdout);
    const color = ansiEnabled();

    if (this.searchMode) {
      const label = `(reverse-i-search)\`${this.searchQuery}': `;
      const text = label + (this.searchMatch ?? '');
      process.stdout.write(text);
      this.lastCursorRow = rowsFor(text, width) - 1;
      return;
    }

    const inputText = this.prompt + this.buffer;
    process.stdout.write(inputText);

    // Rows each rendered menu entry wraps into (a long description, or wide
    // characters, can push a single entry past one row) — summed, not one
    // row per item, or a narrow terminal misplaces the redraw origin.
    let menuRows = 0;
    if (this.menuVisible) {
      for (const [i, item] of this.menuItems.entries()) {
        const selected = i === this.menuIndex;
        const marker = selected ? '›' : ' ';
        const usage = item.usage ? ` ${item.usage}` : '';
        const text = `${marker} ${item.name}${usage} ${color ? DIM : ''}— ${item.description}${color ? RESET : ''}`;
        const rendered = `${selected && color ? INVERT : ''}${text}${selected && color ? RESET : ''}`;
        process.stdout.write(`\n${rendered}`);
        menuRows += rowsFor(rendered, width);
      }
    }

    // Rows the input line itself wraps into, plus the menu rows below it —
    // together, how far below the input's first row the cursor now sits.
    const inputRows = rowsFor(inputText, width);
    const rowsBelowFirst = inputRows - 1 + menuRows;
    if (rowsBelowFirst > 0) {
      readline.moveCursor(process.stdout, 0, -rowsBelowFirst);
    }

    const cursorAbsolute = displayWidth(this.prompt) + displayWidth(this.buffer.slice(0, this.cursorStringIndex()));
    const cursorRow = Math.floor(cursorAbsolute / width);
    const cursorCol = cursorAbsolute % width;
    if (cursorRow > 0) {
      readline.moveCursor(process.stdout, 0, cursorRow);
    }
    readline.cursorTo(process.stdout, cursorCol);
    this.lastCursorRow = cursorRow;
  }
}
