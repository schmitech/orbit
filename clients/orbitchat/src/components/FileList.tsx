import { useState, type MouseEvent } from 'react';
import { FileText, Trash2, Paperclip } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useChatStore } from '../stores/chatStore';
import { FileAttachment } from '../types';
import { ConfirmationModal } from './ConfirmationModal';
import { debugError } from '../utils/debug';

export function FileList() {
  const { t } = useTranslation();
  const {
    conversations,
    currentConversationId,
    removeFileFromConversation
  } = useChatStore();

  const [deleteConfirmation, setDeleteConfirmation] = useState<{
    isOpen: boolean;
    fileId: string;
    filename: string;
    isDeleting: boolean;
  }>({
    isOpen: false,
    fileId: '',
    filename: '',
    isDeleting: false
  });

  const currentConversation = conversations.find(
    conv => conv.id === currentConversationId
  );
  
  const files = currentConversation?.attachedFiles || [];

  const handleDeleteFile = (event: MouseEvent<HTMLButtonElement>, file: FileAttachment) => {
    event.stopPropagation();
    setDeleteConfirmation({
      isOpen: true,
      fileId: file.file_id,
      filename: file.filename,
      isDeleting: false
    });
  };

  const confirmDelete = async () => {
    if (!currentConversationId) return;
    
    setDeleteConfirmation(prev => ({ ...prev, isDeleting: true }));
    try {
      await removeFileFromConversation(
        currentConversationId,
        deleteConfirmation.fileId
      );
      setDeleteConfirmation({
        isOpen: false,
        fileId: '',
        filename: '',
        isDeleting: false
      });
    } catch (error) {
      debugError('Failed to delete file:', error);
      // Still close the modal even if there was an error
      setDeleteConfirmation({
        isOpen: false,
        fileId: '',
        filename: '',
        isDeleting: false
      });
    }
  };

  const cancelDelete = () => {
    setDeleteConfirmation({
      isOpen: false,
      fileId: '',
      filename: '',
      isDeleting: false
    });
  };

  const getFileIcon = (mimeType: string) => {
    if (mimeType.startsWith('image/')) return '🖼️';
    if (mimeType.startsWith('audio/')) return '🎵';
    if (mimeType.includes('pdf')) return '📄';
    if (mimeType.includes('word') || mimeType.includes('document')) return '📝';
    if (mimeType.includes('spreadsheet') || mimeType.includes('excel')) return '📊';
    // Code file icons
    if (mimeType.includes('python') || mimeType.includes('x-python')) return '🐍';
    if (mimeType.includes('javascript') || mimeType.includes('typescript')) return '📜';
    if (mimeType.includes('java')) return '☕';
    if (mimeType.includes('sql')) return '🗄️';
    if (mimeType.includes('c++') || mimeType.includes('csrc') || mimeType.includes('x-c')) return '⚙️';
    if (mimeType.includes('go')) return '🐹';
    if (mimeType.includes('rust')) return '🦀';
    if (mimeType.includes('ruby')) return '💎';
    if (mimeType.includes('php')) return '🐘';
    if (mimeType.includes('shellscript') || mimeType.includes('x-sh')) return '💻';
    if (mimeType.includes('yaml') || mimeType.includes('yml')) return '📋';
    if (mimeType.includes('xml')) return '📐';
    if (mimeType.includes('css') || mimeType.includes('scss') || mimeType.includes('sass') || mimeType.includes('less')) return '🎨';
    return '📎';
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  // Don't show file list if no conversation is selected
  if (!currentConversationId || !currentConversation) {
    return null;
  }

  return (
    <>
      <div className="border-t border-slate-200/70 dark:border-slate-700/60 pt-4 pb-4 relative z-10">
        <div className="px-4 pb-3">
          <div className="flex items-center gap-2 mb-3">
            <Paperclip className="w-4 h-4 text-slate-500 dark:text-slate-400" />
            <h3 className="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wide">
              {t('fileList.header', { count: files.length })}
            </h3>
          </div>
        </div>

        <div className="px-4 max-h-64 overflow-y-auto">
          {files.length === 0 ? (
            <div className="py-6 text-center">
              <FileText className="w-8 h-8 mx-auto mb-2 text-slate-300 dark:text-slate-600" />
              <p className="text-slate-400 dark:text-slate-500 text-xs font-medium">
                {t('fileList.noFilesAttached')}
              </p>
              <p className="text-slate-400 dark:text-slate-500 text-xs mt-1">
                {t('fileList.uploadFilesToUse')}
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {files.map((file) => (
                <div
                  key={file.file_id}
                  className="group flex items-center gap-2 p-2.5 rounded-lg border border-slate-200/70 dark:border-slate-700/60 bg-white/60 dark:bg-slate-900/40 hover:bg-white/80 dark:hover:bg-slate-800/60 transition-all duration-200"
                >
                  <div className="flex-shrink-0 text-lg">
                    {getFileIcon(file.mime_type)}
                  </div>
                  
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-slate-700 dark:text-slate-300 truncate">
                      {file.filename}
                    </p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-slate-500 dark:text-slate-400">
                        {formatFileSize(file.file_size)}
                      </span>
                      {file.processing_status && file.processing_status !== 'completed' && (
                        <span className={`text-xs px-1.5 py-0.5 rounded ${
                          file.processing_status === 'processing'
                            ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300'
                            : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400'
                        }`}>
                          {file.processing_status}
                        </span>
                      )}
                    </div>
                  </div>

                  <button
                    onClick={(e) => handleDeleteFile(e, file)}
                    className="opacity-0 group-hover:opacity-100 p-1.5 hover:bg-red-50 dark:hover:bg-red-900/30 rounded transition-all duration-200 text-red-500 dark:text-red-400"
                    title={t('fileList.removeFileTooltip')}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      <ConfirmationModal
        isOpen={deleteConfirmation.isOpen}
        onClose={cancelDelete}
        onConfirm={confirmDelete}
        title={t('fileList.confirmRemoveTitle')}
        message={t('fileList.confirmRemoveMessage', { filename: deleteConfirmation.filename })}
        confirmText={t('common.remove')}
        cancelText={t('common.cancel')}
        type="danger"
        isLoading={deleteConfirmation.isDeleting}
      />
    </>
  );
}
