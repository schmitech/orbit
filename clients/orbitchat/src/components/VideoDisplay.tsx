import { useState, useEffect, useRef } from 'react';
import { ChevronDown, ChevronUp, Download, X, Maximize2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface VideoDisplayProps {
  video?: string;          // base64-encoded video data (present during live session)
  videoUrl?: string;       // persistent server-side path (used after refresh)
  videoFormat?: string;    // "mp4"
  revisedPrompt?: string;  // provider-rewritten prompt
  adapterName?: string | null;
}

const VIDEO_FETCH_RETRY_DELAYS_MS = [750, 1500, 3000, 5000];
const RETRYABLE_VIDEO_FETCH_STATUSES = new Set([403, 404, 409, 425, 429, 500, 502, 503, 504]);

const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

/**
 * Renders a generated video with a download button and fullscreen on click.
 *
 * Priority:
 *  1. `video` (base64) — available immediately after generation.
 *     Stripped from localStorage to avoid the 5 MB quota.
 *  2. `videoUrl` — a relative path returned by the server once the video has
 *     been persisted server-side. Survives localStorage and page refresh.
 *     Fetched via JS so the Express proxy can inject the API key.
 */
export function VideoDisplay({ video, videoUrl, videoFormat = 'mp4', revisedPrompt, adapterName }: VideoDisplayProps) {
  const { t } = useTranslation();
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [promptExpanded, setPromptExpanded] = useState(false);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const blobUrlRef = useRef<string | null>(null);

  // Fetch the video from the server when we only have a URL (e.g. after refresh)
  useEffect(() => {
    if (video || !videoUrl) return;

    let cancelled = false;

    (async () => {
      try {
        const resolvedAdapterName =
          adapterName ||
          (typeof window !== 'undefined'
            ? window.localStorage.getItem('chat-adapter-name')
            : null);

        let res: Response | null = null;
        for (let attempt = 0; attempt <= VIDEO_FETCH_RETRY_DELAYS_MS.length; attempt += 1) {
          res = await fetch(videoUrl, {
            headers: resolvedAdapterName ? { 'X-Adapter-Name': resolvedAdapterName } : {},
          });

          if (
            res.ok ||
            !RETRYABLE_VIDEO_FETCH_STATUSES.has(res.status) ||
            attempt === VIDEO_FETCH_RETRY_DELAYS_MS.length
          ) {
            break;
          }

          await delay(VIDEO_FETCH_RETRY_DELAYS_MS[attempt]);
          if (cancelled) return;
        }

        if (!res || !res.ok) {
          console.warn('[VideoDisplay] Server returned', res?.status, 'for', videoUrl);
          return;
        }
        if (cancelled) return;

        const bytes = await res.arrayBuffer();
        if (cancelled) return;

        const blob = new Blob([bytes], { type: `video/${videoFormat}` });
        const url = URL.createObjectURL(blob);
        blobUrlRef.current = url;
        setBlobUrl(url);
      } catch (err) {
        console.warn('[VideoDisplay] Failed to fetch video from', videoUrl, err);
      }
    })();

    return () => {
      cancelled = true;
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current);
        blobUrlRef.current = null;
      }
    };
  }, [videoUrl, video, videoFormat, adapterName]);

  const dataUrl = video ? `data:video/${videoFormat};base64,${video}` : null;
  const src = dataUrl ?? blobUrl;

  useEffect(() => {
    if (!lightboxOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setLightboxOpen(false); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [lightboxOpen]);

  const handleDownload = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!src) return;
    const a = document.createElement('a');
    a.href = src;
    a.download = `generated-video.${videoFormat}`;
    a.click();
  };

  if (!src) return null;

  return (
    <>
      <div className="generated-video-wrapper" style={{ marginTop: '0.75rem' }}>
        <div style={{ position: 'relative', display: 'inline-block', maxWidth: '100%' }}>
          <video
            src={src}
            controls
            style={{
              maxWidth: '100%',
              maxHeight: '480px',
              borderRadius: '8px',
              display: 'block',
              backgroundColor: '#000',
            }}
          />
          <div
            style={{
              position: 'absolute',
              bottom: '48px',
              right: '8px',
              display: 'flex',
              gap: '6px',
            }}
          >
            <button
              onClick={handleDownload}
              title={t('videoDisplay.downloadVideoTooltip')}
              style={{
                background: 'rgba(0,0,0,0.55)',
                border: 'none',
                borderRadius: '6px',
                padding: '5px',
                cursor: 'pointer',
                color: '#fff',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <Download size={14} />
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); setLightboxOpen(true); }}
              title={t('videoDisplay.viewFullSizeTooltip')}
              style={{
                background: 'rgba(0,0,0,0.55)',
                border: 'none',
                borderRadius: '6px',
                padding: '5px',
                cursor: 'pointer',
                color: '#fff',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <Maximize2 size={14} />
            </button>
          </div>
        </div>
        {revisedPrompt && (
          <div style={{ marginTop: '8px', maxWidth: '480px' }}>
            <button
              type="button"
              onClick={() => setPromptExpanded((expanded) => !expanded)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: 0,
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                fontSize: '0.75rem',
                fontWeight: 500,
                opacity: 0.72,
              }}
              aria-expanded={promptExpanded}
            >
              {promptExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              {promptExpanded ? t('videoDisplay.hidePrompt') : t('videoDisplay.showPrompt')}
            </button>
            {promptExpanded && (
              <div
                style={{
                  marginTop: '8px',
                  padding: '8px 10px',
                  background: 'rgba(128,128,128,0.08)',
                  borderRadius: '6px',
                }}
              >
                <span
                  style={{
                    display: 'block',
                    fontSize: '0.65rem',
                    fontWeight: 600,
                    opacity: 0.5,
                    textTransform: 'uppercase',
                    letterSpacing: '0.06em',
                    marginBottom: '3px',
                  }}
                >
                  {t('videoDisplay.promptLabel')}
                </span>
                <span style={{ fontSize: '0.8rem', lineHeight: 1.45, opacity: 0.85 }}>
                  {revisedPrompt}
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      {lightboxOpen && (
        <div
          onClick={() => setLightboxOpen(false)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.9)',
            zIndex: 9999,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <button
            onClick={(e) => { e.stopPropagation(); setLightboxOpen(false); }}
            style={{
              position: 'fixed',
              top: '16px',
              right: '16px',
              background: 'rgba(255,255,255,0.15)',
              border: 'none',
              borderRadius: '50%',
              padding: '8px',
              cursor: 'pointer',
              color: '#fff',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <X size={20} />
          </button>
          <video
            src={src}
            controls
            autoPlay
            style={{ maxWidth: '92vw', maxHeight: '92vh', borderRadius: '8px' }}
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </>
  );
}
