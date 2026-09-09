export interface ParsedArgs {
  url?: string;
  key?: string;
  health: boolean;
  positional: string[];
}

export class ArgsError extends Error {}

const FLAGS = new Set(['--url', '--key', '--health']);

function isFlagLike(value: string | undefined): boolean {
  return value === undefined || FLAGS.has(value);
}

/**
 * Minimal, dependency-free argv parser for Phase 0's surface:
 *   --url <url> | --key <key> | --health
 * Anything else is collected as positional args for later phases
 * (e.g. `orbit-chat "question"` in Phase 1).
 *
 * A value-taking flag with no value, or one immediately followed by another
 * flag, is rejected rather than silently swallowing the next flag as its
 * value (e.g. `--url --health` must not disable --health).
 */
export function parseArgs(argv: string[]): ParsedArgs {
  const result: ParsedArgs = { health: false, positional: [] };

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    switch (arg) {
      case '--url': {
        const value = argv[i + 1];
        if (isFlagLike(value)) {
          throw new ArgsError(`--url requires a value`);
        }
        result.url = value;
        i++;
        break;
      }
      case '--key': {
        const value = argv[i + 1];
        if (isFlagLike(value)) {
          throw new ArgsError(`--key requires a value`);
        }
        result.key = value;
        i++;
        break;
      }
      case '--health':
        result.health = true;
        break;
      default:
        result.positional.push(arg);
    }
  }

  return result;
}
