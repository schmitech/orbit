import { useState, useEffect } from 'react';
import { Download, X, ZoomIn } from 'lucide-react';

interface ImageDisplayProps {
  image: string;           // base64-encoded image data
  imageFormat?: string;    // "png", "jpeg", "webp"
  revisedPrompt?: string;  // provider-rewritten prompt (e.g. DALL-E 3)
}

/**
 * Renders a generated image with a download button and lightbox on click.
 */
export function ImageDisplay({ image, imageFormat = 'png', revisedPrompt }: ImageDisplayProps) {
  const [lightboxOpen, setLightboxOpen] = useState(false);

  const dataUrl = `data:image/${imageFormat};base64,${image}`;

  useEffect(() => {
    if (!lightboxOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setLightboxOpen(false); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [lightboxOpen]);

  const handleDownload = (e: React.MouseEvent) => {
    e.stopPropagation();
    const a = document.createElement('a');
    a.href = dataUrl;
    a.download = `generated-image.${imageFormat}`;
    a.click();
  };

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
            src={dataUrl}
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
          <p
            style={{
              fontSize: '0.72rem',
              opacity: 0.6,
              marginTop: '4px',
              fontStyle: 'italic',
              maxWidth: '480px',
            }}
          >
            {revisedPrompt}
          </p>
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
            src={dataUrl}
            alt={revisedPrompt || 'Generated image'}
            style={{ maxWidth: '92vw', maxHeight: '92vh', objectFit: 'contain', borderRadius: '8px' }}
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </>
  );
}
