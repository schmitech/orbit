import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      'api-local': path.resolve(__dirname, '../../dist/api.mjs'),
    },
  },
  optimizeDeps: {
    exclude: ['../../dist/api.mjs']
  }
});
