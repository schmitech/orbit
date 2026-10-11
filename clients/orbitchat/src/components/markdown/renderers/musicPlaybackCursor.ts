const HIGHLIGHT_CLASS = 'abcjs-note-highlight';

type CursorEvent = {
  elements?: Element[][];
  top?: number;
  height?: number;
};

export const clearHighlights = (scoreTarget: HTMLElement) => {
  scoreTarget.querySelectorAll(`.${HIGHLIGHT_CLASS}`).forEach(el => el.classList.remove(HIGHLIGHT_CLASS));
};

const lineOf = (el: Element) => el.className.toString().match(/abcjs-l\d+/)?.[0];

export const createCursorControl = (scoreTarget: HTMLElement) => {
  let previousSystemTop: number | undefined;
  // abcjs only reports elements for voices that start a new note on a given
  // event; a voice mid-way through a longer note is simply absent. Track the
  // last highlighted elements per voice so a slower hand's note stays lit
  // across events where only the other hand is reported.
  const highlightedByVoice = new Map<number, Element[]>();

  return {
    onEvent: (event: CursorEvent) => {
      const voices = event.elements ?? [];
      const elements = voices.flat();
      // A callback from a replaced score must not change the current score.
      if (elements.length && !elements.some(el => scoreTarget.contains(el))) return;

      voices.forEach((voiceElements, voiceIndex) => {
        if (voiceElements.length) highlightedByVoice.set(voiceIndex, voiceElements);
      });

      // A voice that hasn't started a new note since the system advanced is
      // still shown on the old line; drop it rather than leave a highlight
      // stranded on a system the cursor has already left.
      const currentLine = elements.map(lineOf).find(Boolean);
      if (currentLine) {
        highlightedByVoice.forEach((voiceElements, voiceIndex) => {
          if (lineOf(voiceElements[0]) !== currentLine) highlightedByVoice.delete(voiceIndex);
        });
      }

      clearHighlights(scoreTarget);
      [...highlightedByVoice.values()].flat()
        .filter(el => scoreTarget.contains(el))
        .forEach(el => el.classList.add(HIGHLIGHT_CLASS));

      // Timing events describe the whole system, including both piano staves.
      // Following an individual note makes the viewport bounce between hands.
      if (event.top === undefined || event.height === undefined || event.top === previousSystemTop) return;
      const viewport = scoreTarget.closest<HTMLElement>('.music-score-area');
      const svg = scoreTarget.querySelector('svg');
      const matrix = svg?.getScreenCTM();
      if (!viewport || !matrix) return;
      previousSystemTop = event.top;

      const top = new DOMPoint(0, event.top).matrixTransform(matrix).y;
      const bottom = new DOMPoint(0, event.top + event.height).matrixTransform(matrix).y;
      const viewportTop = viewport.getBoundingClientRect().top + viewport.clientTop;
      const margin = Math.min(24, Math.max(0, (viewport.clientHeight - (bottom - top)) / 2));
      if (top < viewportTop + margin || bottom > viewportTop + viewport.clientHeight - margin) {
        // Move immediately at system boundaries so fast playback never outruns
        // a queued smooth-scroll animation. Only the score viewport moves.
        viewport.scrollTo({ top: viewport.scrollTop + top - viewportTop - margin, behavior: 'instant' });
      }
    },
    onFinished: () => {
      clearHighlights(scoreTarget);
      highlightedByVoice.clear();
      previousSystemTop = undefined;
    },
  };
};
