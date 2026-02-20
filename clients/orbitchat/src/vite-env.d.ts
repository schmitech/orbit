/// <reference types="vite/client" />

interface ImportMetaEnv {
  // Injected by vite-plugin-orbitchat-config from orbitchat.yaml
  readonly __ORBITCHAT_CONFIG?: Record<string, unknown>

  // Auth secrets (from .env)
  readonly VITE_AUTH_DOMAIN?: string
  readonly VITE_AUTH_CLIENT_ID?: string
  readonly VITE_AUTH_AUDIENCE?: string

  // Adapter secrets (from .env)
  readonly VITE_ADAPTERS?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
