import { createAudioPlayer, setAudioModeAsync } from 'expo-audio';
import type { AudioPlayer } from 'expo-audio';
import { File, Paths } from 'expo-file-system';

interface AudioChunk {
  audio: string; // Base64 encoded
  audioFormat: string;
  chunkIndex: number;
}

type PlaybackCallback = () => void;

class AudioStreamManager {
  private queue: AudioChunk[] = [];
  private isPlaying = false;
  private enabled = false;
  private currentPlayer: AudioPlayer | null = null;
  private onPlaybackStart: PlaybackCallback | null = null;
  private onPlaybackEnd: PlaybackCallback | null = null;

  async enableAudio(): Promise<boolean> {
    try {
      await setAudioModeAsync({
        playsInSilentMode: true,
        shouldPlayInBackground: false,
        interruptionMode: 'doNotMix',
      });
      this.enabled = true;
      return true;
    } catch {
      return false;
    }
  }

  disableAudio(): void {
    this.enabled = false;
    this.stop();
  }

  setOnPlaybackStart(callback: PlaybackCallback): void {
    this.onPlaybackStart = callback;
  }

  setOnPlaybackEnd(callback: PlaybackCallback): void {
    this.onPlaybackEnd = callback;
  }

  async addChunk(chunk: AudioChunk): Promise<void> {
    if (!this.enabled) return;

    // Insert in order by chunkIndex
    const insertIdx = this.queue.findIndex((c) => c.chunkIndex > chunk.chunkIndex);
    if (insertIdx === -1) {
      this.queue.push(chunk);
    } else {
      this.queue.splice(insertIdx, 0, chunk);
    }

    if (!this.isPlaying) {
      this.playNext();
    }
  }

  private async playNext(): Promise<void> {
    if (!this.enabled || this.queue.length === 0) {
      this.isPlaying = false;
      this.onPlaybackEnd?.();
      return;
    }

    this.isPlaying = true;
    const chunk = this.queue.shift()!;

    try {
      const ext = this.getExtension(chunk.audioFormat);
      const tempFile = new File(Paths.cache, `orbit_audio_${chunk.chunkIndex}.${ext}`);

      // Write base64 audio to temp file
      tempFile.write(chunk.audio, { encoding: 'base64' });

      // Create player and play at full volume
      const player = createAudioPlayer(tempFile.uri);
      player.volume = 1.0;
      this.currentPlayer = player;

      if (chunk.chunkIndex === 0) {
        this.onPlaybackStart?.();
      }

      player.addListener('playbackStatusUpdate', (status) => {
        if (status.didJustFinish) {
          player.remove();
          try { tempFile.delete(); } catch { /* ignore */ }
          this.currentPlayer = null;
          this.playNext();
        }
      });

      player.play();
    } catch {
      // Skip failed chunk and continue with next
      this.currentPlayer = null;
      this.playNext();
    }
  }

  stop(): void {
    this.queue = [];
    if (this.currentPlayer) {
      this.currentPlayer.pause();
      this.currentPlayer.remove();
      this.currentPlayer = null;
    }
    this.isPlaying = false;
  }

  reset(): void {
    this.stop();
  }

  isAudioEnabled(): boolean {
    return this.enabled;
  }

  isCurrentlyPlaying(): boolean {
    return this.isPlaying;
  }

  getQueueSize(): number {
    return this.queue.length;
  }

  private getExtension(format: string): string {
    const map: Record<string, string> = {
      mp3: 'mp3',
      wav: 'wav',
      opus: 'opus',
      ogg: 'ogg',
      webm: 'webm',
      aac: 'aac',
    };
    return map[format.toLowerCase()] || 'mp3';
  }
}

// Singleton instance
export const audioStreamManager = new AudioStreamManager();
