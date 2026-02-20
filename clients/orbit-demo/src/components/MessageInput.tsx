import { useState, useRef, useCallback } from 'react';
import { useChatStore } from '../stores/chatStore';
import { getApiClient } from '../api/client';
import { useVoice } from '../hooks/useVoice';
import { MAX_MESSAGE_LENGTH } from '../config/constants';

interface MessageInputProps {
  onSend: (content: string, fileIds: string[], audioInput?: string) => void;
  disabled?: boolean;
  activeThreadId: string | null;
  onClearThread: () => void;
}

export function MessageInput({
  onSend,
  disabled,
  activeThreadId,
}: MessageInputProps) {
  const [text, setText] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isLoading = useChatStore((s) => s.isLoading);
  const attachedFileIds = useChatStore((s) => s.attachedFileIds);
  const addAttachedFileIds = useChatStore((s) => s.addAttachedFileIds);
  const clearAttachedFileIds = useChatStore((s) => s.clearAttachedFileIds);
  const error = useChatStore((s) => s.error);
  const clearError = useChatStore((s) => s.clearError);

  const { isRecording, error: voiceError, startRecording, stopRecording } = useVoice();

  const handleAttach = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files?.length) return;
      const api = getApiClient();
      if (!api) {
        useChatStore.setState({
          error: 'Not connected. Configure Orbit URL and API key first.',
        });
        e.target.value = '';
        return;
      }
      const ids: string[] = [];
      let uploadError: string | null = null;
      for (let i = 0; i < files.length; i++) {
        try {
          const res = await api.uploadFile(files[i]);
          ids.push(res.file_id);
        } catch (err) {
          uploadError = err instanceof Error ? err.message : 'File upload failed';
        }
      }
      if (uploadError) {
        useChatStore.setState({ error: uploadError });
      }
      if (ids.length) addAttachedFileIds(ids);
      e.target.value = '';
    },
    [addAttachedFileIds]
  );

  const handleSend = useCallback(() => {
    const content = text.trim();
    if (!content && attachedFileIds.length === 0 && !isRecording) return;
    if (disabled && !content && attachedFileIds.length === 0) return;
    onSend(content || '', [...attachedFileIds]);
    setText('');
    clearAttachedFileIds();
  }, [text, attachedFileIds, disabled, isRecording, onSend, clearAttachedFileIds]);

  const handleMic = useCallback(async () => {
    if (isRecording) {
      const base64 = await stopRecording();
      if (base64) {
        onSend('', [], base64);
        clearAttachedFileIds();
      }
    } else {
      await startRecording();
    }
  }, [isRecording, startRecording, stopRecording, onSend, clearAttachedFileIds]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!isLoading) handleSend();
      }
    },
    [isLoading, handleSend]
  );

  return (
    <div className="message-input-wrap">
      {error && (
        <div className="message-input-error" role="alert">
          {error}
          <button type="button" onClick={clearError} aria-label="Dismiss error">
            ×
          </button>
        </div>
      )}
      {voiceError && (
        <div className="message-input-error" role="alert">
          {voiceError}
        </div>
      )}
      {attachedFileIds.length > 0 && (
        <div className="message-input-attached">
          Attached: {attachedFileIds.length} file(s)
          <button type="button" onClick={clearAttachedFileIds}>
            Clear
          </button>
        </div>
      )}
      <div className="message-input-row">
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileChange}
          multiple
          className="message-input-file-hidden"
          aria-hidden
        />
        <button
          type="button"
          className="btn-attach"
          onClick={handleAttach}
          disabled={disabled || isLoading}
          title="Attach files"
          aria-label="Attach files"
        >
          <span aria-hidden="true">📎</span>
        </button>
        <textarea
          className="message-input-text"
          value={text}
          onChange={(e) => setText(e.target.value.slice(0, MAX_MESSAGE_LENGTH))}
          onKeyDown={handleKeyDown}
          placeholder={activeThreadId ? 'Reply in thread…' : 'Message…'}
          disabled={disabled || isLoading}
          rows={1}
          aria-label="Message"
        />
        <button
          type="button"
          className="btn-mic"
          onClick={handleMic}
          disabled={disabled || isLoading}
          title={isRecording ? 'Stop recording' : 'Record voice'}
          aria-label={isRecording ? 'Stop recording' : 'Record voice'}
        >
          <span aria-hidden="true">{isRecording ? '⏹' : '🎤'}</span>
        </button>
        {isLoading ? (
          <button
            type="button"
            className="btn-stop"
            onClick={() => useChatStore.getState().stopGeneration()}
          >
            Stop
          </button>
        ) : (
          <button
            type="button"
            className="btn-send"
            onClick={handleSend}
            disabled={
              disabled ||
              (text.trim() === '' && attachedFileIds.length === 0 && !isRecording)
            }
          >
            Send
          </button>
        )}
      </div>
    </div>
  );
}
