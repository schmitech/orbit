import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import { Play, Pause, Volume2, Download } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { debugError, debugLog } from '../utils/debug';
import { useTheme } from '../contexts/ThemeContext';

interface AudioPlayerProps {
  audio?: string;  // Base64-encoded audio data (inline return_audio TTS)
  audioUrl?: string;  // Persistent server-side URL (generated audio-skill output)
  audioFormat?: string;  // Audio format (mp3, wav, etc.)
  autoPlay?: boolean;  // Auto-play when component mounts
  maxSizeMB?: number;  // Maximum audio size in MB (default: 10MB)
  downloadFilename?: string;  // Filename to use when downloading; enables the download button
}

function mimeTypeForFormat(audioFormat: string): string {
  return audioFormat === 'mp3' ? 'audio/mpeg' :
    audioFormat === 'wav' ? 'audio/wav' :
    audioFormat === 'ogg' ? 'audio/ogg' :
    audioFormat === 'opus' ? 'audio/opus' :
    audioFormat === 'webm' ? 'audio/webm' :
    `audio/${audioFormat}`;
}

/**
 * AudioPlayer component for playing TTS audio responses.
 *
 * Accepts either:
 *  - `audio` (base64) — inline data from the return_audio/tts_voice chat flow.
 *  - `audioUrl` — a persistent server-side URL (e.g. from the "Audio" generation
 *    skill), fetched via JS so the Express proxy can inject the API key,
 *    mirroring ImageDisplay/VideoDisplay/DocumentDisplay.
 *
 * Renders play/pause controls and a progress bar; optionally a download
 * button when `downloadFilename` is provided.
 */
