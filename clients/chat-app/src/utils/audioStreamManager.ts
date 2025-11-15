/**
 * Real-time Audio Stream Manager
 *
 * Manages queuing and playback of audio chunks as they arrive,
 * enabling conversational voice responses similar to ChatGPT.
 */

import { debugLog, debugError } from './debug';

interface AudioChunk {
  audio: string;  // Base64 encoded
  audioFormat: string;
  chunkIndex: number;
}

class AudioStreamManager {
  private audioQueue: AudioChunk[] = [];
  private isPlaying: boolean = false;
  private currentAudio: HTMLAudioElement | null = null;
  private audioContext: AudioContext | null = null;
  private isEnabled: boolean = false;
  private onPlaybackStart: (() => void) | null = null;
  private onPlaybackEnd: (() => void) | null = null;
  private onChunkPlayed: ((chunkIndex: number) => void) | null = null;
  private blobUrls: string[] = [];

  constructor() {
    // Check if audio autoplay is likely to work
    this.checkAutoplaySupport();
  }

  private async checkAutoplaySupport(): Promise<void> {
    try {
      // Create a silent audio context to test autoplay
      if (typeof AudioContext !== 'undefined') {
        this.audioContext = new AudioContext();
        if (this.audioContext.state === 'suspended') {
          debugLog('[AudioStreamManager] AudioContext suspended - waiting for user interaction');
        } else {
          this.isEnabled = true;
          debugLog('[AudioStreamManager] AudioContext active - autoplay should work');
        }
      }
    } catch (err) {
      debugError('[AudioStreamManager] Failed to create AudioContext:', err);
    }
  }

  /**
   * Enable audio playback after user interaction (required by browsers)
   * Call this after a user gesture like clicking a button
   */
  public async enableAudio(): Promise<boolean> {
    try {
      if (this.audioContext && this.audioContext.state === 'suspended') {
        await this.audioContext.resume();
      }

      // Create a silent audio to unlock audio playback
      const silentAudio = new Audio('data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=');
      silentAudio.volume = 0;
      await silentAudio.play();
      silentAudio.pause();

      this.isEnabled = true;
      debugLog('[AudioStreamManager] Audio playback enabled');
      return true;
    } catch (err) {
      debugError('[AudioStreamManager] Failed to enable audio:', err);
      return false;
    }
  }

  /**
   * Check if audio is enabled and can autoplay
   */
  public isAudioEnabled(): boolean {
    return this.isEnabled;
  }

  /**
   * Set callback for when playback starts
   */
  public setOnPlaybackStart(callback: () => void): void {
    this.onPlaybackStart = callback;
  }

  /**
   * Set callback for when all playback ends
   */
  public setOnPlaybackEnd(callback: () => void): void {
    this.onPlaybackEnd = callback;
  }

  /**
   * Set callback for when a chunk finishes playing
   */
  public setOnChunkPlayed(callback: (chunkIndex: number) => void): void {
    this.onChunkPlayed = callback;
  }

  /**
   * Add an audio chunk to the queue and start playing if not already
   */
  public async addChunk(chunk: AudioChunk): Promise<void> {
    debugLog(`[AudioStreamManager] Adding chunk ${chunk.chunkIndex} to queue`);

    // Add to queue (maintain order)
    this.audioQueue.push(chunk);
    this.audioQueue.sort((a, b) => a.chunkIndex - b.chunkIndex);

    // Start playing if not already
    if (!this.isPlaying && this.isEnabled) {
      this.playNextChunk();
    }
  }

  /**
   * Play the next chunk in the queue
   */
  private async playNextChunk(): Promise<void> {
    if (this.audioQueue.length === 0) {
      this.isPlaying = false;
      debugLog('[AudioStreamManager] Queue empty, playback complete');
      if (this.onPlaybackEnd) {
        this.onPlaybackEnd();
      }
      return;
    }

    if (!this.isEnabled) {
      debugLog('[AudioStreamManager] Audio not enabled, skipping playback');
      return;
    }

    this.isPlaying = true;
    const chunk = this.audioQueue.shift()!;

    try {
      if (!this.isPlaying) {
        // Playback was stopped
        return;
      }

      if (this.onPlaybackStart && chunk.chunkIndex === 0) {
        this.onPlaybackStart();
      }

      debugLog(`[AudioStreamManager] Playing chunk ${chunk.chunkIndex}`);

      // Decode base64 to binary
      const binaryString = atob(chunk.audio);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      // Determine MIME type
      const mimeType = chunk.audioFormat === 'mp3' ? 'audio/mpeg' :
                      chunk.audioFormat === 'wav' ? 'audio/wav' :
                      chunk.audioFormat === 'ogg' ? 'audio/ogg' :
                      chunk.audioFormat === 'opus' ? 'audio/ogg; codecs=opus' :
                      chunk.audioFormat === 'webm' ? 'audio/webm' :
                      `audio/${chunk.audioFormat}`;

      // Create blob and audio element
      const audioBlob = new Blob([bytes], { type: mimeType });
      const audioUrl = URL.createObjectURL(audioBlob);
      this.blobUrls.push(audioUrl);

      const audio = new Audio(audioUrl);
      this.currentAudio = audio;

      // Play and wait for completion
      await new Promise<void>((resolve, reject) => {
        audio.addEventListener('ended', () => {
          debugLog(`[AudioStreamManager] Chunk ${chunk.chunkIndex} finished`);
          if (this.onChunkPlayed) {
            this.onChunkPlayed(chunk.chunkIndex);
          }
          resolve();
        }, { once: true });

        audio.addEventListener('error', (e) => {
          debugError(`[AudioStreamManager] Error playing chunk ${chunk.chunkIndex}:`, e);
          reject(e);
        }, { once: true });

        audio.play().catch(reject);
      });

      // Continue with next chunk
      this.playNextChunk();

    } catch (err) {
      debugError(`[AudioStreamManager] Failed to play chunk ${chunk.chunkIndex}:`, err);
      // Try to continue with next chunk even if one fails
      this.playNextChunk();
    }
  }

  /**
   * Stop playback and clear queue
   */
  public stop(): void {
    debugLog('[AudioStreamManager] Stopping playback');
    this.isPlaying = false;
    this.audioQueue = [];

    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio.src = '';
      this.currentAudio = null;
    }

    // Clean up blob URLs
    this.blobUrls.forEach(url => URL.revokeObjectURL(url));
    this.blobUrls = [];
  }

  /**
   * Reset the manager (for new conversation)
   */
  public reset(): void {
    this.stop();
    debugLog('[AudioStreamManager] Manager reset');
  }

  /**
   * Get current queue size
   */
  public getQueueSize(): number {
    return this.audioQueue.length;
  }

  /**
   * Check if currently playing
   */
  public isCurrentlyPlaying(): boolean {
    return this.isPlaying;
  }
}

// Singleton instance
export const audioStreamManager = new AudioStreamManager();
