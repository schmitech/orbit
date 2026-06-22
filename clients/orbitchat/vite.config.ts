import { defineConfig, type ViteDevServer, type PluginOption } from 'vite';
import react from '@vitejs/plugin-react';
import { orbitchatConfigPlugin } from './vite-plugin-orbitchat-config';

// Plugin to fix MaxListenersExceededWarning in development
// Vite's HMR can add multiple close listeners
const fixMaxListenersPlugin = () => ({
  name: 'fix-max-listeners',
  configureServer(server: ViteDevServer) {
    // Increase max listeners to prevent warning during HMR
    if (server.httpServer) {
      server.httpServer.setMaxListeners(20);
    }
  },
});

// https://vitejs.dev/config/
export default defineConfig(() => {
  const plugins: PluginOption[] = [react(), fixMaxListenersPlugin(), orbitchatConfigPlugin()];

  return {
    plugins,
    optimizeDeps: {
      exclude: [
        'lucide-react',
      ],
    },
    build: {
      chunkSizeWarningLimit: 650,
      rollupOptions: {
        output: {
          manualChunks: {
            'vendor-react': ['react', 'react-dom'],
            'vendor-markdown': [
              'react-markdown',
              'remark-gfm',
              'remark-math',
              'rehype-katex',
              'katex',
              'unified',
            ],
            'vendor-syntax': ['react-syntax-highlighter'],
            'vendor-auth': [
              '@auth0/auth0-react',
              '@azure/msal-browser',
              '@azure/msal-react',
            ],
          },
        },
      },
    },
  };
});
