import { randomUUID } from 'node:crypto';
import * as fs from 'node:fs';
import type { ApiClient } from '@schmitech/chatbot-api';
import { findAgent, listAgents, type AgentChoice } from './agents.js';
import { extractAttachments, AttachmentError } from './attachments.js';
import { saveArtifacts } from './artifacts.js';
import { createClient, streamChat } from './client.js';
import type { Connection } from './connection.js';
import { classifyError } from './errors.js';
import { LineReader, type CommandSpec } from './input.js';
import { findModel, listModels } from './models.js';
import { MarkdownRenderer } from './markdown.js';
import { Spinner } from './spinner.js';

/** Single source of truth for both `/help` text and the interactive `/` menu, so the two can't drift. */
const COMMANDS: CommandSpec[] = [
  { name: '/new', usage: '', description: 'start a new session (clears server-side context)' },
  { name: '/agents', usage: '<name|number>', description: 'pick an agent (arrow keys), or /agents <name|number>' },
  { name: '/models', usage: '', description: 'pick a model for the current agent (arrow keys)' },
  { name: '/model', usage: '<id|number>', description: 'set the model for later turns' },
  { name: '/key', usage: '', description: 'switch API key without restarting (masked prompt)' },
  { name: '/clear', usage: '', description: 'clear the screen and this session\'s server-side history' },
  { name: '/help', usage: '', description: 'show this message' },
  { name: '/exit', usage: '', description: 'exit' },
];

const HELP = `Commands:
${COMMANDS.map((c) => `  ${(c.name + ' ' + c.usage).padEnd(21)}${c.description}`).join('\n')}
  Ctrl+C               cancel the in-flight turn; again (while idle) to exit
  Ctrl+R               reverse search through this session's input history
  Ctrl+D               exit
@path/to/file inline in a message attaches that file to the turn.
Type / to see a filtered command menu (arrow keys + Tab/Enter to pick).
Anything else is sent as a chat turn.`;

/** Completes an `@path` token against the filesystem as the user types it. */
function completer(line: string): [string[], string] {
  const match = /(?:^|\s)@(\S*)$/.exec(line);
  if (!match) {
    return [[], line];
  }

  const partial = match[1];
  const slash = partial.lastIndexOf('/');
  const dir = slash === -1 ? '.' : partial.slice(0, slash) || '/';
  const prefix = slash === -1 ? partial : partial.slice(slash + 1);
  const dirPrefix = slash === -1 ? '' : `${partial.slice(0, slash)}/`;

  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return [[], partial];
  }

  const hits = entries
    .filter((entry) => entry.name.startsWith(prefix))
    .map((entry) => `${dirPrefix}${entry.name}${entry.isDirectory() ? '/' : ''}`);

  return [hits, partial];
}

const CLEAR_HISTORY_TIMEOUT_MS = 1500;

/**
 * Delete a session's server-side history without letting a stalled or
 * unreachable network hang the caller — the SDK call has no abort signal, so
 * this races it against a short timer instead of awaiting it directly. Used
 * by `/new`, `/clear`, and exit-time cleanup, so all three share one bound
 * rather than each risking drifting out of sync (or a hang) independently.
 *
 * `timedOut` tells the caller the request is being abandoned, not confirmed
 * done — e.g. exit-time cleanup uses that to decide whether it still needs
 * to force the process closed.
 */
async function clearHistoryBestEffort(
  client: ApiClient,
  sessionId: string
): Promise<{ timedOut: boolean; error?: string }> {
  let timedOut = false;
  let error: string | undefined;
  await new Promise<void>((resolve) => {
    const timer = setTimeout(() => {
      timedOut = true;
      resolve();
    }, CLEAR_HISTORY_TIMEOUT_MS);
    client
      .clearConversationHistory(sessionId)
      .catch((err) => {
        error = classifyError(err).message;
      })
      .then(() => {
        clearTimeout(timer);
        resolve();
      });
  });
  return { timedOut, error };
}

/**
 * Interactive REPL: a prompt line plus streaming transcript. Input is a
 * hand-rolled raw-mode line editor (`input.ts`) rather than plain
 * `node:readline` — needed to render the `/` command menu and Ctrl+R
 * reverse-search overlay, neither of which readline's completer hook
 * supports. `input.ts` still exposes an async iterator, so the turn-handling
 * logic below is unchanged from the readline-based version.
 */
