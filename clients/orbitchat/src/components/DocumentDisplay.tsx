import { useEffect, useMemo, useRef, useState, type MouseEvent } from 'react';
import { Download, ExternalLink, FileCode, FileSpreadsheet, FileText, Presentation, X } from 'lucide-react';
import { getAccessToken } from '../auth/tokenStore';
import { getUserIdHeaderValue } from '../auth/userId';
import { MarkdownRenderer } from './markdown/MarkdownRenderer';

interface DocumentDisplayProps {
  document?: string;
  documentUrl?: string;
  documentFormat?: string;
  revisedPrompt?: string;
  adapterName?: string | null;
}

type LoadState = 'idle' | 'loading' | 'ready' | 'error';

const MIME_TYPES: Record<string, string> = {
  pdf: 'application/pdf',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  md: 'text/markdown',
  csv: 'text/csv',
};

const FORMAT_LABELS: Record<string, string> = {
  pdf: 'PDF',
  docx: 'Word document',
  xlsx: 'Excel workbook',
  pptx: 'PowerPoint deck',
  md: 'Markdown document',
  csv: 'CSV file',
};

const DOCX_PRIVATE_USE_BULLET_RE =
  /[\uE000-\uF8FF]|\\[eE][0-9a-fA-F]{2,3}|\\[fF][0-8][0-9a-fA-F]{2,3}/;
const DOCX_PREVIEW_NUM_RULE_RE =
  /((?:p\.)?generated-docx-preview-num-\d+-\d+:before\s*\{[^}]*?)content\s*:\s*"([^"]*)"\s*;([^}]*?\})/g;

function normalizeDocxBulletContent(content: string) {
  if (!DOCX_PRIVATE_USE_BULLET_RE.test(content)) {
    return null;
  }

  const suffix = content.match(/(?:\\9|\t|\u00A0| )+$/)?.[0] || '\\9';
  return `•${suffix}`;
}

function normalizeDocxPreviewBullets(container: HTMLElement) {
  const styleElements = Array.from(container.querySelectorAll('style'));

  styleElements.forEach(styleElement => {
    const css = styleElement.textContent;
    if (!css || !DOCX_PRIVATE_USE_BULLET_RE.test(css)) {
      return;
    }

    styleElement.textContent = css.replace(
      DOCX_PREVIEW_NUM_RULE_RE,
      (match, before: string, content: string, after: string) => {
        const normalizedContent = normalizeDocxBulletContent(content);
        if (!normalizedContent) {
          return match;
        }
        const sanitizedAfter = after.replace(/\s*font-family\s*:\s*[^;{}]+;?/gi, '');
        return `${before}content: "${normalizedContent}";${sanitizedAfter}`;
      }
    );
  });

  const symbolSpans = Array.from(container.querySelectorAll<HTMLSpanElement>('span[style*="font-family"]'));
  symbolSpans.forEach(span => {
    if (!/\b(symbol|wingdings|webdings)\b/i.test(span.style.fontFamily)) {
      return;
    }

    const text = span.textContent || '';
    if (DOCX_PRIVATE_USE_BULLET_RE.test(text)) {
      span.textContent = text.replace(DOCX_PRIVATE_USE_BULLET_RE, '•');
      span.style.fontFamily = '';
    }
  });
}

function normalizeFormat(format?: string): string {
  const normalized = (format || 'pdf').toLowerCase().replace(/^\./, '');
  return normalized || 'pdf';
}

function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = window.atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes.buffer;
}

function getDocumentIcon(format: string) {
  if (format === 'xlsx' || format === 'csv') return <FileSpreadsheet className="h-5 w-5" />;
  if (format === 'pptx') return <Presentation className="h-5 w-5" />;
  if (format === 'md') return <FileCode className="h-5 w-5" />;
  return <FileText className="h-5 w-5" />;
}

