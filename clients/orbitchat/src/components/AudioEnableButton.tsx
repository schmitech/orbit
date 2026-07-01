import { useState, useEffect } from 'react';
import { Volume2, VolumeX } from 'lucide-react';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation();
  const [isEnabled, setIsEnabled] = useState(() => audioStreamManager.isAudioEnabled());
  const [isPlaying, setIsPlaying] = useState(false);

  useEffect(() => {
    // Set up callbacks
    const handlePlaybackStart = () => {
      setIsPlaying(true);
    };

    const handlePlaybackEnd = () => {
      setIsPlaying(false);
    };

    audioStreamManager.setOnPlaybackStart(handlePlaybackStart);
    audioStreamManager.setOnPlaybackEnd(handlePlaybackEnd);

    return () => {
      audioStreamManager.setOnPlaybackStart(() => {});
      audioStreamManager.setOnPlaybackEnd(() => {});
    };
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
      title={isEnabled ? (isPlaying ? t('audio.button.audioPlayingTitle') : t('audio.button.voiceEnabledTitle')) : t('audio.button.enableVoiceTitle')}
    >
      {isEnabled ? (
        <>
          <Volume2 className={`h-4 w-4 ${isPlaying ? 'animate-pulse' : ''}`} />
          <span className="text-sm font-medium">
            {isPlaying ? t('audio.button.playingLabel') : t('audio.button.voiceOnLabel')}
          </span>
        </>
      ) : (
        <>
          <VolumeX className="h-4 w-4" />
          <span className="text-sm font-medium">{t('audio.button.enableVoiceLabel')}</span>
        </>
      )}
    </button>
  );
}
