import { debugLog } from './debug';

declare global {
  interface Window {
    webkitAudioContext?: typeof AudioContext;
  }
}

/**
 * iMessage-inspired sound effects using the Web Audio API.
 * Each effect is a short sequence of tones rather than a single beep,
 * giving a richer, more polished feel similar to iOS message sounds.
 */

// Reuse a single AudioContext to stay within browser limits
let sharedContext: AudioContext | null = null;

function getAudioContext(): AudioContext | null {
  if (typeof window === 'undefined') return null;

  const AudioCtx = window.AudioContext ?? window.webkitAudioContext;
  if (!AudioCtx) {
    debugLog('[SoundEffects] AudioContext not supported in this browser');
    return null;
  }

  if (!sharedContext || sharedContext.state === 'closed') {
    sharedContext = new AudioCtx();
  }

  if (sharedContext.state === 'suspended') {
    sharedContext.resume();
  }

  return sharedContext;
}

interface ToneStep {
  /** Frequency in Hz */
  frequency: number;
  /** Offset from playback start (seconds) */
  startTime: number;
  /** How long the tone rings (seconds) */
  duration: number;
  /** Peak gain 0-1 */
  gain: number;
  type: OscillatorType;
}

function playToneSequence(steps: ToneStep[]): void {
  const ctx = getAudioContext();
  if (!ctx) return;

  const now = ctx.currentTime;

  for (const step of steps) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.frequency.value = step.frequency;
    osc.type = step.type;

    const start = now + step.startTime;
    const end = start + step.duration;

    // Quick attack, smooth exponential decay
    gain.gain.setValueAtTime(0.001, start);
    gain.gain.linearRampToValueAtTime(step.gain, start + 0.008);
    gain.gain.exponentialRampToValueAtTime(0.001, end);

    osc.start(start);
    osc.stop(end + 0.01);
  }
}

// ---------------------------------------------------------------------------
// Sound definitions
// ---------------------------------------------------------------------------

export type SoundEffectType = 'messageSent' | 'messageReceived' | 'success' | 'error' | 'notification';

const soundSequences: Record<SoundEffectType, ToneStep[]> = {
  // Send: quick two-note ascending "bloop" (C6 → F6)
  messageSent: [
    { frequency: 1046, startTime: 0,    duration: 0.08, gain: 0.15, type: 'sine' },
    { frequency: 1397, startTime: 0.07, duration: 0.11, gain: 0.18, type: 'sine' },
  ],

  // Receive: iMessage-style ascending tri-tone chime (B5 → E6 → G6)
  messageReceived: [
    { frequency: 988,  startTime: 0,    duration: 0.12, gain: 0.16, type: 'sine' },
    { frequency: 1319, startTime: 0.13, duration: 0.12, gain: 0.18, type: 'sine' },
    { frequency: 1568, startTime: 0.26, duration: 0.18, gain: 0.14, type: 'sine' },
  ],

  // Success: bright rising confirmation (G5 → D6)
  success: [
    { frequency: 784,  startTime: 0,    duration: 0.10, gain: 0.14, type: 'sine' },
    { frequency: 1175, startTime: 0.11, duration: 0.18, gain: 0.18, type: 'sine' },
  ],

  // Error: gentle descending double-tone (E4 → C4)
  error: [
    { frequency: 330, startTime: 0,    duration: 0.15, gain: 0.16, type: 'sine' },
    { frequency: 262, startTime: 0.18, duration: 0.22, gain: 0.13, type: 'sine' },
  ],

  // Notification: soft attention chime (A5 → C#6)
  notification: [
    { frequency: 880,  startTime: 0,    duration: 0.10, gain: 0.14, type: 'sine' },
    { frequency: 1109, startTime: 0.12, duration: 0.16, gain: 0.17, type: 'sine' },
  ],
};

/**
 * Play a sound effect if sound is enabled.
 * @param type - The type of sound effect to play
 * @param soundEnabled - Whether sound effects are enabled (from settings)
 */
export function playSoundEffect(type: SoundEffectType, soundEnabled: boolean): void {
  if (!soundEnabled) return;

  const steps = soundSequences[type];
  if (!steps) {
    debugLog(`[SoundEffects] Unknown sound effect type: ${type}`);
    return;
  }

  try {
    playToneSequence(steps);
    debugLog(`[SoundEffects] Playing ${type} sound effect`);
  } catch (error) {
    debugLog(`[SoundEffects] Failed to play ${type} sound effect:`, error);
  }
}

/**
 * Hook-style accessor (kept for API compatibility).
 */
export function useSoundEffects() {
  return {
    playSoundEffect: (type: SoundEffectType, soundEnabled: boolean) => {
      playSoundEffect(type, soundEnabled);
    }
  };
}