export function DocumentDisplay({
  document,
  documentUrl,
  documentFormat = 'pdf',
  revisedPrompt,
  adapterName,
}: DocumentDisplayProps) {
  const format = normalizeFormat(documentFormat);
  const [status, setStatus] = useState<LoadState>(document || documentUrl ? 'loading' : 'idle');
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [arrayBuffer, setArrayBuffer] = useState<ArrayBuffer | null>(null);
  const [xlsxRows, setXlsxRows] = useState<string[][]>([]);
  const [xlsxSheetName, setXlsxSheetName] = useState<string>('');
  const [mdContent, setMdContent] = useState<string | null>(null);
  const [csvRows, setCsvRows] = useState<string[][]>([]);
  const [csvTotalRows, setCsvTotalRows] = useState(0);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const blobUrlRef = useRef<string | null>(null);
  const docxContainerRef = useRef<HTMLDivElement>(null);
  const modalDocxContainerRef = useRef<HTMLDivElement>(null);

  const title = revisedPrompt || FORMAT_LABELS[format] || 'Generated document';
  const filename = useMemo(() => `generated-document.${format}`, [format]);
  const mimeType = MIME_TYPES[format] || 'application/octet-stream';

  useEffect(() => {
    if (!document && !documentUrl) {
      return;
    }

    let cancelled = false;

    const loadDocument = async () => {
      setStatus('loading');
      setErrorMessage(null);
      setXlsxRows([]);
      setXlsxSheetName('');
      setMdContent(null);
      setCsvRows([]);
      setCsvTotalRows(0);

      try {
        const bytes = document
          ? base64ToArrayBuffer(document)
          : await (async () => {
              const resolvedAdapterName =
                adapterName?.trim() ||
                (typeof window !== 'undefined'
                  ? window.localStorage.getItem('chat-adapter-name')
                  : null);
              const headers: Record<string, string> = {
                'X-User-ID': await getUserIdHeaderValue(),
              };
              if (resolvedAdapterName) {
                headers['X-Adapter-Name'] = resolvedAdapterName;
              }
              const token = await getAccessToken();
              if (token) {
                headers.Authorization = `Bearer ${token}`;
              }

              const res = await fetch(documentUrl!, {
                headers,
              });

              if (!res.ok) {
                throw new Error(`Server returned ${res.status}`);
              }

              return res.arrayBuffer();
            })();

        if (cancelled) return;

        const blob = new Blob([bytes], { type: mimeType });
        const url = URL.createObjectURL(blob);
        if (blobUrlRef.current) {
          URL.revokeObjectURL(blobUrlRef.current);
        }
        blobUrlRef.current = url;
        setBlobUrl(url);
        setArrayBuffer(bytes.slice(0));

        if (format === 'xlsx') {
          const { default: readXlsxFile } = await import('read-excel-file/browser');
          const sheets = await readXlsxFile(blob);
          const firstSheet = sheets[0];
          setXlsxSheetName(firstSheet?.sheet || 'First sheet');
          setXlsxRows(
            (firstSheet?.data || [])
              .slice(0, 100)
              .map(row => row.slice(0, 30).map(cell => cell === null || cell === undefined ? '' : String(cell)))
          );
        }

        if (format === 'md') {
          setMdContent(new TextDecoder('utf-8').decode(bytes));
        }

        if (format === 'csv') {
          const text = new TextDecoder('utf-8').decode(bytes);
          const { default: Papa } = await import('papaparse');
          const result = Papa.parse<string[]>(text, { skipEmptyLines: true });
          setCsvTotalRows(result.data.length);
          setCsvRows(result.data.slice(0, 25));
        }

        setStatus('ready');
      } catch (error) {
        if (cancelled) return;
        console.warn('[DocumentDisplay] Failed to load document from', documentUrl, error);
        setErrorMessage(error instanceof Error ? error.message : 'Unable to load document');
        setStatus('error');
      }
    };

    loadDocument();

    return () => {
      cancelled = true;
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current);
        blobUrlRef.current = null;
      }
    };
  }, [adapterName, document, documentUrl, format, mimeType]);

  useEffect(() => {
    if (status !== 'ready' || format !== 'docx' || !arrayBuffer || !docxContainerRef.current) {
      return;
    }

    const container = docxContainerRef.current;
    container.replaceChildren();
    import('docx-preview').then(async ({ renderAsync }) => {
      await renderAsync(arrayBuffer.slice(0), container, undefined, {
        className: 'generated-docx-preview',
        inWrapper: false,
        ignoreWidth: true,
        ignoreHeight: true,
      });
      normalizeDocxPreviewBullets(container);
    }).catch(error => {
      console.warn('[DocumentDisplay] Failed to render DOCX preview', error);
      setErrorMessage('Unable to render document preview');
    });
  }, [arrayBuffer, format, status]);

  useEffect(() => {
    if (!previewOpen || format !== 'docx' || !arrayBuffer || !modalDocxContainerRef.current) {
      return;
    }

    const container = modalDocxContainerRef.current;
    container.replaceChildren();
    import('docx-preview').then(async ({ renderAsync }) => {
      await renderAsync(arrayBuffer.slice(0), container, undefined, {
        className: 'generated-docx-preview',
        inWrapper: false,
        ignoreWidth: true,
        ignoreHeight: true,
      });
      normalizeDocxPreviewBullets(container);
    }).catch(error => {
      console.warn('[DocumentDisplay] Failed to render modal DOCX preview', error);
    });
  }, [arrayBuffer, format, previewOpen]);

  useEffect(() => {
    if (!previewOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setPreviewOpen(false);
    };
    window.document.addEventListener('keydown', onKey);
    return () => window.document.removeEventListener('keydown', onKey);
  }, [previewOpen]);

  const handleDownload = (e?: MouseEvent) => {
    e?.stopPropagation();
    if (!blobUrl) return;
    const a = window.document.createElement('a');
    a.href = blobUrl;
    a.download = filename;
    a.click();
  };

  const canPreviewInline = status === 'ready' && (format === 'pdf' || format === 'docx' || format === 'xlsx' || format === 'md' || format === 'csv');
  const canOpenFullPreview = canPreviewInline && format !== 'xlsx' && format !== 'csv';

  if (status === 'idle') return null;

  return (
    <>
      <div className="mt-3 max-w-full overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm dark:border-[#3b3c49] dark:bg-[#202123]">
        <div className="flex items-center gap-3 border-b border-gray-100 px-3 py-2.5 dark:border-[#3b3c49]">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-blue-50 text-blue-600 dark:bg-blue-500/10 dark:text-blue-300">
            {getDocumentIcon(format)}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-[#353740] dark:text-[#ececf1]">{title}</p>
            <p className="text-xs text-gray-500 dark:text-[#bfc2cd]">
              {FORMAT_LABELS[format] || `${format.toUpperCase()} document`}
              {status === 'loading' ? ' · Loading preview...' : ''}
              {status === 'error' ? ` · ${errorMessage || 'Preview unavailable'}` : ''}
            </p>
          </div>
          {canOpenFullPreview && (
            <button
              type="button"
              onClick={() => setPreviewOpen(true)}
              className="rounded-md p-2 text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700 dark:text-[#bfc2cd] dark:hover:bg-[#3c3f4a] dark:hover:text-[#ececf1]"
              title="Open preview"
              aria-label="Open preview"
            >
              <ExternalLink className="h-4 w-4" />
            </button>
          )}
          <button
            type="button"
            onClick={handleDownload}
            disabled={!blobUrl}
            className="rounded-md p-2 text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700 disabled:cursor-not-allowed disabled:opacity-50 dark:text-[#bfc2cd] dark:hover:bg-[#3c3f4a] dark:hover:text-[#ececf1]"
            title="Download document"
            aria-label="Download document"
          >
            <Download className="h-4 w-4" />
          </button>
        </div>

        {canPreviewInline && (
          <div className="max-h-[460px] overflow-auto bg-gray-50 dark:bg-[#171717]">
            {format === 'pdf' && blobUrl && (
              <iframe
                src={blobUrl}
                title={title}
                className="block h-[460px] w-full border-0 bg-white"
              />
            )}
            {format === 'docx' && (
              <div
                ref={docxContainerRef}
                className="min-h-[240px] bg-white p-5 text-sm text-[#111827] dark:bg-white dark:text-[#111827]"
              />
            )}
            {format === 'xlsx' && (
              <div className="p-3">
                {xlsxSheetName && (
                  <p className="mb-2 text-xs font-medium text-gray-500 dark:text-[#bfc2cd]">{xlsxSheetName}</p>
                )}
                <div className="overflow-auto rounded-md border border-gray-200 bg-white dark:border-[#3b3c49] dark:bg-[#202123]">
                  <table className="min-w-full border-collapse text-left text-xs">
                    <tbody>
                      {xlsxRows.length > 0 ? xlsxRows.map((row, rowIndex) => (
                        <tr key={rowIndex} className={rowIndex === 0 ? 'bg-gray-50 font-medium dark:bg-white/5' : undefined}>
                          {row.map((cell, cellIndex) => (
                            <td key={cellIndex} className="max-w-[220px] truncate border-b border-r border-gray-100 px-2 py-1.5 text-[#353740] dark:border-[#3b3c49] dark:text-[#ececf1]">
                              {cell}
                            </td>
                          ))}
                        </tr>
                      )) : (
                        <tr>
                          <td className="px-3 py-4 text-sm text-gray-500 dark:text-[#bfc2cd]">No sheet data found.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            {format === 'md' && mdContent !== null && (
              <div className="bg-white p-5 text-sm text-[#111827] dark:bg-[#171717] dark:text-[#ececf1]">
                <MarkdownRenderer content={mdContent} disableMath />
              </div>
            )}
            {format === 'csv' && (
              <div className="p-3">
                {csvTotalRows > 25 && (
                  <p className="mb-2 text-xs text-gray-500 dark:text-[#bfc2cd]">
                    Showing first 25 of {csvTotalRows} rows — download for the full file.
                  </p>
                )}
                <div className="overflow-auto rounded-md border border-gray-200 bg-white dark:border-[#3b3c49] dark:bg-[#202123]">
                  <table className="min-w-full border-collapse text-left text-xs">
                    <tbody>
                      {csvRows.length > 0 ? csvRows.map((row, rowIndex) => (
                        <tr key={rowIndex} className={rowIndex === 0 ? 'bg-gray-50 font-medium dark:bg-white/5' : undefined}>
                          {row.map((cell, cellIndex) => (
                            <td key={cellIndex} className="max-w-[220px] truncate border-b border-r border-gray-100 px-2 py-1.5 text-[#353740] dark:border-[#3b3c49] dark:text-[#ececf1]">
                              {cell}
                            </td>
                          ))}
                        </tr>
                      )) : (
                        <tr>
                          <td className="px-3 py-4 text-sm text-gray-500 dark:text-[#bfc2cd]">No data found.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {status === 'ready' && !canPreviewInline && (
          <div className="px-3 py-4 text-sm text-gray-600 dark:text-[#bfc2cd]">
            Preview is not available for this format. Use download to open it locally.
          </div>
        )}
      </div>

      {previewOpen && blobUrl && (
        <div
          onClick={() => setPreviewOpen(false)}
          className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/85 p-4"
        >
          <button
            onClick={(e) => { e.stopPropagation(); setPreviewOpen(false); }}
            className="fixed right-4 top-4 flex items-center rounded-full border-0 bg-white/15 p-2 text-white"
            title="Close preview"
            aria-label="Close preview"
          >
            <X className="h-5 w-5" />
          </button>
          <div
            onClick={(e) => e.stopPropagation()}
            className="h-[92vh] w-[92vw] overflow-auto rounded-lg bg-white"
          >
            {format === 'pdf' && (
              <iframe src={blobUrl} title={title} className="h-full w-full border-0" />
            )}
            {format === 'docx' && (
              <div ref={modalDocxContainerRef} className="min-h-full bg-white p-8 text-[#111827]" />
            )}
            {format === 'md' && mdContent !== null && (
              <div className="min-h-full bg-white p-8 text-sm text-[#111827]">
                <MarkdownRenderer content={mdContent} disableMath />
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
