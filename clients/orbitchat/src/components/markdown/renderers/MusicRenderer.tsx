import React, { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react';
import { useTranslation } from 'react-i18next';
import 'abcjs/abcjs-audio.css';
import type { MusicRendererProps } from '../types';
import { normalizeAbcForRendering } from './abcNotation';
import { copyCodeToClipboard, exportSvgAsPng } from './graphExportUtils';

type AbcTune = {
  metaText?: {
    title?: string;
  };
};

type SynthControllerLike = {
  load: (
    target: HTMLElement,
    cursorControl?: Record<string, unknown> | null,
    options?: Record<string, boolean>,
  ) => void;
  setTune: (tune: AbcTune, userAction: boolean, options?: Record<string, unknown>) => Promise<unknown>;
  play: () => Promise<unknown>;
  pause: () => void;
};

type MusicPlaybackController = {
  play: () => Promise<unknown>;
  pause: () => Promise<void>;
};

type AbcSynthLike = {
  supportsAudio: () => boolean;
  SynthController: new () => SynthControllerLike;
  getMidiFile: (source: AbcTune, options?: Record<string, unknown>) => ArrayBuffer;
};

type AbcJsLike = {
  renderAbc: (target: HTMLElement | string, code: string, options?: Record<string, unknown>) => AbcTune[];
  synth?: AbcSynthLike;
};

type WindowWithAbcjs = {
  ABCJS?: AbcJsLike;
};

// Dynamic import for abcjs to handle both ESM and CommonJS
let abcjs: AbcJsLike | null = null;
let nextMusicPlayerId = 0;
let activeMusicPlayerId: string | null = null;
const musicPlayerPausers = new Map<string, () => void>();
const SOUNDFONT_URL = 'https://paulrosen.github.io/midi-js-soundfonts/FluidR3_GM/';

const pauseOtherMusicPlayers = (activeId: string) => {
  musicPlayerPausers.forEach((pause, id) => {
    if (id !== activeId) pause();
  });
};

const setSecondaryControlsDisabled = (target: HTMLElement, disabled: boolean) => {
  target.querySelectorAll<HTMLButtonElement | HTMLInputElement>(
    '.abcjs-midi-reset, .abcjs-midi-progress-background, .abcjs-midi-tempo',
  ).forEach(control => {
    control.disabled = disabled;
  });
};

const HIGHLIGHT_CLASS = 'abcjs-note-highlight';

type CursorEvent = { elements?: Element[][] };

const clearHighlights = (scoreTarget: HTMLElement) => {
  scoreTarget.querySelectorAll(`.${HIGHLIGHT_CLASS}`).forEach(el => el.classList.remove(HIGHLIGHT_CLASS));
};

// Only nudge the scroll position when the playing note is getting close to
// the viewport edge, so we don't fight a smooth-scroll animation on every
// cursor event (these fire multiple times per second).
const SCROLL_MARGIN_PX = 96;

const keepNoteInView = (el: Element) => {
  const rect = el.getBoundingClientRect();
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
  if (rect.top < SCROLL_MARGIN_PX || rect.bottom > viewportHeight - SCROLL_MARGIN_PX) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
};

const createCursorControl = (scoreTarget: HTMLElement) => ({
  onStart: () => {
    scoreTarget.scrollIntoView({ behavior: 'smooth', block: 'start' });
  },
  onEvent: (event: CursorEvent) => {
    clearHighlights(scoreTarget);
    const elements = event.elements?.flat() ?? [];
    elements.forEach(el => el.classList.add(HIGHLIGHT_CLASS));
    if (elements[0]) keepNoteInView(elements[0]);
  },
  onFinished: () => clearHighlights(scoreTarget),
});

const prepareSynthController = (
  synth: AbcSynthLike,
  tune: AbcTune,
  target: HTMLElement,
  scoreTarget: HTMLElement,
  playerId: string,
  labels: { playPause: string; restart: string; seek: string; tempo: string },
) => {
  target.innerHTML = '';
  const synthController = new synth.SynthController();
  synthController.load(target, createCursorControl(scoreTarget), {
    displayLoop: false,
    displayRestart: true,
    displayPlay: true,
    displayProgress: true,
    displayWarp: true,
  });

  const setControlLabel = (selector: string, label: string) => {
    const element = target.querySelector(selector);
    element?.setAttribute('title', label);
    element?.setAttribute('aria-label', label);
  };
  setControlLabel('.abcjs-midi-start', labels.playPause);
  setControlLabel('.abcjs-midi-reset', labels.restart);
  setControlLabel('.abcjs-midi-progress-background', labels.seek);
  setControlLabel('.abcjs-midi-tempo', labels.tempo);
  setSecondaryControlsDisabled(target, true);

  // abcjs names its transport toggle `play()`. Calling its raw `pause()` does
  // not reset the internal isStarted flag, so the next Play would be ignored.
  // Keep that quirk inside this adapter and expose unambiguous operations to
  // the renderer and the one-player-at-a-time coordinator.
  const controller: MusicPlaybackController = {
    play: () => synthController.play(),
    pause: async () => {
      const playButton = target.querySelector('.abcjs-midi-start');
      if (playButton?.classList.contains('abcjs-pushed')) {
        await synthController.play();
      } else {
        synthController.pause();
      }
      clearHighlights(scoreTarget);
    },
  };

  musicPlayerPausers.set(playerId, () => {
    void controller.pause();
  });

  void synthController.setTune(tune, false, { soundFontUrl: SOUNDFONT_URL, chordsOff: true });
  return controller;
};

const loadAbcjs = async () => {
  if (typeof window === 'undefined') {
    throw new Error('abcjs requires a browser environment');
  }

  if (abcjs) return abcjs;

  try {
    // Import abcjs (CommonJS module, will be default export in ESM)
    const abcjsModule = await import('abcjs');

    // CommonJS modules are typically the default export when imported as ESM
    const abcjsLib = abcjsModule.default || abcjsModule;

    if (!abcjsLib) {
      throw new Error('abcjs module is empty');
    }

    if (typeof abcjsLib.renderAbc !== 'function') {
      throw new Error(`renderAbc is not a function. Available methods: ${Object.keys(abcjsLib).join(', ')}`);
    }

    abcjs = abcjsLib;
    return abcjs;
  } catch (err) {
    // Fallback: try to load from window if available
    const windowWithAbcjs = window as WindowWithAbcjs;
    if (typeof window !== 'undefined' && windowWithAbcjs.ABCJS) {
      abcjs = windowWithAbcjs.ABCJS;
      return abcjs;
    }
    const errorMessage = err instanceof Error ? err.message : 'Failed to load abcjs';
    throw new Error(`Failed to load abcjs: ${errorMessage}`);
  }
};

/**
 * Detects if the code is ABC notation
 */
const isAbcNotation = (code: string): boolean => {
  const trimmed = code.trim();
  // ABC notation typically starts with headers like X:, T:, M:, L:, K:
  return /^[XMTLK]:/m.test(trimmed) || /^X:\d+/m.test(trimmed);
};

/**
 * Check if ABC notation appears incomplete (streaming)
 */
const isLikelyIncomplete = (code: string): boolean => {
  const trimmed = code.trim();

  // Must have at least X: header to start
  if (!trimmed.includes('X:')) {
    return true;
  }

  // Check if we have the minimum required headers
  // ABC notation needs at least X: and K: (key signature) to render
  const hasKey = /^K:/m.test(trimmed);
  if (!hasKey) {
    return true;
  }

  // Check if the last line looks incomplete (ends mid-header or mid-note)
  const lines = trimmed.split('\n');
  const lastLine = lines[lines.length - 1].trim();

  // Incomplete header (has colon but nothing after, or just a letter)
  if (lastLine.match(/^[A-Z]:?\s*$/) && lastLine.length < 3) {
    return true;
  }

  // Line ends with a bar that suggests more content coming
  if (lastLine.endsWith('|') && !lastLine.endsWith('|]') && !lastLine.endsWith('||')) {
    // Could be incomplete, but also could be valid - check if very short
    const noteContent = lastLine.replace(/\|/g, '').trim();
    if (noteContent.length < 2) {
      return true;
    }
  }

  return false;
};

export const MusicRenderer: React.FC<MusicRendererProps> = ({ code }) => {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const audioControlsRef = useRef<HTMLDivElement>(null);
  const synthControllerRef = useRef<MusicPlaybackController | null>(null);
  const renderedTuneRef = useRef<AbcTune | null>(null);
  const [playerId] = useState(() => `music-player-${++nextMusicPlayerId}`);
  const [error, setError] = useState<string | null>(null);
  const [playbackError, setPlaybackError] = useState<string | null>(null);
  const [audioSupported, setAudioSupported] = useState(true);
  const [isLoading, setIsLoading] = useState(true);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isAbc, setIsAbc] = useState(false);
  const [showErrorDetails, setShowErrorDetails] = useState(false);
  const [copiedCode, setCopiedCode] = useState(false);
  const [exportingPng, setExportingPng] = useState(false);
  const [exportingMidi, setExportingMidi] = useState(false);
  const [hasRenderedTune, setHasRenderedTune] = useState(false);
  const lastCodeRef = useRef<string>('');
  const lastUpdateTimeRef = useRef<number>(0);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // First effect: Detect ABC notation and streaming state
  useEffect(() => {
    const trimmed = code.trim();
    if (!trimmed) {
      return;
    }

    const now = Date.now();
    const timeSinceLastUpdate = now - lastUpdateTimeRef.current;
    const codeChanged = code !== lastCodeRef.current;

    lastCodeRef.current = code;
    lastUpdateTimeRef.current = now;

    // Detect streaming
    const incomplete = isLikelyIncomplete(trimmed);
    const rapidUpdate = codeChanged && timeSinceLastUpdate < 500 && timeSinceLastUpdate > 0;
    const likelyStreaming = incomplete || rapidUpdate;

    if (incomplete) {
      setTimeout(() => {
        setIsStreaming(true);
        setIsLoading(true);
        setError(null);
      }, 0);
      return;
    }

    if (isAbcNotation(code)) {
      setTimeout(() => {
        setIsAbc(true);
        setError(null);
        if (likelyStreaming) {
          setIsStreaming(true);
        }
      }, 0);
    } else {
      setTimeout(() => {
        setIsAbc(false);
        if (likelyStreaming) {
          setIsStreaming(true);
          setError(null);
        } else {
          setError('Unable to detect ABC notation. Expected ABC notation starting with headers like X:, T:, M:, L:, or K:');
          setIsLoading(false);
          setIsStreaming(false);
        }
      }, 0);
    }
  }, [code]);

  // Second effect: Render ABC notation after container is mounted
  useEffect(() => {
    if (!isAbc || !code.trim()) {
      return;
    }

    // If streaming, debounce the render
    if (isStreaming) {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }

      debounceTimerRef.current = setTimeout(() => {
        setIsStreaming(false);
      }, 400);
    }

    let cancelled = false;
    const effectAudioTarget = audioControlsRef.current;

    const renderAbc = async () => {
      try {
        setIsLoading(true);
        setPlaybackError(null);
        setHasRenderedTune(false);

        // Wait for container to be available (with retries)
        let retries = 0;
        const maxRetries = 10;
        while (!containerRef.current && retries < maxRetries) {
          await new Promise(resolve => setTimeout(resolve, 50));
          retries++;
        }

        if (!containerRef.current) {
          throw new Error('Container element not found after waiting');
        }

        const abcjsLib = await loadAbcjs();

        // Clear previous content
        containerRef.current.innerHTML = '';

        // Render ABC notation
        const renderedTunes = abcjsLib.renderAbc(containerRef.current, normalizeAbcForRendering(code), {
          responsive: 'resize',
          staffwidth: 740,
          paddingleft: 0,
          paddingright: 0,
          paddingtop: 15,
          paddingbottom: 15,
          scale: 1.0,
        });

        if (cancelled) return;

        const renderedTune = renderedTunes[0];
        renderedTuneRef.current = renderedTune ?? null;
        setHasRenderedTune(Boolean(renderedTune));

        const audioTarget = effectAudioTarget;
        const synth = abcjsLib.synth;
        const canPlayAudio = Boolean(renderedTune && audioTarget && synth?.supportsAudio());
        setAudioSupported(canPlayAudio);

        if (canPlayAudio && renderedTune && audioTarget && synth && containerRef.current) {
          const controller = prepareSynthController(synth, renderedTune, audioTarget, containerRef.current, playerId, {
            playPause: t('markdown.music.playPauseTitle'),
            restart: t('markdown.music.restartTitle'),
            seek: t('markdown.music.seekTitle'),
            tempo: t('markdown.music.tempoTitle'),
          });

          if (cancelled) {
            void controller.pause();
            return;
          }

          synthControllerRef.current = controller;
        }

        setError(null);
        setIsLoading(false);
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Failed to render ABC notation';
        setError(errorMessage);
        setIsLoading(false);
      }
    };

    renderAbc();

    return () => {
      cancelled = true;
      musicPlayerPausers.delete(playerId);
      if (activeMusicPlayerId === playerId) activeMusicPlayerId = null;
      void synthControllerRef.current?.pause();
      synthControllerRef.current = null;
      renderedTuneRef.current = null;
      if (effectAudioTarget) effectAudioTarget.innerHTML = '';
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [code, isAbc, isStreaming, playerId, t]);

  if (!code.trim()) {
    return null;
  }

  if (error) {
    return (
      <div className="graph-error">
        <div className="graph-error-header">
          <div className="graph-error-icon">⚠️</div>
          <div className="graph-error-content">
            <div className="graph-error-title">ABC Notation Rendering Error</div>
            <div className="graph-error-message">{error}</div>
          </div>
        </div>
        <button
          className="graph-error-toggle"
          onClick={() => setShowErrorDetails(!showErrorDetails)}
          type="button"
        >
          {showErrorDetails ? 'Hide' : 'Show'} Details
        </button>
        {showErrorDetails && (
          <details className="graph-error-details" open>
            <summary style={{ cursor: 'pointer', marginBottom: '8px', fontWeight: 500 }}>
              ABC Notation Code
            </summary>
            <pre style={{ 
              marginTop: '8px', 
              fontSize: '0.8em', 
              opacity: 0.8,
              padding: '8px',
              background: 'rgba(0, 0, 0, 0.05)',
              borderRadius: '4px',
              overflow: 'auto',
              maxHeight: '200px'
            }}>
              <code>{code}</code>
            </pre>
          </details>
        )}
      </div>
    );
  }

  // Show loading/streaming state
  if ((isLoading || isStreaming) && !isAbc) {
    return (
      <div className="graph-container music-container abc-container">
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '30px 20px',
          color: 'var(--md-text-secondary, #6b7280)',
          minHeight: '120px',
        }}>
          <svg
            style={{
              animation: 'spin 1s linear infinite',
              marginBottom: '10px',
              width: '28px',
              height: '28px',
            }}
            viewBox="0 0 24 24"
            fill="none"
          >
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" strokeDasharray="32" strokeLinecap="round" />
          </svg>
          <span style={{ fontWeight: 500, fontSize: '14px' }}>
            {isStreaming ? 'Receiving music notation...' : 'Loading music notation...'}
          </span>
          <style>{`
            @keyframes spin {
              from { transform: rotate(0deg); }
              to { transform: rotate(360deg); }
            }
          `}</style>
        </div>
      </div>
    );
  }

  const handleExportPng = async () => {
    const svgEl = containerRef.current?.querySelector('svg') as SVGSVGElement | null;
    if (!svgEl) return;
    setExportingPng(true);
    await exportSvgAsPng(svgEl, 'music-notation.png');
    setExportingPng(false);
  };

  const handleExportMidi = async () => {
    const renderedTune = renderedTuneRef.current;
    if (!renderedTune) return;

    setExportingMidi(true);
    setPlaybackError(null);
    try {
      const abcjsLib = await loadAbcjs();
      const midiBuffer = abcjsLib.synth?.getMidiFile(renderedTune, { midiOutputType: 'binary', chordsOff: true });
      if (!midiBuffer) throw new Error('MIDI export is unavailable');

      const title = renderedTune.metaText?.title?.trim() || 'music-score';
      const safeTitle = title
        .normalize('NFKD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-zA-Z0-9_-]+/g, '-')
        .replace(/^-+|-+$/g, '') || 'music-score';
      const objectUrl = URL.createObjectURL(new Blob([midiBuffer], { type: 'audio/midi' }));
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = `${safeTitle}.mid`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
    } catch {
      setPlaybackError(t('markdown.music.midiExportFailure'));
    } finally {
      setExportingMidi(false);
    }
  };

  const handleAudioControlClickCapture = (event: ReactMouseEvent<HTMLDivElement>) => {
    const target = event.target as Element;
    const playButton = target.closest<HTMLButtonElement>('.abcjs-midi-start');
    const controller = synthControllerRef.current;
    const audioTarget = audioControlsRef.current;
    if (!playButton || !controller || !audioTarget) return;

    event.preventDefault();
    event.stopPropagation();
    event.nativeEvent.stopImmediatePropagation();

    const isCurrentlyPlaying = playButton.classList.contains('abcjs-pushed');
    if (!isCurrentlyPlaying) {
      activeMusicPlayerId = playerId;
      pauseOtherMusicPlayers(playerId);
      setPlaybackError(null);
      playButton.classList.add('abcjs-loading');
    } else if (activeMusicPlayerId === playerId) {
      activeMusicPlayerId = null;
    }

    const playbackAction = isCurrentlyPlaying ? controller.pause() : controller.play();

    void playbackAction
      .then(async () => {
        if (synthControllerRef.current !== controller) {
          await controller.pause();
          return;
        }
        if (!isCurrentlyPlaying && activeMusicPlayerId !== playerId) {
          await controller.pause();
          return;
        }
        if (!isCurrentlyPlaying) {
          setSecondaryControlsDisabled(audioTarget, false);
        }
      })
      .catch(() => {
        if (synthControllerRef.current !== controller) return;
        void controller.pause();
        if (activeMusicPlayerId === playerId) activeMusicPlayerId = null;
        playButton.classList.remove('abcjs-pushed');
        setPlaybackError(t('markdown.music.playbackFailure'));

        const synth = abcjs?.synth;
        const tune = renderedTuneRef.current;
        if (synth && tune) {
          synthControllerRef.current = prepareSynthController(
            synth,
            tune,
            audioTarget,
            playerId,
            {
              playPause: t('markdown.music.playPauseTitle'),
              restart: t('markdown.music.restartTitle'),
              seek: t('markdown.music.seekTitle'),
              tempo: t('markdown.music.tempoTitle'),
            },
          );
        }
      })
      .finally(() => playButton.classList.remove('abcjs-loading'));
  };

  // Render ABC notation - always render container so ref is available
  if (isAbc) {
    return (
      <div
        className="graph-container music-container abc-container"
        style={{
          padding: '16px',
          position: 'relative',
          flexDirection: 'column',
          alignItems: 'stretch',
        }}
      >
        {!isLoading && !isStreaming && (
          <div className="graph-action-bar">
            <button
              className="graph-action-button"
              type="button"
              onClick={() => copyCodeToClipboard(code, setCopiedCode)}
              title={copiedCode ? t('markdown.codeBlock.copied') : t('markdown.codeBlock.copyTitle')}
              aria-label={t('markdown.music.copyNotationAriaLabel')}
            >
              {copiedCode ? (
                <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M13.5 4.5L6 12L2.5 8.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
              ) : (
                <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M5.5 4.5H3.5C2.94772 4.5 2.5 4.94772 2.5 5.5V12.5C2.5 13.0523 2.94772 13.5 3.5 13.5H10.5C11.0523 13.5 11.5 13.0523 11.5 12.5V10.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/><path d="M13.5 9.5V3.5C13.5 2.94772 13.0523 2.5 12.5 2.5H6.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
              )}
              <span>{copiedCode ? t('markdown.codeBlock.copied') : t('markdown.codeBlock.copyLabel')}</span>
            </button>
            <button
              className="graph-action-button"
              type="button"
              onClick={handleExportPng}
              title={t('markdown.music.exportPngTitle')}
              aria-label={t('markdown.music.exportPngAriaLabel')}
              disabled={exportingPng}
            >
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M8 2v8M5 7l3 3 3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/><path d="M3 11v2a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1v-2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
              <span>{exportingPng ? 'Exporting…' : 'PNG'}</span>
            </button>
            <button
              className="graph-action-button"
              type="button"
              onClick={handleExportMidi}
              title={t('markdown.music.exportMidiTitle')}
              aria-label={t('markdown.music.exportMidiAriaLabel')}
              disabled={exportingMidi || !hasRenderedTune}
            >
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M8 2v8M5 7l3 3 3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/><path d="M3 11v2a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1v-2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
              <span>{exportingMidi ? t('markdown.music.exporting') : 'MIDI'}</span>
            </button>
          </div>
        )}
        {isStreaming && (
          <div
            style={{
              position: 'absolute',
              top: '8px',
              right: '8px',
              display: 'flex',
              alignItems: 'center',
              padding: '4px 8px',
              backgroundColor: 'rgba(59, 130, 246, 0.1)',
              borderRadius: '4px',
              fontSize: '12px',
              color: '#3b82f6',
              zIndex: 10,
            }}
          >
            <svg
              style={{
                animation: 'spin 1s linear infinite',
                marginRight: '4px',
                width: '12px',
                height: '12px'
              }}
              viewBox="0 0 24 24"
              fill="none"
            >
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" strokeDasharray="32" strokeLinecap="round" />
            </svg>
            Updating...
            <style>{`
              @keyframes spin {
                from { transform: rotate(0deg); }
                to { transform: rotate(360deg); }
              }
            `}</style>
          </div>
        )}
        {isLoading && !isStreaming && (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '20px',
            color: 'var(--md-text-secondary, #6b7280)',
            minHeight: '80px',
          }}>
            <svg
              style={{
                animation: 'spin 1s linear infinite',
                marginBottom: '8px',
                width: '24px',
                height: '24px',
              }}
              viewBox="0 0 24 24"
              fill="none"
            >
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" strokeDasharray="32" strokeLinecap="round" />
            </svg>
            <span style={{ fontSize: '13px' }}>{t('markdown.music.rendering')}</span>
            <style>{`
              @keyframes spin {
                from { transform: rotate(0deg); }
                to { transform: rotate(360deg); }
              }
            `}</style>
          </div>
        )}
        <div
          ref={containerRef}
          style={{
            display: 'flex',
            justifyContent: 'center',
            overflow: 'auto',
          }}
        />
        <div
          ref={audioControlsRef}
          className="music-playback-controls"
          onClickCapture={handleAudioControlClickCapture}
          hidden={isLoading || isStreaming || !audioSupported}
        />
        {!isLoading && !isStreaming && !audioSupported && (
          <div className="music-playback-message" role="status">
            {t('markdown.music.audioUnsupported')}
          </div>
        )}
        {playbackError && (
          <div className="music-playback-message music-playback-error" role="alert">
            {playbackError}
          </div>
        )}
      </div>
    );
  }

  return null;
};
