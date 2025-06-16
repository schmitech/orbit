import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Configure static file serving to include the widget dist directory
    fs: {
      // Allow serving files from parent directory (for ../dist/)
      allow: ['..']
    }
  },
  // Add alias for easier access to dist files
  resolve: {
    alias: {
      '@widget-dist': '../dist'
    }
  }
})
