import React, { useState, useRef, useEffect, useCallback, useMemo, useLayoutEffect } from 'react';
import { ArrowUp, CircleHelp, Mic, MicOff, Paperclip, X, Loader2, CheckCircle2, Volume2, VolumeX, Square, CircleAlert, TriangleAlert, Sparkles } from 'lucide-react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { useVoice } from '../hooks/useVoice';
import { useAutocomplete } from '../hooks/useAutocomplete';
import type { UseSkillsResult } from '../hooks/useSkills';
import { FileUpload } from './FileUpload';
import { ConfirmationModal } from './ConfirmationModal';
import { SkillPicker } from './SkillPicker';
import { FileAttachment } from '../types';
import type { AllowedModel } from '../types';
import { useChatStore } from '../stores/chatStore';
import { debugLog, debugError } from '../utils/debug';
import { AppConfig } from '../utils/config';
import { FileUploadService, FileUploadProgress } from '../services/fileService';
import { getAdapterInputPlaceholder, getDefaultInputPlaceholder, getEnableAudioInput, getEnableAudioOutput, getEnableAutocomplete, getEnableUploadButton, getIsAuthConfigured, getVoiceRecognitionLanguage, getVoiceSilenceTimeoutMs, resolveApiUrl } from '../utils/runtimeConfig';
import { useSettings } from '../contexts/SettingsContext';
import { playSoundEffect } from '../utils/soundEffects';
import { audioStreamManager } from '../utils/audioStreamManager';
import { useIsAuthenticated } from '../hooks/useIsAuthenticated';
import { useLoginPromptStore } from '../stores/loginPromptStore';
import { MarkdownRenderer } from './markdown';
import { useTheme } from '../contexts/ThemeContext';
import { useFocusTrap } from '../hooks/useFocusTrap';
import { ModelPickerButton } from './ModelPickerButton';
import { FileChip } from './FileChip';
import { setFileThumbnail } from '../utils/fileTypeVisuals';

interface MessageInputProps {
  onSend: (message: string, fileIds?: string[], threadId?: string, skill?: string) => void;
  disabled?: boolean;
  placeholder?: string;
  autoFocusEnabled?: boolean;
  suppressMobileAutoFocus?: boolean;
  /**
   * Limit autofocus to desktop viewports (≥1024px) and focus without scrolling.
   * Used by the single-mode landing composer so the agent's intro text stays
   * visible: phones and tablets get no caret (avoids the on-screen keyboard
   * popping and the intro scrolling out of view), while desktop keeps a ready
   * caret in place because it has the vertical room to show both.
   */
  desktopOnlyAutoFocus?: boolean;
  /**
   * When true, constrains the input to a tighter max width and centers it.
   * Used for the empty state layout so the field and title feel aligned.
   */
  isCentered?: boolean;
  /**
   * Optional max width utility class for non-centered layouts.
   */
  maxWidthClass?: string;
  /**
   * Adapter notes/description content shown via a help icon modal.
   */
  adapterNotes?: string | null;
  /**
   * Shared skill-selection state, owned by the parent so it survives the
   * empty-state ↔ active-conversation MessageInput swap. Without this, each
   * MessageInput instance kept its own selectedSkill and the chip was lost
   * (and could no longer be dismissed) on the first message of a conversation.
   */
  skillState: UseSkillsResult;
  availableModels?: AllowedModel[];
  defaultModel?: string | null;
  selectedModel?: string | null;
  onSelectModel?: (name: string | null) => void;
}

const MIME_EXTENSION_MAP: Record<string, string> = {
  'image/jpeg': 'jpg',
  'image/jpg': 'jpg',
  'image/png': 'png',
  'image/tiff': 'tiff',
  'image/tif': 'tif',
  'image/gif': 'gif',
  'image/webp': 'webp',
  'application/pdf': 'pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
  'application/msword': 'doc',
  'text/plain': 'txt',
  'text/markdown': 'md',
  'application/json': 'json'
};

const DEFAULT_TEXTAREA_VERTICAL_PADDING = 4;
const VERTICAL_ALIGNMENT_OFFSET = 3;
const PLACEHOLDER_VERTICAL_OFFSET = 0;
const INLINE_SUGGESTION_VERTICAL_OFFSET = 0;
const TEXTAREA_HORIZONTAL_PADDING = 2;

function resolveAutocompleteSupport(adapterInfo: unknown): boolean | null {
  if (!adapterInfo || typeof adapterInfo !== 'object') {
    return null;
  }

  const info = adapterInfo as Record<string, unknown>;
  const directCapabilityKeys = [
    'supportsAutocomplete',
    'isAutocompleteSupported',
    'autocompleteSupported'
  ];

  for (const key of directCapabilityKeys) {
    if (typeof info[key] === 'boolean') {
      return info[key] as boolean;
    }
  }

  const nestedCapabilityParents = ['capabilities', 'features'];
  const nestedCapabilityKeys = ['autocomplete', 'supportsAutocomplete', 'autocomplete_supported'];

  for (const parent of nestedCapabilityParents) {
    const nested = info[parent];
    if (!nested || typeof nested !== 'object') {
      continue;
    }

    const nestedInfo = nested as Record<string, unknown>;
    for (const key of nestedCapabilityKeys) {
      if (typeof nestedInfo[key] === 'boolean') {
        return nestedInfo[key] as boolean;
      }
    }
  }

  return null;
}

function getExtensionFromMimeType(mimeType: string | undefined): string {
  if (!mimeType) {
    return 'bin';
  }
  if (MIME_EXTENSION_MAP[mimeType]) {
    return MIME_EXTENSION_MAP[mimeType];
  }
  const parts = mimeType.split('/');
  return parts.length === 2 && parts[1] ? parts[1] : 'bin';
}

function sanitizeFilenamePart(name: string): string {
  const sanitized = name.replace(/[^a-zA-Z0-9._-]/g, '_').replace(/_+/g, '_');
  return sanitized || 'pasted-file';
}

function getExtensionFromName(name: string): string | null {
  const lastDot = name.lastIndexOf('.');
  if (lastDot === -1 || lastDot === name.length - 1) {
    return null;
  }
  return name.slice(lastDot + 1).toLowerCase();
}

function getBaseName(name: string): string {
  const lastDot = name.lastIndexOf('.');
  if (lastDot === -1) {
    return name;
  }
  return name.slice(0, lastDot);
}

function isFileProcessing(processingStatus?: string): boolean {
  return !processingStatus || processingStatus === 'processing' || processingStatus === 'uploading';
}

function prepareClipboardFile(file: File, index: number): File {
  const timestamp = Date.now();
  const originalName = file.name && file.name.trim().length > 0 ? file.name.trim() : `pasted-file`;
  const baseName = sanitizeFilenamePart(getBaseName(originalName));
  const existingExtension = getExtensionFromName(originalName);
  const extension = existingExtension || getExtensionFromMimeType(file.type);
  const uniqueName = `${baseName}-${timestamp}-${index}.${extension}`;
  return new File([file], uniqueName, { type: file.type || 'application/octet-stream' });
}

