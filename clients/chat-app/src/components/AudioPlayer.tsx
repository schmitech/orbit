import { useEffect, useRef, useState } from 'react';
import { Play, Pause, Volume2 } from 'lucide-react';
import { debugError, debugLog } from '../utils/debug';

interface AudioPlayerProps {
  audio: string;  // Base64-encoded audio data
  audioFormat?: string;  // Audio format (mp3, wav, etc.)
  autoPlay?: boolean;  // Auto-play when component mounts
  maxSizeMB?: number;  // Maximum audio size in MB (default: 10MB)
}

/**
 * AudioPlayer component for playing TTS audio responses
 *
 * Converts base64-encoded audio data to a playable audio element
 * with play/pause controls and a progress bar.
 */
export function AudioPlayer({ audio, audioFormat = 'mp3', autoPlay = false, maxSizeMB = 10 }: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sizeWarning, setSizeWarning] = useState<string | null>(null);

  // Convert base64 to blob and create object URL
  useEffect(() => {
    if (!audio) return;

    let audioUrl: string | null = null;
    let isMounted = true;

    const loadAudio = async () => {
      try {
        setIsLoading(true);
        setError(null);
        setSizeWarning(null);

        // Check audio data size before processing
        const estimatedSizeBytes = (audio.length * 3) / 4; // Base64 is ~33% larger than binary
        const estimatedSizeMB = estimatedSizeBytes / (1024 * 1024);

        if (estimatedSizeMB > maxSizeMB) {
          throw new Error(`Audio file too large (${estimatedSizeMB.toFixed(1)}MB > ${maxSizeMB}MB limit)`);
        }

        if (estimatedSizeMB > 2) {
          // Warn about large audio files (>2MB)
          setSizeWarning(`Large audio file (${estimatedSizeMB.toFixed(1)}MB) - may take time to load`);
          debugLog('[AudioPlayer] Large audio file detected', { sizeMB: estimatedSizeMB.toFixed(2) });
        }

        // Validate base64 string
        if (!/^[A-Za-z0-9+/=]+$/.test(audio.replace(/\s/g, ''))) {
          throw new Error('Invalid base64 audio data');
        }

        // Decode base64 to binary
        const binaryString = atob(audio);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
          bytes[i] = binaryString.charCodeAt(i);
        }

        // Determine MIME type
        const mimeType = audioFormat === 'mp3' ? 'audio/mpeg' :
                        audioFormat === 'wav' ? 'audio/wav' :
                        audioFormat === 'ogg' ? 'audio/ogg' :
                        audioFormat === 'opus' ? 'audio/opus' :
                        audioFormat === 'webm' ? 'audio/webm' :
                        `audio/${audioFormat}`;

        // Create blob and object URL
        const audioBlob = new Blob([bytes], { type: mimeType });
        audioUrl = URL.createObjectURL(audioBlob);

        if (!isMounted || !audioRef.current) {
          // Component unmounted before we could set the src
          if (audioUrl) URL.revokeObjectURL(audioUrl);
          return;
        }

        audioRef.current.src = audioUrl;
        setIsLoading(false);

        debugLog('[AudioPlayer] Audio loaded successfully', {
          format: audioFormat,
          mimeType,
          size: audioBlob.size
        });

        // Auto-play if enabled
        if (autoPlay && audioRef.current) {
          audioRef.current.play().catch(err => {
            debugError('[AudioPlayer] Auto-play failed:', err);
            // Auto-play might be blocked by browser policy - this is expected behavior
          });
        }
      } catch (err) {
        debugError('[AudioPlayer] Failed to load audio:', err);
        if (isMounted) {
          setError('Failed to load audio');
          setIsLoading(false);
        }
      }
    };

    loadAudio();

    // Cleanup: revoke object URL when component unmounts
    return () => {
      isMounted = false;
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
      }
    };
  }, [audio, audioFormat, autoPlay]);

  // Update duration when metadata is loaded
  const handleLoadedMetadata = () => {
    if (audioRef.current) {
      setDuration(audioRef.current.duration);
    }
  };

  // Update current time as audio plays
  const handleTimeUpdate = () => {
    if (audioRef.current) {
      setCurrentTime(audioRef.current.currentTime);
    }
  };

  // Handle play/pause events
  const handlePlay = () => setIsPlaying(true);
  const handlePause = () => setIsPlaying(false);
  const handleEnded = () => {
    setIsPlaying(false);
    setCurrentTime(0);
  };

  // Toggle play/pause
  const togglePlay = () => {
    if (!audioRef.current) return;

    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play().catch(err => {
        debugError('[AudioPlayer] Playback failed:', err);
        setError('Playback failed');
      });
    }
  };

  // Seek to specific time
  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!audioRef.current) return;

    const time = parseFloat(e.target.value);
    audioRef.current.currentTime = time;
    setCurrentTime(time);
  };

  // Format time (seconds) as MM:SS
  const formatTime = (seconds: number): string => {
    if (!isFinite(seconds)) return '0:00';
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

  return (
    <div className="mt-3 flex flex-col gap-1">
      {/* Size warning */}
      {sizeWarning && (
        <div className="text-xs text-amber-600 dark:text-amber-400 px-1">
          ⚠️ {sizeWarning}
        </div>
      )}
      <div className="flex items-center gap-3 rounded-md border border-gray-300 bg-white px-3 py-2 dark:border-[#4a4b54] dark:bg-[#343541]">
        {/* Hidden audio element */}
        <audio
          ref={audioRef}
          onLoadedMetadata={handleLoadedMetadata}
          onTimeUpdate={handleTimeUpdate}
          onPlay={handlePlay}
          onPause={handlePause}
          onEnded={handleEnded}
        />

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
          max={duration || 0}
          value={currentTime}
          onChange={handleSeek}
          disabled={isLoading || !duration}
          className="flex-1 cursor-pointer accent-gray-600 dark:accent-[#bfc2cd]"
          style={{
            background: duration
              ? `linear-gradient(to right, rgb(75 85 99) 0%, rgb(75 85 99) ${(currentTime / duration) * 100}%, rgb(229 231 235) ${(currentTime / duration) * 100}%, rgb(229 231 235) 100%)`
              : 'rgb(229 231 235)'
          }}
        />
        <span className="text-xs text-gray-500 dark:text-[#bfc2cd]">
          {formatTime(duration)}
        </span>
      </div>

        {/* Audio icon */}
        <Volume2 className="h-4 w-4 text-gray-500 dark:text-[#bfc2cd]" />
      </div>
    </div>
  );
}
