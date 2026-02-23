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
  private mimeTypeCache: Map<string, string> = new Map();
  private onChunkPlayed: ((chunkIndex: number) => void) | null = null;
  private blobUrls: string[] = [];
  private suppressPlaybackErrors: boolean = false;

  /**
   * Enable audio playback after user interaction (required by browsers).
   * Call this from a direct user gesture handler (click / tap / keydown).
   *
   * Mobile browsers enforce TWO independent autoplay gates:
   *   1. AudioContext — must be created / resumed inside a gesture
   *   2. HTMLAudioElement.play() — must be *called* (not awaited) inside a gesture
   *
   * IMPORTANT: the `.play()` call must happen BEFORE any `await` so it stays
   * in the synchronous portion of the gesture handler.  The browser checks
   * the call-site, not when the promise resolves.
   */
  public async enableAudio(): Promise<boolean> {
    try {
      // ---------------------------------------------------------------
      // Phase 1 — SYNCHRONOUS (must stay in the gesture call-stack)
      // ---------------------------------------------------------------

      // 1a. Create AudioContext
      if (!this.audioContext) {
        const AudioCtx =
          typeof AudioContext !== 'undefined'
            ? AudioContext
            : (typeof window !== 'undefined' && window.webkitAudioContext) || null;
        if (AudioCtx) {
          this.audioContext = new AudioCtx();
        }
      }

      // 1b. Kick off AudioContext resume (returns a promise but the *call*
      //     itself is synchronous and that is what the browser needs).
      const resumePromise =
        this.audioContext?.state === 'suspended'
          ? this.audioContext.resume()
          : Promise.resolve();

      // 1c. Unlock HTMLAudioElement BEFORE any await.  We generate a tiny
      //     but valid silent WAV in-memory (the previous 0-byte data URL
      //     was rejected by some mobile browsers as invalid audio).
      let htmlUnlockPromise: Promise<void> = Promise.resolve();
      try {
        const silentBlob = this.createSilentWavBlob();
        const silentUrl = URL.createObjectURL(silentBlob);
        const silentAudio = new Audio();
        silentAudio.setAttribute('playsinline', '');
        silentAudio.setAttribute('webkit-playsinline', '');
        silentAudio.src = silentUrl;
        silentAudio.volume = 0;
        // .play() MUST be called synchronously here — do NOT await yet
        htmlUnlockPromise = silentAudio.play()
          .then(() => { silentAudio.pause(); })
          .catch(() => {
            debugLog('[AudioStreamManager] HTMLAudioElement silent unlock failed (will retry on next gesture)');
          })
          .finally(() => { URL.revokeObjectURL(silentUrl); });
      } catch {
        debugLog('[AudioStreamManager] Could not create silent audio element');
      }

      // ---------------------------------------------------------------
      // Phase 2 — ASYNC (gesture context no longer required)
      // ---------------------------------------------------------------

      // 2a. Wait for AudioContext to be ready
      await resumePromise;

      // 2b. Play a silent buffer through AudioContext (belt-and-suspenders)
      if (this.audioContext && this.audioContext.state === 'running') {
        const buf = this.audioContext.createBuffer(1, 1, 22050);
        const src = this.audioContext.createBufferSource();
        src.buffer = buf;
        src.connect(this.audioContext.destination);
        src.start(0);
      }

      // 2c. Wait for HTMLAudioElement unlock to settle
      await htmlUnlockPromise;

      this.isEnabled = true;
      debugLog('[AudioStreamManager] Audio playback enabled', {
        audioContextState: this.audioContext?.state
      });
      return true;
    } catch (err) {
      debugError('[AudioStreamManager] Failed to enable audio:', err);
      return false;
    }
  }

  /**
   * Generate a tiny valid silent WAV blob (0.05 s, 8 kHz, mono, 16-bit).
   * Using a real PCM payload instead of a 0-byte data URL ensures mobile
   * browsers treat it as legitimate audio and honour the play() call.
   */
  private createSilentWavBlob(): Blob {
    const sampleRate = 8000;
    const numSamples = 400;          // 0.05 seconds
    const bytesPerSample = 2;        // 16-bit
    const dataSize = numSamples * bytesPerSample;
    const headerSize = 44;
    const buffer = new ArrayBuffer(headerSize + dataSize);
    const v = new DataView(buffer);

    const writeStr = (offset: number, str: string) => {
      for (let i = 0; i < str.length; i++) v.setUint8(offset + i, str.charCodeAt(i));
    };

    writeStr(0, 'RIFF');
    v.setUint32(4, 36 + dataSize, true);
    writeStr(8, 'WAVE');
    writeStr(12, 'fmt ');
    v.setUint32(16, 16, true);       // fmt chunk size
    v.setUint16(20, 1, true);        // PCM
    v.setUint16(22, 1, true);        // mono
    v.setUint32(24, sampleRate, true);
    v.setUint32(28, sampleRate * bytesPerSample, true);
    v.setUint16(32, bytesPerSample, true);
    v.setUint16(34, 16, true);       // bits per sample
    writeStr(36, 'data');
    v.setUint32(40, dataSize, true);
    // PCM samples are all zeros (silence) — ArrayBuffer is zero-initialized

    return new Blob([buffer], { type: 'audio/wav' });
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
   * Ensure AudioContext is ready for playback.
   * Creation happens in enableAudio() (inside a user gesture).  This method
   * only handles the resume-if-suspended case (e.g. after backgrounding).
   */
  private async ensureAudioContext(): Promise<boolean> {
    // Fall back to creating here if enableAudio() was called without AudioContext support at the time
    if (!this.audioContext) {
      const AudioCtx =
        typeof AudioContext !== 'undefined'
          ? AudioContext
          : (typeof window !== 'undefined' && window.webkitAudioContext) || null;
      if (AudioCtx) {
        try {
          this.audioContext = new AudioCtx();
        } catch (err) {
          debugError('[AudioStreamManager] Failed to create AudioContext:', err);
          return false;
        }
      }
    }

    if (this.audioContext?.state === 'suspended') {
      try {
        await this.audioContext.resume();
      } catch (err) {
        debugLog('[AudioStreamManager] AudioContext resume deferred', err);
        return false;
      }
    }
    return true;
  }

  /**
   * Resolve the best MIME type for a given audio format string.
   * iOS Safari doesn't support the Ogg container, so for "opus" audio we
   * probe the browser and fall back to WebM or bare audio/opus.
   */
  private resolveMimeType(format: string): string {
    const cached = this.mimeTypeCache.get(format);
    if (cached) return cached;

    let mime: string;
    switch (format) {
      case 'mp3':
        mime = 'audio/mpeg';
        break;
      case 'wav':
        mime = 'audio/wav';
        break;
      case 'webm':
        mime = 'audio/webm';
        break;
      case 'ogg':
        mime = 'audio/ogg';
        break;
      case 'opus': {
        // Probe browser codec support — iOS Safari can't play Ogg containers
        const probe = typeof document !== 'undefined' ? document.createElement('audio') : null;
        if (probe?.canPlayType('audio/ogg; codecs=opus')) {
          mime = 'audio/ogg; codecs=opus';
        } else if (probe?.canPlayType('audio/webm; codecs=opus')) {
          mime = 'audio/webm; codecs=opus';
        } else {
          mime = 'audio/mp4';   // last resort — works on iOS for many payloads
        }
        break;
      }
      default:
        mime = `audio/${format}`;
    }

    this.mimeTypeCache.set(format, mime);
    debugLog(`[AudioStreamManager] Resolved MIME type for "${format}": ${mime}`);
    return mime;
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

      // Determine MIME type (with iOS Safari fallback for Opus)
      const mimeType = this.resolveMimeType(chunk.audioFormat);

      // Create blob and audio element
      const audioBlob = new Blob([bytes], { type: mimeType });
      const audioUrl = URL.createObjectURL(audioBlob);
      this.blobUrls.push(audioUrl);

      const cleanup = () => {
        if (this.currentAudio) {
          try { this.currentAudio.pause(); } catch { /* ignore */ }
          this.currentAudio.removeAttribute('src');
          this.currentAudio.load();
        }
        URL.revokeObjectURL(audioUrl);
        this.blobUrls = this.blobUrls.filter(url => url !== audioUrl);
      };

      // ---------- Try HTMLAudioElement first ----------
      let played = false;
      try {
        played = await this.playViaAudioElement(audioUrl, chunk, mimeType, cleanup);
      } catch {
        played = false;
      }

      // ---------- Fallback: decode through AudioContext ----------
      if (!played && !this.suppressPlaybackErrors && this.audioContext) {
        debugLog(`[AudioStreamManager] HTMLAudioElement failed for chunk ${chunk.chunkIndex}, trying AudioContext fallback`);
        try {
          played = await this.playViaAudioContext(bytes.buffer, chunk.chunkIndex);
        } catch (ctxErr) {
          debugError(`[AudioStreamManager] AudioContext fallback also failed for chunk ${chunk.chunkIndex}:`, ctxErr);
        }
        cleanup();
      }
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
   * Play audio through an HTMLAudioElement (primary path).
   * Returns true if playback completed, false if the browser blocked it.
   */
  private playViaAudioElement(
    audioUrl: string,
    chunk: AudioChunk,
    mimeType: string,
    cleanup: () => void
  ): Promise<boolean> {
    return new Promise<boolean>((resolve) => {
      const audio = new Audio();
      audio.setAttribute('playsinline', '');
      audio.setAttribute('webkit-playsinline', '');
      audio.src = audioUrl;
      this.currentAudio = audio;

      let settled = false;
      const settle = (ok: boolean) => {
        if (settled) return;
        settled = true;
        resolve(ok);
      };

      const errorHandler = () => {
        if (this.suppressPlaybackErrors) { cleanup(); settle(true); return; }
        const err = audio.error;
        debugError(`[AudioStreamManager] Media error on chunk ${chunk.chunkIndex}:`, err ? {
          code: err.code, message: err.message,
          SRC_NOT_SUPPORTED: err.code === MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED
        } : 'unknown');
        cleanup();
        settle(false);
      };
      audio.addEventListener('error', errorHandler, { once: true });

      const tryPlay = async () => {
        if (settled) return;
        try {
          audio.addEventListener('ended', () => {
            if (settled) return;
            debugLog(`[AudioStreamManager] Chunk ${chunk.chunkIndex} finished`);
            if (this.onChunkPlayed) this.onChunkPlayed(chunk.chunkIndex);
            cleanup();
            settle(true);
          }, { once: true });

          await audio.play();
        } catch (playErr) {
          if (this.suppressPlaybackErrors) { cleanup(); settle(true); return; }
          debugLog(`[AudioStreamManager] audio.play() rejected for chunk ${chunk.chunkIndex}:`, playErr);
          cleanup();
          settle(false);  // signal caller to try AudioContext fallback
        }
      };

      if (audio.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
        tryPlay();
      } else {
        audio.addEventListener('canplay', () => tryPlay(), { once: true });
      }
    });
  }

  /**
   * Fallback: decode audio data via AudioContext.decodeAudioData and play
   * through an AudioBufferSourceNode.  This bypasses the HTMLAudioElement
   * autoplay gate entirely — only the AudioContext gate matters, and we
   * already unlocked that during enableAudio().
   */
  private playViaAudioContext(
    arrayBuffer: ArrayBuffer,
    chunkIndex: number
  ): Promise<boolean> {
    return new Promise<boolean>((resolve, reject) => {
      if (!this.audioContext) { reject(new Error('No AudioContext')); return; }

      // decodeAudioData consumes the buffer, so we need a copy
      const copy = arrayBuffer.slice(0);
      this.audioContext.decodeAudioData(
        copy,
        (audioBuffer) => {
          if (!this.audioContext || this.suppressPlaybackErrors) { resolve(true); return; }
          const source = this.audioContext.createBufferSource();
          source.buffer = audioBuffer;
          source.connect(this.audioContext.destination);
          source.onended = () => {
            debugLog(`[AudioStreamManager] Chunk ${chunkIndex} finished (AudioContext path)`);
            if (this.onChunkPlayed) this.onChunkPlayed(chunkIndex);
            resolve(true);
          };
          source.start(0);
        },
        (decodeErr) => {
          reject(decodeErr);
        }
      );
    });
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
