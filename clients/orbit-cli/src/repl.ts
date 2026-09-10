import { randomUUID } from 'node:crypto';
import * as fs from 'node:fs';
import * as readline from 'node:readline';
import type { ApiClient } from '@schmitech/chatbot-api';
import { findAgent, listAgents, type AgentChoice } from './agents.js';
import { extractAttachments, AttachmentError } from './attachments.js';
import { saveArtifacts } from './artifacts.js';
import { streamChat } from './client.js';
import { classifyError } from './errors.js';
import { findModel, listModels } from './models.js';
import { MarkdownRenderer } from './markdown.js';

const HELP = `Commands:
  /new                 start a new session (clears server-side context)
  /agents              list agents; /agents <name|number> to select
  /models              list models for the current agent
  /model <id|number>   set the model for later turns
  /clear               clear the screen
  /help                show this message
  /exit                exit
  Ctrl+C               cancel the in-flight turn; again (while idle) to exit
  Ctrl+D               exit
@path/to/file inline in a message attaches that file to the turn.
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

/**
 * Interactive REPL: a prompt line plus streaming transcript, built on plain
 * node:readline rather than a TUI framework — Phase 2's own note said a
 * half-day Ink spike was needed before committing to it; that spike was
 * skipped rather than run, since a framework choice earns its keep once
 * rendering is complex enough to need it, and readline's terminal mode
 * already gives history navigation with up/down for free.
 */
export async function runRepl(
  client: ApiClient,
  initialSkill: string | undefined,
  initialModel: string | undefined
): Promise<number> {
  let ownAdapter;
  try {
    ownAdapter = await client.getAdapterInfo();
  } catch (error) {
    const { code, message } = classifyError(error);
    process.stderr.write(`${message}\n`);
    return code;
  }

  const agents = await listAgents(client, ownAdapter);
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

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: true,
    prompt: '> ',
    completer,
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

  process.stdout.write('Connected. Type /help for commands, Ctrl+D to exit.\n');
  rl.prompt();

  for await (const line of rl) {
    const text = line.trim();

    if (!text) {
      rl.prompt();
      continue;
    }

    if (text.startsWith('/')) {
      const [command, ...rest] = text.split(/\s+/);
      const arg = rest.join(' ');
      switch (command) {
        case '/new':
          client.setSessionId(randomUUID());
          process.stdout.write('Started a new session.\n');
          break;

        case '/agents':
          if (!arg) {
            process.stdout.write(
              agents
                .map((a, i) => `${i + 1}. ${a.label}${a === currentAgent ? '  (current)' : ''}`)
                .join('\n') + '\n'
            );
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
              process.stdout.write(
                lastModels
                  .map((m, i) => `${i + 1}. ${m.name ?? m.id}${(m.name ?? m.id) === currentModel ? '  (current)' : ''}`)
                  .join('\n') + '\n'
              );
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

        default:
          process.stdout.write(`Unknown command: ${command} (try /help)\n`);
      }
      rl.prompt();
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
      rl.prompt();
      continue;
    }

    controller = new AbortController();
    currentRequestId = undefined;
    const renderer = new MarkdownRenderer();

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
          renderer.push(chunk.text);
        }
        const artifactPaths = await saveArtifacts(client, chunk);
        if (artifactPaths.length > 0) {
          // The buffered trailing partial line (typically the final chunk's
          // text, with no newline yet) must land before the notice, or it
          // reads as if the artifact arrived before the reply that mentions it.
          renderer.flush();
          for (const path of artifactPaths) {
            process.stdout.write(`Saved artifact: ${path}\n`);
          }
        }
      }
      renderer.flush();
      process.stdout.write('\n');
    } catch (error) {
      renderer.flush();
      if (!controller.signal.aborted) {
        const { message: msg } = classifyError(error);
        process.stderr.write(`${msg}\n`);
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
