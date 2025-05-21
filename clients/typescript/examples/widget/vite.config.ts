import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import svgr from 'vite-plugin-svgr';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    svgr()
  ],
  define: {
    'process.env': '{}',
    'global': '{}'
  },
  build: {
    lib: {
      entry: 'src/index.ts',
      formats: ['es', 'umd'],
      name: 'ChatbotWidget',
      fileName: (format) => `chatbot-widget.${format}.js`
    },
    rollupOptions: {
      external: ['react', 'react-dom'],
      output: {
        exports: 'named',
        globals: {
          react: 'React',
          'react-dom': 'ReactDOM'
        },
        assetFileNames: 'chatbot-widget.css',
        intro: 'if (typeof window !== "undefined") { window.global = window; }',
      }
    },
    cssCodeSplit: false,
    cssTarget: 'chrome61'
  },
  optimizeDeps: {
    exclude: ['lucide-react']
  }
});
