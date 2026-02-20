/**
 * Minimal TTS playback: play base64-encoded audio chunks or full audio.
 */
let audioEnabled = true;
const chunkQueue: { base64: string; format: string }[] = [];
let isPlaying = false;

export function setAudioEnabled(enabled: boolean): void {
  audioEnabled = enabled;
}

export function isAudioEnabled(): boolean {
  return audioEnabled;
}

function playNextInQueue(): void {
  if (!audioEnabled || chunkQueue.length === 0) {
    isPlaying = false;
    return;
  }
  const next = chunkQueue.shift()!;
  const audio = new Audio(`data:audio/${next.format};base64,${next.base64}`);
  audio.playbackRate = 1;
  audio.onended = () => playNextInQueue();
  audio.onerror = () => playNextInQueue();
  audio.play().catch(() => playNextInQueue());
  isPlaying = true;
}

export function playAudioChunk(base64: string, format: string = 'webm'): void {
  if (!audioEnabled) return;
  chunkQueue.push({ base64, format });
  if (!isPlaying) playNextInQueue();
}

export function playFullAudio(base64: string, format: string = 'mp3'): void {
  if (!audioEnabled) return;
  const audio = new Audio(`data:audio/${format};base64,${base64}`);
  audio.play().catch(() => {});
}

export function stopAudio(): void {
  chunkQueue.length = 0;
  isPlaying = false;
}
