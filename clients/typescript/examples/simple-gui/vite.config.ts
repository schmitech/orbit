import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      'api-local': path.resolve(__dirname, '../../api/dist/api.mjs'),
    },
  },
  optimizeDeps: {
    exclude: ['../../api/dist/api.mjs']
  },
  server: {
    hmr: {
      overlay: false
    },
    watch: {
      usePolling: false
    }
  }
});
