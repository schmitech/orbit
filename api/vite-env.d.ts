/// <reference types="vite/client" />

interface ImportMeta {
  readonly env: {
    readonly [key: string]: string | undefined;
  };
} 