export async function runRepl(
  initialClient: ApiClient,
  connection: Connection,
  initialSkill: string | undefined,
  initialModel: string | undefined
): Promise<number> {
  let client = initialClient;
  let ownAdapter;
  try {
    ownAdapter = await client.getAdapterInfo();
  } catch (error) {
    const { code, message } = classifyError(error);
    process.stderr.write(`${message}\n`);
    return code;
  }

  let agents = await listAgents(client, ownAdapter);
  let currentAgent: AgentChoice = agents[0];
  if (initialSkill) {
    const found = findAgent(agents, initialSkill);
    if (found) {
      currentAgent = found;
    } else {
      process.stderr.write(`Unknown agent "${initialSkill}"; using the default adapter.\n`);
    }
  }

  let currentModel = initialModel;
  let lastModels: Awaited<ReturnType<typeof listModels>> = [];

  let controller: AbortController | null = null;
  let currentRequestId: string | undefined;

  // Set whenever any clearHistoryBestEffort call times out (from /new,
  // /clear, or exit itself): that call's underlying fetch has no abort
  // signal, so it keeps running — and its open socket can keep the process
  // alive — well past the point our own await gave up on it. A /new whose
  // background cleanup already timed out earlier must not let a later,
  // unrelated fast exit-time cleanup return normally and leave that
  // dangling fetch as the reason the process never actually exits.
  let hasAbandonedCleanup = false;
  // A /new-triggered cleanup that hasn't settled yet (hasn't even hit its
  // own timeout) at the moment of exit is a second, distinct race:
  // `hasAbandonedCleanup` alone wouldn't catch it, since nothing has timed
  // out *yet* — it might resolve fine a moment later, or it might not. Exit
  // must not gamble on which; tracking it here means exit can force-close
  // rather than leave that outcome to chance.
  const pendingBackgroundCleanups = new Set<Promise<unknown>>();

  const rl = new LineReader({
    prompt: '> ',
    commands: COMMANDS,
    completer,
    onSigint: () => {
      if (controller) {
        controller.abort();
        const sessionId = client.getSessionId();
        if (sessionId && currentRequestId) {
          client.stopChat(sessionId, currentRequestId).catch(() => {});
        }
        process.stdout.write('\n[cancelled]\n');
        // The turn's catch block restores the prompt once the abort unwinds.
      } else {
        rl.requestExit();
      }
    },
  });

  process.stdout.write('Connected. Type /help for commands, Ctrl+D to exit.\n');

  for await (const line of rl) {
    const text = line.trim();

    if (!text) {
      continue;
    }

    if (text.startsWith('/')) {
      const [command, ...rest] = text.split(/\s+/);
      const arg = rest.join(' ');
      switch (command) {
        case '/new': {
          const oldSessionId = client.getSessionId();
          client.setSessionId(randomUUID());
          process.stdout.write('Started a new session.\n');
          // Fire-and-forget: /new's whole point is switching immediately, so
          // it must not block the next prompt on a network round trip (an
          // unreachable server would otherwise freeze the REPL for the full
          // clearHistoryBestEffort timeout). Otherwise the abandoned
          // session's history sits in the database with nothing left
          // pointing at it — the same orphan this command's own description
          // promises not to leave behind — so still report it if cleanup
          // doesn't land, just asynchronously once it settles.
          if (oldSessionId) {
            const cleanup = clearHistoryBestEffort(client, oldSessionId)
              .then(({ timedOut, error }) => {
                if (timedOut) {
                  hasAbandonedCleanup = true;
                }
                if (timedOut || error) {
                  process.stderr.write(`Previous session's history was not cleared: ${error ?? 'timed out'}\n`);
                }
              })
              .catch(() => {});
            pendingBackgroundCleanups.add(cleanup);
            cleanup.finally(() => pendingBackgroundCleanups.delete(cleanup));
          }
          break;
        }

        case '/agents':
          if (!arg) {
            const idx = await rl.selectFromList(
              'Select agent (type to filter, Esc to cancel): ',
              agents.map((a) => `${a.label}${a === currentAgent ? '  (current)' : ''}`)
            );
            if (idx !== null) {
              currentAgent = agents[idx];
              currentModel = undefined;
              lastModels = [];
              process.stdout.write(`Switched to ${currentAgent.label}.\n`);
            }
          } else {
            const found = findAgent(agents, arg);
            if (!found) {
              process.stdout.write(`No agent matches "${arg}". Try /agents to list them.\n`);
            } else {
              currentAgent = found;
              currentModel = undefined;
              lastModels = [];
              process.stdout.write(`Switched to ${found.label}.\n`);
            }
          }
          break;

        case '/models':
          try {
            lastModels = await listModels(client, currentAgent.adapterName, currentAgent.skill);
            if (lastModels.length === 0) {
              process.stdout.write('This agent has no restricted model list (uses its configured default).\n');
            } else {
              const idx = await rl.selectFromList(
                'Select model (type to filter, Esc to cancel): ',
                lastModels.map((m) => {
                  const id = m.name ?? m.id;
                  return `${id}${id === currentModel ? '  (current)' : ''}`;
                })
              );
              if (idx !== null) {
                const picked = lastModels[idx];
                currentModel = picked.name ?? picked.id;
                process.stdout.write(`Model set to ${currentModel}.\n`);
              }
            }
          } catch (error) {
            const { message } = classifyError(error);
            process.stderr.write(`${message}\n`);
          }
          break;

        case '/model':
          if (!arg) {
            process.stdout.write(`Current model: ${currentModel ?? '(adapter default)'}\n`);
          } else {
            const found = findModel(lastModels, arg);
            currentModel = found ? found.name ?? found.id : arg;
            process.stdout.write(`Model set to ${currentModel}.\n`);
          }
          break;

        case '/key': {
          if (arg) {
            // The full "/key <arg>" line is already in scrollback and
            // history by the time this runs (LineReader.finish() prints and
            // records it before dispatch) — accepting the key here would
            // just launder an already-leaked secret. Bare `/key` instead
            // routes through the masked prompt below, which never echoes or
            // records what's typed.
            process.stdout.write(
              'For your key\'s safety, run /key with no argument — it will prompt you separately with input hidden.\n'
            );
            break;
          }
          const newKey = await rl.readSecret('API key: ');
          if (newKey === null) {
            process.stdout.write('Cancelled.\n');
            break;
          }
          if (!newKey.trim()) {
            process.stderr.write('API key cannot be empty.\n');
            break;
          }
          const candidate = createClient(
            { url: connection.url, apiKey: newKey.trim() },
            client.getSessionId() ?? undefined
          );
          let newAdapter;
          try {
            newAdapter = await candidate.getAdapterInfo();
          } catch (error) {
            const { message } = classifyError(error);
            process.stderr.write(`Could not switch key: ${message}\n`);
            break;
          }
          // A different key can map to a different adapter with its own
          // skills/models, so re-discover agents and drop the old
          // model/skill selection rather than carrying it over silently.
          client = candidate;
          ownAdapter = newAdapter;
          agents = await listAgents(client, ownAdapter);
          currentAgent = agents[0];
          currentModel = undefined;
          lastModels = [];
          process.stdout.write(`Switched API key. Now using ${currentAgent.label}.\n`);
          break;
        }

        case '/clear': {
          // Best-effort: also delete the server-side conversation history for
          // this session (DELETE /admin/chat-history/{id}, ownership-checked
          // by API key server-side) so "clear" matches what it looks like —
          // a fresh conversation, not just a repainted terminal. A server
          // without a conversational adapter configured 503s here; that's
          // not a reason to skip the terminal clear itself. Bounded the same
          // way as /new and exit-time cleanup, so a stalled network can't
          // hang this command either.
          const sessionId = client.getSessionId();
          let historyError: string | undefined;
          if (sessionId) {
            const result = await clearHistoryBestEffort(client, sessionId);
            if (result.timedOut) {
              hasAbandonedCleanup = true;
            }
            historyError = result.timedOut ? 'timed out' : result.error;
          }
          // Home + erase screen + erase saved lines (the same sequence the
          // `clear` utility emits). Erasing only the visible screen (the
          // previous `cursorTo`/`clearScreenDown` pair) left the prior
          // conversation sitting in the terminal's scrollback just above the
          // now-blank viewport — visually it looked like the app had
          // "scrolled away," reachable only via the scrollbar. Clearing
          // scrollback too means there's nothing left to scroll up to.
          process.stdout.write('\x1b[H\x1b[2J\x1b[3J');
          if (historyError) {
            process.stderr.write(`Terminal cleared, but server-side history was not: ${historyError}\n`);
          }
          break;
        }

        case '/help':
          process.stdout.write(`${HELP}\n`);
          break;

        case '/exit':
          rl.requestExit();
          continue;

        default:
          process.stdout.write(`Unknown command: ${command} (try /help)\n`);
      }
      continue;
    }

    let message: string;
    let fileIds: string[];
    try {
      ({ text: message, fileIds } = await extractAttachments(client, text));
    } catch (error) {
      if (error instanceof AttachmentError) {
        process.stderr.write(`${error.message}\n`);
      } else {
        const { message: msg } = classifyError(error);
        process.stderr.write(`${msg}\n`);
      }
      continue;
    }

    controller = new AbortController();
    currentRequestId = undefined;
    const renderer = new MarkdownRenderer();
    const spinner = new Spinner();
    spinner.start();

    try {
      for await (const chunk of streamChat(client, message, {
        skill: currentAgent.skill,
        model: currentModel,
        fileIds,
        abortSignal: controller.signal,
      })) {
        if (chunk.request_id) {
          currentRequestId = chunk.request_id;
        }
        if (chunk.text) {
          spinner.stop();
          renderer.push(chunk.text);
        }
        const artifactPaths = await saveArtifacts(client, chunk);
        if (artifactPaths.length > 0) {
          spinner.stop();
          // The buffered trailing partial line (typically the final chunk's
          // text, with no newline yet) must land before the notice, or it
          // reads as if the artifact arrived before the reply that mentions it.
          renderer.flush();
          for (const path of artifactPaths) {
            process.stdout.write(`Saved artifact: ${path}\n`);
          }
        }
      }
      spinner.stop();
      renderer.flush();
      process.stdout.write('\n');
    } catch (error) {
      spinner.stop();
      renderer.flush();
      if (!controller.signal.aborted) {
        const { message: msg } = classifyError(error);
        process.stderr.write(`${msg}\n`);
      }
    } finally {
      spinner.stop();
      controller = null;
      currentRequestId = undefined;
    }
  }

  process.stdout.write('\n');

  // The loop above ends on every exit path (/exit, Ctrl+D, idle Ctrl+C), so
  // this one spot covers all of them. Best-effort: an unreachable server or
  // a deployment without a conversational adapter (503) shouldn't block or
  // spam an error on the way out — but leaving the row behind would orphan
  // this session's history in the database with nothing left to ever clear it.
  //
  // clearHistoryBestEffort bounds the SDK call, which has no abort signal of
  // its own, against a short timer instead of an OS-level TCP timeout. The
  // two outcomes are handled differently: if cleanup wins, its request is
  // done and there's nothing left dangling, so this falls through to the
  // normal `return 0` below — which matters when stdout/stderr are
  // redirected to a file or pipe, since only the normal return path lets
  // that output drain before the process exits. Only a timeout — this call's
  // own, or an earlier /new's fire-and-forget one that never got the chance
  // to force-exit itself (it isn't the one deciding whether the REPL is
  // exiting) — force-exits: at that point some request is being abandoned
  // outright, its fetch potentially still open, and there is no other way to
  // stop waiting on it.
  const sessionId = client.getSessionId();
  if (sessionId) {
    const { timedOut } = await clearHistoryBestEffort(client, sessionId);
    if (timedOut) {
      hasAbandonedCleanup = true;
    }
  }

  // A /new-triggered cleanup can still be mid-flight here, not yet past its
  // own timeout — indistinguishable at this instant from one that's about to
  // succeed. Exiting normally would gamble the process's shutdown on which;
  // its still-open fetch either way is reason enough to force-close rather
  // than wait and find out.
  if (hasAbandonedCleanup || pendingBackgroundCleanups.size > 0) {
    process.exit(0);
  }

  return 0;
}
