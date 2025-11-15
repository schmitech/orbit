import { useEffect, useRef, useState } from 'react';
import { Play, Pause, Volume2 } from 'lucide-react';
import { debugError, debugLog } from '../utils/debug';
import { StreamingAudioChunk } from '../types';

interface StreamingAudioPlayerProps {
  audioChunks: StreamingAudioChunk[];  // Array of audio chunks in order
  audioFormat?: string;  // Audio format (mp3, wav, opus, etc.)
  autoPlay?: boolean;  // Auto-play when component mounts
}

/**
 * StreamingAudioPlayer component for playing TTS audio chunks as they arrive
 *
 * This component buffers and plays audio chunks sequentially as they're received,
 * providing low-latency audio playback during streaming responses.
 */
export function StreamingAudioPlayer({ 
  audioChunks, 
  audioFormat = 'opus', 
  autoPlay = false 
}: StreamingAudioPlayerProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [totalDuration, setTotalDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  
  // Track audio URLs and elements for each chunk
  const audioUrlsRef = useRef<Map<number, string>>(new Map());
  const audioElementsRef = useRef<Map<number, HTMLAudioElement>>(new Map());
  const isPlayingRef = useRef(false);

  // Determine MIME type
  const mimeType = audioFormat === 'mp3' ? 'audio/mpeg' :
                  audioFormat === 'wav' ? 'audio/wav' :
                  audioFormat === 'ogg' ? 'audio/ogg' :
                  audioFormat === 'opus' ? 'audio/opus' :
                  audioFormat === 'webm' ? 'audio/webm' :
                  `audio/${audioFormat}`;

  // Load audio chunks and create blob URLs
  useEffect(() => {
    if (!audioChunks || audioChunks.length === 0) {
      setIsLoading(false);
      return;
    }

    let isMounted = true;

    const loadAudioChunks = async () => {
      try {
        setIsLoading(true);
        setError(null);

        // Process all chunks
        for (const chunk of audioChunks) {
          if (!isMounted) return;

          // Skip if already loaded
          if (audioUrlsRef.current.has(chunk.chunkIndex)) {
            continue;
          }

          try {
            // Decode base64 to binary
            const binaryString = atob(chunk.audio);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
              bytes[i] = binaryString.charCodeAt(i);
            }

            // Create blob and object URL
            const audioBlob = new Blob([bytes], { type: mimeType });
            const audioUrl = URL.createObjectURL(audioBlob);
            audioUrlsRef.current.set(chunk.chunkIndex, audioUrl);

            // Create audio element
            const audioElement = new Audio(audioUrl);
            audioElement.preload = 'auto';
            audioElementsRef.current.set(chunk.chunkIndex, audioElement);

            // Wait for metadata to load
            await new Promise((resolve, reject) => {
              audioElement.addEventListener('loadedmetadata', () => {
                resolve(undefined);
              });
              audioElement.addEventListener('error', reject);
            });

            debugLog(`[StreamingAudioPlayer] Loaded chunk ${chunk.chunkIndex}`, {
              duration: audioElement.duration
            });
          } catch (err) {
            debugError(`[StreamingAudioPlayer] Failed to load chunk ${chunk.chunkIndex}:`, err);
          }
        }

        // Calculate total duration
        let total = 0;
        for (let i = 0; i < audioChunks.length; i++) {
          const audioElement = audioElementsRef.current.get(i);
          if (audioElement && audioElement.duration) {
            total += audioElement.duration;
          }
        }
        setTotalDuration(total);

        if (isMounted) {
          setIsLoading(false);
          
          // Auto-play if enabled
          if (autoPlay && audioElementsRef.current.size > 0) {
            playAllChunks();
          }
        }
      } catch (err) {
        debugError('[StreamingAudioPlayer] Failed to load audio chunks:', err);
        if (isMounted) {
          setError('Failed to load audio');
          setIsLoading(false);
        }
      }
    };

    loadAudioChunks();

    // Cleanup: Just mark as unmounted, don't revoke URLs here
    // URLs will be revoked on component unmount to prevent ERR_FILE_NOT_FOUND
    return () => {
      isMounted = false;
    };
  }, [audioChunks, audioFormat, autoPlay, mimeType]);

  // Cleanup on unmount - revoke all remaining blob URLs
  useEffect(() => {
    return () => {
      audioUrlsRef.current.forEach(url => URL.revokeObjectURL(url));
      audioUrlsRef.current.clear();
      audioElementsRef.current.forEach(audio => {
        audio.pause();
        audio.src = '';
      });
      audioElementsRef.current.clear();
    };
  }, []);

  // Play all loaded chunks sequentially
  const playAllChunks = async () => {
    if (isPlayingRef.current) {
      return; // Already playing
    }

    try {
      setIsPlaying(true);
      isPlayingRef.current = true;
      setCurrentTime(0);

      let accumulatedTime = 0;

      // Play chunks in order
      for (let i = 0; i < audioChunks.length; i++) {
        if (!isPlayingRef.current) {
          break; // Stopped
        }

        const audioElement = audioElementsRef.current.get(i);
        if (!audioElement) {
          // Chunk not loaded yet, wait a bit and try again
          await new Promise(resolve => setTimeout(resolve, 100));
          i--; // Retry this chunk
          continue;
        }

        // Update current time as audio plays
        const updateTime = () => {
          if (isPlayingRef.current && audioElement) {
            const chunkTime = audioElement.currentTime || 0;
            setCurrentTime(accumulatedTime + chunkTime);
            if (audioElement.ended || !isPlayingRef.current) {
              return;
            }
            requestAnimationFrame(updateTime);
          }
        };

        // Start playing this chunk
        await new Promise<void>((resolve, reject) => {
          audioElement.currentTime = 0;
          audioElement.addEventListener('ended', () => {
            accumulatedTime += audioElement.duration;
            resolve();
          }, { once: true });
          audioElement.addEventListener('error', reject, { once: true });
          
          const playPromise = audioElement.play();
          if (playPromise) {
            playPromise.catch(reject);
          }

          // Start time updates
          updateTime();
        });
      }

      setIsPlaying(false);
      isPlayingRef.current = false;
      setCurrentTime(totalDuration);
    } catch (err) {
      debugError('[StreamingAudioPlayer] Playback failed:', err);
      setIsPlaying(false);
      isPlayingRef.current = false;
      setError('Playback failed');
    }
  };

  // Toggle play/pause
  const togglePlay = () => {
    if (isPlaying) {
      // Pause - stop all audio elements
      setIsPlaying(false);
      isPlayingRef.current = false;
      audioElementsRef.current.forEach(audio => {
        audio.pause();
        audio.currentTime = 0;
      });
    } else {
      // Play
      if (audioElementsRef.current.size > 0) {
        playAllChunks();
      } else {
        // Wait for chunks to load
        setIsLoading(true);
      }
    }
  };

  // Format time (seconds) as MM:SS
  const formatTime = (seconds: number): string => {
    if (!isFinite(seconds) || seconds < 0) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  if (error) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-700 dark:bg-red-900/20 dark:text-red-400">
        <Volume2 className="h-4 w-4" />
        <span>{error}</span>
      </div>
    );
  }

  if (!audioChunks || audioChunks.length === 0) {
    return null;
  }

  return (
    <div className="mt-3 flex flex-col gap-1">
      <div className="flex items-center gap-3 rounded-md border border-gray-300 bg-white px-3 py-2 dark:border-[#4a4b54] dark:bg-[#343541]">
        {/* Play/Pause button */}
        <button
          onClick={togglePlay}
          disabled={isLoading}
          className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-gray-200 hover:bg-gray-300 disabled:opacity-50 dark:bg-[#4a4b54] dark:hover:bg-[#565869]"
          title={isPlaying ? 'Pause' : 'Play'}
        >
          {isLoading ? (
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-gray-400 border-t-transparent" />
          ) : isPlaying ? (
            <Pause className="h-4 w-4 text-gray-700 dark:text-[#ececf1]" />
          ) : (
            <Play className="h-4 w-4 text-gray-700 dark:text-[#ececf1]" />
          )}
        </button>

        {/* Progress bar */}
        <div className="flex flex-1 items-center gap-2">
          <span className="text-xs text-gray-500 dark:text-[#bfc2cd]">
            {formatTime(currentTime)}
          </span>
          <input
            type="range"
            min="0"
            max={totalDuration || 0}
            value={currentTime}
            disabled={isLoading || !totalDuration}
            className="flex-1 cursor-pointer accent-gray-600 dark:accent-[#bfc2cd]"
            style={{
              background: totalDuration
                ? `linear-gradient(to right, rgb(75 85 99) 0%, rgb(75 85 99) ${(currentTime / totalDuration) * 100}%, rgb(229 231 235) ${(currentTime / totalDuration) * 100}%, rgb(229 231 235) 100%)`
                : 'rgb(229 231 235)'
            }}
          />
          <span className="text-xs text-gray-500 dark:text-[#bfc2cd]">
            {formatTime(totalDuration)}
          </span>
        </div>

        {/* Audio icon */}
        <Volume2 className="h-4 w-4 text-gray-500 dark:text-[#bfc2cd]" />
      </div>
      
      {/* Chunk loading status */}
      {audioChunks.length > 0 && (
        <div className="text-xs text-gray-500 dark:text-[#bfc2cd] px-1">
          {audioElementsRef.current.size} / {audioChunks.length} chunks loaded
        </div>
      )}
    </div>
  );
}

