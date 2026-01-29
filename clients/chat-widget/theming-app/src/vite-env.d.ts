/// <reference types="vite/client" />

declare module 'react-syntax-highlighter' {
  import { ComponentType } from 'react';
  export const Prism: ComponentType<any>;
}

declare module 'react-syntax-highlighter/dist/esm/styles/hljs' {
  export const github: Record<string, unknown>;
}
