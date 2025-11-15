import { useState, useEffect } from 'react';
import { Volume2, VolumeX } from 'lucide-react';
import { audioStreamManager } from '../utils/audioStreamManager';
import { debugLog } from '../utils/debug';

interface AudioEnableButtonProps {
  className?: string;
}

/**
 * Button to enable real-time audio playback.
 * Required due to browser autoplay policies - needs user gesture to enable audio.
 */
export function AudioEnableButton({ className = '' }: AudioEnableButtonProps) {
  const [isEnabled, setIsEnabled] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);

  useEffect(() => {
    // Check initial state
    setIsEnabled(audioStreamManager.isAudioEnabled());

    // Set up callbacks
    audioStreamManager.setOnPlaybackStart(() => {
      setIsPlaying(true);
    });

    audioStreamManager.setOnPlaybackEnd(() => {
      setIsPlaying(false);
    });
  }, []);

  const handleEnableAudio = async () => {
    if (isEnabled) {
      // Toggle off - stop any playing audio
      audioStreamManager.stop();
      setIsEnabled(false);
      setIsPlaying(false);
      debugLog('[AudioEnableButton] Audio disabled');
    } else {
      // Enable audio
      const success = await audioStreamManager.enableAudio();
      setIsEnabled(success);
      if (success) {
        debugLog('[AudioEnableButton] Audio enabled successfully');
      }
    }
  };

  return (
    <button
      onClick={handleEnableAudio}
      className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-all ${
        isEnabled
          ? isPlaying
            ? 'bg-green-500 text-white hover:bg-green-600'
            : 'bg-blue-500 text-white hover:bg-blue-600'
          : 'bg-gray-200 text-gray-700 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600'
      } ${className}`}
      title={isEnabled ? (isPlaying ? 'Audio playing...' : 'Voice enabled - Click to disable') : 'Click to enable voice responses'}
    >
      {isEnabled ? (
        <>
          <Volume2 className={`h-4 w-4 ${isPlaying ? 'animate-pulse' : ''}`} />
          <span className="text-sm font-medium">
            {isPlaying ? 'Playing...' : 'Voice On'}
          </span>
        </>
      ) : (
        <>
          <VolumeX className="h-4 w-4" />
          <span className="text-sm font-medium">Enable Voice</span>
        </>
      )}
    </button>
  );
}
