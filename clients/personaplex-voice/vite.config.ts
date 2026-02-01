import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    port: 5174,
    open: true,
  },
  build: {
    target: 'esnext',
  },
});
