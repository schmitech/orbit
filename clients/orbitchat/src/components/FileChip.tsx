import { CircleAlert, Loader2, X } from 'lucide-react';
import { getFileThumbnail, getFileTypeVisual } from '../utils/fileTypeVisuals';

export type FileChipStatus = 'uploading' | 'processing' | 'completed' | 'error';

interface FileChipProps {
  filename: string;
  fileId?: string;
  status: FileChipStatus;
  statusText?: string;
  errorMessage?: string;
  onRemove?: () => void;
  removeTitle?: string;
  className?: string;
}

export function FileChip({
  filename,
  fileId,
  status,
  statusText,
  errorMessage,
  onRemove,
  removeTitle,
  className = '',
}: FileChipProps) {
  const isBusy = status === 'uploading' || status === 'processing';
  const isError = status === 'error';
  const visual = getFileTypeVisual(filename);
  const thumbnailUrl = fileId ? getFileThumbnail(fileId) : undefined;
  const Icon = visual.Icon;

  const subtitle = isError
    ? errorMessage || statusText
    : statusText || visual.label;

  return (
    <div
      className={`group relative flex w-full min-w-[168px] max-w-[240px] items-center gap-2.5 rounded-xl border p-2 transition-colors ${
        isError
          ? 'border-red-200 bg-red-50 dark:border-red-500/30 dark:bg-[#1a1010]'
          : 'border-gray-200 bg-gray-50 dark:border-[#242424] dark:bg-[#101010]'
      } ${className}`}
    >
      <div
        className={`flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-lg text-white ${
          isError ? 'bg-red-500' : visual.colorClass
        }`}
      >
        {thumbnailUrl && !isError ? (
          <div className="relative h-full w-full">
            <img src={thumbnailUrl} alt="" className="h-full w-full object-cover" />
            {isBusy && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/35">
                <Loader2 className="h-[18px] w-[18px] animate-spin text-white drop-shadow" />
              </div>
            )}
          </div>
        ) : isBusy ? (
          <Loader2 className="h-[18px] w-[18px] animate-spin" />
        ) : isError ? (
          <CircleAlert className="h-[18px] w-[18px]" />
        ) : (
          <Icon className="h-[18px] w-[18px]" />
        )}
      </div>

      <div className="min-w-0 flex-1">
        <p
          className={`truncate text-sm font-medium leading-tight ${
            isError ? 'text-red-700 dark:text-red-300' : 'text-[#353740] dark:text-[#ececf1]'
          }`}
          title={filename}
        >
          {filename}
        </p>
        {subtitle && (
          <p
            className={`truncate text-xs leading-tight mt-0.5 ${
              isError ? 'text-red-500 dark:text-red-400' : 'text-gray-400 dark:text-[#8e8ea0]'
            }`}
          >
            {subtitle}
          </p>
        )}
      </div>

      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          title={removeTitle}
          aria-label={removeTitle}
          className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full border border-gray-200 bg-white text-gray-500 shadow-sm transition-colors hover:text-red-600 dark:border-[#3c3f4a] dark:bg-[#2d2f39] dark:text-[#bfc2cd] dark:hover:text-red-400"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}
