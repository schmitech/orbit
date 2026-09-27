/**
 * ABC uses a blank line as an end-of-tune marker. Generated notation often
 * includes a blank line merely to separate the headers/voice declarations
 * from the first bar (or to group later systems). In that case abcjs renders
 * only the title block and silently drops the music that follows.
 *
 * Once a tune has a key signature, remove blank lines inside it. A blank line
 * immediately before another X: header remains intact so genuine multi-tune
 * documents keep their tune boundary.
 */
export const normalizeAbcForRendering = (code: string): string => {
  const lines = code.split(/\r?\n/);
  const normalized: string[] = [];
  let inTune = false;
  let hasKeySignature = false;

  for (let index = 0; index < lines.length; index++) {
    const line = lines[index];
    const trimmed = line.trim();

    if (/^X\s*:/.test(trimmed)) {
      inTune = true;
      hasKeySignature = false;
    } else if (inTune && /^K\s*:/.test(trimmed)) {
      hasKeySignature = true;
    }

    if (trimmed === '' && inTune && hasKeySignature) {
      let nextLineIndex = index + 1;
      while (nextLineIndex < lines.length && lines[nextLineIndex].trim() === '') {
        nextLineIndex++;
      }

      const nextLine = lines[nextLineIndex]?.trim();
      if (nextLine && !/^X\s*:/.test(nextLine)) {
        continue;
      }
    }

    normalized.push(line);
  }

  return normalized.join('\n');
};