export function MessageInput({
  onSend,
  disabled = false,
  placeholder = getDefaultInputPlaceholder(),
  autoFocusEnabled = true,
  suppressMobileAutoFocus = false,
  desktopOnlyAutoFocus = false,
  isCentered = false,
  maxWidthClass = 'max-w-5xl',
  adapterNotes,
  skillState,
  availableModels = [],
  defaultModel = null,
  selectedModel = null,
  onSelectModel,
}: MessageInputProps) {
  const { t } = useTranslation();
  const [message, setMessage] = useState('');
  const [isComposing, setIsComposing] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const [showAgentInfo, setShowAgentInfo] = useState(false);
  const [showFileUpload, setShowFileUpload] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState<FileAttachment[]>([]);
  const [conversationUploadingState, setConversationUploadingState] = useState<Record<string, boolean>>({});
  const [pasteUploadingFiles, setPasteUploadingFiles] = useState<Map<string, FileUploadProgress>>(new Map());
  const [isHoveringUpload, setIsHoveringUpload] = useState(false);
  const [isHoveringMic, setIsHoveringMic] = useState(false);
  const [pasteError, setPasteError] = useState<string | null>(null);
  const [uploadSuccessMessage, setUploadSuccessMessage] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [fileDeleteConfirmation, setFileDeleteConfirmation] = useState<{
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
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const agentInfoModalRef = useRef<HTMLDivElement>(null);
  const uploadPanelRef = useRef<HTMLDivElement>(null);
  const autocompletePanelRef = useRef<HTMLDivElement>(null);
  const skillPickerPanelRef = useRef<HTMLDivElement>(null);
  const processedFilesRef = useRef<Set<string>>(new Set());
  const voiceMessageRef = useRef('');
  const pendingVoiceAutoSendRef = useRef(false);
  const lastProcessedVoiceCompletionRef = useRef(0);
  const lastConversationIdRef = useRef<string | null>(null);
  const { settings, updateSettings } = useSettings();
  const { theme, isDark } = useTheme();
  const agentInfoForcedThemeClass = theme.mode === 'dark' ? 'dark' : theme.mode === 'light' ? 'light' : '';
  const agentInfoSyntaxTheme: 'dark' | 'light' = isDark ? 'dark' : 'light';
  useFocusTrap(agentInfoModalRef, { enabled: showAgentInfo, onEscape: () => setShowAgentInfo(false) });
  const setConversationUploading = useCallback((conversationId: string | null, uploading: boolean) => {
    if (!conversationId) {
      return;
    }
    setConversationUploadingState(prev => {
      if (prev[conversationId] === uploading) {
        return prev;
      }
      const next = { ...prev };
      if (uploading) {
        next[conversationId] = true;
      } else {
        delete next[conversationId];
      }
      return next;
    });
  }, []);
  const [voiceCompletionCount, setVoiceCompletionCount] = useState(0);
  const [showSkillPicker, setShowSkillPicker] = useState(false);
  const [activeSkillIndex, setActiveSkillIndex] = useState(0);
  const [textareaVerticalPadding, setTextareaVerticalPadding] = useState(() => ({
    top: DEFAULT_TEXTAREA_VERTICAL_PADDING + VERTICAL_ALIGNMENT_OFFSET,
    bottom: Math.max(DEFAULT_TEXTAREA_VERTICAL_PADDING - VERTICAL_ALIGNMENT_OFFSET, 0)
  }));
  const [textareaLineHeight, setTextareaLineHeight] = useState<number | null>(null);

  const isAuthenticated = useIsAuthenticated();
  const isGuest = getIsAuthConfigured() && !isAuthenticated;
  const showLoginPrompt = useLoginPromptStore(state => state.showLoginPrompt);
  const { createConversation, currentConversationId, conversations, isLoading, syncConversationFiles, stopStreaming, removeFileFromConversation } = useChatStore();
  const currentConversation = conversations.find(c => c.id === currentConversationId);
  const conversationMessagesCount = currentConversation
    ? currentConversation.messages.filter(msg => !(msg.role === 'assistant' && msg.isStreaming)).length
    : 0;
  const totalMessagesCount = conversations.reduce(
    (total, conv) => total + conv.messages.filter(msg => !(msg.role === 'assistant' && msg.isStreaming)).length,
    0
  );
  const conversationMessageLimitReached =
    !!currentConversation &&
    AppConfig.maxMessagesPerConversation !== null &&
    conversationMessagesCount >= AppConfig.maxMessagesPerConversation;
  const workspaceMessageLimitReached =
    AppConfig.maxTotalMessages !== null && totalMessagesCount >= AppConfig.maxTotalMessages;

  const handleVoiceCompletion = useCallback(() => {
    setVoiceCompletionCount((count) => count + 1);
  }, []);
  const voiceSilenceTimeoutMs = getVoiceSilenceTimeoutMs();
  const voiceRecognitionLanguage = getVoiceRecognitionLanguage();

  const {
    isListening,
    isSupported: voiceSupported,
    startListening,
    stopListening,
    error: voiceError
  } = useVoice((text) => {
    setMessage(prev => {
      const separator = prev.length > 0 && !/\s$/.test(prev) ? ' ' : '';
      const updated = (prev + separator + text).slice(0, AppConfig.maxMessageLength);
      voiceMessageRef.current = updated;
      return updated;
    });
  }, handleVoiceCompletion, {
    silenceTimeoutMs: voiceSilenceTimeoutMs,
    language: voiceRecognitionLanguage || undefined
  });

  const audioOutputEnabled = getEnableAudioOutput();
  const audioInputEnabled = getEnableAudioInput();
  const voiceRecordingAvailable = audioInputEnabled && voiceSupported;
  const uploadFeatureEnabled = getEnableUploadButton();
  const autocompleteEnabled = getEnableAutocomplete();
  const currentAdapterSupportsAutocomplete = resolveAutocompleteSupport(currentConversation?.adapterInfo);

  // Skill state is owned by the parent (ChatInterface) and shared across both
  // the empty-state and docked MessageInput instances, so a selected skill is
  // not lost when the conversation transitions from empty to active.
  const { skills, isLoading: skillsLoading, selectedSkill, selectSkill, clearSkill } = skillState;

  const autocompleteAdapterName = currentConversation?.adapterName || null;
  // Autocomplete suggestions based on nl_examples from intent templates
  const {
    suggestions,
    selectedIndex,
    setSelectedIndex,
    selectNext,
    selectPrevious,
    clearSuggestions,
    focusInputAfterSelection,
    suppressUntilQueryChange
  } = useAutocomplete(message, {
    enabled: autocompleteEnabled && !isListening,
    apiUrl: currentConversation?.apiUrl,
    adapterName: autocompleteAdapterName,
    sessionId: currentConversation?.sessionId,
    adapterSupportsAutocomplete: currentAdapterSupportsAutocomplete,
    skill: selectedSkill?.name || null,
    inputRef: textareaRef
  });
  const hasSuggestions = suggestions.length > 0;
  const autocompleteVisible = !isListening;
  const showAutocompletePanel = autocompleteVisible && hasSuggestions && !showSkillPicker;

  const skillQuery = message.startsWith('/') ? message.slice(1) : '';
  const normalizedSkillQuery = skillQuery.toLowerCase().replace(/-/g, ' ');
  const filteredSkills = normalizedSkillQuery
    ? skills.filter(skill =>
        skill.name.replace(/-/g, ' ').toLowerCase().includes(normalizedSkillQuery) ||
        skill.description.toLowerCase().includes(normalizedSkillQuery)
      )
    : skills;
  const safeActiveSkillIndex = filteredSkills.length > 0 ? Math.min(activeSkillIndex, filteredSkills.length - 1) : 0;
  const activeSkill = filteredSkills[safeActiveSkillIndex] ?? null;
  const activeSkillDisplayName = activeSkill?.name.replace(/-/g, ' ') ?? '';
  const skillInlineSuggestion =
    showSkillPicker &&
    activeSkill &&
    message.startsWith('/') &&
    activeSkillDisplayName.toLowerCase().startsWith(skillQuery.toLowerCase()) &&
    activeSkillDisplayName.length > skillQuery.length
      ? activeSkillDisplayName.slice(skillQuery.length)
      : null;
  const activeSuggestionIndex = selectedIndex >= 0 ? selectedIndex : 0;
  const activeSuggestion = hasSuggestions ? suggestions[activeSuggestionIndex] : null;
  const inlineSuggestion = useMemo(() => {
    if (!activeSuggestion) {
      return null;
    }
    const suggestionText = activeSuggestion.text || '';
    if (!message) {
      return suggestionText;
    }
    const currentValue = message;
    if (suggestionText.toLowerCase().startsWith(currentValue.toLowerCase()) && suggestionText.length > currentValue.length) {
      return suggestionText.slice(currentValue.length);
    }
    return null;
  }, [activeSuggestion, message]);
  const activeInlineSuggestion = skillInlineSuggestion ?? inlineSuggestion;
  const showCustomPlaceholder = message.trim().length === 0 && !activeInlineSuggestion;
  const renderSuggestionText = useCallback((suggestionText: string) => {
    if (!message) {
      return <span className="line-clamp-1 text-current">{suggestionText}</span>;
    }

    if (!suggestionText.toLowerCase().startsWith(message.toLowerCase())) {
      return <span className="line-clamp-1 text-current">{suggestionText}</span>;
    }

    const typedPart = suggestionText.slice(0, message.length);
    const completionPart = suggestionText.slice(message.length);

    return (
      <span className="line-clamp-1">
        <span className="text-gray-500 dark:text-[#8e8ea0]">{typedPart}</span>
        <span className="font-semibold text-[#353740] dark:text-[#ececf1]">{completionPart}</span>
      </span>
    );
  }, [message]);

  const selectSkillAndClose = useCallback((skill: typeof skills[number]) => {
    selectSkill(skill);
    setShowSkillPicker(false);
    setMessage('');
    clearSuggestions();
    setActiveSkillIndex(0);
    textareaRef.current?.focus();
  }, [clearSuggestions, selectSkill]);

  // Opens the skill picker from the "/ Skills" hint affordance — mirrors the
  // user typing "/" so all the existing picker logic (filter, keyboard nav,
  // Escape-to-close) applies unchanged. Also covers mobile, where typing "/"
  // is less discoverable.
  const openSkillPicker = useCallback(() => {
    setMessage('/');
    setShowSkillPicker(true);
    setActiveSkillIndex(0);
    textareaRef.current?.focus();
  }, []);

  const closeSkillPicker = useCallback(() => {
    setShowSkillPicker(false);
    setMessage('');
    setActiveSkillIndex(0);
    textareaRef.current?.focus();
  }, []);

  const adjustTextareaVerticalAlignment = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea || typeof window === 'undefined') {
      return;
    }
    const applyPadding = (value: number) => {
      const topPadding = value + VERTICAL_ALIGNMENT_OFFSET;
      const bottomPadding = Math.max(value - VERTICAL_ALIGNMENT_OFFSET, 0);
      textarea.style.paddingTop = `${topPadding}px`;
      textarea.style.paddingBottom = `${bottomPadding}px`;
      setTextareaVerticalPadding({
        top: topPadding,
        bottom: bottomPadding
      });
    };
    const computedStyle = window.getComputedStyle(textarea);
    const lineHeight = parseFloat(computedStyle.lineHeight || '0');
    if (!Number.isNaN(lineHeight) && lineHeight > 0) {
      setTextareaLineHeight(prev => (prev === lineHeight ? prev : lineHeight));
    } else {
      setTextareaLineHeight(prev => (prev === null ? prev : null));
    }
    // Keep the content padding fixed. Deriving it from clientHeight creates a
    // feedback loop: after a multi-line message is cleared, the retained
    // textarea height is converted into padding, which then keeps the field
    // artificially tall on the next resize.
    applyPadding(DEFAULT_TEXTAREA_VERTICAL_PADDING);
  }, []);
  const isCaretAtMessageEnd = () => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return false;
    }
    return textarea.selectionStart === textarea.selectionEnd && textarea.selectionStart === message.length;
  };

  // Check if any files are currently uploading or processing
  const conversationFiles = currentConversation?.attachedFiles || [];
  const visibleAttachedFiles = currentConversationId ? conversationFiles : attachedFiles;
  const totalFilesAcrossConversations = conversations.reduce(
    (total, conv) => total + (conv.attachedFiles?.length || 0),
    0
  );
  const conversationFileLimitReached =
    AppConfig.maxFilesPerConversation !== null &&
    AppConfig.maxFilesPerConversation > 0 &&
    conversationFiles.length >= AppConfig.maxFilesPerConversation;
  const workspaceFileLimitReached =
    AppConfig.maxTotalFiles !== null && totalFilesAcrossConversations >= AppConfig.maxTotalFiles;
  
  // Check if adapter supports file processing
  const isFileSupported = currentConversation?.adapterInfo?.isFileSupported ?? false;
  
  // Don't sync attachedFiles with conversationFiles - attachedFiles should only show files attached to current message
  // Files in conversation will be included when sending the message via conversationFiles
  
  // Check if any attached files are still processing
  // Include files with undefined status (still uploading), 'uploading', or 'processing' status
  const hasProcessingFiles = visibleAttachedFiles.some(file => {
    if (!file.processing_status) {
      // File doesn't have status yet - likely still uploading
      return true;
    }
    return file.processing_status !== 'completed' && 
           file.processing_status !== 'error' &&
           file.processing_status !== 'failed';
  });

  const isUploading = currentConversationId ? !!conversationUploadingState[currentConversationId] : false;
  const hasAnyUploadingConversations = Object.values(conversationUploadingState).some(Boolean);
  const hasTypedMessage = message.trim().length > 0;

  // Disable input if files are uploading, processing, or if already disabled
  const messageLimitActive = conversationMessageLimitReached || workspaceMessageLimitReached;
  const isInputDisabled = disabled || hasProcessingFiles || isUploading || messageLimitActive;
  
  const canUseFileUploads = uploadFeatureEnabled && isFileSupported;
  // File selection only needs to be blocked while an upload is actively in the
  // FileUpload pipeline. Already attached files may still be processing, but
  // they are rendered by MessageInput and should not hide or disable the picker.
  const fileLimitActive = conversationFileLimitReached || workspaceFileLimitReached;
  const isFileUploadDisabled = !canUseFileUploads || disabled || isUploading || messageLimitActive || fileLimitActive;
  const isUploadProgressOnly = !showFileUpload && (isUploading || pasteUploadingFiles.size > 0);
  const shouldShowFileUploadControl = showFileUpload || (isUploading && pasteUploadingFiles.size === 0);

  // Auto-resize textarea with maximum height limit
  useLayoutEffect(() => {
    if (textareaRef.current) {
      const textarea = textareaRef.current;
      const maxHeight = 120; // Maximum height in pixels (about 4-5 lines)

      // Mobile Safari can retain the previous scrollHeight for a textarea
      // immediately after its value is cleared. Explicitly restore the
      // single-line height so a previously expanded composer cannot linger.
      if (message.length === 0) {
        textarea.style.height = '32px';
        textarea.style.overflowY = 'hidden';
        adjustTextareaVerticalAlignment();
        return;
      }

      textarea.style.height = 'auto';
      const scrollHeight = textarea.scrollHeight;
      // Set height to scrollHeight, but cap it at maxHeight
      textarea.style.height = `${Math.min(scrollHeight, maxHeight)}px`;
      // Enable overflow-y when content exceeds max height
      textarea.style.overflowY = scrollHeight > maxHeight ? 'auto' : 'hidden';
      adjustTextareaVerticalAlignment();
    }
  }, [message, adjustTextareaVerticalAlignment]);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof ResizeObserver === 'undefined') {
      return;
    }
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }
    const resizeObserver = new ResizeObserver(() => {
      adjustTextareaVerticalAlignment();
    });
    resizeObserver.observe(textarea);
    return () => {
      resizeObserver.disconnect();
    };
  }, [adjustTextareaVerticalAlignment]);

  // Helper function to check if focus is in any textarea (including thread inputs)
  const isFocusInTextarea = () => {
    const activeElement = document.activeElement;
    return activeElement && activeElement.tagName === 'TEXTAREA';
  };

  const shouldSkipAutoFocus = useCallback(() => {
    if (typeof window === 'undefined') {
      return false;
    }
    // Below desktop, don't steal focus for the landing composer — a caret here
    // pops the mobile/tablet keyboard and scrolls the agent's intro out of view.
    if (desktopOnlyAutoFocus && !window.matchMedia('(min-width: 1024px)').matches) {
      return true;
    }
    if (suppressMobileAutoFocus && window.matchMedia('(max-width: 767px)').matches) {
      return true;
    }
    return false;
  }, [desktopOnlyAutoFocus, suppressMobileAutoFocus]);

  // preventScroll keeps the desktop landing caret from scrolling the intro text
  // off-screen; elsewhere preventScroll: false is the normal focus behavior.
  const focusTextarea = useCallback(() => {
    textareaRef.current?.focus({ preventScroll: desktopOnlyAutoFocus });
  }, [desktopOnlyAutoFocus]);

  // Auto-focus when not disabled (when AI response is complete)
  useEffect(() => {
    // Only auto-focus if no textarea is currently focused (to avoid stealing focus from thread inputs)
    if (shouldSkipAutoFocus()) {
      return;
    }
    if (autoFocusEnabled && !isInputDisabled && textareaRef.current && !isFocusInTextarea()) {
      focusTextarea();
    }
  }, [autoFocusEnabled, isInputDisabled, shouldSkipAutoFocus, focusTextarea]);

  // On mobile Safari, focusing an empty textarea while the skills row is
  // mounting can leave its native caret painted at the pre-layout position.
  // Refocus on the next frame once the grid has settled, without stealing
  // focus from another control or scrolling the page.
  const hasVisibleSkillRow = Boolean(selectedSkill) || (skills.length > 0 && message.length === 0 && !isInputDisabled);
  useEffect(() => {
    if (
      typeof window === 'undefined' ||
      !window.matchMedia('(max-width: 767px)').matches ||
      !hasVisibleSkillRow ||
      document.activeElement !== textareaRef.current
    ) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      const textarea = textareaRef.current;
      if (!textarea || document.activeElement !== textarea) {
        return;
      }
      textarea.blur();
      textarea.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [hasVisibleSkillRow]);

  // Focus input field when assistant response finishes (isLoading becomes false)
  const prevIsLoadingRef = useRef(isLoading);
  useEffect(() => {
    // If loading just finished (transitioned from true to false), focus the input
    // But only if user is not currently focused on any textarea (including thread inputs)
    if (shouldSkipAutoFocus()) {
      prevIsLoadingRef.current = isLoading;
      return;
    }
    if (autoFocusEnabled && prevIsLoadingRef.current && !isLoading && !isInputDisabled && textareaRef.current) {
      // Small delay to ensure the UI has updated
      setTimeout(() => {
        // Only focus main input if user is not already focused on a textarea
        if (textareaRef.current && !isFocusInTextarea()) {
          focusTextarea();
        }
      }, 100);
    }
    prevIsLoadingRef.current = isLoading;
  }, [autoFocusEnabled, isLoading, isInputDisabled, shouldSkipAutoFocus, focusTextarea]);

  // Auto-send message when voice recording completes
  useEffect(() => {
    if (!voiceRecordingAvailable) {
      return;
    }

    if (voiceCompletionCount > lastProcessedVoiceCompletionRef.current) {
      pendingVoiceAutoSendRef.current = true;
      lastProcessedVoiceCompletionRef.current = voiceCompletionCount;
    }

    if (!pendingVoiceAutoSendRef.current || voiceCompletionCount === 0) {
      return;
    }

    const voiceMessage = voiceMessageRef.current.trim();
    const currentState = useChatStore.getState();

    debugLog('[MessageInput] Auto-send check after voice completion:', {
      hasMessage: !!voiceMessage,
      isInputDisabled,
      isComposing,
      isLoading: currentState.isLoading
    });

    pendingVoiceAutoSendRef.current = false;
    if (!voiceMessage) {
      return;
    }

    if (isInputDisabled || isComposing) {
      debugLog('[MessageInput] Auto-send skipped because input is currently disabled or composing');
      return;
    }

    const currentConv = currentState.conversations.find(conv => conv.id === currentState.currentConversationId);
    const conversationFiles = currentConv?.attachedFiles || [];
    const allFileIds = conversationFiles.map(f => f.file_id);

    const activeSkillName = selectedSkill?.name;
    debugLog('[MessageInput] Auto-sending voice message immediately:', voiceMessage);
    onSend(voiceMessage, allFileIds.length > 0 ? allFileIds : undefined, undefined, activeSkillName);
    if (activeSkillName) {
      clearSkill();
    }
    setTimeout(() => {
      setShowSkillPicker(false);
    }, 0);

    clearSuggestions();
    setTimeout(() => {
      setMessage('');
    }, 0);
    voiceMessageRef.current = '';
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.overflowY = 'hidden';
      adjustTextareaVerticalAlignment();
    }
  }, [voiceRecordingAvailable, voiceCompletionCount, isInputDisabled, isComposing, onSend, selectedSkill, clearSkill, adjustTextareaVerticalAlignment, clearSuggestions]);

  // Close upload area when upload starts (hide upload widget, show only progress)
  useEffect(() => {
    if (isUploading && showFileUpload) {
      // Upload has started - hide upload widget, only progress will be visible
      setTimeout(() => {
        setShowFileUpload(false);
      }, 0);
    }
  }, [isUploading, showFileUpload]);

  const syncFilesWithConversation = useCallback((files: FileAttachment[], targetConversationId?: string | null) => {
    setTimeout(() => {
      let store = useChatStore.getState();
      let conversationId = targetConversationId || store.currentConversationId;
      
      if (!conversationId) {
        conversationId = createConversation();
        store = useChatStore.getState();
        conversationId = store.currentConversationId || conversationId;
      }

      if (!conversationId) {
        debugError('[MessageInput] Unable to sync files: conversation ID missing');
        return;
      }
      
      const conversationFileIds = store.conversations
        .find(conversation => conversation.id === conversationId)
        ?.attachedFiles
        ?.map(file => file.file_id) || [];
      const currentFileIds = new Set([
        ...conversationFileIds,
        ...files.map(file => file.file_id),
      ]);
      const conversationKeyPrefix = `${conversationId}-`;
      const keysToRemove: string[] = [];
      processedFilesRef.current.forEach((_, key) => {
        if (
          key.startsWith(conversationKeyPrefix) &&
          !currentFileIds.has(key.slice(conversationKeyPrefix.length))
        ) {
          keysToRemove.push(key);
        }
      });
      keysToRemove.forEach(key => processedFilesRef.current.delete(key));
      
      files.forEach(file => {
        const fileKey = `${conversationId}-${file.file_id}`;
        if (!processedFilesRef.current.has(fileKey)) {
          processedFilesRef.current.add(fileKey);
          
          debugLog(`[MessageInput] Adding file ${file.file_id} to conversation ${conversationId}`);
          store.addFileToConversation(conversationId!, file);
        }
      });
    }, 0);
  }, [createConversation]);

  // Reset attached files when switching conversations to avoid bleed-through
  useEffect(() => {
    if (currentConversationId !== lastConversationIdRef.current) {
      lastConversationIdRef.current = currentConversationId || null;
      if (currentConversationId && currentConversation) {
        const convFiles = currentConversation.attachedFiles || [];
        setTimeout(() => {
          setAttachedFiles(convFiles.map(file => ({ ...file })));
        }, 0);
      } else {
        setTimeout(() => {
          setAttachedFiles([]);
        }, 0);
      }
    }
  }, [currentConversationId, currentConversation]);

  // Sync attachedFiles with conversationFiles to ensure pasted files appear in UI
  useEffect(() => {
    if (currentConversationId && currentConversation) {
      const convFiles = currentConversation.attachedFiles || [];
      if (convFiles.length > 0) {
        setTimeout(() => {
          setAttachedFiles(prev => {
            const attachedFileIds = new Set(prev.map(f => f.file_id));
            const missingFiles = convFiles.filter(f => !attachedFileIds.has(f.file_id));
            
            if (missingFiles.length > 0) {
              debugLog(`[MessageInput] Syncing ${missingFiles.length} missing files from conversation to UI`);
              return [...prev, ...missingFiles];
            }
            return prev;
          });
        }, 0);
      } else if (convFiles.length === 0 && attachedFiles.length > 0) {
        setTimeout(() => {
          setAttachedFiles([]);
        }, 0);
      }
    }
  }, [currentConversationId, currentConversation, conversations, attachedFiles.length]);

  // Track the last conversation/file signature we synced to avoid redundant fetch loops
  const lastSyncedConversationRef = useRef<string | null>(null);
  const lastSyncedSignatureRef = useRef<string>('');

  // Stable file signature derived from file IDs — avoids re-triggering when the
  // attachedFiles array reference changes but the actual file set hasn't.
  const convFiles = currentConversation?.attachedFiles || [];
  const fileSignature = convFiles.length > 0
    ? `${convFiles.length}:${convFiles.map(f => f.file_id).join('|')}`
    : '';
  const hasFilesStillProcessing = convFiles.some(f => isFileProcessing(f.processing_status));

  // Sync and poll file status when switching to a conversation or when files change
  useEffect(() => {
    if (!currentConversationId || !currentConversation?.adapterName) {
      return;
    }

    const hasFiles = fileSignature !== '';

    const shouldSyncOnChange =
      hasFiles &&
      (
        lastSyncedConversationRef.current !== currentConversationId ||
        lastSyncedSignatureRef.current !== fileSignature
      );

    if (shouldSyncOnChange) {
      debugLog(`[MessageInput] Syncing files for conversation ${currentConversationId}...`);
      lastSyncedConversationRef.current = currentConversationId;
      lastSyncedSignatureRef.current = fileSignature;
      syncConversationFiles(currentConversationId).catch(error => {
        debugError('[MessageInput] Failed to sync conversation files:', error);
      });
    } else if (!hasFiles) {
      // Reset signature when conversation has no files to ensure next upload triggers a sync
      lastSyncedConversationRef.current = currentConversationId;
      lastSyncedSignatureRef.current = '';
    }

    // Only poll if there are files still processing
    if (!hasFilesStillProcessing) {
      return;
    }

    debugLog(`[MessageInput] Files still processing, starting poll...`);

    // Poll for file status updates every 3 seconds for files that are still processing
    const pollInterval = setInterval(async () => {
      const currentState = useChatStore.getState();
      const currentConv = currentState.conversations.find(conv => conv.id === currentConversationId);

      if (!currentConv) {
        clearInterval(pollInterval);
        return;
      }

      const currentFiles = currentConv.attachedFiles || [];
      const stillProcessing = currentFiles.filter(f => isFileProcessing(f.processing_status));

      if (stillProcessing.length === 0) {
        debugLog('[MessageInput] All files completed processing, stopping poll');
        clearInterval(pollInterval);
        return;
      }

      // Sync again to get updated statuses
      try {
        await syncConversationFiles(currentConversationId);
      } catch (error) {
        debugError('[MessageInput] Failed to poll file status:', error);
      }
    }, 3000);

    return () => {
      clearInterval(pollInterval);
    };
    // Use stable fileSignature string instead of attachedFiles array reference.
  }, [currentConversationId, currentConversation?.adapterName, fileSignature, hasFilesStillProcessing, syncConversationFiles]);

  useEffect(() => {
    setTimeout(() => {
      setConversationUploadingState(prev => {
        const existingIds = new Set(conversations.map(conv => conv.id));
        let changed = false;
        const next = { ...prev };
        Object.keys(next).forEach(id => {
          if (!existingIds.has(id)) {
            delete next[id];
            changed = true;
          }
        });
        return changed ? next : prev;
      });
    }, 0);
  }, [conversations]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (hasTypedMessage && !isInputDisabled && !isComposing) {
      // Stop listening if still active
      if (isListening) {
        stopListening();
      }

      // For multimodal conversations, send ALL files attached to the conversation
      // (not just the newly attached ones in this message)
      const conversationFiles = currentConversation?.attachedFiles || [];
      const allFileIds = conversationFiles.map(f => f.file_id);

      const activeSkillName = selectedSkill?.name;
      onSend(message.trim(), allFileIds.length > 0 ? allFileIds : undefined, undefined, activeSkillName);
      if (activeSkillName) {
        clearSkill();
      }
      setShowSkillPicker(false);
      playSoundEffect('messageSent', settings.soundEnabled);
      setMessage('');
      voiceMessageRef.current = ''; // Clear voice message ref when manually submitting
      setAttachedFiles([]);
      setShowFileUpload(false);
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
        textareaRef.current.style.overflowY = 'hidden';
        adjustTextareaVerticalAlignment();
      }
    }
  };

  const showUploadSuccessToast = useCallback((uploadedFiles: FileAttachment[]) => {
    if (!uploadedFiles || uploadedFiles.length === 0) {
      return;
    }

    const successMessage =
      uploadedFiles.length === 1
        ? t('messageInput.uploadSuccess.single', { filename: uploadedFiles[0].filename })
        : t('messageInput.uploadSuccess.multiple', { count: uploadedFiles.length });

    playSoundEffect('success', settings.soundEnabled);
    setUploadSuccessMessage(successMessage);
    setTimeout(() => {
      setUploadSuccessMessage(null);
    }, 6000);
  }, [settings.soundEnabled, t]);

  const handleFilesSelected = useCallback((conversationId: string | null, files: FileAttachment[]) => {
    debugLog(`[MessageInput] handleFilesSelected called with ${files.length} files for conversation ${conversationId}:`, files);
    if (!conversationId) {
      return;
    }
    if (conversationId === currentConversationId) {
      setAttachedFiles(files);
    }
    syncFilesWithConversation(files, conversationId);
  }, [currentConversationId, syncFilesWithConversation]);

  const handleUploadSuccessToast = useCallback((conversationId: string, newFiles: FileAttachment[]) => {
    if (conversationId !== currentConversationId) {
      return;
    }
    showUploadSuccessToast(newFiles);
  }, [currentConversationId, showUploadSuccessToast]);

  const openFileDeleteConfirmation = useCallback((file: FileAttachment) => {
    setFileDeleteConfirmation({
      isOpen: true,
      fileId: file.file_id,
      filename: file.filename,
      isDeleting: false
    });
  }, []);

  const closeFileDeleteConfirmation = useCallback(() => {
    setFileDeleteConfirmation(prev => {
      if (prev.isDeleting) {
        return prev;
      }
      return {
        isOpen: false,
        fileId: '',
        filename: '',
        isDeleting: false
      };
    });
  }, []);

  const confirmFileDelete = useCallback(async () => {
    if (!currentConversationId || !fileDeleteConfirmation.fileId) {
      return;
    }

    setFileDeleteConfirmation(prev => ({ ...prev, isDeleting: true }));

    try {
      await removeFileFromConversation(currentConversationId, fileDeleteConfirmation.fileId);
      setAttachedFiles(prev => prev.filter(file => file.file_id !== fileDeleteConfirmation.fileId));
      setFileDeleteConfirmation({
        isOpen: false,
        fileId: '',
        filename: '',
        isDeleting: false
      });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : t('messageInput.fileRemoveFailed');
      debugError('[MessageInput] Failed to remove file:', error);
      setUploadError(errorMessage);
      setFileDeleteConfirmation({
        isOpen: false,
        fileId: '',
        filename: '',
        isDeleting: false
      });
    }
  }, [currentConversationId, fileDeleteConfirmation.fileId, removeFileFromConversation, t]);

  const normalizeSuggestionText = useCallback((text: string) => {
    return text.replace(/\s+/g, ' ').trim();
  }, []);

  const handleSelectSuggestion = useCallback((text: string) => {
    const normalized = normalizeSuggestionText(text);
    setMessage(normalized);
    clearSuggestions();
    suppressUntilQueryChange(normalized);
    focusInputAfterSelection(normalized);
  }, [clearSuggestions, focusInputAfterSelection, normalizeSuggestionText, suppressUntilQueryChange]);

  const acceptSuggestionByIndex = useCallback((index: number) => {
    if (index < 0) {
      return;
    }
    const suggestion = suggestions[index] || suggestions[0];
    if (suggestion) {
      handleSelectSuggestion(suggestion.text);
    }
  }, [suggestions, handleSelectSuggestion]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (showSkillPicker) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveSkillIndex(prev => {
          if (filteredSkills.length === 0) {
            return 0;
          }
          return (prev + 1) % filteredSkills.length;
        });
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveSkillIndex(prev => {
          if (filteredSkills.length === 0) {
            return 0;
          }
          return (prev - 1 + filteredSkills.length) % filteredSkills.length;
        });
        return;
      }
      if (e.key === 'Home') {
        e.preventDefault();
        setActiveSkillIndex(0);
        return;
      }
      if (e.key === 'End') {
        e.preventDefault();
        setActiveSkillIndex(Math.max(filteredSkills.length - 1, 0));
        return;
      }
      if ((e.key === 'Enter' && !e.shiftKey) || e.key === 'Tab') {
        if (activeSkill) {
          e.preventDefault();
          selectSkillAndClose(activeSkill);
          return;
        }
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        closeSkillPicker();
        return;
      }
    }

    // Handle autocomplete navigation when suggestions are visible
    if (hasSuggestions && autocompleteVisible) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        selectNext();
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        selectPrevious();
        return;
      }
      if (e.key === 'Tab') {
        e.preventDefault();
        const targetIndex = selectedIndex >= 0 ? selectedIndex : 0;
        acceptSuggestionByIndex(targetIndex);
        return;
      }
      if (e.key === 'ArrowRight' && isCaretAtMessageEnd()) {
        if (inlineSuggestion && activeSuggestion) {
          e.preventDefault();
          handleSelectSuggestion(activeSuggestion.text);
          return;
        }
        if (selectedIndex >= 0) {
          e.preventDefault();
          acceptSuggestionByIndex(selectedIndex);
          return;
        }
      }
      if (e.key === 'Enter' && selectedIndex >= 0) {
        e.preventDefault();
        acceptSuggestionByIndex(selectedIndex);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        clearSuggestions();
        return;
      }
    }

    // Normal Enter handling (submit message)
    if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleVoiceToggle = () => {
    if (isListening) {
      stopListening();
    } else {
      clearSuggestions();
      startListening();
    }
  };

  const handleVoiceResponseToggle = () => {
    const enabling = !settings.voiceEnabled;
    updateSettings({ voiceEnabled: enabling });

    // Unlock AudioContext immediately while still inside the tap gesture.
    // Mobile browsers require AudioContext creation/resume within a user
    // gesture handler — deferring to a later event often loses the context.
    if (enabling) {
      audioStreamManager.enableAudio();
    }
  };

  const handlePaste = useCallback(async (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    if (!uploadFeatureEnabled || !isFocused || !isFileSupported || isInputDisabled) {
      return;
    }

    const clipboardData = e.clipboardData;
    if (!clipboardData || !clipboardData.items) {
      return;
    }

    const items = Array.from(clipboardData.items);
    const fileItems = items.filter(item => item.kind === 'file');

    if (fileItems.length === 0) {
      return;
    }

    const filesFromClipboard: File[] = [];
    fileItems.forEach((item, index) => {
      const file = item.getAsFile();
      if (file) {
        filesFromClipboard.push(prepareClipboardFile(file, index));
      }
    });

    if (filesFromClipboard.length === 0) {
      return;
    }

    e.preventDefault();
    setPasteError(null);
    setUploadSuccessMessage(null);
    setShowFileUpload(false);

    let pasteConversationId: string | null = null;
    // Thumbnails generated below but not yet handed off to the shared store
    // (i.e. their upload never got as far as returning a fileId) - revoked
    // in the catch block below so a failed paste doesn't leak the blob URL.
    const pendingThumbnailUrls = new Set<string>();

    try {
      const pasteStore = useChatStore.getState();
      const currentConv = pasteStore.conversations.find(conv => conv.id === pasteStore.currentConversationId);
      const currentFiles = currentConv?.attachedFiles || [];
      const projectedConversationFileCount = currentFiles.length + filesFromClipboard.length;

      if (projectedConversationFileCount > AppConfig.maxFilesPerConversation) {
        if (isGuest) {
          useLoginPromptStore.getState().openLoginPrompt(
            t('fileUpload.maxFilesGuestLimitMessage', { count: AppConfig.maxFilesPerConversation })
          );
        }
        throw new Error(t('fileUpload.maxFilesPerConversationError', { count: AppConfig.maxFilesPerConversation }));
      }

      if (AppConfig.maxTotalFiles !== null) {
        const totalFilesAcrossConversations = pasteStore.conversations.reduce(
          (total, conv) => total + (conv.attachedFiles?.length || 0),
          0
        );
        if (totalFilesAcrossConversations + filesFromClipboard.length > AppConfig.maxTotalFiles) {
          if (isGuest) {
            useLoginPromptStore.getState().openLoginPrompt(
              t('fileUpload.maxTotalFilesGuestLimitMessage', { count: AppConfig.maxTotalFiles })
            );
          }
          throw new Error(t('fileUpload.maxTotalFilesError', { count: AppConfig.maxTotalFiles }));
        }
      }

      if (!currentConv) {
        throw new Error(t('messageInput.conversationNotFoundShort'));
      }

      if (!currentConv.adapterName) {
        throw new Error(t('fileUpload.adapterNotConfigured'));
      }

      const conversationApiUrl = resolveApiUrl(currentConv.apiUrl);
      const conversationAdapterName = currentConv.adapterName;
      pasteConversationId = currentConv.id;

      setConversationUploading(pasteConversationId, true);
      const uploadedAttachments: FileAttachment[] = [];

      for (let index = 0; index < filesFromClipboard.length; index++) {
        const file = filesFromClipboard[index];
        const fallbackName = file.name || `Clipboard file ${index + 1}`;
        const progressKey = `${fallbackName}-${Date.now()}-${index}`;
        // Pasted clipboard content is usually a screenshot - generate its thumbnail
        // immediately while the File object is still in memory.
        const localThumbnailUrl = file.type.startsWith('image/') ? URL.createObjectURL(file) : null;
        if (localThumbnailUrl) {
          pendingThumbnailUrls.add(localThumbnailUrl);
        }
        let pastedFileId: string | null = null;

        setPasteUploadingFiles(prev => {
          const next = new Map(prev);
          next.set(progressKey, {
            filename: fallbackName,
            progress: 0,
            status: 'uploading'
          });
          return next;
        });

        const updateEntry = (progress: FileUploadProgress) => {
          if (progress.fileId && !pastedFileId) {
            pastedFileId = progress.fileId;
            if (localThumbnailUrl) {
              setFileThumbnail(progress.fileId, localThumbnailUrl);
              pendingThumbnailUrls.delete(localThumbnailUrl);
            }
          }
          setPasteUploadingFiles(prev => {
            const next = new Map(prev);
            const existing = next.get(progressKey);
            if (!existing) {
              return next;
            }
            next.set(progressKey, {
              ...existing,
              filename: fallbackName,
              progress: progress.progress,
              status: progress.status,
              fileId: progress.fileId
            });
            return next;
          });
        };

        const removeProgressEntry = () => {
          setPasteUploadingFiles(prev => {
            const next = new Map(prev);
            next.delete(progressKey);
            return next;
          });
        };
        debugLog(`[MessageInput] Pasting file: ${file.name}, type: ${file.type || 'unknown'}, size: ${file.size}`);
        const uploadedAttachment = await FileUploadService.uploadFile(
          file,
          (progress) => {
            debugLog(`[MessageInput] Paste upload progress for ${file.name}: ${progress.progress}% - ${progress.status}`);
            updateEntry(progress);
          },
          undefined,
          conversationApiUrl,
          conversationAdapterName
        );
        uploadedAttachments.push(uploadedAttachment);

        if (pasteConversationId && pasteConversationId === currentConversationId) {
          setAttachedFiles(prev => (
            prev.some(file => file.file_id === uploadedAttachment.file_id)
              ? prev
              : [...prev, uploadedAttachment]
          ));
        }
        syncFilesWithConversation([uploadedAttachment], pasteConversationId);
        removeProgressEntry();
      }

      if (uploadedAttachments.length > 0) {
        showUploadSuccessToast(uploadedAttachments);
      }
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to paste file';
      debugError('[MessageInput] Paste error:', error);
      playSoundEffect('error', settings.soundEnabled);
      setPasteError(errorMessage);
      if (errorMessage.toLowerCase().includes('maximum')) {
        setUploadError(errorMessage);
      }
      setTimeout(() => {
        setPasteError(null);
      }, 5000);
      setPasteUploadingFiles(new Map());
      pendingThumbnailUrls.forEach(url => URL.revokeObjectURL(url));
    } finally {
      setConversationUploading(pasteConversationId, false);
    }
  }, [currentConversationId, isFocused, isFileSupported, isGuest, isInputDisabled, setConversationUploading, settings.soundEnabled, showUploadSuccessToast, syncFilesWithConversation, uploadFeatureEnabled, t]);

  const adapterInputPlaceholder = getAdapterInputPlaceholder(currentConversation?.adapterName);
  let effectivePlaceholder: string | null | undefined;
  if (workspaceMessageLimitReached) {
    effectivePlaceholder = isGuest
      ? t('messageInput.placeholder.guestLimitTotal', { count: AppConfig.maxTotalMessages })
      : t('messageInput.placeholder.workspaceLimitTotal', { count: AppConfig.maxTotalMessages });
  } else if (conversationMessageLimitReached) {
    effectivePlaceholder = isGuest
      ? t('messageInput.placeholder.guestLimitPerConversation', { count: AppConfig.maxMessagesPerConversation })
      : t('messageInput.placeholder.conversationLimitReached', { count: AppConfig.maxMessagesPerConversation });
  } else if (hasProcessingFiles || isUploading) {
    effectivePlaceholder = t('messageInput.placeholder.filesUploading');
  } else if (adapterInputPlaceholder) {
    effectivePlaceholder = adapterInputPlaceholder;
  } else if (canUseFileUploads) {
    effectivePlaceholder = t('messageInput.placeholder.messageOrbit');
  } else {
    effectivePlaceholder = placeholder;
  }

  const limitWarnings: string[] = [];
  if (workspaceMessageLimitReached && AppConfig.maxTotalMessages !== null) {
    if (isGuest) {
      if (showLoginPrompt) {
        limitWarnings.push(t('messageInput.limitWarning.guestTotalMessages', { count: AppConfig.maxTotalMessages }));
      }
    } else {
      limitWarnings.push(t('messageInput.limitWarning.workspaceTotalMessages', { count: AppConfig.maxTotalMessages }));
    }
  }
  if (conversationMessageLimitReached && AppConfig.maxMessagesPerConversation !== null) {
    if (isGuest) {
      if (showLoginPrompt) {
        limitWarnings.push(t('messageInput.limitWarning.guestPerConversation', { count: AppConfig.maxMessagesPerConversation }));
      }
    } else {
      limitWarnings.push(t('messageInput.limitWarning.conversationLimitReached', { count: AppConfig.maxMessagesPerConversation }));
    }
  }
  if (uploadError) {
    limitWarnings.push(uploadError);
  }

  // Play sound when voice error appears
  useEffect(() => {
    if (!audioInputEnabled || !voiceError) {
      return;
    }
    playSoundEffect('error', settings.soundEnabled);
  }, [audioInputEnabled, settings.soundEnabled, voiceError]);

  useEffect(() => {
    if (!uploadError) {
      return;
    }
    const timeout = setTimeout(() => setUploadError(null), 5000);
    return () => clearTimeout(timeout);
  }, [uploadError]);

  useEffect(() => {
    if (!showFileUpload) {
      return;
    }

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented) {
        return;
      }
      setShowFileUpload(false);
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [showFileUpload]);

  useEffect(() => {
    if (!(showFileUpload || isUploading || pasteUploadingFiles.size > 0 || hasAnyUploadingConversations)) {
      return;
    }
    uploadPanelRef.current?.scrollIntoView({
      behavior: 'smooth',
      block: 'nearest'
    });
  }, [showFileUpload, isUploading, pasteUploadingFiles.size, hasAnyUploadingConversations]);

  // Auto-scroll suggestions into view (needed in centered/empty-state layout)
  useEffect(() => {
    if (!showAutocompletePanel) {
      return;
    }
    autocompletePanelRef.current?.scrollIntoView({
      behavior: 'smooth',
      block: 'nearest'
    });
  }, [showAutocompletePanel]);

  // Auto-scroll skill suggestions into view when opened near the bottom of the page.
  useEffect(() => {
    if (!showSkillPicker) {
      return;
    }
    skillPickerPanelRef.current?.scrollIntoView({
      behavior: 'smooth',
      block: 'end'
    });
  }, [showSkillPicker, filteredSkills.length]);

  const contentMaxWidth = maxWidthClass;
  const containerAlignmentClasses = isCentered ? 'flex justify-center' : '';

  return (
    <>
    <div className={`bg-transparent px-2 py-1.5 md:bg-transparent md:px-0 md:pt-4 md:pb-2 md:dark:bg-transparent sm:px-4 ${containerAlignmentClasses}`}>
      <div className={`mx-auto w-full ${contentMaxWidth}`}>
        {voiceError && audioInputEnabled && (
          <div role="alert" aria-live="assertive" className="mb-2.5 w-full flex items-start gap-2.5 rounded-lg bg-red-50 dark:bg-red-950/40 px-3.5 py-2.5 animate-fadeIn">
            <CircleAlert className="h-4 w-4 mt-0.5 flex-shrink-0 text-red-500 dark:text-red-400" />
            <span className="text-sm text-red-700 dark:text-red-300">{voiceError}</span>
          </div>
        )}
        {pasteError && (
          <div role="alert" aria-live="assertive" className="mb-2.5 w-full flex items-start gap-2.5 rounded-lg bg-red-50 dark:bg-red-950/40 px-3.5 py-2.5 animate-fadeIn">
            <CircleAlert className="h-4 w-4 mt-0.5 flex-shrink-0 text-red-500 dark:text-red-400" />
            <span className="text-sm text-red-700 dark:text-red-300">{pasteError}</span>
          </div>
        )}
        {uploadSuccessMessage && (
          <div role="status" aria-live="polite" className="mb-2.5 w-full flex items-center gap-2.5 rounded-lg bg-gray-50 dark:bg-[#1f1f24] px-3.5 py-2.5 animate-fadeIn">
            <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-900/40">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
            </div>
            <span className="text-sm text-[#353740] dark:text-[#ececf1]">{uploadSuccessMessage}</span>
          </div>
        )}
        {limitWarnings.length > 0 && (
          <div role="status" aria-live="polite" className="mb-2.5 w-full flex items-start gap-2.5 rounded-lg bg-amber-50 dark:bg-amber-950/30 px-3.5 py-2.5 animate-fadeIn">
            <TriangleAlert className="h-4 w-4 mt-0.5 flex-shrink-0 text-amber-500 dark:text-amber-400" />
            <div className="flex-1 min-w-0">
              <ul className="list-none space-y-0.5">
                {limitWarnings.map((warning, index) => (
                  <li key={`${warning}-${index}`} className="text-sm text-amber-800 dark:text-amber-200">{warning}</li>
                ))}
              </ul>
              {isGuest && (messageLimitActive || fileLimitActive) && showLoginPrompt && (
                <button
                  type="button"
                  onClick={() => useLoginPromptStore.getState().openLoginPrompt(t('messageInput.signInPrompt.message'))}
                  className="mt-2 inline-flex items-center gap-1.5 rounded-md bg-[#353740] px-3 py-1.5 text-xs font-medium text-white hover:bg-[#40414f] dark:bg-white dark:text-[#353740] dark:hover:bg-gray-200 transition-colors"
                >
                  {t('messageInput.signInPrompt.button')}
                </button>
              )}
            </div>
          </div>
        )}

        <div className="relative w-full">
          {/* Autocomplete suggestions are rendered below the form */}

          <form onSubmit={handleSubmit} className="flex w-full flex-col gap-2 md:gap-3">
          {/* Mobile uses a stacked composer so the model picker never squeezes
              the textarea. Desktop keeps the compact single-row layout. */}
          <div
            className={`grid grid-cols-1 items-center gap-2 md:flex md:flex-row md:flex-nowrap md:gap-2 rounded-xl md:rounded-lg border px-2.5 py-2 md:px-4 md:py-3 shadow-sm transition-all ${
              isFocused
                ? 'border-gray-400 shadow-md dark:border-[#3a3a3a] dark:shadow-lg'
                : 'border-gray-300 dark:border-[#242424]'
            } bg-gray-50 dark:bg-[#111111]`}
          >
          <div className="col-span-full flex w-full shrink-0 basis-full items-center justify-between gap-2 md:contents">
            {selectedSkill && (
              <div className="flex h-8 max-w-[45%] shrink-0 items-center gap-1.5 rounded-full border border-gray-300 bg-white px-2.5 text-xs text-gray-700 shadow-sm dark:border-[#3a3a3a] dark:bg-[#1a1a1a] dark:text-gray-200 sm:max-w-[38%] md:self-center md:max-w-[32%]">
                <Sparkles className="h-3.5 w-3.5 shrink-0 text-gray-500 dark:text-gray-400" aria-hidden="true" />
                <span className="min-w-0 truncate font-medium capitalize">
                  {selectedSkill.name.replace(/-/g, ' ')}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    clearSkill();
                    textareaRef.current?.focus();
                  }}
                  className="-mr-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-300 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-gray-100 dark:focus-visible:ring-gray-600"
                  aria-label={t('messageInput.selectedSkill.removeAriaLabel')}
                >
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </div>
            )}

            {/* Keep the Skills affordance visible whenever the adapter exposes
                skills. Disable it while a draft exists (opening it would replace
                the draft with "/") or while the composer is unavailable. */}
            {!selectedSkill && skills.length > 0 && (
              <button
                type="button"
                onClick={openSkillPicker}
                disabled={message.length > 0 || isInputDisabled}
                className="flex h-8 shrink-0 items-center gap-1.5 rounded-full border border-gray-300 bg-white px-2.5 text-xs font-medium text-gray-600 shadow-sm transition-colors hover:bg-gray-100 hover:text-gray-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-300 disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:bg-white disabled:hover:text-gray-600 dark:border-[#3a3a3a] dark:bg-[#1a1a1a] dark:text-gray-300 dark:hover:bg-white/10 dark:hover:text-gray-100 dark:focus-visible:ring-gray-600 dark:disabled:hover:bg-[#1a1a1a] dark:disabled:hover:text-gray-300 md:self-center"
                aria-label={t('messageInput.skillsHint.ariaLabel')}
                title={t('messageInput.skillsHint.title')}
              >
                <span
                  className="flex h-4 w-4 shrink-0 items-center justify-center rounded bg-gray-200 font-mono text-[10px] leading-none text-gray-600 dark:bg-[#2a2a2a] dark:text-gray-300"
                  aria-hidden="true"
                >
                  /
                </span>
                {t('messageInput.skillsHint.text')}
              </button>
            )}

            {/* On mobile, capability selectors share the top row so the
                textarea and bottom action bar stay spacious. */}
            <ModelPickerButton
              availableModels={availableModels}
              defaultModel={defaultModel}
              selectedModel={selectedModel}
              onSelect={(name) => onSelectModel?.(name)}
              wrapperClassName="relative ml-auto block md:hidden"
              maxWidthClass="max-w-[150px]"
            />
          </div>

          {/* Textarea row */}
          <div className="relative flex-1 w-full min-w-0 md:translate-y-0.5">
            {showCustomPlaceholder && effectivePlaceholder && (
              <div
                className="pointer-events-none absolute inset-0 truncate whitespace-nowrap text-base md:text-sm text-gray-500 dark:text-[#8e8ea0]"
                style={{
                  paddingTop: Math.max(textareaVerticalPadding.top - PLACEHOLDER_VERTICAL_OFFSET, 0),
                  paddingBottom: textareaVerticalPadding.bottom,
                  paddingLeft: `${TEXTAREA_HORIZONTAL_PADDING}px`,
                  paddingRight: 0,
                  lineHeight: textareaLineHeight ? `${textareaLineHeight}px` : undefined
                }}
                aria-hidden="true"
              >
                {effectivePlaceholder}
              </div>
            )}
            {activeInlineSuggestion && isFocused && (
              <div
                className="pointer-events-none absolute inset-0 whitespace-pre-wrap text-base md:text-sm text-gray-400 dark:text-[#8e8ea0]"
                style={{
                  paddingTop: Math.max(textareaVerticalPadding.top - INLINE_SUGGESTION_VERTICAL_OFFSET, 0),
                  paddingBottom: textareaVerticalPadding.bottom,
                  paddingLeft: `${TEXTAREA_HORIZONTAL_PADDING}px`,
                  paddingRight: 0,
                  lineHeight: textareaLineHeight ? `${textareaLineHeight}px` : undefined
                }}
                aria-hidden="true"
              >
                <span className="invisible">{message}</span>
                <span>{activeInlineSuggestion}</span>
              </div>
            )}
            <textarea
              ref={textareaRef}
              aria-label={t('messageInput.textarea.ariaLabel')}
              value={message}
              onChange={(e) => {
                const val = e.target.value;
                setMessage(val);
                if (val.startsWith('/')) {
                  setActiveSkillIndex(0);
                }
                setShowSkillPicker(val.startsWith('/') && skills.length > 0);
              }}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              onCompositionStart={() => setIsComposing(true)}
              onCompositionEnd={() => setIsComposing(false)}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              placeholder={effectivePlaceholder}
              disabled={isInputDisabled}
              rows={1}
              maxLength={AppConfig.maxMessageLength}
              className="relative z-10 flex-1 w-full min-w-0 resize-none bg-transparent py-0 text-base md:text-sm text-[#353740] placeholder-transparent focus:outline-none dark:text-[#ececf1] dark:placeholder-transparent"
              style={{
                minHeight: '24px',
                maxHeight: '120px',
                paddingTop: `${textareaVerticalPadding.top}px`,
                paddingBottom: `${textareaVerticalPadding.bottom}px`,
                paddingLeft: `${TEXTAREA_HORIZONTAL_PADDING}px`,
                paddingRight: 0,
                border: 'none',
                outline: 'none',
                boxShadow: 'none',
                WebkitAppearance: 'none',
                MozAppearance: 'none',
                appearance: 'none',
                caretColor: (message.trim() || isFocused) ? 'inherit' : 'transparent'
              }}
            />
          </div>

          {/* Action buttons */}
          <div className="flex w-full flex-shrink-0 items-center justify-between gap-2 md:w-auto md:justify-end">
            <div className="flex items-center gap-1 md:gap-2">
              {isCentered && !uploadFeatureEnabled && (
                <div className="hidden md:block h-8 w-8 shrink-0" aria-hidden="true" />
              )}
              {uploadFeatureEnabled && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    if (!isFileUploadDisabled) {
                      setShowFileUpload(!showFileUpload);
                    }
                  }}
                  disabled={isFileUploadDisabled}
                  onMouseEnter={() => setIsHoveringUpload(true)}
                  onMouseLeave={() => setIsHoveringUpload(false)}
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-all active:scale-95 ${
                    showFileUpload || visibleAttachedFiles.length > 0
                      ? 'bg-gray-200 text-[#353740] dark:bg-[#565869] dark:text-[#ececf1]'
                      : isFileUploadDisabled
                      ? 'cursor-not-allowed text-gray-300 dark:text-[#6b6f7a]'
                      : 'text-gray-500 hover:bg-gray-200 hover:text-[#353740] dark:text-[#bfc2cd] dark:hover:bg-[#565869]'
                  }`}
                  title={
                    !isFileSupported
                      ? t('messageInput.fileUpload.titleNotSupported')
                      : fileLimitActive && conversationFileLimitReached && AppConfig.maxFilesPerConversation !== null
                      ? t('messageInput.fileUpload.titleLimitPerConversation', { count: AppConfig.maxFilesPerConversation })
                      : fileLimitActive && workspaceFileLimitReached && AppConfig.maxTotalFiles !== null
                      ? t('messageInput.fileUpload.titleLimitWorkspace', { count: AppConfig.maxTotalFiles })
                      : isInputDisabled
                      ? t('messageInput.fileUpload.titleUploading')
                      : visibleAttachedFiles.length > 0
                      ? t('messageInput.fileUpload.titleAttached', { count: visibleAttachedFiles.length })
                      : t('messageInput.fileUpload.attachAriaLabel')
                  }
                  aria-label={t('messageInput.fileUpload.attachAriaLabel')}
                >
                  {isFileUploadDisabled && isHoveringUpload ? (
                    <X className="h-4 w-4" />
                  ) : (
                    <Paperclip className="h-4 w-4" />
                  )}
                </button>
              )}

              {/* Character count - hidden on mobile to save space */}
              {message.length > 0 && (
                <div className="hidden md:block px-2 text-xs text-gray-500 dark:text-[#bfc2cd] md:min-w-[72px] md:text-right">
                  <span className={message.length >= AppConfig.maxMessageLength ? 'text-red-600 font-semibold' : ''}>
                    {message.length}/{AppConfig.maxMessageLength}
                  </span>
                </div>
              )}
            </div>

            {/* Right side buttons */}
            <div className="flex items-center gap-1 md:gap-2">
              <ModelPickerButton
                availableModels={availableModels}
                defaultModel={defaultModel}
                selectedModel={selectedModel}
                onSelect={(name) => onSelectModel?.(name)}
                wrapperClassName="relative hidden md:block"
                maxWidthClass="max-w-[220px]"
              />
              {(audioOutputEnabled || audioInputEnabled) && (
                <>
                  {audioOutputEnabled && (
                  <button
                    type="button"
                    onClick={handleVoiceResponseToggle}
                    className={`hidden md:flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-all active:scale-95 ${
                      settings.voiceEnabled
                        ? 'bg-blue-100 text-blue-600 dark:bg-blue-900/40 dark:text-blue-300'
                        : 'text-gray-500 hover:bg-gray-200 hover:text-[#353740] dark:text-[#bfc2cd] dark:hover:bg-[#565869]'
                    }`}
                    title={
                      settings.voiceEnabled
                        ? t('messageInput.voiceOutput.titleEnabled')
                        : t('messageInput.voiceOutput.titleDisabled')
                    }
                    aria-label={settings.voiceEnabled ? t('messageInput.voiceOutput.ariaLabelEnabled') : t('messageInput.voiceOutput.ariaLabelDisabled')}
                  >
                    {settings.voiceEnabled ? (
                      <Volume2 className="h-5 w-5" />
                    ) : (
                      <VolumeX className="h-5 w-5" />
                    )}
                  </button>
                  )}
                  {voiceRecordingAvailable && (
                    <button
                      type="button"
                      onClick={handleVoiceToggle}
                      disabled={isInputDisabled}
                      onMouseEnter={() => setIsHoveringMic(true)}
                      onMouseLeave={() => setIsHoveringMic(false)}
                      className={`hidden md:flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-all active:scale-95 ${
                        isListening
                          ? '!flex bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-300'
                          : isInputDisabled
                          ? 'cursor-not-allowed text-gray-300 dark:text-[#6b6f7a]'
                          : 'text-gray-500 hover:bg-gray-200 hover:text-[#353740] dark:text-[#bfc2cd] dark:hover:bg-[#565869]'
                      }`}
                      title={
                        isInputDisabled
                          ? t('messageInput.voiceInput.titleUploading')
                          : isListening
                          ? t('messageInput.voiceInput.titleListening')
                          : t('messageInput.voiceInput.titleDisabled')
                      }
                      aria-label={isListening ? t('messageInput.voiceInput.ariaLabelListening') : t('messageInput.voiceInput.ariaLabelDisabled')}
                    >
                      {isListening || (isInputDisabled && isHoveringMic) ? (
                        <MicOff className="h-5 w-5" />
                      ) : (
                        <Mic className="h-5 w-5" />
                      )}
                    </button>
                  )}
                </>
              )}

              {adapterNotes && (
                <button
                  type="button"
                  onClick={() => setShowAgentInfo(true)}
                  className="hidden md:flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-all active:scale-95 text-gray-500 hover:bg-gray-200 hover:text-[#353740] dark:text-[#bfc2cd] dark:hover:bg-[#565869]"
                  title={t('messageInput.agentInfo.title')}
                  aria-label={t('messageInput.agentInfo.ariaLabel')}
                >
                  <CircleHelp className="h-5 w-5" />
                </button>
              )}

              {(hasProcessingFiles || isUploading) && (
                <div className="flex h-8 w-8 shrink-0 items-center justify-center">
                  <Loader2 className="h-4 w-4 animate-spin text-gray-500 dark:text-[#bfc2cd]" />
                </div>
              )}

              {isLoading ? (
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    stopStreaming();
                  }}
                  className="flex h-9 w-9 md:h-8 md:w-8 shrink-0 items-center justify-center rounded-full transition-all active:scale-95 bg-red-500 text-white hover:bg-red-600 dark:bg-red-600 dark:hover:bg-red-700"
                  title={t('messageInput.stop.title')}
                  aria-label={t('messageInput.stop.ariaLabel')}
                >
                  <Square className="h-4 w-4 md:h-3 md:w-3 fill-current" />
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!hasTypedMessage || isInputDisabled || isComposing}
                  className={`flex h-9 w-9 md:h-8 md:w-8 shrink-0 items-center justify-center rounded-full transition-all active:scale-95 ${
                    hasTypedMessage && !isInputDisabled && !isComposing
                      ? 'bg-black text-white hover:bg-gray-800 dark:bg-white dark:text-black dark:hover:bg-gray-200'
                      : 'bg-gray-300 text-gray-500 dark:bg-[#565869] dark:text-[#6b6f7a]'
                  }`}
                  title={t('messageInput.submit.title')}
                  aria-label={t('messageInput.submit.ariaLabel')}
                >
                  <ArrowUp className="h-4 w-4" />
                </button>
              )}
            </div>
          </div>
        </div>

        {visibleAttachedFiles.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {visibleAttachedFiles.map((file) => {
              const isProcessing = isFileProcessing(file.processing_status);
              const isFailed = file.processing_status === 'failed' || file.processing_status === 'error';
              const status = isFailed ? 'error' : isProcessing
                ? (file.processing_status === 'uploading' ? 'uploading' : 'processing')
                : 'completed';
              const statusText = isProcessing
                ? (file.processing_status === 'uploading' ? t('messageInput.attachedFile.uploadingStatus') : t('messageInput.attachedFile.processingStatus'))
                : undefined;

              return (
                <FileChip
                  key={file.file_id}
                  filename={file.filename}
                  fileId={file.file_id}
                  status={status}
                  statusText={statusText}
                  errorMessage={isFailed ? (file.error_message || t('messageInput.fileProcessingFailedTitle')) : undefined}
                  onRemove={() => {
                    if (isFailed) {
                      // Failed files: dismiss immediately without confirmation
                      if (currentConversationId) {
                        removeFileFromConversation(currentConversationId, file.file_id);
                      }
                      setAttachedFiles(prev => prev.filter(f => f.file_id !== file.file_id));
                    } else {
                      openFileDeleteConfirmation(file);
                    }
                  }}
                  removeTitle={isFailed ? t('messageInput.attachedFile.removeTitleFailed') : t('messageInput.attachedFile.removeTitleNormal')}
                />
              );
            })}
          </div>
        )}

        {uploadFeatureEnabled && (isFileSupported || hasAnyUploadingConversations) && (
          <div
            ref={uploadPanelRef}
            className={`${isUploadProgressOnly ? '' : 'rounded-lg border border-gray-200/80 bg-white p-2.5 dark:border-[#3c3f4a] dark:bg-[#2a2b32]'} transition-all duration-200 ${
              !showFileUpload && !isUploading && pasteUploadingFiles.size === 0 && !hasAnyUploadingConversations
                ? 'hidden'
                : ''
            }`}
          >
            {showFileUpload && (
              <div className="mb-2 flex items-center justify-between px-1">
                <span className="text-xs font-medium text-gray-500 dark:text-[#8e8ea0] uppercase tracking-wider">{t('messageInput.uploadPanel.headingAttach')}</span>
                <button
                  type="button"
                  onClick={() => setShowFileUpload(false)}
                  className="flex h-6 w-6 items-center justify-center rounded-md text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:text-[#6b6f7a] dark:hover:bg-[#3c3f4a] dark:hover:text-[#bfc2cd] transition-colors"
                  title={t('messageInput.uploadPanel.closeTitle')}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            )}
            {!isUploadProgressOnly && isUploading && !showFileUpload && pasteUploadingFiles.size === 0 && (
              <div className="mb-2 px-1">
                <span className="text-xs font-medium text-gray-500 dark:text-[#8e8ea0] uppercase tracking-wider">{t('messageInput.uploadPanel.headingUploading')}</span>
              </div>
            )}
            {pasteUploadingFiles.size > 0 && (
              <div className="mb-2 flex flex-wrap gap-2">
                {Array.from(pasteUploadingFiles.entries()).map(([key, progress]) => (
                  <FileChip
                    key={key}
                    filename={progress.filename}
                    fileId={progress.fileId}
                    status={progress.status}
                    statusText={
                      progress.status === 'uploading'
                        ? t('messageInput.uploadProgress.statusUploading')
                        : progress.status === 'processing'
                        ? t('messageInput.uploadProgress.statusProcessing')
                        : progress.status === 'completed'
                        ? t('messageInput.uploadProgress.statusCompleted')
                        : undefined
                    }
                    errorMessage={progress.error}
                  />
                ))}
              </div>
            )}
            {/*
              Keep FileUpload mounted while uploads are in progress so progress bars stay visible
              even if the widget was auto-hidden after selecting files.
            */}
            <div className={`${shouldShowFileUploadControl ? 'block max-h-[40vh] overflow-y-auto' : 'hidden'}`} aria-hidden={!shouldShowFileUploadControl}>
              <FileUpload
                conversationId={currentConversationId}
                onFilesSelected={handleFilesSelected}
                onUploadError={(error) => {
                  debugError('File upload error:', error);
                  setUploadError(error);
                }}
                onUploadingChange={setConversationUploading}
                onUploadSuccess={handleUploadSuccessToast}
                maxFiles={AppConfig.maxFilesPerConversation}
                disabled={isFileUploadDisabled}
              />
            </div>
          </div>
        )}

        <div className="h-3 md:h-1">
          {voiceRecordingAvailable && isListening && (
            <span className="flex items-center gap-2 text-sm md:text-xs text-gray-500 dark:text-[#bfc2cd]">
              <span className="h-2.5 w-2.5 md:h-2 md:w-2 animate-pulse rounded-full bg-red-500" />
              {t('messageInput.listeningIndicator')}
            </span>
          )}
        </div>
        </form>

        {/* Skill picker panel - shown when user types / */}
        {showSkillPicker && (
          <div ref={skillPickerPanelRef} className="w-full pt-1">
            <SkillPicker
              skills={skills}
              isLoading={skillsLoading}
              selectedSkill={selectedSkill}
              activeSkillName={activeSkill?.name}
              query={skillQuery}
              onActiveSkillChange={(skill) => {
                const nextIndex = filteredSkills.findIndex(item => item.name === skill.name);
                if (nextIndex >= 0) {
                  setActiveSkillIndex(nextIndex);
                }
              }}
              onSelect={selectSkillAndClose}
              onClose={closeSkillPicker}
            />
          </div>
        )}

        {/* ChatGPT-style autocomplete suggestions below input */}
        {showAutocompletePanel && (
          <div ref={autocompletePanelRef} role="listbox" aria-label={t('messageInput.autocompletePanel.ariaLabel')} className="w-full pt-1">
            {suggestions.map((suggestion, index) => {
              const isSelected = index === selectedIndex;

              return (
                <button
                  key={index}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  className={`flex w-full items-center gap-3 px-3 py-3 md:py-2.5 text-left text-[15px] md:text-sm transition-colors ${
                    isSelected
                      ? 'bg-gray-100 dark:bg-[#2d2f39]'
                      : 'hover:bg-gray-50 dark:hover:bg-[#2d2f39]/60'
                  }`}
                  onClick={() => handleSelectSuggestion(suggestion.text)}
                  onMouseEnter={() => setSelectedIndex(index)}
                >
                  {renderSuggestionText(suggestion.text)}
                </button>
              );
            })}
          </div>
        )}

        <ConfirmationModal
          isOpen={fileDeleteConfirmation.isOpen}
          onClose={closeFileDeleteConfirmation}
          onConfirm={confirmFileDelete}
          title={t('messageInput.fileDelete.title')}
          message={t('messageInput.fileDelete.message', { filename: fileDeleteConfirmation.filename })}
          confirmText={t('messageInput.fileDelete.confirmText')}
          cancelText={t('common.cancel')}
          type="danger"
          isLoading={fileDeleteConfirmation.isDeleting}
        />
        </div>
      </div>
    </div>

    {showAgentInfo && adapterNotes && typeof document !== 'undefined' && createPortal(
      <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/60 p-4 backdrop-blur-sm animate-fadeIn">
        <div
          ref={agentInfoModalRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby="agent-info-title"
          tabIndex={-1}
          className="w-full max-w-2xl max-h-[calc(100vh-2rem)] overflow-y-auto rounded-2xl bg-white shadow-2xl transform animate-fadeIn dark:bg-[#1a1b1e]"
        >
          <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-[#2d2f39]">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-blue-100 dark:bg-blue-900/20 flex items-center justify-center">
                <CircleHelp className="w-5 h-5 text-blue-500" />
              </div>
              <h2 id="agent-info-title" className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                {t('messageInput.agentInfoModal.title')}
              </h2>
            </div>
            <button
              type="button"
              onClick={() => setShowAgentInfo(false)}
              className="p-2 hover:bg-gray-100 dark:hover:bg-[#25262f] rounded-lg transition-colors"
              aria-label={t('messageInput.agentInfoModal.closeAriaLabel')}
            >
              <X className="w-5 h-5 text-gray-500 dark:text-gray-400" />
            </button>
          </div>
          <div className="p-6">
            <MarkdownRenderer
              content={adapterNotes}
              className={`message-markdown w-full min-w-0 prose prose-slate dark:prose-invert max-w-none text-sm leading-relaxed text-[#434654] dark:text-[#d7dae3] [&>:first-child]:mt-0 [&>:last-child]:mb-0 ${agentInfoForcedThemeClass}`}
              syntaxTheme={agentInfoSyntaxTheme}
            />
          </div>
          <div className="flex items-center justify-end p-6 border-t border-gray-200 dark:border-[#2d2f39] bg-gray-50 dark:bg-[#111113] rounded-b-2xl">
            <button
              type="button"
              onClick={() => setShowAgentInfo(false)}
              className="px-4 py-3 md:py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors font-medium shadow-sm hover:shadow-md"
            >
              {t('messageInput.agentInfoModal.confirmButton')}
            </button>
          </div>
        </div>
      </div>,
      document.body
    )}
    </>
  );
}
