/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string
  readonly VITE_DEFAULT_KEY?: string
  readonly VITE_SESSION_ID?: string
  readonly VITE_LOCAL_API_PATH?: string
  readonly VITE_MAX_FILES_PER_CONVERSATION?: string
  readonly VITE_MAX_FILE_SIZE_MB?: string
  readonly VITE_ENABLE_UPLOAD?: string
  readonly VITE_ENABLE_AUDIO_OUTPUT?: string
  readonly VITE_ENABLE_FEEDBACK?: string
  readonly VITE_MAX_TOTAL_FILES?: string
  readonly VITE_MAX_CONVERSATIONS?: string
  readonly VITE_MAX_MESSAGES_PER_CONVERSATION?: string
  readonly VITE_MAX_MESSAGES_PER_THREAD?: string
  readonly VITE_MAX_TOTAL_MESSAGES?: string
  readonly VITE_MAX_MESSAGE_LENGTH?: string
  readonly VITE_ENABLE_CONVERSATION_THREADS?: string
  readonly VITE_SHOW_GITHUB_STATS?: string
  readonly VITE_GITHUB_OWNER?: string
  readonly VITE_GITHUB_REPO?: string
  readonly VITE_USE_LOCAL_API?: string
  readonly VITE_CONSOLE_DEBUG?: string
  readonly VITE_ADAPTERS?: string
  readonly VITE_LOCALE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
