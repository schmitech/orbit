import { randomUUID } from 'node:crypto';
import { ArgsError, parseArgs } from './args.js';
import { ConfigError, resolveConnection } from './connection.js';
import { createClient } from './client.js';
import { classifyError } from './errors.js';
import { runOneShot } from './one-shot.js';
import { runRepl } from './repl.js';
import { readStdin } from './stdin.js';
import { EXIT_OK, EXIT_USAGE } from './exit-codes.js';

async function main(): Promise<void> {
  let args;
  try {
    args = parseArgs(process.argv.slice(2));
  } catch (error) {
    if (error instanceof ArgsError) {
      process.stderr.write(`${error.message}\n`);
      process.exit(EXIT_USAGE);
    }
    throw error;
  }

  let connection;
  try {
    connection = await resolveConnection(args);
  } catch (error) {
    if (error instanceof ConfigError) {
      process.stderr.write(`${error.message}\n`);
      process.exit(EXIT_USAGE);
    }
    throw error;
  }

  // The server requires a non-empty session ID on every chat turn. One-shot
  // mode is a single, disposable turn, so a fresh UUID per run is enough —
  // there is no REPL state to carry it across turns yet (Phase 2).
  const client = createClient(connection, args.health ? undefined : randomUUID());

  if (args.health) {
    try {
      // getHealth() is unauthenticated, so it only proves the server is
      // reachable. Also call getAdapterInfo(), which is key-scoped and
      // rejects invalid/disabled keys — without it a bad key would still
      // report success.
      const [health, adapterInfo] = await Promise.all([
        client.getHealth(),
        client.getAdapterInfo(),
      ]);
      process.stdout.write(`${JSON.stringify({ ...health, adapter: adapterInfo })}\n`);
      process.exit(EXIT_OK);
    } catch (error) {
      const { code, message } = classifyError(error);
      process.stderr.write(`${message}\n`);
      process.exit(code);
    }
  }

  const rawMessage = args.positional[0];
  if (rawMessage === undefined) {
    if (!process.stdin.isTTY) {
      process.stderr.write(
        'No message provided and stdin is not a terminal. Pass a message, or "-" to read one from stdin.\n'
      );
      process.exit(EXIT_USAGE);
    }
    const code = await runRepl(client, args.agent, args.model);
    process.exitCode = code;
    return;
  }

  const message = rawMessage === '-' ? (await readStdin()).trim() : rawMessage;
  if (!message) {
    process.stderr.write('No message provided.\n');
    process.exit(EXIT_USAGE);
  }

  // A broken pipe (e.g. `orbit-chat "hi" | head -1`) should exit quietly,
  // not throw an unhandled EPIPE error.
  process.stdout.on('error', (error) => {
    if ((error as NodeJS.ErrnoException).code === 'EPIPE') {
      process.exit(EXIT_OK);
    }
  });

  const controller = new AbortController();
  process.once('SIGINT', () => controller.abort());

  const code = await runOneShot(client, message, {
    skill: args.agent,
    model: args.model,
    signal: controller.signal,
  });
  // Set exitCode and let the event loop drain naturally rather than calling
  // process.exit(), which can terminate the process before buffered
  // stdout.write calls finish — truncating the response when it is large or
  // stdout is a pipe.
  process.exitCode = code;
}

main().catch((error) => {
  process.stderr.write(`Unexpected error: ${error instanceof Error ? error.stack ?? error.message : String(error)}\n`);
  process.exit(1);
});
