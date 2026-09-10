/** True when stdout is a real terminal and the user hasn't opted out via `NO_COLOR`. */
export function ansiEnabled(): boolean {
  return Boolean(process.stdout.isTTY) && !process.env.NO_COLOR;
}
