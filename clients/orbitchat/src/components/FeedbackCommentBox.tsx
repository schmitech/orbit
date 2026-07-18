import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowUp } from 'lucide-react';

// Keep in sync with the server's MAX_COMMENT_LENGTH (server/services/feedback_service.py).
export const FEEDBACK_COMMENT_MAX_LENGTH = 2000;

interface FeedbackCommentBoxProps {
  initialValue?: string | null;
  onSubmit: (comment: string) => void | Promise<void>;
  onCancel: () => void;
  isSubmitting?: boolean;
}

/**
 * Inline expanding box for an optional free-text feedback comment (thumbs-down).
 * Presentational only — the parent owns persistence via the chat store.
 */
export function FeedbackCommentBox({
  initialValue = '',
  onSubmit,
  onCancel,
  isSubmitting = false,
}: FeedbackCommentBoxProps) {
  const { t } = useTranslation();
  const [value, setValue] = useState(initialValue ?? '');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Focus and place the caret at the end when the box opens.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  }, []);

  // Auto-resize the textarea as content changes.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [value]);

  const handleSubmit = () => {
    if (isSubmitting) return;
    onSubmit(value.trim());
  };

  return (
    <div className="mt-2 rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 dark:border-[#242424] dark:bg-[#101010]">
      <div className="mb-1 text-[11px] font-medium text-gray-500 dark:text-[#8e8ea0]">
        {t('message.feedback.commentPrompt')}
      </div>
      <textarea
        ref={textareaRef}
        className="block w-full resize-none overflow-hidden bg-transparent text-sm leading-6 text-[#353740] placeholder-slate-500 outline-none disabled:opacity-60 dark:text-[#ececf1] dark:placeholder-[#70707c]"
        placeholder={t('message.feedback.commentPlaceholder')}
        aria-label={t('message.feedback.commentPlaceholder')}
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
          }
          if (e.key === 'Escape') {
            e.preventDefault();
            onCancel();
          }
        }}
        disabled={isSubmitting}
        rows={1}
        maxLength={FEEDBACK_COMMENT_MAX_LENGTH}
        style={{ minHeight: '24px', maxHeight: '120px' }}
      />
      <div className="mt-1.5 flex items-center justify-end gap-2">
        {value.length > 0 && (
          <span className="mr-auto text-[11px] text-gray-500 dark:text-[#bfc2cd]">
            <span className={value.length >= FEEDBACK_COMMENT_MAX_LENGTH ? 'text-red-600 font-semibold' : ''}>
              {value.length}/{FEEDBACK_COMMENT_MAX_LENGTH}
            </span>
          </span>
        )}
        <button
          type="button"
          onClick={onCancel}
          disabled={isSubmitting}
          className="rounded-full bg-gray-200 px-3 py-1 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-300 disabled:opacity-60 dark:bg-[#4a4b54] dark:text-gray-200 dark:hover:bg-[#565869]"
        >
          {t('message.feedback.commentCancel')}
        </button>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={isSubmitting}
          className="flex items-center gap-1.5 rounded-full bg-blue-600 px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-blue-500 dark:hover:bg-blue-400"
        >
          <ArrowUp className="h-3.5 w-3.5" />
          {t('message.feedback.commentSend')}
        </button>
      </div>
    </div>
  );
}
