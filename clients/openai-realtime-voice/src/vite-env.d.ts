/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ORBIT_SERVER_URL?: string
  readonly VITE_ORBIT_API_URL?: string
  readonly VITE_ADAPTER_NAME?: string
  readonly VITE_API_KEY?: string
  readonly VITE_APP_TITLE?: string
  readonly VITE_DISPLAY_SETTINGS?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
