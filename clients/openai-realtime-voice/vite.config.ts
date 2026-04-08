import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    port: 5175,
    open: true,
  },
  build: {
    target: 'esnext',
  },
});
