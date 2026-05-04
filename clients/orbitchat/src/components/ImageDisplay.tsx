import { useState, useEffect, useRef } from 'react';
import { Download, X, ZoomIn } from 'lucide-react';

interface ImageDisplayProps {
  image?: string;          // base64-encoded image data (present during live session)
  imageUrl?: string;       // persistent server-side path (used after refresh)
  imageFormat?: string;    // "png", "jpeg", "webp"
  revisedPrompt?: string;  // provider-rewritten prompt (e.g. DALL-E 3)
}

/**
 * Renders a generated image with a download button and lightbox on click.
 *
 * Priority:
 *  1. `image` (base64) — available immediately after generation, used for the
 *     current session. Stripped from localStorage to avoid the 5 MB quota.
 *  2. `imageUrl` — a relative path returned by the server once the image has
 *     been persisted server-side. Survives localStorage and page refresh.
 *     Fetched via JS so the Express proxy can inject the API key.
 */
export function ImageDisplay({ image, imageUrl, imageFormat = 'png', revisedPrompt }: ImageDisplayProps) {
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const blobUrlRef = useRef<string | null>(null);

  // Fetch the image from the server when we only have a URL (e.g. after refresh)
  useEffect(() => {
    if (image || !imageUrl) return;

    let cancelled = false;

    (async () => {
      try {
        const adapterName =
          typeof window !== 'undefined'
            ? window.localStorage.getItem('chat-adapter-name')
            : null;

        const res = await fetch(imageUrl, {
          headers: adapterName ? { 'X-Adapter-Name': adapterName } : {},
        });

        if (!res.ok) {
          console.warn('[ImageDisplay] Server returned', res.status, 'for', imageUrl);
          return;
        }
        if (cancelled) return;

        const bytes = await res.arrayBuffer();
        if (cancelled) return;

        const blob = new Blob([bytes], { type: `image/${imageFormat}` });
        const url = URL.createObjectURL(blob);
        blobUrlRef.current = url;
        setBlobUrl(url);
      } catch (err) {
        console.warn('[ImageDisplay] Failed to fetch image from', imageUrl, err);
      }
    })();

    return () => {
      cancelled = true;
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current);
        blobUrlRef.current = null;
      }
    };
  }, [imageUrl, image, imageFormat]);

  const dataUrl = image ? `data:image/${imageFormat};base64,${image}` : null;
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
    a.download = `generated-image.${imageFormat}`;
    a.click();
  };

  if (!src) return null;

  return (
    <>
      <div className="generated-image-wrapper" style={{ marginTop: '0.75rem' }}>
        <div
          className="generated-image-container"
          style={{ position: 'relative', display: 'inline-block', cursor: 'zoom-in', maxWidth: '100%' }}
          onClick={() => setLightboxOpen(true)}
          title={revisedPrompt || 'Generated image — click to enlarge'}
        >
          <img
            src={src}
            alt={revisedPrompt || 'Generated image'}
            style={{
              maxWidth: '100%',
              maxHeight: '480px',
              borderRadius: '8px',
              display: 'block',
              objectFit: 'contain',
            }}
          />
          <div
            style={{
              position: 'absolute',
              bottom: '8px',
              right: '8px',
              display: 'flex',
              gap: '6px',
            }}
          >
            <button
              onClick={handleDownload}
              title="Download image"
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
              title="View full size"
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
              <ZoomIn size={14} />
            </button>
          </div>
        </div>
        {revisedPrompt && (
          <div
            style={{
              marginTop: '8px',
              padding: '8px 10px',
              background: 'rgba(128,128,128,0.08)',
              borderRadius: '6px',
              maxWidth: '480px',
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
              Prompt
            </span>
            <span style={{ fontSize: '0.8rem', lineHeight: 1.45, opacity: 0.85 }}>
              {revisedPrompt}
            </span>
          </div>
        )}
      </div>

      {lightboxOpen && (
        <div
          onClick={() => setLightboxOpen(false)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.85)',
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
          <img
            src={src}
            alt={revisedPrompt || 'Generated image'}
            style={{ maxWidth: '92vw', maxHeight: '92vh', objectFit: 'contain', borderRadius: '8px' }}
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </>
  );
}
