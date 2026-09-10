export interface ParsedArgs {
  url?: string;
  key?: string;
  health: boolean;
  version: boolean;
  agent?: string;
  model?: string;
  positional: string[];
}

export class ArgsError extends Error {}

const FLAGS = new Set(['--url', '--key', '--health', '--agent', '--model', '--version', '-v']);

function isFlagLike(value: string | undefined): boolean {
  return value === undefined || FLAGS.has(value);
}

/**
 * Minimal, dependency-free argv parser:
 *   --url <url> | --key <key> | --health | --agent <name> | --model <id>
 * Anything else is collected as positional args, e.g. the one-shot message
 * in `orbit-chat "question"` or `orbit-chat -` (read stdin).
 *
 * A value-taking flag with no value, or one immediately followed by another
 * flag, is rejected rather than silently swallowing the next flag as its
 * value (e.g. `--url --health` must not disable --health).
 */
export function parseArgs(argv: string[]): ParsedArgs {
  const result: ParsedArgs = { health: false, version: false, positional: [] };

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    switch (arg) {
      case '--version':
      case '-v':
        result.version = true;
        break;
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
      case '--agent': {
        const value = argv[i + 1];
        if (isFlagLike(value)) {
          throw new ArgsError(`--agent requires a value`);
        }
        result.agent = value;
        i++;
        break;
      }
      case '--model': {
        const value = argv[i + 1];
        if (isFlagLike(value)) {
          throw new ArgsError(`--model requires a value`);
        }
        result.model = value;
        i++;
        break;
      }
      default:
        result.positional.push(arg);
    }
  }

  return result;
}
