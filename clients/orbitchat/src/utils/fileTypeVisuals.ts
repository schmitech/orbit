import {
  File,
  FileArchive,
  FileAudio,
  FileCode,
  FileImage,
  FileSpreadsheet,
  FileText,
  FileVideo,
  Presentation,
  type LucideIcon,
} from 'lucide-react';

export interface FileTypeVisual {
  Icon: LucideIcon;
  colorClass: string;
  label: string;
  isImage: boolean;
}

const EXTENSION_GROUPS: Array<{ extensions: string[]; Icon: LucideIcon; colorClass: string }> = [
  { extensions: ['pdf'], Icon: FileText, colorClass: 'bg-red-500' },
  { extensions: ['doc', 'docx'], Icon: FileText, colorClass: 'bg-blue-500' },
  { extensions: ['xls', 'xlsx', 'csv'], Icon: FileSpreadsheet, colorClass: 'bg-emerald-600' },
  { extensions: ['ppt', 'pptx'], Icon: Presentation, colorClass: 'bg-orange-500' },
  { extensions: ['png', 'jpg', 'jpeg', 'webp', 'tiff', 'gif'], Icon: FileImage, colorClass: 'bg-violet-500' },
  { extensions: ['wav', 'mp3', 'ogg', 'flac', 'webm', 'm4a', 'aac'], Icon: FileAudio, colorClass: 'bg-teal-600' },
  { extensions: ['mp4', 'mov', 'avi', 'mkv'], Icon: FileVideo, colorClass: 'bg-pink-600' },
  { extensions: ['zip', 'rar', '7z', 'tar', 'gz'], Icon: FileArchive, colorClass: 'bg-amber-600' },
  {
    extensions: [
      'js', 'mjs', 'ts', 'tsx', 'py', 'java', 'sql', 'cpp', 'cxx', 'cc', 'c', 'h', 'hpp',
      'go', 'rs', 'rb', 'php', 'sh', 'bash', 'zsh', 'yaml', 'yml', 'xml', 'css', 'scss',
      'sass', 'less', 'json', 'html', 'vtt',
    ],
    Icon: FileCode,
    colorClass: 'bg-slate-500',
  },
];

const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'webp', 'tiff', 'gif']);

function getExtension(filename: string): string {
  const match = /\.([a-z0-9]+)$/i.exec(filename.trim());
  return match ? match[1].toLowerCase() : '';
}

export function getFileTypeVisual(filename: string): FileTypeVisual {
  const extension = getExtension(filename);
  const group = EXTENSION_GROUPS.find(g => g.extensions.includes(extension));

  return {
    Icon: group?.Icon ?? File,
    colorClass: group?.colorClass ?? 'bg-gray-400 dark:bg-gray-500',
    label: extension ? extension.toUpperCase() : '',
    isImage: IMAGE_EXTENSIONS.has(extension),
  };
}

// Local blob-URL previews for images, keyed by the server-assigned file_id.
// Generated once at selection time (while the File object is still in memory)
// and read by both the upload-progress chip and the post-upload attached-file
// chip so the same thumbnail persists across that transition.
const thumbnailUrlsByFileId = new Map<string, string>();

export function setFileThumbnail(fileId: string, objectUrl: string): void {
  const existing = thumbnailUrlsByFileId.get(fileId);
  if (existing && existing !== objectUrl) {
    URL.revokeObjectURL(existing);
  }
  thumbnailUrlsByFileId.set(fileId, objectUrl);
}

export function getFileThumbnail(fileId: string): string | undefined {
  return thumbnailUrlsByFileId.get(fileId);
}

export function revokeFileThumbnail(fileId: string): void {
  const existing = thumbnailUrlsByFileId.get(fileId);
  if (existing) {
    URL.revokeObjectURL(existing);
    thumbnailUrlsByFileId.delete(fileId);
  }
}
