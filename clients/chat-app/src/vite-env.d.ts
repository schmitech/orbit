/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string
  readonly VITE_DEFAULT_KEY?: string
  readonly VITE_SESSION_ID?: string
  readonly VITE_MAX_FILES_PER_CONVERSATION?: string
  readonly VITE_MAX_FILE_SIZE_MB?: string
  readonly VITE_MAX_TOTAL_FILES?: string
  readonly VITE_MAX_CONVERSATIONS?: string
  readonly VITE_MAX_MESSAGES_PER_CONVERSATION?: string
  readonly VITE_MAX_TOTAL_MESSAGES?: string
  readonly VITE_MAX_MESSAGE_LENGTH?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
