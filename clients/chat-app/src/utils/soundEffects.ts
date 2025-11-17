import { debugLog } from './debug';

/**
 * Sound effects utility for playing notification sounds
 * Respects the user's soundEnabled setting from SettingsContext
 */

// Simple beep sound using Web Audio API
function playBeep(frequency: number = 800, duration: number = 100, type: 'sine' | 'square' | 'triangle' = 'sine'): void {
  try {
    // Check if AudioContext is available
    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
    if (!AudioContextClass) {
      debugLog('[SoundEffects] AudioContext not supported in this browser');
      return;
    }

    const audioContext = new AudioContextClass();
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();

    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);

    oscillator.frequency.value = frequency;
    oscillator.type = type;

    gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + duration / 1000);

    oscillator.start(audioContext.currentTime);
    oscillator.stop(audioContext.currentTime + duration / 1000);
  } catch (error) {
    debugLog('[SoundEffects] Failed to play beep:', error);
  }
}

// Sound effect types
export type SoundEffectType = 'messageSent' | 'messageReceived' | 'success' | 'error' | 'notification';

// Sound effect configurations
const soundEffects: Record<SoundEffectType, { frequency: number; duration: number; type: 'sine' | 'square' | 'triangle' }> = {
  messageSent: { frequency: 600, duration: 80, type: 'sine' },
  messageReceived: { frequency: 800, duration: 100, type: 'sine' },
  success: { frequency: 1000, duration: 150, type: 'sine' },
  error: { frequency: 400, duration: 200, type: 'square' },
  notification: { frequency: 700, duration: 120, type: 'sine' }
};

/**
 * Play a sound effect if sound is enabled
 * @param type - The type of sound effect to play
 * @param soundEnabled - Whether sound effects are enabled (from settings)
 */
export function playSoundEffect(type: SoundEffectType, soundEnabled: boolean): void {
  if (!soundEnabled) {
    return;
  }

  const config = soundEffects[type];
  if (!config) {
    debugLog(`[SoundEffects] Unknown sound effect type: ${type}`);
    return;
  }

  try {
    playBeep(config.frequency, config.duration, config.type);
    debugLog(`[SoundEffects] Playing ${type} sound effect`);
  } catch (error) {
    debugLog(`[SoundEffects] Failed to play ${type} sound effect:`, error);
  }
}

/**
 * Hook to get sound effects player that respects settings
 * This should be used in components that need to play sounds
 */
export function useSoundEffects() {
  // This will be used with useSettings hook in components
  return {
    playSoundEffect: (type: SoundEffectType, soundEnabled: boolean) => {
      playSoundEffect(type, soundEnabled);
    }
  };
}

