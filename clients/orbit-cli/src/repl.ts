import { randomUUID } from 'node:crypto';
import * as readline from 'node:readline';
import type { ApiClient } from '@schmitech/chatbot-api';
import { streamChat } from './client.js';
import { classifyError } from './errors.js';

const HELP = `Commands:
  /new           start a new session (clears server-side context)
  /clear         clear the screen
  /help          show this message
  /exit          exit
  Ctrl+C         cancel the in-flight turn; again (while idle) to exit
  Ctrl+D         exit
Anything else is sent as a chat turn.
(/agents and /models land in Phase 3.)`;

/**
 * Interactive REPL: a prompt line plus streaming transcript, built on plain
 * node:readline rather than a TUI framework — Phase 2's own note says a
 * half-day Ink spike is needed before committing to it, and the CLI's
 * "less complicated than OrbitChat" brief doesn't need scrollback or resize
 * handling. readline's built-in terminal history already gives up/down
 * without extra code, and swapping in Ink later is a Phase 3+ decision,
 * not one this phase has to force.
 */
export async function runRepl(
  client: ApiClient,
  initialSkill: string | undefined,
  initialModel: string | undefined
): Promise<number> {
  let skill = initialSkill;
  let model = initialModel;

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: true,
    prompt: '> ',
  });

  let controller: AbortController | null = null;
  let currentRequestId: string | undefined;

  rl.on('SIGINT', () => {
    if (controller) {
      controller.abort();
      const sessionId = client.getSessionId();
      if (sessionId && currentRequestId) {
        client.stopChat(sessionId, currentRequestId).catch(() => {});
      }
      process.stdout.write('\n[cancelled]\n');
      // The turn's catch block restores the prompt once the abort unwinds.
    } else {
      process.stdout.write('\n');
      rl.close();
    }
  });

  process.stdout.write(`Connected. Type /help for commands, Ctrl+D to exit.\n`);
  rl.prompt();

  for await (const line of rl) {
    const text = line.trim();

    if (!text) {
      rl.prompt();
      continue;
    }

    if (text.startsWith('/')) {
      const [command] = text.split(/\s+/);
      switch (command) {
        case '/new':
          client.setSessionId(randomUUID());
          process.stdout.write('Started a new session.\n');
          break;
        case '/clear':
          readline.cursorTo(process.stdout, 0, 0);
          readline.clearScreenDown(process.stdout);
          break;
        case '/help':
          process.stdout.write(`${HELP}\n`);
          break;
        case '/exit':
          rl.close();
          continue;
        case '/agents':
        case '/models':
        case '/model':
          process.stdout.write(`${command} lands in Phase 3.\n`);
          break;
        default:
          process.stdout.write(`Unknown command: ${command} (try /help)\n`);
      }
      rl.prompt();
      continue;
    }

    controller = new AbortController();
    currentRequestId = undefined;

    try {
      for await (const chunk of streamChat(client, text, {
        skill,
        model,
        abortSignal: controller.signal,
      })) {
        if (chunk.request_id) {
          currentRequestId = chunk.request_id;
        }
        if (chunk.text) {
          process.stdout.write(chunk.text);
        }
      }
      process.stdout.write('\n');
    } catch (error) {
      if (!controller.signal.aborted) {
        const { message } = classifyError(error);
        process.stderr.write(`${message}\n`);
      }
    } finally {
      controller = null;
      currentRequestId = undefined;
    }

    rl.prompt();
  }

  process.stdout.write('\n');
  return 0;
}
