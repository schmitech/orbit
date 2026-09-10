import { ansiEnabled } from './tty.js';

const FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];
const INTERVAL_MS = 80;

/** A `\r`-overwritten spinner shown while waiting for the first stream chunk. No-op without a color-capable TTY. */
export class Spinner {
  private timer: ReturnType<typeof setInterval> | null = null;
  private frame = 0;

  start(): void {
    if (!ansiEnabled() || this.timer) {
      return;
    }
    this.timer = setInterval(() => {
      process.stdout.write(`\r${FRAMES[this.frame]} `);
      this.frame = (this.frame + 1) % FRAMES.length;
    }, INTERVAL_MS);
  }

  /** Stop and erase the spinner line so following output starts at column 0. */
  stop(): void {
    if (!this.timer) {
      return;
    }
    clearInterval(this.timer);
    this.timer = null;
    process.stdout.write('\r\x1b[K');
  }
}
