import { ArgsError, parseArgs } from './args.js';
import { ConfigError, resolveConnection } from './connection.js';
import { createClient } from './client.js';
import { classifyError } from './errors.js';
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

  const client = createClient(connection);

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

  // Phase 1+ (one-shot mode, REPL) land here.
  process.stderr.write('Connected. One-shot and interactive modes are not implemented yet (Phase 1+).\n');
  process.exit(EXIT_OK);
}

main().catch((error) => {
  process.stderr.write(`Unexpected error: ${error instanceof Error ? error.stack ?? error.message : String(error)}\n`);
  process.exit(1);
});
