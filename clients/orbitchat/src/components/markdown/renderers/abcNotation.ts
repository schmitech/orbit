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
  const voiceClefs = new Map<string, string>();
  let inTune = false;
  let hasKeySignature = false;
  let defaultClef = 'treble';

  // Parentheses in %%score/%%staves put multiple voices on one staff. A
  // generated piano score sometimes groups its treble and bass voices that
  // way, so the bass is audible but visually overlaid on the treble staff.
  // Collect the declared clefs first; directives commonly appear before the
  // V: declarations they reference.
  for (const sourceLine of lines) {
    const trimmed = sourceLine.trim();
    const keyMatch = trimmed.match(/^K\s*:.*\bclef\s*=\s*(treble|bass)\b/i);
    if (keyMatch) defaultClef = keyMatch[1].toLowerCase();

    const voiceMatch = trimmed.match(/^V\s*:\s*(\S+)(.*)$/i);
    if (!voiceMatch) continue;

    const clefMatch = voiceMatch[2].match(/\bclef\s*=\s*(treble|bass)\b/i);
    voiceClefs.set(voiceMatch[1], clefMatch?.[1].toLowerCase() ?? defaultClef);
  }

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

  const withCorrectStaffGrouping = normalized.map(line => {
    if (!/^\s*%%(?:score|staves)\b/i.test(line)) return line;

    return line.replace(/\(([^()]+)\)/g, (group, contents: string) => {
      const voiceIds = contents.trim().split(/\s+/);
      if (voiceIds.length < 2 || voiceIds.some(id => !voiceClefs.has(id))) {
        return group;
      }

      const groupedClefs = new Set(voiceIds.map(id => voiceClefs.get(id)));
      if (groupedClefs.size < 2) return group;

      return voiceIds.map(id => `( ${id} )`).join(' ');
    });
  });

  return withCorrectStaffGrouping.join('\n');
};