export function AudioPlayer({ audio, audioUrl, audioFormat = 'mp3', autoPlay = false, maxSizeMB = 10, downloadFilename }: AudioPlayerProps) {
  const { t } = useTranslation();
  const { isDark } = useTheme();
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sizeWarning, setSizeWarning] = useState<string | null>(null);
  const [resolvedSrc, setResolvedSrc] = useState<string | null>(null);

  // Decode base64 inline audio into a playable blob URL
  useEffect(() => {
    if (!audio) return;

    let objectUrl: string | null = null;
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
          throw new Error(t('audio.player.audioFileTooLargePlaceholder', { sizeMB: estimatedSizeMB.toFixed(1), maxMB: maxSizeMB }));
        }

        if (estimatedSizeMB > 2) {
          // Warn about large audio files (>2MB)
          setSizeWarning(t('audio.player.largeAudioWarning', { sizeMB: estimatedSizeMB.toFixed(1) }));
          debugLog('[AudioPlayer] Large audio file detected', { sizeMB: estimatedSizeMB.toFixed(2) });
        }

        // Validate base64 string
        if (!/^[A-Za-z0-9+/=]+$/.test(audio.replace(/\s/g, ''))) {
          throw new Error(t('audio.player.invalidBase64Error'));
        }

        // Decode base64 to binary
        const binaryString = atob(audio);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
          bytes[i] = binaryString.charCodeAt(i);
        }

        const mimeType = mimeTypeForFormat(audioFormat);

        // Create blob and object URL
        const audioBlob = new Blob([bytes], { type: mimeType });
        objectUrl = URL.createObjectURL(audioBlob);

        if (!isMounted) {
          if (objectUrl) URL.revokeObjectURL(objectUrl);
          return;
        }

        setResolvedSrc(objectUrl);
        setIsLoading(false);

        debugLog('[AudioPlayer] Audio loaded successfully', {
          format: audioFormat,
          mimeType,
          size: audioBlob.size
        });
      } catch (err) {
        debugError('[AudioPlayer] Failed to load audio:', err);
        if (isMounted) {
          setError(t('audio.player.loadFailureError'));
          setIsLoading(false);
        }
      }
    };

    loadAudio();

    // Cleanup: revoke object URL when component unmounts
    return () => {
      isMounted = false;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [audio, audioFormat, maxSizeMB, t]);

  // Fetch a persistent audioUrl (generated audio-skill output) into a playable blob URL
  useEffect(() => {
    if (audio || !audioUrl) return;

    let objectUrl: string | null = null;
    let cancelled = false;

    const loadAudio = async () => {
      try {
        setIsLoading(true);
        setError(null);

        const adapterName =
          typeof window !== 'undefined'
            ? window.localStorage.getItem('chat-adapter-name')
            : null;

        const res = await fetch(audioUrl, {
          headers: adapterName ? { 'X-Adapter-Name': adapterName } : {},
        });

        if (!res.ok) {
          throw new Error(`Server returned ${res.status}`);
        }
        if (cancelled) return;

        const bytes = await res.arrayBuffer();
        if (cancelled) return;

        const audioBlob = new Blob([bytes], { type: mimeTypeForFormat(audioFormat) });
        objectUrl = URL.createObjectURL(audioBlob);

        setResolvedSrc(objectUrl);
        setIsLoading(false);
      } catch (err) {
        debugError('[AudioPlayer] Failed to fetch audio from', audioUrl, err);
        if (!cancelled) {
          setError(t('audio.player.loadFailureError'));
          setIsLoading(false);
        }
      }
    };

    loadAudio();

    return () => {
      cancelled = true;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [audio, audioUrl, audioFormat, t]);

  // Auto-play once a source resolves
  useEffect(() => {
    if (autoPlay && resolvedSrc && audioRef.current) {
      audioRef.current.play().catch(err => {
        debugError('[AudioPlayer] Auto-play failed:', err);
        // Auto-play might be blocked by browser policy - this is expected behavior
      });
    }
  }, [autoPlay, resolvedSrc]);

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
        setError(t('audio.player.playbackFailureError'));
      });
    }
  };

  // Seek to specific time
  const handleSeek = (event: ChangeEvent<HTMLInputElement>) => {
    if (!audioRef.current) return;

    const time = parseFloat(event.target.value);
    audioRef.current.currentTime = time;
    setCurrentTime(time);
  };

  // Download the currently resolved audio blob
  const handleDownload = () => {
    if (!resolvedSrc) return;
    const a = document.createElement('a');
    a.href = resolvedSrc;
    a.download = downloadFilename || `generated-audio.${audioFormat}`;
    a.click();
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
      <div className="flex items-center gap-3 rounded-md border border-gray-200 bg-white/80 px-3 py-2 dark:border-[#3b3c49] dark:bg-white/5">
        {/* Hidden audio element */}
        <audio
          ref={audioRef}
          src={resolvedSrc ?? undefined}
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
        title={isPlaying ? t('audio.player.pauseTitle') : t('audio.player.playTitle')}
        aria-label={isPlaying ? t('audio.player.pauseAriaLabel') : t('audio.player.playAriaLabel')}
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
            background: (() => {
              const filled = isDark ? 'rgb(191 194 205)' : 'rgb(75 85 99)';
              const unfilled = isDark ? 'rgba(255 255 255 / 0.12)' : 'rgb(229 231 235)';
              const pct = duration ? (currentTime / duration) * 100 : 0;
              return `linear-gradient(to right, ${filled} 0%, ${filled} ${pct}%, ${unfilled} ${pct}%, ${unfilled} 100%)`;
            })()
          }}
        />
        <span className="text-xs text-gray-500 dark:text-[#bfc2cd]">
          {formatTime(duration)}
        </span>
      </div>

        {/* Download button (only when a filename is provided, e.g. generated-audio skill output) */}
        {downloadFilename && (
          <button
            onClick={handleDownload}
            disabled={isLoading || !resolvedSrc}
            className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-gray-200 hover:bg-gray-300 disabled:opacity-50 dark:bg-[#4a4b54] dark:hover:bg-[#565869]"
            title={t('audio.player.downloadAudioTooltip')}
          >
            <Download className="h-4 w-4 text-gray-700 dark:text-[#ececf1]" />
          </button>
        )}
      </div>
    </div>
  );
}
