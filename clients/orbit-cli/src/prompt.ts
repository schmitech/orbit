import * as readline from 'node:readline';

const ETX = '\x03'; // Ctrl+C
const DEL = '\x7f'; // Backspace (most terminals)
const BS = '\x08'; // Backspace (some terminals)

/** Prompt on stderr so stdout stays clean for piped/scripted output. */
export function ask(question: string): Promise<string> {
  const rl = readline.createInterface({ input: process.stdin, output: process.stderr });
  return new Promise((resolve) => {
    rl.question(question, (answer) => {
      rl.close();
      resolve(answer.trim());
    });
  });
}

/** Prompt for a secret without echoing it to the terminal. */
export function askSecret(question: string): Promise<string> {
  return new Promise((resolve) => {
    const stdin = process.stdin;
    process.stderr.write(question);

    const wasRaw = stdin.isTTY ? stdin.isRaw : false;
    if (stdin.isTTY) stdin.setRawMode(true);
    stdin.resume();
    stdin.setEncoding('utf8');

    let value = '';
    const cleanup = () => {
      stdin.removeListener('data', onData);
      if (stdin.isTTY) stdin.setRawMode(wasRaw);
      stdin.pause();
    };

    const onData = (chunk: string) => {
      for (const char of chunk) {
        if (char === '\n' || char === '\r') {
          cleanup();
          process.stderr.write('\n');
          resolve(value.trim());
          return;
        } else if (char === ETX) {
          cleanup();
          process.stderr.write('\n');
          process.exit(130);
        } else if (char === DEL || char === BS) {
          value = value.slice(0, -1);
        } else {
          value += char;
        }
      }
    };

    stdin.on('data', onData);
  });
}
