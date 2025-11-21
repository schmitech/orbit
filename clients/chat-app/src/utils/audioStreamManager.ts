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
  private suppressPlaybackErrors: boolean = false;

  /**
   * Enable audio playback after user interaction (required by browsers)
   * Call this after a user gesture like clicking a button
   * 
   * Note: AudioContext is created lazily when first audio chunk is played,
   * not here, to avoid browser warnings about autoplay policies.
   */
  public async enableAudio(): Promise<boolean> {
    try {
      // Don't create AudioContext here - create it lazily when we actually play audio
      // This prevents the browser warning about AudioContext not being in a user gesture
      
      // Create a silent audio to unlock audio playback
      // This helps with browser autoplay policies and must happen in user gesture context
      try {
        const silentAudio = new Audio('data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=');
        silentAudio.volume = 0;
        await silentAudio.play();
        silentAudio.pause();
      } catch (silentAudioError) {
        // Silent audio unlock might fail if not in user gesture context
        // This is okay - we'll still mark as enabled and try again later
        debugLog('[AudioStreamManager] Silent audio unlock deferred (will work on next interaction)');
      }

      this.isEnabled = true;
      debugLog('[AudioStreamManager] Audio playback enabled');
      return true;
    } catch (err) {
      debugError('[AudioStreamManager] Failed to enable audio:', err);
      return false;
    }
  }

  /**
   * Disable all audio playback and drop queued chunks
   */
  public disableAudio(): void {
    if (!this.isEnabled && !this.isPlaying) {
      return;
    }
    this.isEnabled = false;
    this.stop();
    debugLog('[AudioStreamManager] Audio playback disabled');
  }

  /**
   * Initialize AudioContext lazily when needed (during user gesture)
   * This is called from playNextChunk to ensure it's within a user gesture context
   */
  private async ensureAudioContext(): Promise<boolean> {
    if (!this.audioContext && typeof AudioContext !== 'undefined') {
      try {
        this.audioContext = new AudioContext();
        // If created in suspended state, try to resume (should work if in user gesture)
        if (this.audioContext.state === 'suspended') {
          await this.audioContext.resume();
        }
        return true;
      } catch (err) {
        debugError('[AudioStreamManager] Failed to create/resume AudioContext:', err);
        return false;
      }
    }
    // Resume if suspended
    if (this.audioContext && this.audioContext.state === 'suspended') {
      try {
        await this.audioContext.resume();
      } catch (err) {
        debugLog('[AudioStreamManager] AudioContext resume deferred');
        return false;
      }
    }
    return true;
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
    if (!this.isEnabled) {
      debugLog(`[AudioStreamManager] Audio disabled, dropping chunk ${chunk.chunkIndex}`);
      return;
    }

    debugLog(`[AudioStreamManager] Adding chunk ${chunk.chunkIndex} to queue`);

    // Add to queue (maintain order)
    this.audioQueue.push(chunk);
    this.audioQueue.sort((a, b) => a.chunkIndex - b.chunkIndex);

    // Start playing if not already
    if (!this.isPlaying) {
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
      this.audioQueue = [];
      this.isPlaying = false;
      return;
    }

    // Safe to allow errors again for new playback
    this.suppressPlaybackErrors = false;

    // Initialize AudioContext lazily when we actually need to play audio
    // This ensures it's created within a user gesture context (when user interacts)
    await this.ensureAudioContext();

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

      // Validate audio data
      if (!chunk.audio || chunk.audio.length === 0) {
        throw new Error(`Empty audio data for chunk ${chunk.chunkIndex}`);
      }

      // Decode base64 to binary
      let binaryString: string;
      try {
        binaryString = atob(chunk.audio);
      } catch (err) {
        throw new Error(`Failed to decode base64 audio for chunk ${chunk.chunkIndex}: ${err instanceof Error ? err.message : String(err)}`);
      }

      if (binaryString.length === 0) {
        throw new Error(`Decoded audio data is empty for chunk ${chunk.chunkIndex}`);
      }

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

      const audio = new Audio();
      // Explicitly set src to ensure it's set before loading
      audio.src = audioUrl;
      this.currentAudio = audio;
      
      const cleanup = () => {
        if (audio.src) {
          audio.src = '';
        }
        URL.revokeObjectURL(audioUrl);
        this.blobUrls = this.blobUrls.filter(url => url !== audioUrl);
      };

      // Wait for audio to be ready before playing
      await new Promise<void>((resolve, reject) => {
        let isResolved = false;
        
        // Set up error handler
        const errorHandler = () => {
          if (isResolved) return;
          
          // Extract error details from the audio element
          const error = audio.error;
          const errorDetails = error ? {
            code: error.code,
            message: error.message || `MediaError code ${error.code}`,
            MEDIA_ERR_ABORTED: error.code === MediaError.MEDIA_ERR_ABORTED,
            MEDIA_ERR_NETWORK: error.code === MediaError.MEDIA_ERR_NETWORK,
            MEDIA_ERR_DECODE: error.code === MediaError.MEDIA_ERR_DECODE,
            MEDIA_ERR_SRC_NOT_SUPPORTED: error.code === MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED
          } : 'Unknown error';
          
          // When playback is intentionally stopped we expect an empty src error
          if (this.suppressPlaybackErrors) {
            isResolved = true;
            cleanup();
            resolve();
            return;
          }

          isResolved = true;
          console.error(`[AudioStreamManager] Error playing chunk ${chunk.chunkIndex}:`, errorDetails, {
            audioFormat: chunk.audioFormat,
            chunkIndex: chunk.chunkIndex,
            audioLength: chunk.audio.length,
            mimeType: mimeType,
            audioContextState: this.audioContext?.state,
            audioSrc: audio.src,
            audioReadyState: audio.readyState
          });
          debugError(`[AudioStreamManager] Error playing chunk ${chunk.chunkIndex}:`, errorDetails);
          cleanup();
          reject(new Error(`Audio playback error: ${JSON.stringify(errorDetails)}`));
        };
        
        audio.addEventListener('error', errorHandler, { once: true });

        // Wait for audio to be ready to play
        const canPlayHandler = async () => {
          if (isResolved) return;
          
          try {
            // Set up ended handler
            audio.addEventListener('ended', () => {
              if (isResolved) return;
              isResolved = true;
              debugLog(`[AudioStreamManager] Chunk ${chunk.chunkIndex} finished`);
              if (this.onChunkPlayed) {
                this.onChunkPlayed(chunk.chunkIndex);
              }
              cleanup();
              resolve();
            }, { once: true });

            // Try to play
            const playPromise = audio.play();
            if (playPromise) {
              await playPromise;
            }
          } catch (err) {
            if (isResolved) return;
            if (this.suppressPlaybackErrors) {
              isResolved = true;
              cleanup();
              resolve();
              return;
            }
            isResolved = true;
            console.error(`[AudioStreamManager] Audio.play() rejected for chunk ${chunk.chunkIndex}:`, err, {
              audioFormat: chunk.audioFormat,
              chunkIndex: chunk.chunkIndex,
              audioContextState: this.audioContext?.state,
              isEnabled: this.isEnabled,
              audioSrc: audio.src,
              audioReadyState: audio.readyState
            });
            cleanup();
            reject(err);
          }
        };

        // Use 'canplay' event - fired when enough data is available to start playback
        if (audio.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
          // Already ready, play immediately
          canPlayHandler();
        } else {
          // Wait for audio to load - use 'canplay' which fires when enough data is available
          audio.addEventListener('canplay', canPlayHandler, { once: true });
        }
      });
      this.currentAudio = null;

      // Continue with next chunk
      this.playNextChunk();

    } catch (err) {
      if (this.suppressPlaybackErrors) {
        debugLog('[AudioStreamManager] Playback stopped, suppressing audio error');
        return;
      }
      const errorMessage = err instanceof Error ? err.message : String(err);
      console.error(`[AudioStreamManager] Failed to play chunk ${chunk.chunkIndex}:`, errorMessage, err, {
        audioFormat: chunk.audioFormat,
        chunkIndex: chunk.chunkIndex,
        audioLength: chunk.audio?.length,
        audioContextState: this.audioContext?.state,
        isEnabled: this.isEnabled
      });
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
    this.suppressPlaybackErrors = true;
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
