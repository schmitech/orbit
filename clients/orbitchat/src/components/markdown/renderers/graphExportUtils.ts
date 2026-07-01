export const copyCodeToClipboard = async (text: string, setFeedback: (v: boolean) => void): Promise<void> => {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;opacity:0';
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand('copy');
    } catch {
      // fallback failed — ignore
    }
    document.body.removeChild(ta);
  }
  setFeedback(true);
  setTimeout(() => setFeedback(false), 2000);
};

const downloadFile = (href: string, filename: string) => {
  const a = document.createElement('a');
  a.href = href;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};

export const exportSvgAsPng = (
  svgEl: SVGSVGElement,
  filename: string,
  explicitDims?: { w: number; h: number }
): Promise<void> =>
  new Promise((resolve) => {
    const bbox = explicitDims ? null : svgEl.getBoundingClientRect();
    const w = explicitDims?.w ?? Math.max(bbox?.width ?? 0, 400);
    const h = explicitDims?.h ?? Math.max(bbox?.height ?? 0, 200);

    const clone = svgEl.cloneNode(true) as SVGSVGElement;
    clone.setAttribute('width', String(w));
    clone.setAttribute('height', String(h));

    const svgStr = new XMLSerializer().serializeToString(clone);

    // Fall back to SVG download when canvas export is blocked (e.g. tainted canvas
    // from <foreignObject> or external font references in Mermaid output).
    const fallbackToSvg = () => {
      const svgBlob = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' });
      const svgUrl = URL.createObjectURL(svgBlob);
      downloadFile(svgUrl, filename.replace(/\.png$/i, '.svg'));
      resolve();
    };

    // Base64 data URI avoids some blob-URL CORS taint issues.
    let dataUri: string;
    try {
      dataUri = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svgStr)));
    } catch {
      fallbackToSvg();
      return;
    }

    const img = new Image();
    img.onload = () => {
      const scale = window.devicePixelRatio || 2;
      const canvas = document.createElement('canvas');
      canvas.width = w * scale;
      canvas.height = h * scale;
      const ctx = canvas.getContext('2d')!;
      ctx.scale(scale, scale);
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, w, h);
      ctx.drawImage(img, 0, 0, w, h);

      try {
        canvas.toBlob((pngBlob) => {
          if (!pngBlob) {
            fallbackToSvg();
            return;
          }
          const pngUrl = URL.createObjectURL(pngBlob);
          downloadFile(pngUrl, filename);
          resolve();
        }, 'image/png');
      } catch {
        // Canvas tainted (SVG references external resources) — fall back to SVG.
        fallbackToSvg();
      }
    };
    img.onerror = () => fallbackToSvg();
    img.src = dataUri;
  });
