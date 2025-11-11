import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    exclude: ['lucide-react'],
  },
  resolve: {
    alias: {
      // Alias for local node-api package during development
      '@local-node-api': path.resolve(__dirname, '../node-api/dist'),
    },
  },
  server: {
    fs: {
      // Allow serving files from the parent clients directory
      // This enables importing from ../node-api/dist during local development
      allow: [
        // Search up for workspace root
        path.resolve(__dirname, '..'),
      ],
    },
  },
});
